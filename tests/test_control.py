"""Tests for command mappings captured from the current ORVIBO app."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "orvibo_cloud"
    / "control.py"
)
SPEC = importlib.util.spec_from_file_location("orvibo_cloud_control", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
control = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = control
SPEC.loader.exec_module(control)


class ControlTests(unittest.TestCase):
    def test_curtain_positions_use_home_assistant_scale(self) -> None:
        self.assertEqual(control.curtain_position_command(100).value1, 100)
        self.assertEqual(control.curtain_position_command(0).value1, 0)
        self.assertEqual(control.curtain_position_command(67).value1, 67)
        self.assertEqual(control.curtain_stop_command().order, "stop")
        self.assertEqual(control.curtain_position_from_orvibo(100), 100)
        self.assertEqual(control.curtain_position_from_orvibo(0), 0)
        self.assertEqual(control.curtain_position_from_orvibo(67), 67)
        self.assertIsNone(control.curtain_position_from_orvibo(101))

    def test_light_power_mapping_matches_active_low_state(self) -> None:
        turn_on = control.light_power_command(True, 128, 3817)
        turn_off = control.light_power_command(False, 128, 3817)

        self.assertEqual(
            (turn_on.order, turn_on.value1, turn_on.value2, turn_on.value3),
            ("on", 0, 128, 262),
        )
        self.assertEqual(
            (turn_off.order, turn_off.value1, turn_off.value2, turn_off.value3),
            ("off", 1, 128, 262),
        )
        self.assertTrue(control.light_is_on_from_orvibo(turn_on.value1))
        self.assertFalse(control.light_is_on_from_orvibo(turn_off.value1))
        self.assertTrue(control.light_is_on_from_orvibo(0))
        self.assertFalse(control.light_is_on_from_orvibo(1))
        self.assertIsNone(control.light_is_on_from_orvibo(None))

    def test_power_only_light_mapping_matches_captures(self) -> None:
        turn_on = control.power_only_light_command(True)
        turn_off = control.power_only_light_command(False)

        self.assertEqual(
            (turn_on.order, turn_on.value1, turn_on.value2, turn_on.value3),
            ("on", 0, 0, 0),
        )
        self.assertEqual(
            (turn_off.order, turn_off.value1, turn_off.value2, turn_off.value3),
            ("off", 1, 0, 0),
        )

    def test_property_light_power_mapping_matches_captures(self) -> None:
        turn_on = control.property_light_power_command(True)
        turn_off = control.property_light_power_command(False)

        self.assertEqual(turn_on.order, "set property")
        self.assertEqual(turn_on.properties, {"onoff": {"status": "on"}})
        self.assertEqual(turn_off.properties, {"onoff": {"status": "off"}})

    def test_light_brightness_mapping_preserves_kelvin(self) -> None:
        command = control.light_brightness_command(146, 3000)
        self.assertEqual(
            (command.order, command.value1, command.value2, command.value3),
            ("fast move to level", 0, 146, 3000),
        )

    def test_property_light_brightness_mapping_clears_value3(self) -> None:
        command = control.property_light_brightness_command(139)
        self.assertEqual(
            (command.order, command.value1, command.value2, command.value3),
            ("fast move to level", 0, 139, 0),
        )

    def test_light_color_temperature_mapping_uses_mired(self) -> None:
        command = control.light_color_temp_command(146, 4000)
        self.assertEqual(
            (command.order, command.value1, command.value2, command.value3),
            ("fast color temperature", 0, 146, 250),
        )
        self.assertEqual(control.mired_to_kelvin(250), 4000)

    def test_verified_tunable_light_profiles_are_supported(self) -> None:
        for sub_device_type in ("4", "6", "13"):
            with self.subTest(sub_device_type=sub_device_type):
                self.assertTrue(
                    control.is_supported_tunable_light_profile(
                        "38", sub_device_type, "model", 146, 250
                    )
                )

        self.assertTrue(
            control.is_supported_tunable_light_profile(
                "503",
                "436",
                "294339fdc9b04613bb6cf1569305b78c",
                -1,
                -1,
            )
        )
        self.assertFalse(
            control.is_supported_tunable_light_profile(
                "503", "436", "unknown-model", -1, -1
            )
        )
        self.assertFalse(
            control.is_supported_tunable_light_profile(
                "38", "4", "model", None, None
            )
        )

    def test_verified_power_only_light_profiles_are_supported(self) -> None:
        self.assertTrue(control.is_supported_power_only_light_profile("1", "1"))
        self.assertTrue(control.is_supported_power_only_light_profile("102", "1"))
        self.assertFalse(control.is_supported_power_only_light_profile("1", "11"))


if __name__ == "__main__":
    unittest.main()
