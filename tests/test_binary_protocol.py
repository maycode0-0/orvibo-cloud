"""Tests for ORVIBO AES packet framing."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types
import unittest

COMPONENT_PATH = (
    Path(__file__).parents[1] / "custom_components" / "orvibo_cloud"
)


def _load_binary_module():
    package_name = "orvibo_cloud_binary_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(COMPONENT_PATH)]
    sys.modules[package_name] = package
    return importlib.import_module(f"{package_name}.binary")


class BinaryProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.binary = _load_binary_module()
        except ModuleNotFoundError as err:
            if err.name == "Crypto":
                raise unittest.SkipTest("pycryptodome is not installed") from err
            raise

    def test_static_packet_round_trip_and_fragment_reassembly(self) -> None:
        client = self.binary.OrviboBinaryClient(
            host="china.orvibo.com",
            email="account@example.com",
            password_md5="0" * 32,
            family_id="family-1",
        )
        payload = {"cmd": 230, "familyId": "family-1", "serial": 1}
        packet = client._build_packet(payload, dynamic=False)

        client._receive_buffer.extend(packet[:17])
        self.assertEqual(client._extract_frames(), [])
        client._receive_buffer.extend(packet[17:])
        self.assertEqual(client._extract_frames(), [payload])

    def test_fragment_reassembly_preserves_split_magic_prefix(self) -> None:
        client = self.binary.OrviboBinaryClient(
            host="china.orvibo.com",
            email="account@example.com",
            password_md5="0" * 32,
            family_id="family-1",
        )
        payload = {"cmd": 0, "key": "0123456789ABCDEF"}
        packet = client._build_packet(payload, dynamic=False)

        client._receive_buffer.extend(packet[:1])
        self.assertEqual(client._extract_frames(), [])
        client._receive_buffer.extend(packet[1:])

        self.assertEqual(client._extract_frames(), [payload])

    def test_corrupt_packet_is_rejected(self) -> None:
        client = self.binary.OrviboBinaryClient(
            host="china.orvibo.com",
            email="account@example.com",
            password_md5="0" * 32,
            family_id="family-1",
        )
        packet = bytearray(client._build_packet({"cmd": 0}, dynamic=False))
        packet[-1] ^= 0x01
        self.assertIsNone(client._decode_packet(bytes(packet)))

    def test_device_table_request_matches_captured_app_shape(self) -> None:
        client = self.binary.OrviboBinaryClient(
            host="china.orvibo.com",
            email="account@example.com",
            password_md5="0" * 32,
            family_id="f" * 32,
        )
        payload = client._device_page_payload(0)
        packet = client._build_packet(payload, dynamic=False)

        self.assertEqual(payload["cmd"], 147)
        self.assertEqual(payload["pageIndex"], 0)
        self.assertEqual(payload["dataType"], "all")
        self.assertNotIn("lastUpdateTime", payload)
        self.assertEqual(len(packet), 282)

        next_page = client._device_page_payload(1)
        self.assertEqual(next_page["lastUpdateTime"], 0)

    def test_login_rejection_includes_safe_status_detail(self) -> None:
        client = self.binary.OrviboBinaryClient(
            host="china.orvibo.com",
            email="account@example.com",
            password_md5="0" * 32,
            family_id="family-1",
        )
        client._send = lambda payload: None
        client._receive = lambda timeout, idle_timeout: [
            {"cmd": 2, "status": 5, "message": "do not expose server text"}
        ]

        with self.assertRaisesRegex(
            self.binary.OrviboBinaryError,
            r"login was rejected \(status=5\)",
        ):
            client._login()

    def test_control_payload_matches_captured_app_shape(self) -> None:
        client = self.binary.OrviboBinaryClient(
            host="china.orvibo.com",
            email="account@example.com",
            password_md5="0" * 32,
            family_id="family-1",
        )

        payload = client._control_payload(
            "device-1",
            "hardware-uid-1",
            "open",
            67,
            146,
            250,
            0,
        )

        self.assertEqual(payload["cmd"], 15)
        self.assertEqual(payload["uid"], "hardware-uid-1")
        self.assertEqual(payload["deviceId"], "device-1")
        self.assertEqual(payload["groupId"], "")
        self.assertEqual(payload["order"], "open")
        self.assertEqual(payload["value1"], 67)
        self.assertEqual(payload["value2"], 146)
        self.assertEqual(payload["value3"], 250)
        self.assertEqual(payload["qualityOfService"], 1)
        self.assertEqual(payload["defaultResponse"], 1)
        self.assertEqual(payload["propertyResponse"], 0)

    def test_control_returns_cmd_42_state_values(self) -> None:
        client = self.binary.OrviboBinaryClient(
            host="china.orvibo.com",
            email="account@example.com",
            password_md5="0" * 32,
            family_id="family-1",
        )
        client._connect = lambda: None
        client._handshake = lambda: []
        client._login = lambda: []
        client._send = lambda payload: None
        client._receive = lambda timeout, idle_timeout: [
            {"cmd": 42, "value1": 1, "value2": 146, "value3": 250, "value4": 0}
        ]

        self.assertEqual(
            client.control_device(
                "device-1",
                "hardware-uid-1",
                "fast color temperature",
                0,
                146,
                250,
            ),
            (1, 146, 250, 0),
        )

    def test_control_rejects_missing_hardware_uid_before_connecting(self) -> None:
        client = self.binary.OrviboBinaryClient(
            host="china.orvibo.com",
            email="account@example.com",
            password_md5="0" * 32,
            family_id="family-1",
        )

        with self.assertRaisesRegex(
            self.binary.OrviboBinaryError,
            "control identifiers are missing",
        ):
            client.control_device("device-1", "", "open", 0)


if __name__ == "__main__":
    unittest.main()
