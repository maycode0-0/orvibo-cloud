"""Orvibo Cloud integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .api import OrviboCloudClient
from .capture import OrviboRawEventCapture
from .const import (
    CONF_FAMILY_ID,
    CONF_HOST,
    CONF_PASSWORD_HASH,
    CONF_RAW_EVENT_CAPTURE,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import OrviboCloudCoordinator
from .selection import (
    configured_device_areas,
    device_is_selected,
    selected_device_ids,
)

_LOGGER = logging.getLogger(__name__)


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
    binary_user_name = coordinator.data.binary_user_name
    binary_password = coordinator.data.binary_password
    if not binary_user_name or not binary_password:
        _LOGGER.warning(
            "ORVIBO push listener was not started because port-10002 "
            "credentials were not returned by device discovery"
            )
        return True
    coordinator.raw_event_capture = OrviboRawEventCapture(
        hass,
        entry.data[CONF_HOST],
        binary_user_name,
        binary_password,
        entry.data[CONF_FAMILY_ID],
        capture_raw_events=entry.options.get(CONF_RAW_EVENT_CAPTURE, False),
        )
    coordinator.raw_event_capture.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Orvibo Cloud config entry."""

    coordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.raw_event_capture is not None:
        await coordinator.raw_event_capture.async_stop()
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
    """Create selected cloud devices and remove devices no longer selected."""

    registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    account_identifier = (DOMAIN, entry.data["user_id"])
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={account_identifier},
        manufacturer="ORVIBO",
        model="Cloud account",
        name="ORVIBO Cloud",
    )

    available_ids = {device.uid for device in coordinator.data.devices}
    selected_ids = selected_device_ids(entry.options, available_ids)
    device_areas = configured_device_areas(entry.options)

    for registry_device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        orvibo_ids = {
            identifier
            for domain, identifier in registry_device.identifiers
            if domain == DOMAIN
        }
        cloud_device_ids = orvibo_ids - {entry.data["user_id"]}
        if not cloud_device_ids or any(
            device_is_selected(entry.options, device_id)
            for device_id in cloud_device_ids
        ):
            continue
        for entity in er.async_entries_for_device(
            entity_registry,
            registry_device.id,
            include_disabled_entities=True,
        ):
            if entity.config_entry_id == entry.entry_id:
                entity_registry.async_remove(entity.entity_id)
        registry.async_update_device(
            registry_device.id,
            remove_config_entry_id=entry.entry_id,
        )

    for device in coordinator.data.devices:
        if device.uid not in selected_ids:
            continue
        fallback_name = (
            device.model or device.device_type or f"ORVIBO {device.uid[-6:]}"
        )
        registry_device = registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, device.uid)},
            manufacturer="ORVIBO",
            model=device.model or device.device_type or "Cloud device",
            name=device.name or fallback_name,
            suggested_area=device.room or None,
            via_device=account_identifier,
        )
        if device.uid in device_areas:
            registry.async_update_device(
                registry_device.id,
                area_id=device_areas[device.uid],
            )
