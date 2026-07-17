"""Data update coordinator for Orvibo Cloud."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    OrviboAccount,
    OrviboCannotConnectError,
    OrviboCloudClient,
    OrviboInvalidAuthError,
    OrviboProtocolError,
)
from .const import (
    CONF_FAMILY_ID,
    CONF_HOST,
    CONF_PASSWORD_HASH,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class OrviboCloudCoordinator(DataUpdateCoordinator[OrviboAccount]):
    """Refresh the Orvibo access token and family metadata."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: OrviboCloudClient,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.entry = entry
        self.client = client
        self.device_discovery_error: str | None = None
        self.privacy_device_discovery_error: str | None = None

    async def _async_update_data(self) -> OrviboAccount:
        try:
            account = await self.client.async_discover(
                email=self.entry.data[CONF_EMAIL],
                password_md5=self.entry.data[CONF_PASSWORD_HASH],
                hosts=(self.entry.data[CONF_HOST],),
                family_id=self.entry.data[CONF_FAMILY_ID],
            )
        except OrviboInvalidAuthError as err:
            raise ConfigEntryAuthFailed from err
        except (OrviboCannotConnectError, OrviboProtocolError) as err:
            raise UpdateFailed(str(err)) from err

        self.device_discovery_error = None
        self.privacy_device_discovery_error = None
        return account
