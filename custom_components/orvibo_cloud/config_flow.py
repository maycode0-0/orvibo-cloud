"""Config flow for Orvibo Cloud."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult
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
from .protocol import password_hash


class OrviboCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Orvibo Cloud config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending_account: OrviboAccount | None = None
        self._pending_data: dict[str, Any] = {}
        self._reauth_entry: config_entries.ConfigEntry | None = None

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
                self._pending_data[CONF_FAMILY_ID] = (
                    account.families[0].family_id if account.families else ""
                )
                return self.async_create_entry(title=email, data=self._pending_data)

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
            return self.async_create_entry(
                title=self._pending_data[CONF_EMAIL],
                data=self._pending_data,
            )
        return self.async_show_form(
            step_id="family",
            data_schema=vol.Schema(
                {vol.Required(CONF_FAMILY_ID): vol.In(choices)}
            ),
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
                    new_data[CONF_FAMILY_ID] = (
                        account.families[0].family_id if account.families else ""
                    )
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
