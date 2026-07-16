"""Orvibo Cloud integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr

from .api import OrviboCloudClient
from .const import CONF_HOST, DOMAIN, PLATFORMS
from .coordinator import OrviboCloudCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Orvibo Cloud from a config entry."""

    client = OrviboCloudClient(
        async_get_clientsession(hass),
        host=entry.data[CONF_HOST],
    )
    coordinator = OrviboCloudCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    _async_register_devices(hass, entry, coordinator)
    entry.async_on_unload(
        coordinator.async_add_listener(
            lambda: _async_register_devices(hass, entry, coordinator)
        )
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Orvibo Cloud config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: OrviboCloudCoordinator,
) -> None:
    """Create or update every cloud device returned by ORVIBO."""

    registry = dr.async_get(hass)
    account_identifier = (DOMAIN, entry.data["user_id"])
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={account_identifier},
        manufacturer="ORVIBO",
        model="Cloud account",
        name="ORVIBO Cloud",
    )

    for device in coordinator.data.devices:
        fallback_name = device.model or device.device_type or f"ORVIBO {device.uid[-6:]}"
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, device.uid)},
            manufacturer="ORVIBO",
            model=device.model or device.device_type or "Cloud device",
            name=device.name or fallback_name,
            suggested_area=device.room or None,
            via_device=account_identifier,
        )
