"""ORVIBO mutual-TLS binary cloud client used for device discovery."""

from __future__ import annotations

from collections.abc import Mapping
import json
import logging
from pathlib import Path
import secrets
import select
import socket
import ssl
import struct
import time
from typing import Any, Final
import zlib

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from .protocol import OrviboDevice, extract_devices

_LOGGER = logging.getLogger(__name__)

_STATIC_KEY: Final = b"khggd54865SNJHGF"
_CLIENT_VERSION: Final = "5.2.6.302"
_PORT: Final = 10002
_HEADER_SIZE: Final = 42
_MAX_DEVICE_PAGES: Final = 20
_CERT_PATH: Final = Path(__file__).with_name("orvibo_client_cert.pem")
_KEY_PATH: Final = Path(__file__).with_name("orvibo_client_key.pem")


class OrviboBinaryError(Exception):
    """Raised when an ORVIBO binary operation fails."""


class OrviboBinaryClient:
    """Blocking binary protocol client. Run it in HA's executor."""

    def __init__(
        self,
        host: str,
        email: str,
        password_md5: str,
        family_id: str,
    ) -> None:
        self._host = host
        self._email = email
        self._password_md5 = password_md5
        self._family_id = family_id
        self._socket: ssl.SSLSocket | None = None
        self._receive_buffer = bytearray()
        self._dynamic_key: bytes | None = None
        self._session_id = "0" * 32
        self._serial = int(time.time())
        self._identifier = secrets.token_hex(8)

    def discover(self) -> tuple[OrviboDevice, ...]:
        """Connect, authenticate, query, and normalize all returned devices."""

        packets: list[dict[str, Any]] = []
        try:
            self._connect()
            packets.extend(self._handshake())
            packets.extend(self._login())
            packets.extend(self._query_devices())
        finally:
            self.close()

        shapes = [
            {"cmd": packet.get("cmd"), "keys": sorted(packet.keys())}
            for packet in packets
        ]
        devices = extract_devices(packets)
        _LOGGER.debug(
            "ORVIBO binary discovery returned %d packets, %d devices, shapes=%s",
            len(packets),
            len(devices),
            shapes,
        )
        return devices

    def control_device(
        self,
        device_id: str,
        device_uid: str,
        order: str,
        value1: int,
        value2: int = 0,
        value3: int = 0,
        value4: int = 0,
    ) -> tuple[int | None, int | None, int | None, int | None]:
        """Open a binary session and send one device control command."""

        if not device_id or not device_uid:
            raise OrviboBinaryError("ORVIBO control identifiers are missing")
        try:
            self._connect()
            self._handshake()
            self._login()
            self._send(
                self._control_payload(
                    device_id,
                    device_uid,
                    order,
                    value1,
                    value2,
                    value3,
                    value4,
                )
            )
            packets = self._receive(timeout=10, idle_timeout=1)
        finally:
            self.close()

        response = next(
            (
                packet
                for packet in packets
                if packet.get("cmd") == 42 or "status" in packet
            ),
            None,
        )
        if response is None:
            raise OrviboBinaryError("ORVIBO control did not return a response")
        if response.get("status") not in (None, 0, "0"):
            raise OrviboBinaryError(
                "ORVIBO control was rejected "
                f"(status={response.get('status')!r})"
            )
        values: list[int | None] = []
        for key in ("value1", "value2", "value3", "value4"):
            try:
                values.append(int(response[key]))
            except (KeyError, TypeError, ValueError):
                values.append(None)
        return values[0], values[1], values[2], values[3]

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _connect(self) -> None:
        if not _CERT_PATH.is_file() or not _KEY_PATH.is_file():
            raise OrviboBinaryError("ORVIBO client certificate files are missing")

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # The private port uses ORVIBO's legacy certificate chain.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.load_cert_chain(_CERT_PATH, _KEY_PATH)

        raw_socket = socket.create_connection((self._host, _PORT), timeout=15)
        raw_socket.settimeout(15)
        self._socket = context.wrap_socket(raw_socket, server_hostname=self._host)

    def _next_serial(self) -> int:
        self._serial += 1
        return self._serial

    def _base_payload(self, command: int) -> dict[str, Any]:
        return {
            "cmd": command,
            "serial": self._next_serial(),
            "clientType": 1,
            "uniSerial": int(time.time() * 1000),
            "serverRecord": False,
            "ver": _CLIENT_VERSION,
            "debugInfo": f"Android_ZhiJia365_32_{_CLIENT_VERSION}",
        }

    @staticmethod
    def _encrypt(plaintext: bytes, key: bytes) -> bytes:
        return AES.new(key, AES.MODE_ECB).encrypt(pad(plaintext, AES.block_size))

    @staticmethod
    def _decrypt(ciphertext: bytes, key: bytes) -> bytes:
        return unpad(AES.new(key, AES.MODE_ECB).decrypt(ciphertext), AES.block_size)

    def _build_packet(self, payload: Mapping[str, Any], dynamic: bool = True) -> bytes:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        use_dynamic = dynamic and self._dynamic_key is not None
        key = self._dynamic_key if use_dynamic else _STATIC_KEY
        assert key is not None
        flag = b"dk" if use_dynamic else b"pk"
        encrypted = self._encrypt(raw, key)
        checksum = struct.pack(">I", zlib.crc32(encrypted) & 0xFFFFFFFF)
        session = self._session_id.encode("ascii")[:32].ljust(32, b"0")
        length = _HEADER_SIZE + len(encrypted)
        return b"hd" + struct.pack(">H", length) + flag + checksum + session + encrypted

    def _send(self, payload: Mapping[str, Any], dynamic: bool = True) -> None:
        if self._socket is None:
            raise OrviboBinaryError("ORVIBO binary socket is not connected")
        self._socket.sendall(self._build_packet(payload, dynamic=dynamic))

    def _decode_packet(self, packet: bytes) -> dict[str, Any] | None:
        if len(packet) < _HEADER_SIZE or packet[:2] != b"hd":
            return None
        encrypted = packet[_HEADER_SIZE:]
        if not encrypted or len(encrypted) % AES.block_size:
            return None
        expected_crc = struct.unpack(">I", packet[6:10])[0]
        if zlib.crc32(encrypted) & 0xFFFFFFFF != expected_crc:
            return None

        session = packet[10:42].decode("ascii", errors="ignore").strip("\x00")
        if session and session != "0" * 32:
            self._session_id = session.ljust(32, "0")[:32]

        for key in (self._dynamic_key, _STATIC_KEY):
            if key is None:
                continue
            try:
                value = json.loads(self._decrypt(encrypted, key).decode("utf-8"))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                return value
        return None

    def _extract_frames(self) -> list[dict[str, Any]]:
        packets: list[dict[str, Any]] = []
        while True:
            start = self._receive_buffer.find(b"hd")
            if start < 0:
                # Keep a possible split frame marker for the next socket read.
                if self._receive_buffer.endswith(b"h"):
                    self._receive_buffer[:] = b"h"
                else:
                    self._receive_buffer.clear()
                break
            if start:
                del self._receive_buffer[:start]
            if len(self._receive_buffer) < 4:
                break
            length = struct.unpack(">H", self._receive_buffer[2:4])[0]
            if length < _HEADER_SIZE:
                del self._receive_buffer[:2]
                continue
            if len(self._receive_buffer) < length:
                break
            frame = bytes(self._receive_buffer[:length])
            del self._receive_buffer[:length]
            decoded = self._decode_packet(frame)
            if decoded is not None:
                packets.append(decoded)
        return packets

    def _receive(self, timeout: float, idle_timeout: float = 0.5) -> list[dict[str, Any]]:
        if self._socket is None:
            raise OrviboBinaryError("ORVIBO binary socket is not connected")
        deadline = time.monotonic() + timeout
        last_data: float | None = None
        packets: list[dict[str, Any]] = []

        while time.monotonic() < deadline:
            if last_data is not None and time.monotonic() - last_data >= idle_timeout:
                break
            wait = min(0.25, max(0.0, deadline - time.monotonic()))
            readable, _, _ = select.select([self._socket], [], [], wait)
            if not readable:
                continue
            data = self._socket.recv(65536)
            if not data:
                break
            last_data = time.monotonic()
            self._receive_buffer.extend(data)
            packets.extend(self._extract_frames())
        return packets

    def _handshake(self) -> list[dict[str, Any]]:
        payload = self._base_payload(0)
        payload.update(
            {
                "source": "ZhiJia365",
                "softwareVersion": "50206302",
                "sysVersion": "Android14_34",
                "hardwareVersion": "HomeAssistant",
                "language": "zh",
                "identifier": self._identifier,
                "phoneName": "Home Assistant",
            }
        )
        self._send(payload, dynamic=False)
        packets = self._receive(timeout=10, idle_timeout=1)
        response = next(
            (packet for packet in packets if packet.get("cmd") == 0 and packet.get("key")),
            None,
        )
        if response is None:
            commands = [packet.get("cmd") for packet in packets]
            raise OrviboBinaryError(
                "ORVIBO binary handshake did not return a key "
                f"(packets={len(packets)}, commands={commands})"
            )
        self._dynamic_key = str(response["key"]).encode("utf-8")[:16]
        if len(self._dynamic_key) != 16:
            raise OrviboBinaryError("ORVIBO binary handshake returned an invalid key")
        session_id = response.get("sessionId")
        if isinstance(session_id, str) and session_id:
            self._session_id = session_id.ljust(32, "0")[:32]
        return packets

    def _login(self) -> list[dict[str, Any]]:
        payload = self._base_payload(2)
        payload.update(
            {
                "userName": self._email,
                "password": self._password_md5,
                "familyId": self._family_id,
                "type": 4,
                "needAccountDetailError": True,
            }
        )
        self._send(payload)
        packets = self._receive(timeout=10, idle_timeout=1)
        response = next((packet for packet in packets if packet.get("cmd") == 2), None)
        if response is None:
            commands = [packet.get("cmd") for packet in packets]
            raise OrviboBinaryError(
                "ORVIBO binary login did not return a response "
                f"(packets={len(packets)}, commands={commands})"
            )
        if response.get("status") not in (None, 0, "0"):
            raise OrviboBinaryError(
                "ORVIBO binary login was rejected "
                f"(status={response.get('status')!r})"
            )
        return packets

    def _device_page_payload(self, page_index: int) -> dict[str, Any]:
        """Build the read-only device table request used by ZhiJia365."""

        payload = self._base_payload(147)
        payload.update(
            {
                "familyId": self._family_id,
                "pageIndex": page_index,
                "dataType": "all",
            }
        )
        if page_index:
            # Zero requests a complete table snapshot rather than an incremental sync.
            payload["lastUpdateTime"] = 0
        return payload

    def _query_device_page(self, page_index: int) -> list[dict[str, Any]]:
        self._send(self._device_page_payload(page_index))
        return self._receive(timeout=10, idle_timeout=2)

    def _query_online_status(self) -> list[dict[str, Any]]:
        payload = self._base_payload(230)
        payload["familyId"] = self._family_id
        self._send(payload)
        return self._receive(timeout=8, idle_timeout=2)

    def _control_payload(
        self,
        device_id: str,
        device_uid: str,
        order: str,
        value1: int,
        value2: int = 0,
        value3: int = 0,
        value4: int = 0,
    ) -> dict[str, Any]:
        """Build the cmd=15 payload used by the current app for device control."""

        payload = self._base_payload(15)
        payload.update(
            {
                "uid": device_uid,
                "userName": self._email,
                "deviceId": device_id,
                "groupId": "",
                "order": order,
                "value1": value1,
                "value2": value2,
                "value3": value3,
                "value4": value4,
                "delayTime": 0,
                "qualityOfService": 1,
                "defaultResponse": 1,
                "propertyResponse": 0,
            }
        )
        return payload

    def _query_devices(self) -> list[dict[str, Any]]:
        """Download the complete paginated device table and online state."""

        packets: list[dict[str, Any]] = []
        seen_device_ids: set[str] = set()

        for page_index in range(_MAX_DEVICE_PAGES):
            page_packets = self._query_device_page(page_index)
            packets.extend(page_packets)

            page_device_ids = {
                device.uid for device in extract_devices(page_packets)
            }
            new_device_ids = page_device_ids - seen_device_ids
            seen_device_ids.update(page_device_ids)

            if page_index == 0:
                # The app requests host status between table metadata and page one.
                packets.extend(self._query_online_status())
                continue
            if not page_packets or not new_device_ids:
                break

        return packets


def discover_devices(
    host: str,
    email: str,
    password_md5: str,
    family_id: str,
) -> tuple[OrviboDevice, ...]:
    """Executor-friendly entry point for ORVIBO device discovery."""

    return OrviboBinaryClient(host, email, password_md5, family_id).discover()


def control_device(
    host: str,
    email: str,
    password_md5: str,
    family_id: str,
    device_id: str,
    device_uid: str,
    order: str,
    value1: int,
    value2: int = 0,
    value3: int = 0,
    value4: int = 0,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Send one device command through ORVIBO's mutual-TLS cloud socket."""

    return OrviboBinaryClient(
        host,
        email,
        password_md5,
        family_id,
    ).control_device(
        device_id,
        device_uid,
        order,
        value1,
        value2,
        value3,
        value4,
    )
