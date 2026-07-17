"""Device selection helpers for ORVIBO config entries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

CONF_SELECTED_DEVICE_IDS = "selected_device_ids"
CONF_DEVICE_AREAS = "device_areas"


def selected_device_ids(
    options: Mapping[str, Any],
    available_device_ids: Iterable[str],
) -> set[str]:
    """Return selected IDs, defaulting legacy entries to every available device."""

    available = {str(device_id) for device_id in available_device_ids}
    if CONF_SELECTED_DEVICE_IDS not in options:
        return available
    configured = options.get(CONF_SELECTED_DEVICE_IDS)
    if not isinstance(configured, (list, tuple, set)):
        return set()
    return {str(device_id) for device_id in configured} & available


def device_is_selected(options: Mapping[str, Any], device_id: str) -> bool:
    """Return whether one device should be exposed by the integration."""

    if CONF_SELECTED_DEVICE_IDS not in options:
        return True
    configured = options.get(CONF_SELECTED_DEVICE_IDS)
    if not isinstance(configured, (list, tuple, set)):
        return False
    return device_id in {str(value) for value in configured}


def configured_device_areas(options: Mapping[str, Any]) -> dict[str, str | None]:
    """Return the configured HA area ID for each selected device."""

    configured = options.get(CONF_DEVICE_AREAS)
    if not isinstance(configured, Mapping):
        return {}
    areas: dict[str, str | None] = {}
    for device_id, area_id in configured.items():
        if area_id is None:
            areas[str(device_id)] = None
        elif isinstance(area_id, str) and area_id:
            areas[str(device_id)] = area_id
    return areas
