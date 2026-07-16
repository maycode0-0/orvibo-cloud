"""Binary sensors for Orvibo Cloud."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_USER_ID, DOMAIN
from .coordinator import OrviboCloudCoordinator
from .entity import OrviboCloudEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OrviboCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OrviboCloudConnectionBinarySensor(coordinator)])


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
