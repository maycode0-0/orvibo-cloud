"""Sensors for Orvibo Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_FAMILY_ID, CONF_USER_ID, DOMAIN
from .coordinator import OrviboCloudCoordinator
from .entity import OrviboCloudDeviceEntity, OrviboCloudEntity
from .protocol import property_percentage
from .selection import device_is_selected


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OrviboCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        OrviboCloudFamilySensor(coordinator),
        OrviboCloudDeviceCountSensor(coordinator),
    ]
    entities.extend(
        OrviboBatterySensor(coordinator, device.uid)
        for device in coordinator.data.devices
        if device_is_selected(entry.options, device.uid)
        and "battery_power" in device.properties
    )
    async_add_entities(entities)


class OrviboCloudFamilySensor(OrviboCloudEntity, SensorEntity):
    """Expose the selected Orvibo family."""

    _attr_icon = "mdi:home-account"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "family"

    def __init__(self, coordinator: OrviboCloudCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.data[CONF_USER_ID]}_family"

    @property
    def native_value(self) -> str:
        selected_id = self.coordinator.entry.data.get(CONF_FAMILY_ID, "")
        selected = next(
            (
                family
                for family in self.coordinator.data.families
                if family.family_id == selected_id
            ),
            None,
        )
        return selected.name if selected else selected_id or "Unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "family_id": self.coordinator.entry.data.get(CONF_FAMILY_ID, ""),
            "family_count": len(self.coordinator.data.families),
            "cloud_host": self.coordinator.data.host,
        }


class OrviboCloudDeviceCountSensor(OrviboCloudEntity, SensorEntity):
    """Expose the number of devices returned by ORVIBO Cloud."""

    _attr_icon = "mdi:devices"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "device_count"

    def __init__(self, coordinator: OrviboCloudCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.data[CONF_USER_ID]}_device_count"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.devices)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "discovery_error": self.coordinator.device_discovery_error,
            "device_types": sorted(
                {
                    device.device_type
                    for device in self.coordinator.data.devices
                    if device.device_type
                }
            ),
        }


class OrviboBatterySensor(OrviboCloudDeviceEntity, SensorEntity):
    """Report the battery percentage of a property-based device."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Battery"

    def __init__(
        self,
        coordinator: OrviboCloudCoordinator,
        device_id: str,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_battery"

    @property
    def native_value(self) -> int | None:
        device = self._device
        if device is None:
            return None
        return property_percentage(device.properties, "battery_power")
