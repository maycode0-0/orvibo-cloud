"""Binary sensors for Orvibo Cloud."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_USER_ID, DOMAIN
from .coordinator import OrviboCloudCoordinator
from .entity import OrviboCloudDeviceEntity, OrviboCloudEntity
from .protocol import property_switch_state
from .selection import device_is_selected


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OrviboCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [
        OrviboCloudConnectionBinarySensor(coordinator)
    ]
    entities.extend(
        OrviboDoorBinarySensor(coordinator, device.uid)
        for device in coordinator.data.devices
        if device_is_selected(entry.options, device.uid)
        and "door_status" in device.properties
    )
    async_add_entities(entities)


class OrviboCloudConnectionBinarySensor(OrviboCloudEntity, BinarySensorEntity):
    """Report whether the latest authenticated refresh succeeded."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "connection"

    def __init__(self, coordinator: OrviboCloudCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.data[CONF_USER_ID]}_connection"

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class OrviboDoorBinarySensor(OrviboCloudDeviceEntity, BinarySensorEntity):
    """Report the open/closed state of a property-based door lock."""

    _attr_device_class = BinarySensorDeviceClass.DOOR
    _attr_name = "Door"

    def __init__(
        self,
        coordinator: OrviboCloudCoordinator,
        device_id: str,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_door"

    @property
    def is_on(self) -> bool | None:
        device = self._device
        if device is None:
            return None
        return property_switch_state(device.properties, "door_status")
