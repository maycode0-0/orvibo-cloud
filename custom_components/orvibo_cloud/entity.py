"""Shared Orvibo Cloud entity helpers."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_USER_ID, DOMAIN
from .coordinator import OrviboCloudCoordinator
from .protocol import OrviboDevice


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


class OrviboCloudDeviceEntity(CoordinatorEntity[OrviboCloudCoordinator]):
    """Base entity attached to one ORVIBO device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OrviboCloudCoordinator,
        device_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        device = self._device
        assert device is not None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="ORVIBO",
            model=device.model or device.device_type or "Cloud device",
            name=(
                device.name
                or device.model
                or device.device_type
                or f"ORVIBO {device_id[-6:]}"
            ),
            suggested_area=device.room or None,
            via_device=(DOMAIN, coordinator.entry.data[CONF_USER_ID]),
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
        # Battery devices sleep with online=0 while their cloud snapshot is valid.
        return super().available and device is not None
