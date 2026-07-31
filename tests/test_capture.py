"""Tests for redacted ORVIBO raw event capture."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types
import unittest

COMPONENT_PATH = Path(__file__).parents[1] / "custom_components" / "orvibo_cloud"
SETUP_PATH = COMPONENT_PATH / "__init__.py"


def _load_capture_module():
    package_name = "orvibo_cloud_capture_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(COMPONENT_PATH)]
    sys.modules[package_name] = package

    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    homeassistant.core = core
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.core"] = core
    binary = types.ModuleType(f"{package_name}.binary")
    binary.OrviboBinaryClient = object
    binary.OrviboCaptureError = RuntimeError
    sys.modules[f"{package_name}.binary"] = binary
    return importlib.import_module(f"{package_name}.capture")


class RawEventRedactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.capture = _load_capture_module()

    def test_credentials_are_removed_and_identifiers_are_stable(self) -> None:
        salt = b"test-salt"
        packet = {
            "cmd":42,
            "token": "secret-token",
            "sessionId": "secret-session",
            "deviceId": "front-door-lock",
            "uid": "front-door-lock",
            "value1":1,
        }

        redacted = self.capture.redact_packet(packet, salt)

        self.assertEqual(redacted["cmd"],42)
        self.assertEqual(redacted["token"], "<redacted>")
        self.assertEqual(redacted["sessionId"], "<redacted>")
        self.assertNotIn("front-door-lock", str(redacted))
        self.assertEqual(redacted["deviceId"], redacted["uid"])
        self.assertEqual(redacted["value1"],1)

    def test_unknown_strings_only_expose_length(self) -> None:
        redacted = self.capture.redact_packet(
            {
                "message": "door opened by Alice",
                "properties": {"unlockType": "fingerprint"},
            },
            b"test-salt",
        )

        self.assertEqual(redacted["message"], "<string:length=20>")
        self.assertEqual(
            redacted["properties"]["unlockType"],
            "<string:length=11>",
        )

    def test_nested_collections_are_bounded(self) -> None:
        redacted = self.capture.redact_packet(
            {"events": list(range(55))},
            b"test-salt",
        )

        self.assertEqual(len(redacted["events"]),51)
        self.assertEqual(redacted["events"][-1], "<truncated:5>")

    def test_dynamic_mapping_keys_are_fingerprinted(self) -> None:
        redacted = self.capture.redact_packet(
            {
                "AA:BB:CC:DD:EE:FF": {"value1":1},
                "AABBCCDDEEFF": {"value1":2},
            },
            b"test-salt",
        )

        self.assertNotIn("AA:BB:CC:DD:EE:FF", redacted)
        self.assertNotIn("AABBCCDDEEFF", redacted)
        self.assertTrue(all(key.startswith("<id:") for key in redacted))


class RawEventSetupStructureTests(unittest.TestCase):
    def test_capture_uses_transient_port_10002_credentials(self) -> None:
        source = SETUP_PATH.read_text(encoding="utf-8")

        self.assertIn("coordinator.data.binary_user_name", source)
        self.assertIn("coordinator.data.binary_password", source)
        capture_call = source.split("OrviboRawEventCapture(", maxsplit=1)[1].split(
            ")", maxsplit=1
        )[0]
        self.assertNotIn("CONF_EMAIL", capture_call)
        self.assertNotIn("CONF_PASSWORD_HASH", capture_call)

    def test_capture_does_not_start_without_binary_credentials(self) -> None:
        source = SETUP_PATH.read_text(encoding="utf-8")

        self.assertIn("if not binary_user_name or not binary_password:", source)
        self.assertIn("credentials were not returned by device discovery", source)

    def test_door_sensor_matches_uid_and_device_id(self) -> None:
        source = (SETUP_PATH.parent / "binary_sensor.py").read_text(encoding="utf-8")

        self.assertIn('event.data.get("uid")', source)
        self.assertIn('event.data.get("device_id")', source)
        self.assertIn(
            "self._device_id not in {event_uid, event_device_id}",
            source,
        )


class LockEventParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.capture = _load_capture_module()

    def test_cmd_42_extracts_safe_lock_states(self) -> None:
        event = self.capture.parse_lock_event(
            {
                "cmd":42,
                "uid":"lock-1",
                "deviceId":"device-1",
                "serial":1725,
                "properties":{
                    "door_status":"closed",
                    "reverse_lock":"off",
                    "handle":"down",
                    "ssid":"secret-wifi",
                },
                "updateTimeSec":1785419851,
            }
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["uid"], "lock-1")
        self.assertEqual(event["door_state"], "closed")
        self.assertEqual(event["lock_state"], "unlocked")
        self.assertEqual(event["states"], {
            "door_status":"closed",
            "reverse_lock":"off",
            "handle":"down",
        })
        self.assertNotIn("ssid", event)

    def test_on_off_door_status_is_normalized(self) -> None:
        opened = self.capture.parse_lock_event(
            {"cmd":42, "uid":"lock-1", "properties":{"door_status":"on"}}
        )
        closed = self.capture.parse_lock_event(
            {"cmd":42, "uid":"lock-1", "properties":{"door_status":"off"}}
        )

        assert opened is not None
        assert closed is not None
        self.assertEqual(opened["door_state"], "open")
        self.assertEqual(closed["door_state"], "closed")

    def test_non_lock_and_unknown_values_are_ignored(self) -> None:
        self.assertIsNone(self.capture.parse_lock_event({"cmd":53, "uid":"lock-1"}))
        self.assertIsNone(
            self.capture.parse_lock_event(
                {
                    "cmd":42,
                    "uid":"lock-1",
                    "properties":{"door_status":"fingerprint"},
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
