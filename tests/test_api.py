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

    def test_privacy_device_request_uses_current_app_endpoint(self) -> None:
        session = FakeSession(
            {
                "status": 0,
                "data": {
                    "tableName": "privacyDevice",
                    "dataList": [
                        {
                            "deviceId": "camera-device-01",
                            "deviceName": "Giant Eye 2K",
                            "model": "S1",
                            "deviceType": 200,
                            "online": 1,
                        }
                    ]
                },
            }
        )
        client = self.api.OrviboCloudClient(session)

        with (
            patch.object(self.api.time, "time", return_value=1700000000.123),
            patch.object(self.api.secrets, "randbelow", return_value=23456),
        ):
            devices = asyncio.run(
                client._async_privacy_devices(
                    "china.orvibo.com",
                    "access",
                    "user-1",
                )
            )

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].uid, "camera-device-01")
        self.assertEqual(devices[0].model, "S1")
        self.assertIsNotNone(session.last_post)
        url, body, timeout = session.last_post
        self.assertEqual(
            url,
            "https://china.orvibo.com/v2/privacyDevice/statistics/users",
        )
        self.assertEqual(body["accessToken"], "access")
        self.assertEqual(body["userId"], "user-1")
        self.assertEqual(body["random"], "123456")
        self.assertEqual(timeout.total, 15)

    def test_merge_devices_keeps_rest_only_camera(self) -> None:
        device = self.api.OrviboDevice
        rest_camera = device(
            uid="camera-device-01",
            name="Giant Eye 2K",
            model="S1",
            device_type="200",
            room="Living room",
            parent_uid="",
            online=None,
        )
        binary_camera = device(
            uid="camera-device-01",
            name="",
            model="",
            device_type="",
            room="",
            parent_uid="",
            online=True,
        )
        binary_curtain = device(
            uid="curtain-device-01",
            name="Curtain",
            model="",
            device_type="34",
            room="Bedroom",
            parent_uid="",
            online=True,
        )

        devices = self.api.merge_devices(
            (rest_camera,),
            (binary_camera, binary_curtain),
        )

        self.assertEqual(
            [item.uid for item in devices],
            ["camera-device-01", "curtain-device-01"],
        )
        camera = devices[0]
        self.assertEqual(camera.name, "Giant Eye 2K")
        self.assertEqual(camera.model, "S1")
        self.assertTrue(camera.online)


if __name__ == "__main__":
    unittest.main()
