"""Pure command mappings verified against the current ORVIBO app."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrviboControlCommand:
    """Values carried by an ORVIBO cmd=15 device command."""

    order: str
    value1: int
    value2: int = 0
    value3: int = 0
    value4: int = 0


def curtain_position_command(ha_position: int) -> OrviboControlCommand:
    """Convert HA's 0=closed convention to ORVIBO's 0=open convention."""

    position = max(0, min(100, int(ha_position)))
    return OrviboControlCommand("open", 100 - position)


def curtain_stop_command() -> OrviboControlCommand:
    """Build a curtain stop command."""

    return OrviboControlCommand("stop", 0)


def light_power_command(
    is_on: bool,
    brightness: int,
    color_temp_kelvin: int,
) -> OrviboControlCommand:
    """Build the app's non-intuitive on/off command mapping."""

    return OrviboControlCommand(
        "off" if is_on else "on",
        1 if is_on else 0,
        _brightness(brightness),
        kelvin_to_mired(color_temp_kelvin),
    )


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
