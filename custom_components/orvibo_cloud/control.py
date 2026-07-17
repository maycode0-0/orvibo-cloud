"""Pure command mappings verified against the current ORVIBO app."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_TUNABLE_LIGHT_SUB_DEVICE_TYPES = {"4", "6", "13"}
_PROPERTY_LIGHT_MODELS = {
    "294339fdc9b04613bb6cf1569305b78c",
    "71b94d0309094d1e9c678e4c21bbf878",
    "f731c19a484c419282051494ceecd66a",
}


@dataclass(frozen=True, slots=True)
class OrviboControlCommand:
    """Values carried by an ORVIBO cmd=15 device command."""

    order: str
    value1: int
    value2: int = 0
    value3: int = 0
    value4: int = 0
    properties: Mapping[str, Any] | None = None


def curtain_position_command(ha_position: int) -> OrviboControlCommand:
    """Build a curtain command using the shared 0=closed, 100=open scale."""

    position = max(0, min(100, int(ha_position)))
    return OrviboControlCommand("open", position)


def curtain_stop_command() -> OrviboControlCommand:
    """Build a curtain stop command."""

    return OrviboControlCommand("stop", 0)


def curtain_position_from_orvibo(value: int | None) -> int | None:
    """Convert a reported ORVIBO curtain position to Home Assistant."""

    if value is None or not 0 <= value <= 100:
        return None
    return value


def light_power_command(
    is_on: bool,
    brightness: int,
    color_temp_kelvin: int,
) -> OrviboControlCommand:
    """Build an active-low light power command."""

    return OrviboControlCommand(
        "on" if is_on else "off",
        0 if is_on else 1,
        _brightness(brightness),
        kelvin_to_mired(color_temp_kelvin),
    )


def power_only_light_command(is_on: bool) -> OrviboControlCommand:
    """Build the captured command used by type-1 and type-102 light relays."""

    return OrviboControlCommand(
        "on" if is_on else "off",
        0 if is_on else 1,
    )


def property_light_power_command(is_on: bool) -> OrviboControlCommand:
    """Build the property command used by type-503 light endpoints."""

    return OrviboControlCommand(
        "set property",
        0,
        properties={"onoff": {"status": "on" if is_on else "off"}},
    )


def light_is_on_from_orvibo(value: int | None) -> bool | None:
    """Interpret the active-low power state used by verified type-38 lights."""

    if value not in (0, 1):
        return None
    return value == 0


def is_supported_tunable_light_profile(
    device_type: str,
    sub_device_type: str,
    model: str,
    brightness: int | None,
    color_temp_mired: int | None,
) -> bool:
    """Return whether a device matches a verified tunable-light profile."""

    if device_type == "503":
        return sub_device_type == "436" and model in _PROPERTY_LIGHT_MODELS
    return device_type == "38" and (
        sub_device_type in _TUNABLE_LIGHT_SUB_DEVICE_TYPES
        and brightness is not None
        and 0 <= brightness <= 255
        and color_temp_mired is not None
        and color_temp_mired > 0
    )


def is_supported_power_only_light_profile(
    device_type: str,
    sub_device_type: str,
) -> bool:
    """Return whether a device matches a verified relay-light profile."""

    return device_type in {"1", "102"} and sub_device_type == "1"


def light_brightness_command(
    brightness: int,
    color_temp_kelvin: int,
) -> OrviboControlCommand:
    """Build a brightness command while preserving color temperature."""

    return OrviboControlCommand(
        "fast move to level",
        0,
        _brightness(brightness),
        max(1, int(color_temp_kelvin)),
    )


def property_light_brightness_command(brightness: int) -> OrviboControlCommand:
    """Build the captured brightness command used by type-503 light endpoints."""

    return OrviboControlCommand(
        "fast move to level",
        0,
        _brightness(brightness),
        0,
    )


def light_color_temp_command(
    brightness: int,
    color_temp_kelvin: int,
) -> OrviboControlCommand:
    """Build a color-temperature command while preserving brightness."""

    return OrviboControlCommand(
        "fast color temperature",
        0,
        _brightness(brightness),
        kelvin_to_mired(color_temp_kelvin),
    )


def kelvin_to_mired(color_temp_kelvin: int) -> int:
    """Convert Kelvin to the integer mired unit used in device status."""

    return round(1_000_000 / max(1, int(color_temp_kelvin)))


def mired_to_kelvin(mired: int) -> int | None:
    """Convert an ORVIBO mired value to Kelvin."""

    return None if mired <= 0 else round(1_000_000 / mired)


def _brightness(value: int) -> int:
    return max(1, min(255, int(value)))
