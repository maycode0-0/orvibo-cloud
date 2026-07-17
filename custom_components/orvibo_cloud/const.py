"""Constants for the Orvibo Cloud integration."""

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "orvibo_cloud"

CONF_FAMILY_ID: Final = "family_id"
CONF_HOST: Final = "host"
CONF_PASSWORD_HASH: Final = "password_hash"
CONF_USER_ID: Final = "user_id"

DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=30)

ORVIBO_HOSTS: Final = (
    "china.orvibo.com",
    "homemate.orvibo.com",
    "germany.orvibo.com",
    "usa.orvibo.com",
)

PLATFORMS: Final = (
    Platform.BINARY_SENSOR,
    Platform.COVER,
    Platform.LIGHT,
    Platform.SENSOR,
)
