"""Diagnostics support for Orvibo Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD_HASH, CONF_USER_ID, DOMAIN
from .coordinator import OrviboCloudCoordinator

_TO_REDACT = {CONF_PASSWORD_HASH, CONF_USER_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return account diagnostics without credentials or OAuth tokens."""

    coordinator: OrviboCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry": async_redact_data(dict(entry.data), _TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "family_count": len(coordinator.data.families),
        "device_count": len(coordinator.data.devices),
        "device_discovery_error": coordinator.device_discovery_error,
        "families": [
            {"family_id": "**REDACTED**", "name": family.name}
            for family in coordinator.data.families
        ],
        "devices": [
            {
                "uid": "**REDACTED**",
                "name": device.name,
                "model": device.model,
                "device_type": device.device_type,
                "room": device.room,
                "parent_uid": "**REDACTED**" if device.parent_uid else "",
                "online": device.online,
            }
            for device in coordinator.data.devices
        ],
    }
