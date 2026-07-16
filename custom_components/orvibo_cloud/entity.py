"""Shared Orvibo Cloud entity helpers."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_USER_ID, DOMAIN
from .coordinator import OrviboCloudCoordinator


class OrviboCloudEntity(CoordinatorEntity[OrviboCloudCoordinator]):
    """Base entity attached to one Orvibo cloud account."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OrviboCloudCoordinator) -> None:
        super().__init__(coordinator)
        user_id = coordinator.entry.data[CONF_USER_ID]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, user_id)},
            manufacturer="ORVIBO",
            model="Cloud account",
            name="ORVIBO Cloud",
        )

