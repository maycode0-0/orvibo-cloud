"""Pure helpers for the Orvibo REST protocol."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Any, Final, Mapping

_HMAC_SECRET: Final = "nQ45RjPtOws96jmH"


@dataclass(frozen=True, slots=True)
class OrviboFamily:
    """An Orvibo family returned by the cloud API."""

    family_id: str
    name: str


@dataclass(frozen=True, slots=True)
class OrviboDevice:
    """A normalized device returned by ORVIBO Cloud."""

    uid: str
    name: str
    model: str
    device_type: str
    room: str
    parent_uid: str
    online: bool | None
    cloud_uid: str = ""
    sub_device_type: str = ""
    value1: int | None = None
    value2: int | None = None
    value3: int | None = None
    value4: int | None = None


def password_hash(password: str) -> str:
    """Return the uppercase MD5 representation expected by Orvibo."""

    return hashlib.md5(password.encode("utf-8")).hexdigest().upper()  # noqa: S324


def _sign_request(body: Mapping[str, Any]) -> str:
    """Sign an ORVIBO REST request using the app's canonical format."""

    canonical = "&".join(f"{key}={body[key]}" for key in sorted(body))
    canonical = f"{canonical}&key={_HMAC_SECRET}"
    return hmac.new(
        _HMAC_SECRET.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()


def build_family_request(
    access_token: str,
    user_id: str,
    timestamp_ms: int,
    nonce: int,
) -> dict[str, str]:
    """Build and sign a family-list request."""

    body = {
        "accessToken": access_token,
        "userId": user_id,
        "timestamp": str(timestamp_ms),
        "random": str(nonce),
    }
    body["sign"] = _sign_request(body)
    return body


def build_readtable_request(
    access_token: str,
    user_id: str,
    family_id: str,
    session_id: str,
    timestamp_ms: int,
    serial: int,
    nonce: str,
    version: str,
) -> dict[str, Any]:
    """Build the full table snapshot request used by the current app."""

    body: dict[str, Any] = {
        "accessToken": access_token,
        "dataType": "all",
        "deviceFlag": 0,
        "familyId": family_id,
        "lastUpdateTime": 0,
        "pageIndex": 0,
        "random": nonce,
        "serial": serial,
        "sessionId": session_id,
        "timestamp": timestamp_ms,
        "userId": user_id,
        "userName": user_id,
        "ver": version,
    }
    body["sign"] = _sign_request(body)
    return body


def parse_families(payload: Mapping[str, Any]) -> tuple[OrviboFamily, ...]:
    """Normalize known family response shapes."""

    raw: Any = payload.get("data", [])
    if isinstance(raw, Mapping):
        raw = raw.get("families") or raw.get("familyList") or raw.get("list") or []
    if not isinstance(raw, list):
        return ()

    families: list[OrviboFamily] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        family_id = str(
            item.get("familyId") or item.get("family_id") or item.get("id") or ""
        ).strip()
        if not family_id or family_id in seen:
            continue
        seen.add(family_id)
        name = str(
            item.get("familyName") or item.get("family_name") or item.get("name") or family_id
        ).strip()
        families.append(OrviboFamily(family_id=family_id, name=name or family_id))
    return tuple(families)


def _first_text(item: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _parse_online(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "online", "connected"}:
            return True
        if normalized in {"0", "false", "offline", "disconnected"}:
            return False
    return None


def parse_readtable_devices(payload: Mapping[str, Any]) -> tuple[OrviboDevice, ...]:
    """Normalize the device table and join its room and online-state tables."""

    data = payload.get("data")
    if not isinstance(data, Mapping):
        return ()

    raw_rooms = data.get("room", [])
    room_names: dict[str, str] = {}
    if isinstance(raw_rooms, list):
        for item in raw_rooms:
            if not isinstance(item, Mapping) or item.get("delFlag") in (1, "1"):
                continue
            room_id = _first_text(item, ("roomId", "roomID"))
            room_name = _first_text(item, ("roomName",))
            if room_id and room_name:
                room_names[room_id] = room_name

    raw_statuses = data.get("deviceStatus", [])
    online_by_device: dict[str, bool | None] = {}
    values_by_device: dict[str, tuple[int | None, ...]] = {}
    if isinstance(raw_statuses, list):
        for item in raw_statuses:
            if not isinstance(item, Mapping) or item.get("delFlag") in (1, "1"):
                continue
            device_id = _first_text(item, ("deviceId", "deviceID"))
            if device_id:
                online_by_device[device_id] = _parse_online(item.get("online"))
                values: list[int | None] = []
                for key in ("value1", "value2", "value3", "value4"):
                    try:
                        values.append(int(item[key]))
                    except (KeyError, TypeError, ValueError):
                        values.append(None)
                values_by_device[device_id] = tuple(values)

    raw_devices = data.get("device", [])
    if not isinstance(raw_devices, list):
        return ()

    devices: dict[str, OrviboDevice] = {}
    for item in raw_devices:
        if not isinstance(item, Mapping) or item.get("delFlag") in (1, "1"):
            continue
        device_id = _first_text(
            item,
            ("deviceId", "deviceID", "deviceUid", "deviceUUID", "uid"),
        )
        if not device_id:
            continue
        room_id = _first_text(item, ("roomId", "roomID"))
        online = online_by_device.get(device_id)
        if device_id not in online_by_device:
            online = _parse_online(item.get("online"))
        values = values_by_device.get(device_id, (None, None, None, None))
        devices[device_id] = OrviboDevice(
            uid=device_id,
            name=_first_text(
                item,
                ("deviceName", "devName", "name", "nickName", "nickname"),
            ),
            model=_first_text(
                item,
                (
                    "model",
                    "modelName",
                    "modelId",
                    "modelID",
                    "productName",
                    "productId",
                    "productID",
                ),
            ),
            device_type=_first_text(
                item,
                ("deviceType", "devType", "type", "category", "deviceCategory"),
            ),
            room=_first_text(item, ("roomName", "room"))
            or room_names.get(room_id, ""),
            parent_uid=_first_text(
                item,
                ("parentUid", "parentId", "parentID", "gatewayUid", "hubUid"),
            ),
            online=online,
            cloud_uid=_first_text(item, ("uid",)),
            sub_device_type=_first_text(
                item,
                ("subDeviceType", "subDevType"),
            ),
            value1=values[0],
            value2=values[1],
            value3=values[2],
            value4=values[3],
        )

    return tuple(sorted(devices.values(), key=lambda device: device.uid))


def extract_devices(payloads: Any) -> tuple[OrviboDevice, ...]:
    """Recursively find and normalize devices in binary protocol payloads."""

    devices: dict[str, OrviboDevice] = {}
    room_names: dict[str, str] = {}
    id_keys = (
        "deviceId",
        "deviceID",
        "deviceUid",
        "deviceUUID",
        "deviceUuid",
        "uuid",
        "uid",
    )
    device_markers = (
        "uid",
        "extAddr",
        "deviceName",
        "devName",
        "deviceType",
        "devType",
        "model",
        "modelName",
        "productId",
        "productID",
    )

    def collect_room_names(value: Any) -> None:
        if isinstance(value, list):
            for child in value:
                collect_room_names(child)
            return
        if not isinstance(value, Mapping):
            return

        room_id = _first_text(value, ("roomId", "roomID"))
        room_name = _first_text(value, ("roomName",))
        if room_id and room_name:
            room_names[room_id] = room_name

        for child in value.values():
            if isinstance(child, (Mapping, list)):
                collect_room_names(child)

    collect_room_names(payloads)

    def visit(value: Any, table_name: str | None = None) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child, table_name)
            return
        if not isinstance(value, Mapping):
            return

        raw_table_name = value.get("tableName")
        if isinstance(raw_table_name, str) and raw_table_name.strip():
            table_name = raw_table_name.strip().lower().replace("_", "")
        is_device_table = table_name in (
            None,
            "device",
            "devices",
            "devicelist",
            "privacydevice",
            "privacydevices",
        )

        uid = _first_text(value, id_keys)
        is_device_row = any(value.get(key) not in (None, "") for key in device_markers)
        if len(uid) >= 6 and is_device_row and is_device_table:
            room_id = _first_text(value, ("roomId", "roomID"))
            candidate = OrviboDevice(
                uid=uid,
                name=_first_text(
                    value,
                    ("deviceName", "devName", "name", "nickName", "nickname"),
                ),
                model=_first_text(
                    value,
                    (
                        "model",
                        "modelName",
                        "modelId",
                        "modelID",
                        "productName",
                        "productId",
                        "productID",
                    ),
                ),
                device_type=_first_text(
                    value,
                    ("deviceType", "devType", "type", "category", "deviceCategory"),
                ),
                room=(
                    _first_text(value, ("roomName", "room"))
                    or room_names.get(room_id, "")
                ),
                parent_uid=_first_text(
                    value,
                    ("parentUid", "parentId", "parentID", "gatewayUid", "hubUid"),
                ),
                online=_parse_online(
                    next(
                        (
                            value[key]
                            for key in ("online", "isOnline", "connected")
                            if key in value
                        ),
                        None,
                    )
                ),
            )
            previous = devices.get(uid)
            if previous is None:
                devices[uid] = candidate
            else:
                devices[uid] = OrviboDevice(
                    uid=uid,
                    name=candidate.name or previous.name,
                    model=candidate.model or previous.model,
                    device_type=candidate.device_type or previous.device_type,
                    room=candidate.room or previous.room,
                    parent_uid=candidate.parent_uid or previous.parent_uid,
                    online=(
                        candidate.online
                        if candidate.online is not None
                        else previous.online
                    ),
                )

        for child in value.values():
            if isinstance(child, (Mapping, list)):
                visit(child, table_name)

    visit(payloads)
    return tuple(sorted(devices.values(), key=lambda device: device.uid))
