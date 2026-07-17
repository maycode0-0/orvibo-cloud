"""Tests for ORVIBO REST device discovery."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


COMPONENT_PATH = (
    Path(__file__).parents[1] / "custom_components" / "orvibo_cloud"
)


def _load_api_module():
    aiohttp = types.ModuleType("aiohttp")
    homeassistant = types.ModuleType("homeassistant")
    homeassistant_const = types.ModuleType("homeassistant.const")

    class ClientError(Exception):
        pass

    class ClientTimeout:
        def __init__(self, *, total: int) -> None:
            self.total = total

    aiohttp.ClientError = ClientError
    aiohttp.ClientSession = object
    aiohttp.ClientTimeout = ClientTimeout
    sys.modules["aiohttp"] = aiohttp

    class Platform:
        BINARY_SENSOR = "binary_sensor"
        COVER = "cover"
        LIGHT = "light"
        SENSOR = "sensor"

    homeassistant_const.Platform = Platform
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.const"] = homeassistant_const

    package_name = "orvibo_cloud_api_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(COMPONENT_PATH)]
    sys.modules[package_name] = package
    return importlib.import_module(f"{package_name}.api")


class FakeResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def json(self, *, content_type=None):
        return self._payload

    async def read(self) -> bytes:
        return b""

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.last_post: tuple[str, dict[str, str], object] | None = None

    def post(self, url: str, *, json: dict[str, str], timeout: object):
        self.last_post = (url, json, timeout)
        return FakeResponse(self._payload)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.api = _load_api_module()

    def test_readtable_request_uses_current_app_endpoint(self) -> None:
        session = FakeSession(
            {
                "code": 0,
                "data": {
                    "account": [
                        {"userId": "user-1", "password": "binary-password"}
                    ],
                    "device": [
                        {
                            "deviceId": "camera-device-01",
                            "deviceName": "Camera",
                            "model": "S1",
                            "deviceType": 200,
                            "roomId": "room-1",
                        }
                    ],
                    "deviceStatus": [
                        {"deviceId": "camera-device-01", "online": 1}
                    ],
                    "room": [{"roomId": "room-1", "roomName": "Living room"}],
                },
            }
        )
        client = self.api.OrviboCloudClient(session)
        client._session_id = "session-0000000000000000000000000"

        with (
            patch.object(self.api.time, "time", return_value=1700000000.123),
            patch.object(
                self.api.secrets,
                "token_hex",
                return_value="0123456789abcdef0123456789abcdef",
            ),
        ):
            devices, binary_user_name, binary_password = asyncio.run(
                client._async_readtable(
                    "china.orvibo.com",
                    "access",
                    "user-1",
                    "family-1",
                )
            )

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].uid, "camera-device-01")
        self.assertEqual(devices[0].model, "S1")
        self.assertEqual(devices[0].room, "Living room")
        self.assertTrue(devices[0].online)
        self.assertEqual(binary_user_name, "user-1")
        self.assertEqual(binary_password, "binary-password")
        self.assertEqual(
            self.api._binary_credentials(
                {
                    "data": {
                        "account": [
                            {"userId": "other-user", "password": "other-password"}
                        ]
                    }
                },
                "user-1",
            ),
            ("", ""),
        )
        self.assertIsNotNone(session.last_post)
        url, body, timeout = session.last_post
        self.assertEqual(
            url,
            "https://china.orvibo.com/v2/cmd/app/readtable",
        )
        self.assertEqual(body["accessToken"], "access")
        self.assertEqual(body["userId"], "user-1")
        self.assertEqual(body["userName"], "user-1")
        self.assertEqual(body["familyId"], "family-1")
        self.assertEqual(body["sessionId"], "session-0000000000000000000000000")
        self.assertEqual(body["random"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(body["lastUpdateTime"], 0)
        self.assertEqual(body["pageIndex"], 0)
        self.assertEqual(body["dataType"], "all")
        self.assertEqual(body["deviceFlag"], 0)
        self.assertEqual(body["ver"], "5.2.6.302")
        self.assertEqual(len(body["sign"]), 64)
        self.assertEqual(timeout.total, 15)


if __name__ == "__main__":
    unittest.main()
