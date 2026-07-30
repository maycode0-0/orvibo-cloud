"""Opt-in redacted capture of unsolicited ORVIBO cloud packets."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import logging
import re
import secrets
from threading import Event, Lock, Thread
from typing import Any, Final

from homeassistant.core import HomeAssistant

from .binary import OrviboBinaryClient, OrviboCaptureError
from .const import ORVIBO_LOCK_EVENT

_LOGGER = logging.getLogger(__name__)
_RECONNECT_DELAY_SECONDS: Final =5
_MAX_DEPTH: Final =6
_MAX_ITEMS: Final =50
_REDACTED: Final = "<redacted>"
_SAFE_FIELD_NAME: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_HEX_IDENTIFIER_KEY: Final = re.compile(r"^[A-Fa-f0-9]{12,64}$")
_SECRET_KEYS: Final = frozenset(
    {
        "accesstoken",
        "authorization",
        "dynamickey",
        "key",
        "password",
        "passwordmd5",
        "secret",
        "sessionid",
        "token",
    }
)
_IDENTIFIER_KEYS: Final = frozenset(
    {
        "account",
        "deviceid",
        "email",
        "familyid",
        "identifier",
        "mac",
        "parentuid",
        "phone",
        "uid",
        "userid",
        "username",
    }
)
_LOCK_COMMAND: Final =42
_LOCK_STATE_KEYS: Final = (
 "door_status",
 "handle",
 "reverse_lock",
 "clild_lock",
)
_SAFE_LOCK_VALUES: Final = frozenset(
 {"open", "closed", "up", "down", "on", "off", "locked", "unlocked"}
)


def _normalized_key(key: object) -> str:
    return "".join(
        character for character in str(key).casefold() if character.isalnum()
    )


def _fingerprint(value: object, salt: bytes) -> str:
    digest = hashlib.sha256(
        salt + str(value).encode("utf-8", errors="replace")
    ).hexdigest()
    return f"<id:{digest[:12]}>"


def _redacted_key(key: object, salt: bytes) -> str:
    text = str(key)
    if _SAFE_FIELD_NAME.fullmatch(text) and not _HEX_IDENTIFIER_KEY.fullmatch(text):
        return text
    return _fingerprint(text, salt)


def redact_packet(
    value: object,
    salt: bytes,
    *,
    key: object = "",
    depth: int =0,
) -> object:
    """Return a bounded packet copy without credentials or stable identifiers."""

    normalized_key = _normalized_key(key)
    if normalized_key in _SECRET_KEYS:
        return _REDACTED
    if normalized_key in _IDENTIFIER_KEYS and value is not None:
        return _fingerprint(value, salt)
    if depth >= _MAX_DEPTH:
        return "<max-depth>"
    if isinstance(value, Mapping):
        entries = list(value.items())
        result = {
            _redacted_key(child_key, salt): redact_packet(
                child_value,
                salt,
                key=child_key,
                depth=depth +1,
            )
            for child_key, child_value in entries[:_MAX_ITEMS]
        }
        if len(entries) > _MAX_ITEMS:
            result["<truncated>"] = len(entries) - _MAX_ITEMS
        return result
    if isinstance(value, (list, tuple)):
        result = [
            redact_packet(item, salt, key=key, depth=depth +1)
            for item in value[:_MAX_ITEMS]
        ]
        if len(value) > _MAX_ITEMS:
            result.append(f"<truncated:{len(value) - _MAX_ITEMS}>")
        return result
    if isinstance(value, str):
        return f"<string:length={len(value)}>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return f"<{type(value).__name__}>"


def parse_lock_event(packet: Mapping[str, Any]) -> dict[str, Any] | None:
    """Extract a safe, normalized lock event from an unsolicited cmd=42 packet."""

    if packet.get("cmd") != _LOCK_COMMAND:
        return None
    uid = packet.get("uid")
    properties = packet.get("properties")
    if not isinstance(uid, str) or not uid or not isinstance(properties, Mapping):
        return None

    states: dict[str, str] = {}
    for key in _LOCK_STATE_KEYS:
        value = properties.get(key)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in _SAFE_LOCK_VALUES:
                states[key] = normalized
    if not states:
        return None

    reverse_lock = states.get("reverse_lock")
    lock_state = (
        "locked"
        if reverse_lock in {"locked", "on"}
        else "unlocked"
        if reverse_lock in {"unlocked", "off"}
        else None
    )
    raw_door_state = states.get("door_status")
    door_state = (
        "open"
        if raw_door_state in {"open", "on"}
        else "closed"
        if raw_door_state in {"closed", "off"}
        else None
    )
    return {
        "uid": uid,
        "device_id": packet.get("deviceId") if isinstance(packet.get("deviceId"), str) else "",
        "door_state": door_state,
        "lock_state": lock_state,
        "states": states,
        "update_time": packet.get("updateTimeSec")
        if isinstance(packet.get("updateTimeSec"), int)
        else None,
    }


class OrviboRawEventCapture:
    """Own the background capture thread and its blocking cloud socket."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        email: str,
        password_md5: str,
        family_id: str,
        capture_raw_events: bool = False,
    ) -> None:
        self._hass = hass
        self._connection = (host, email, password_md5, family_id)
        self._capture_raw_events = capture_raw_events
        self._salt = secrets.token_bytes(32)
        self._stop_event = Event()
        self._socket_lock = Lock()
        self._client: OrviboBinaryClient | None = None
        self._thread: Thread | None = None
        self._last_lock_states: dict[str, tuple[object, ...]] = {}

    def start(self) -> None:
        """Start capturing without blocking Home Assistant's event loop."""

        if self._thread is not None:
            return
        self._thread = Thread(
            target=self._run,
            name="orvibo-raw-event-capture",
            daemon=True,
        )
        self._thread.start()
        if self._capture_raw_events:
            _LOGGER.warning(
                "ORVIBO redacted raw event capture is enabled; captured packet values "
                "will be written to the Home Assistant log"
            )

    async def async_stop(self) -> None:
        """Close the socket and wait for the capture thread to exit."""

        self._stop_event.set()
        with self._socket_lock:
            client = self._client
        if client is not None:
            client.close()
        thread = self._thread
        if thread is not None and thread.is_alive():
            await self._hass.async_add_executor_job(thread.join,5)
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            client = OrviboBinaryClient(*self._connection)
            with self._socket_lock:
                self._client = client
            try:
                client.capture_events(self._stop_event, self._capture)
            except OrviboCaptureError as err:
                if not self._stop_event.is_set():
                    _LOGGER.warning(
                        "ORVIBO raw event capture disconnected "
                        "(stage=%s, error=%s, detail=%s); "
                        "retrying in %s seconds",
                        err.stage,
                        err.error_type,
                        err.detail,
                        _RECONNECT_DELAY_SECONDS,
                    )
            except Exception as err: # noqa: BLE001 - keep the capture thread alive.
                if not self._stop_event.is_set():
                    _LOGGER.warning(
                        "ORVIBO raw event capture disconnected "
                        "(stage=internal, error=%s, detail=unexpected capture failure); "
                        "retrying in %s seconds",
                        type(err).__name__,
                        _RECONNECT_DELAY_SECONDS,
                    )
            finally:
                client.close()
                with self._socket_lock:
                    if self._client is client:
                        self._client = None
            self._stop_event.wait(_RECONNECT_DELAY_SECONDS)

    def _capture(self, packet: Mapping[str, Any]) -> None:
        lock_event = parse_lock_event(packet)
        if lock_event is not None:
            signature = (
                lock_event["uid"],
                lock_event["door_state"],
                lock_event["lock_state"],
                tuple(sorted(lock_event["states"].items())),
            )
            if signature != self._last_lock_states.get(lock_event["uid"]):
                self._last_lock_states[lock_event["uid"]] = signature
                self._hass.loop.call_soon_threadsafe(
                    self._hass.bus.async_fire,
                    ORVIBO_LOCK_EVENT,
                    lock_event,
                )
                _LOGGER.warning(
                    "ORVIBO lock event: uid=%s, door_state=%s, lock_state=%s, states=%s",
                    _fingerprint(lock_event["uid"], self._salt),
                    lock_event["door_state"],
                    lock_event["lock_state"],
                    lock_event["states"],
                )
        if self._capture_raw_events:
            redacted = redact_packet(packet, self._salt)
            _LOGGER.warning(
                "ORVIBO redacted raw event: %s",
                json.dumps(redacted, ensure_ascii=True, separators=(",", ":")),
            )
