"""Constants for the HQPlayer integration."""

from homeassistant.const import Platform

DOMAIN = "hqplayer"

DEFAULT_PORT = 4321
DEFAULT_SCAN_INTERVAL = 10  # seconds
DEFAULT_TIMEOUT = 5.0  # seconds

CONF_SCAN_INTERVAL = "scan_interval"
CONF_ALLOWED_FILTERS = "allowed_filters"

PLATFORMS: list[Platform] = [
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BUTTON,
]

# Volume limits (dB)
MIN_VOLUME_DB = -60.0
MAX_VOLUME_DB = 0.0
VOLUME_STEP_DB = 0.5
