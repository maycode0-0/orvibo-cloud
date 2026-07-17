"""Tests for dependency-free Orvibo protocol helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "orvibo_cloud"
    / "protocol.py"
)
SPEC = importlib.util.spec_from_file_location("orvibo_cloud_protocol", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
protocol = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = protocol
SPEC.loader.exec_module(protocol)


class ProtocolTests(unittest.TestCase):
    def test_password_hash_matches_cloud_format(self) -> None:
        self.assertEqual(
            protocol.password_hash("password"),
            "5F4DCC3B5AA765D61D8327DEB882CF99",
        )

    def test_family_request_is_stable_and_signed(self) -> None:
        body = protocol.build_family_request(
            access_token="access",
            user_id="user-1",
            timestamp_ms=1700000000123,
            nonce=123456,
        )
        self.assertEqual(body["accessToken"], "access")
        self.assertEqual(body["timestamp"], "1700000000123")
        self.assertEqual(
            body["sign"],
            "DE2412D3A82D85E151378ADFC1FF81F25F19E7606AEAC20E73BD6048709EECA5",
        )

    def test_parse_families_normalizes_and_deduplicates(self) -> None:
        families = protocol.parse_families(
            {
                "data": [
                    {"familyId": "one", "familyName": "Home"},
                    {"family_id": "two", "name": "Office"},
                    {"familyId": "one", "familyName": "Duplicate"},
                    {"familyName": "Missing ID"},
                ]
            }
        )
        self.assertEqual(
            [(family.family_id, family.name) for family in families],
            [("one", "Home"), ("two", "Office")],
        )

    def test_readtable_request_is_stable_and_signed(self) -> None:
        body = protocol.build_readtable_request(
            access_token="access",
            user_id="user-1",
            family_id="family-1",
            session_id="session-1",
            timestamp_ms=1700000000123,
            serial=1700000000,
            nonce="0123456789abcdef0123456789abcdef",
            version="5.2.6.302",
        )

        self.assertEqual(body["dataType"], "all")
        self.assertEqual(body["lastUpdateTime"], 0)
        self.assertEqual(body["userName"], "user-1")
        self.assertEqual(
            body["sign"],
            "709C8461A366ED6563072B2B04ECB4612BE4B582651284554C4EABF0CADCE76D",
        )

    def test_parse_readtable_devices_joins_only_device_tables(self) -> None:
        devices = protocol.parse_readtable_devices(
            {
                "code": 0,
                "data": {
                    "account": {"uid": "account-should-not-be-a-device"},
                    "gateway": [
                        {"uid": "gateway-row-should-not-be-a-device", "online": 1}
                    ],
                    "room": [
                        {
                            "roomId": "room-1",
                            "roomName": "Kitchen",
                            "uid": "room-row",
                        }
                    ],
                    "device": [
                        {
                            "deviceId": "device-child-0001",
                            "uid": "shared-gateway-uid",
                            "deviceName": "Ceiling light",
                            "deviceType": 1,
                            "subDeviceType": 6,
                            "roomId": "room-1",
                            "parentId": "gateway-device-1",
                            "delFlag": 0,
                        },
                        {
                            "deviceId": "device-child-0002",
                            "uid": "shared-gateway-uid",
                            "deviceName": "Removed curtain",
                            "deviceType": 34,
                            "delFlag": 1,
                        },
                    ],
                    "deviceStatus": [
                        {
                            "deviceId": "device-child-0001",
                            "uid": "status-row",
                            "online": 1,
                            "value1": 67,
                            "value2": 146,
                            "value3": 250,
                            "value4": 0,
                            "delFlag": 0,
                        }
                    ],
                },
            }
        )

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].uid, "device-child-0001")
        self.assertEqual(devices[0].name, "Ceiling light")
        self.assertEqual(devices[0].room, "Kitchen")
        self.assertEqual(devices[0].parent_uid, "gateway-device-1")
        self.assertTrue(devices[0].online)
        self.assertEqual(devices[0].value1, 67)
        self.assertEqual(devices[0].value2, 146)
        self.assertEqual(devices[0].value3, 250)
        self.assertEqual(devices[0].value4, 0)
        self.assertEqual(devices[0].sub_device_type, "6")

    def test_extract_devices_handles_nested_and_duplicate_devices(self) -> None:
        devices = protocol.extract_devices(
            [
                {
                    "cmd": 230,
                    "deviceList": [
                        {
                            "uid": "0123456789ABCDEF",
                            "deviceName": "Living room light",
                            "deviceType": 10,
                            "roomName": "Living room",
                        },
                        {
                            "deviceId": "camera-device-01",
                            "modelName": "S1",
                            "isOnline": 1,
                        },
                    ],
                },
                {
                    "data": {
                        "uid": "0123456789ABCDEF",
                        "model": "MixSwitch",
                        "online": "online",
                    }
                },
            ]
        )

        self.assertEqual(len(devices), 2)
        light = next(device for device in devices if device.uid == "0123456789ABCDEF")
        camera = next(device for device in devices if device.uid == "camera-device-01")
        self.assertEqual(light.name, "Living room light")
        self.assertEqual(light.model, "MixSwitch")
        self.assertEqual(light.device_type, "10")
        self.assertTrue(light.online)
        self.assertEqual(camera.model, "S1")
        self.assertTrue(camera.online)

    def test_extract_devices_does_not_treat_account_ids_as_devices(self) -> None:
        devices = protocol.extract_devices(
            {"userId": "user-123456", "familyId": "family-123456", "cmd": 2}
        )
        self.assertEqual(devices, ())

    def test_extract_devices_keeps_children_that_share_a_gateway_uid(self) -> None:
        devices = protocol.extract_devices(
            {
                "cmd": 147,
                "tableNameList": [
                    {
                        "tableName": "room",
                        "dataList": [
                            {"roomId": "room-1", "roomName": "Kitchen"}
                        ],
                    },
                    {
                        "tableName": "device",
                        "dataList": [
                            {
                                "deviceId": "device-child-0001",
                                "uid": "5ccf7f140597",
                                "deviceName": "Ceiling light",
                                "deviceType": 1,
                                "roomId": "room-1",
                            },
                            {
                                "deviceId": "device-child-0002",
                                "uid": "5ccf7f140597",
                                "deviceName": "Curtain",
                                "deviceType": 34,
                                "roomId": "room-1",
                            },
                        ],
                    },
                    {
                        "tableName": "permission",
                        "dataList": [
                            {
                                "deviceId": "permission-row-0001",
                                "uid": "5ccf7f140597",
                                "userId": "user-1",
                            }
                        ],
                    },
                ],
            }
        )

        self.assertEqual(
            [device.uid for device in devices],
            ["device-child-0001", "device-child-0002"],
        )
        self.assertEqual({device.room for device in devices}, {"Kitchen"})


if __name__ == "__main__":
    unittest.main()
