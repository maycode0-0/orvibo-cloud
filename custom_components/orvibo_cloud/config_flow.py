"""Config flow for Orvibo Cloud."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_AREA_ID, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import area_registry as ar, selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    OrviboAccount,
    OrviboCannotConnectError,
    OrviboCloudClient,
    OrviboInvalidAuthError,
    OrviboProtocolError,
)
from .const import (
    CONF_FAMILY_ID,
    CONF_HOST,
    CONF_PASSWORD_HASH,
    CONF_USER_ID,
    DOMAIN,
)
from .protocol import OrviboDevice, password_hash
from .selection import (
    CONF_DEVICE_AREAS,
    CONF_SELECTED_DEVICE_IDS,
    configured_device_areas,
    selected_device_ids,
)


def _device_label(device: OrviboDevice) -> str:
    """Build a readable selector label without exposing a full device ID."""

    name = device.name or device.model or device.device_type or "ORVIBO device"
    details = [
        value for value in (device.room, device.model) if value and value != name
    ]
    details.append(device.uid[-6:])
    return " | ".join((name, *details))


def _device_schema(
    devices: tuple[OrviboDevice, ...],
    default: list[str],
) -> vol.Schema:
    """Build the multi-select device form."""

    options = [
        selector.SelectOptionDict(value=device.uid, label=_device_label(device))
        for device in devices
    ]
    return vol.Schema(
        {
            vol.Required(CONF_SELECTED_DEVICE_IDS, default=default): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            )
        }
    )


def _area_schema(default_area_id: str | None) -> vol.Schema:
    """Build one device-area selector with an optional discovered default."""

    key = (
        vol.Optional(CONF_AREA_ID, default=default_area_id)
        if default_area_id
        else vol.Optional(CONF_AREA_ID)
    )
    return vol.Schema({key: selector.AreaSelector()})


def _default_area_id(
    hass: HomeAssistant,
    device: OrviboDevice,
    configured_areas: Mapping[str, str | None],
) -> str | None:
    """Resolve the configured area or create the cloud room as the default."""

    registry = ar.async_get(hass)
    if device.uid in configured_areas:
        area_id = configured_areas[device.uid]
        if area_id is None or area_id in registry.areas:
            return area_id
    if not device.room:
        return None
    return registry.async_get_or_create(device.room).id


class OrviboCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Orvibo Cloud config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending_account: OrviboAccount | None = None
        self._pending_data: dict[str, Any] = {}
        self._pending_devices: tuple[OrviboDevice, ...] = ()
        self._pending_selected_ids: list[str] = []
        self._pending_device_areas: dict[str, str | None] = {}
        self._area_index = 0
        self._devices_loaded = False
        self._reauth_entry: config_entries.ConfigEntry | None = None

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the device and area options flow."""

        return OrviboCloudOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Authenticate an Orvibo account."""

        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            hashed_password = password_hash(user_input[CONF_PASSWORD])
            try:
                account = await OrviboCloudClient(
                    async_get_clientsession(self.hass)
                ).async_discover(email, hashed_password)
            except OrviboInvalidAuthError:
                errors["base"] = "invalid_auth"
            except OrviboCannotConnectError:
                errors["base"] = "cannot_connect"
            except OrviboProtocolError:
                errors["base"] = "unknown"
            else:
                if not account.families:
                    errors["base"] = "no_families"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=vol.Schema(
                            {
                                vol.Required(CONF_EMAIL, default=email): str,
                                vol.Required(CONF_PASSWORD): str,
                            }
                        ),
                        errors=errors,
                    )
                await self.async_set_unique_id(account.user_id)
                self._abort_if_unique_id_configured()
                self._pending_account = account
                self._pending_data = {
                    CONF_EMAIL: email,
                    CONF_PASSWORD_HASH: hashed_password,
                    CONF_HOST: account.host,
                    CONF_USER_ID: account.user_id,
                }
                if len(account.families) > 1:
                    return await self.async_step_family()
                self._pending_data[CONF_FAMILY_ID] = account.families[0].family_id
                return await self.async_step_devices()

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_family(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Let the user select one family for the config entry."""

        if self._pending_account is None:
            return self.async_abort(reason="unknown")
        choices = {
            family.family_id: family.name for family in self._pending_account.families
        }
        if user_input is not None:
            self._pending_data[CONF_FAMILY_ID] = user_input[CONF_FAMILY_ID]
            return await self.async_step_devices()
        return self.async_show_form(
            step_id="family",
            data_schema=vol.Schema(
                {vol.Required(CONF_FAMILY_ID): vol.In(choices)}
            ),
        )

    async def async_step_devices(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Discover devices and require an explicit selection."""

        if self._pending_account is None or CONF_FAMILY_ID not in self._pending_data:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}
        if not self._devices_loaded:
            try:
                account = await OrviboCloudClient(
                    async_get_clientsession(self.hass),
                    host=self._pending_data[CONF_HOST],
                ).async_discover(
                    self._pending_data[CONF_EMAIL],
                    self._pending_data[CONF_PASSWORD_HASH],
                    family_id=self._pending_data[CONF_FAMILY_ID],
                )
            except OrviboInvalidAuthError:
                errors["base"] = "invalid_auth"
            except OrviboCannotConnectError:
                errors["base"] = "cannot_connect"
            except OrviboProtocolError:
                errors["base"] = "unknown"
            else:
                self._pending_account = account
                self._pending_devices = account.devices
                self._devices_loaded = True

        if self._devices_loaded and not self._pending_devices:
            return self.async_abort(reason="no_devices")

        if user_input is not None and CONF_SELECTED_DEVICE_IDS in user_input:
            available = {device.uid for device in self._pending_devices}
            requested = {
                str(device_id)
                for device_id in user_input[CONF_SELECTED_DEVICE_IDS]
            }
            self._pending_selected_ids = [
                device.uid
                for device in self._pending_devices
                if device.uid in requested & available
            ]
            if not self._pending_selected_ids:
                errors["base"] = "no_devices_selected"
            else:
                self._area_index = 0
                self._pending_device_areas = {}
                return await self.async_step_area()

        return self.async_show_form(
            step_id="devices",
            data_schema=_device_schema(self._pending_devices, []),
            errors=errors,
        )

    async def async_step_area(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Assign one Home Assistant area to each selected device."""

        selected = {
            device.uid: device
            for device in self._pending_devices
            if device.uid in self._pending_selected_ids
        }
        devices = [selected[device_id] for device_id in self._pending_selected_ids]
        if not devices or self._area_index >= len(devices):
            return self.async_abort(reason="unknown")

        device = devices[self._area_index]
        if user_input is not None:
            self._pending_device_areas[device.uid] = user_input.get(CONF_AREA_ID)
            self._area_index += 1
            if self._area_index >= len(devices):
                return self.async_create_entry(
                    title=self._pending_data[CONF_EMAIL],
                    data=self._pending_data,
                    options={
                        CONF_SELECTED_DEVICE_IDS: self._pending_selected_ids,
                        CONF_DEVICE_AREAS: self._pending_device_areas,
                    },
                )
            device = devices[self._area_index]

        default_area_id = _default_area_id(
            self.hass,
            device,
            self._pending_device_areas,
        )
        return self.async_show_form(
            step_id="area",
            data_schema=_area_schema(default_area_id),
            description_placeholders={
                "device": _device_label(device),
                "room": device.room or "-",
                "position": str(self._area_index + 1),
                "total": str(len(devices)),
            },
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> FlowResult:
        """Start reauthentication."""

        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Replace rejected credentials."""

        if self._reauth_entry is None:
            return self.async_abort(reason="unknown")
        errors: dict[str, str] = {}
        email = self._reauth_entry.data[CONF_EMAIL]
        if user_input is not None:
            hashed_password = password_hash(user_input[CONF_PASSWORD])
            try:
                account = await OrviboCloudClient(
                    async_get_clientsession(self.hass)
                ).async_discover(email, hashed_password)
            except OrviboInvalidAuthError:
                errors["base"] = "invalid_auth"
            except OrviboCannotConnectError:
                errors["base"] = "cannot_connect"
            except OrviboProtocolError:
                errors["base"] = "unknown"
            else:
                if account.user_id != self._reauth_entry.data[CONF_USER_ID]:
                    errors["base"] = "invalid_auth"
                    return self.async_show_form(
                        step_id="reauth_confirm",
                        data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
                        errors=errors,
                        description_placeholders={"email": email},
                    )
                if not account.families:
                    errors["base"] = "no_families"
                    return self.async_show_form(
                        step_id="reauth_confirm",
                        data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
                        errors=errors,
                        description_placeholders={"email": email},
                    )
                new_data = {
                    **self._reauth_entry.data,
                    CONF_PASSWORD_HASH: hashed_password,
                    CONF_HOST: account.host,
                    CONF_USER_ID: account.user_id,
                }
                known_ids = {family.family_id for family in account.families}
                if new_data.get(CONF_FAMILY_ID) not in known_ids:
                    new_data[CONF_FAMILY_ID] = account.families[0].family_id
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data_updates=new_data,
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"email": email},
        )


class OrviboCloudOptionsFlow(config_entries.OptionsFlow):
    """Change exposed devices and their assigned areas."""

    def __init__(self) -> None:
        self._devices: tuple[OrviboDevice, ...] = ()
        self._selected_ids: list[str] = []
        self._device_areas: dict[str, str | None] = {}
        self._area_index = 0

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Open the device selection form."""

        self._device_areas = configured_device_areas(self.config_entry.options)
        return await self.async_step_devices(user_input)

    async def async_step_devices(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Select the devices exposed by the existing config entry."""

        errors: dict[str, str] = {}
        if not self._devices:
            coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
            if coordinator is not None:
                self._devices = tuple(coordinator.data.devices)
            if not self._devices:
                try:
                    account = await OrviboCloudClient(
                        async_get_clientsession(self.hass),
                        host=self.config_entry.data[CONF_HOST],
                    ).async_discover(
                        self.config_entry.data[CONF_EMAIL],
                        self.config_entry.data[CONF_PASSWORD_HASH],
                        family_id=self.config_entry.data[CONF_FAMILY_ID],
                    )
                except OrviboInvalidAuthError:
                    errors["base"] = "invalid_auth"
                except OrviboCannotConnectError:
                    errors["base"] = "cannot_connect"
                except OrviboProtocolError:
                    errors["base"] = "unknown"
                else:
                    self._devices = account.devices

        if user_input is not None and CONF_SELECTED_DEVICE_IDS in user_input:
            requested = {
                str(device_id)
                for device_id in user_input[CONF_SELECTED_DEVICE_IDS]
            }
            self._selected_ids = [
                device.uid for device in self._devices if device.uid in requested
            ]
            if not self._selected_ids:
                errors["base"] = "no_devices_selected"
            else:
                self._area_index = 0
                return await self.async_step_area()

        defaults = sorted(
            selected_device_ids(
                self.config_entry.options,
                (device.uid for device in self._devices),
            )
        )
        return self.async_show_form(
            step_id="devices",
            data_schema=_device_schema(self._devices, defaults),
            errors=errors,
        )

    async def async_step_area(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Update the area for each selected device."""

        selected = {
            device.uid: device
            for device in self._devices
            if device.uid in self._selected_ids
        }
        devices = [selected[device_id] for device_id in self._selected_ids]
        if not devices or self._area_index >= len(devices):
            return self.async_abort(reason="unknown")

        device = devices[self._area_index]
        if user_input is not None:
            self._device_areas[device.uid] = user_input.get(CONF_AREA_ID)
            self._area_index += 1
            if self._area_index >= len(devices):
                selected_set = set(self._selected_ids)
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SELECTED_DEVICE_IDS: self._selected_ids,
                        CONF_DEVICE_AREAS: {
                            device_id: area_id
                            for device_id, area_id in self._device_areas.items()
                            if device_id in selected_set
                        },
                    },
                )
            device = devices[self._area_index]

        default_area_id = _default_area_id(
            self.hass,
            device,
            self._device_areas,
        )
        return self.async_show_form(
            step_id="area",
            data_schema=_area_schema(default_area_id),
            description_placeholders={
                "device": _device_label(device),
                "room": device.room or "-",
                "position": str(self._area_index + 1),
                "total": str(len(devices)),
            },
        )
