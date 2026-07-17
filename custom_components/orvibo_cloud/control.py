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


def light_is_on_from_orvibo(value: int | None) -> bool | None:
    """Interpret the active-low power state used by verified type-38 lights."""

    if value not in (0, 1):
        return None
    return value == 0


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
