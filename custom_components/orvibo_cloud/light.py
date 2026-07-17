"""Lights for Orvibo Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .binary import OrviboBinaryError, control_device
from .const import (
    CONF_FAMILY_ID,
    CONF_HOST,
    CONF_USER_ID,
    DOMAIN,
)
from .coordinator import OrviboCloudCoordinator
from .control import (
    OrviboControlCommand,
    light_brightness_command,
    light_color_temp_command,
    light_power_command,
    mired_to_kelvin,
)
from .protocol import OrviboDevice

_LIGHT_DEVICE_TYPE = "38"
_LIGHT_SUB_DEVICE_TYPE = "6"
_DEFAULT_BRIGHTNESS = 255
_DEFAULT_COLOR_TEMP_KELVIN = 4000


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up every light model verified from the current app."""

    coordinator: OrviboCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        OrviboColorTemperatureLight(coordinator, device.uid)
        for device in coordinator.data.devices
        if device.device_type == _LIGHT_DEVICE_TYPE
        and _is_supported_light(device)
    )


def _is_supported_light(device: OrviboDevice) -> bool:
    """Return whether this device matches the captured type-38 light profile."""

    return (
        device.sub_device_type == _LIGHT_SUB_DEVICE_TYPE
        and device.value2 is not None
        and device.value3 is not None
    )


class OrviboColorTemperatureLight(
    CoordinatorEntity[OrviboCloudCoordinator], LightEntity
):
    """Control one ORVIBO dimmable color-temperature light."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_min_color_temp_kelvin = 2700
    _attr_max_color_temp_kelvin = 6500

    def __init__(
        self,
        coordinator: OrviboCloudCoordinator,
        device_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._optimistic_on: bool | None = None
        self._optimistic_brightness: int | None = None
        self._optimistic_color_temp_kelvin: int | None = None
        self._attr_unique_id = f"{device_id}_light"
        device = self._device
        assert device is not None
        account_identifier = (DOMAIN, coordinator.entry.data[CONF_USER_ID])
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="ORVIBO",
            model=device.model or "Color temperature light",
            name=device.name or "ORVIBO Light",
            suggested_area=device.room or None,
            via_device=account_identifier,
        )

    @property
    def _device(self) -> OrviboDevice | None:
        return next(
            (
                device
                for device in self.coordinator.data.devices
                if device.uid == self._device_id
            ),
            None,
        )

    @property
    def available(self) -> bool:
        device = self._device
        return (
            super().available
            and device is not None
            and device.online is not False
            and bool(self.coordinator.data.binary_password)
        )

    @property
    def is_on(self) -> bool | None:
        if self._optimistic_on is not None:
            return self._optimistic_on
        device = self._device
        return None if device is None or device.value1 is None else device.value1 != 0

    @property
    def brightness(self) -> int | None:
        if self._optimistic_brightness is not None:
            return self._optimistic_brightness
        device = self._device
        value = None if device is None else device.value2
        return None if value is None else max(0, min(255, value))

    @property
    def color_temp_kelvin(self) -> int | None:
        if self._optimistic_color_temp_kelvin is not None:
            return self._optimistic_color_temp_kelvin
        device = self._device
        mired = None if device is None else device.value3
        if mired is None or mired <= 0:
            return None
        return mired_to_kelvin(mired)

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = max(
            1,
            min(
                255,
                int(
                    kwargs.get(
                        ATTR_BRIGHTNESS,
                        self.brightness or _DEFAULT_BRIGHTNESS,
                    )
                ),
            ),
        )
        color_temp_kelvin = max(
            self.min_color_temp_kelvin,
            min(
                self.max_color_temp_kelvin,
                int(
                    kwargs.get(
                        ATTR_COLOR_TEMP_KELVIN,
                        self.color_temp_kelvin or _DEFAULT_COLOR_TEMP_KELVIN,
                    )
                ),
            ),
        )

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            command = light_color_temp_command(brightness, color_temp_kelvin)
        elif ATTR_BRIGHTNESS in kwargs:
            command = light_brightness_command(brightness, color_temp_kelvin)
        else:
            command = light_power_command(True, brightness, color_temp_kelvin)
        await self._async_control(command)

        self._optimistic_on = True
        self._optimistic_brightness = brightness
        self._optimistic_color_temp_kelvin = color_temp_kelvin
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        brightness = self.brightness or _DEFAULT_BRIGHTNESS
        color_temp_kelvin = self.color_temp_kelvin or _DEFAULT_COLOR_TEMP_KELVIN
        await self._async_control(
            light_power_command(False, brightness, color_temp_kelvin)
        )
        self._optimistic_on = False
        self.async_write_ha_state()

    async def _async_control(
        self,
        command: OrviboControlCommand,
    ) -> None:
        entry_data = self.coordinator.entry.data
        device = self._device
        if device is None or not device.cloud_uid:
            raise HomeAssistantError("ORVIBO control identifiers are missing")
        try:
            await self.hass.async_add_executor_job(
                control_device,
                entry_data[CONF_HOST],
                self.coordinator.data.binary_user_name,
                self.coordinator.data.binary_password,
                entry_data[CONF_FAMILY_ID],
                self._device_id,
                device.cloud_uid,
                command.order,
                command.value1,
                command.value2,
                command.value3,
                command.value4,
            )
        except (OrviboBinaryError, OSError, TimeoutError) as err:
            raise HomeAssistantError(str(err)) from err

    def _handle_coordinator_update(self) -> None:
        self._optimistic_on = None
        self._optimistic_brightness = None
        self._optimistic_color_temp_kelvin = None
        super()._handle_coordinator_update()
