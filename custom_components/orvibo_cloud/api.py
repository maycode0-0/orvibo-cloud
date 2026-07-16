"""Async client for the Orvibo cloud REST API."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import secrets
import time
from typing import Any, Final, Mapping, Sequence

import aiohttp

from .const import ORVIBO_HOSTS
from .protocol import (
    OrviboDevice,
    OrviboFamily,
    build_family_request,
    extract_devices,
    parse_families,
)

_LOGGER = logging.getLogger(__name__)

_OAUTH_PATH: Final = "/getOauthToken"
_FAMILIES_PATH: Final = "/v2/family/statistics/users"
_PRIVACY_DEVICES_PATH: Final = "/v2/privacyDevice/statistics/users"
_REQUEST_TIMEOUT: Final = aiohttp.ClientTimeout(total=15)


class OrviboCloudError(Exception):
    """Base class for Orvibo cloud failures."""


class OrviboCannotConnectError(OrviboCloudError):
    """Raised when no Orvibo endpoint can be reached."""


class OrviboInvalidAuthError(OrviboCloudError):
    """Raised when Orvibo rejects the credentials or token."""


class OrviboProtocolError(OrviboCloudError):
    """Raised when Orvibo returns an unsupported response."""


@dataclass(frozen=True, slots=True)
class OrviboAccount:
    """Authenticated Orvibo account state."""

    host: str
    user_id: str
    access_token: str
    families: tuple[OrviboFamily, ...]
    devices: tuple[OrviboDevice, ...] = ()
    privacy_device_discovery_error: str | None = None


def _is_success(payload: Mapping[str, Any]) -> bool:
    status = payload.get("status", payload.get("code", 0))
    return status in (None, 0, "0", 200, "200")


def merge_devices(
    *device_groups: Sequence[OrviboDevice],
) -> tuple[OrviboDevice, ...]:
    """Merge device sources without discarding richer metadata."""

    merged: dict[str, OrviboDevice] = {}
    for devices in device_groups:
        for candidate in devices:
            previous = merged.get(candidate.uid)
            if previous is None:
                merged[candidate.uid] = candidate
                continue
            merged[candidate.uid] = OrviboDevice(
                uid=candidate.uid,
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
    return tuple(sorted(merged.values(), key=lambda device: device.uid))


class OrviboCloudClient:
    """Authenticate with Orvibo and retrieve account metadata."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str | None = None,
    ) -> None:
        self._session = session
        self._host = host

    async def async_discover(
        self,
        email: str,
        password_md5: str,
        hosts: Sequence[str] = ORVIBO_HOSTS,
    ) -> OrviboAccount:
        """Authenticate against regional hosts and return the first valid account."""

        candidates = (self._host,) if self._host else tuple(hosts)
        auth_rejected = False
        connection_failed = False

        for host in candidates:
            if not host:
                continue
            try:
                token, user_id = await self._async_oauth(host, email, password_md5)
                families = await self._async_families(host, token, user_id)
            except OrviboInvalidAuthError:
                auth_rejected = True
                continue
            except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError) as err:
                connection_failed = True
                # ClientResponseError may contain the OAuth URL and password hash.
                _LOGGER.debug("Orvibo host %s failed with %s", host, type(err).__name__)
                continue

            privacy_device_error: str | None = None
            try:
                devices = await self._async_privacy_devices(host, token, user_id)
            except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError) as err:
                devices = ()
                privacy_device_error = type(err).__name__
            except OrviboProtocolError as err:
                devices = ()
                privacy_device_error = str(err)

            return OrviboAccount(
                host=host,
                user_id=user_id,
                access_token=token,
                families=families,
                devices=devices,
                privacy_device_discovery_error=privacy_device_error,
            )

        if auth_rejected:
            raise OrviboInvalidAuthError("Orvibo rejected the account credentials")
        if connection_failed:
            raise OrviboCannotConnectError("Could not connect to an Orvibo cloud host")
        raise OrviboProtocolError("No Orvibo cloud hosts were configured")

    async def _async_oauth(
        self,
        host: str,
        email: str,
        password_md5: str,
    ) -> tuple[str, str]:
        params = {"userName": email, "type": "0", "password": password_md5}
        async with self._session.get(
            f"https://{host}{_OAUTH_PATH}",
            params=params,
            timeout=_REQUEST_TIMEOUT,
        ) as response:
            if response.status in (400, 401, 403):
                await response.read()
                raise OrviboInvalidAuthError("OAuth login failed")
            response.raise_for_status()
            payload = await response.json(content_type=None)

        if not isinstance(payload, Mapping) or not _is_success(payload):
            raise OrviboInvalidAuthError("OAuth login failed")

        data = payload.get("data", payload)
        if not isinstance(data, Mapping):
            raise OrviboProtocolError("OAuth response did not contain an object")
        token = str(data.get("access_token") or data.get("accessToken") or "").strip()
        user_id = str(data.get("user_id") or data.get("userId") or "").strip()
        if not token or not user_id:
            raise OrviboInvalidAuthError("OAuth response did not contain account tokens")
        return token, user_id

    async def _async_families(
        self,
        host: str,
        access_token: str,
        user_id: str,
    ) -> tuple[OrviboFamily, ...]:
        body = build_family_request(
            access_token=access_token,
            user_id=user_id,
            timestamp_ms=int(time.time() * 1000),
            nonce=secrets.randbelow(900000) + 100000,
        )
        async with self._session.post(
            f"https://{host}{_FAMILIES_PATH}",
            json=body,
            timeout=_REQUEST_TIMEOUT,
        ) as response:
            if response.status in (401, 403):
                await response.read()
                raise OrviboInvalidAuthError("Orvibo rejected the OAuth token")
            response.raise_for_status()
            payload = await response.json(content_type=None)

        if not isinstance(payload, Mapping):
            raise OrviboProtocolError("Family response did not contain an object")
        if not _is_success(payload):
            raise OrviboInvalidAuthError("Orvibo rejected the OAuth token")
        return parse_families(payload)

    async def _async_privacy_devices(
        self,
        host: str,
        access_token: str,
        user_id: str,
    ) -> tuple[OrviboDevice, ...]:
        """Fetch privacy devices using the endpoint in the current ZhiJia365 app."""

        body = build_family_request(
            access_token=access_token,
            user_id=user_id,
            timestamp_ms=int(time.time() * 1000),
            nonce=secrets.randbelow(900000) + 100000,
        )
        async with self._session.post(
            f"https://{host}{_PRIVACY_DEVICES_PATH}",
            json=body,
            timeout=_REQUEST_TIMEOUT,
        ) as response:
            if response.status in (401, 403):
                await response.read()
                raise OrviboProtocolError(
                    "Privacy-device endpoint rejected the OAuth token"
                )
            response.raise_for_status()
            payload = await response.json(content_type=None)

        if not isinstance(payload, Mapping):
            raise OrviboProtocolError(
                "Privacy-device response did not contain an object"
            )
        if not _is_success(payload):
            status = payload.get("status", payload.get("code"))
            raise OrviboProtocolError(
                f"Privacy-device request failed (status={status!r})"
            )

        devices = extract_devices(payload)
        _LOGGER.debug(
            "ORVIBO privacy-device REST discovery returned %d devices, keys=%s",
            len(devices),
            sorted(payload.keys()),
        )
        return devices
