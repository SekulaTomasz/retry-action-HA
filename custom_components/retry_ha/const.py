"""Constants for the Retry HA integration."""

DOMAIN = "retry_ha"
NAME = "Retry HA"

# Attributes
ATTR_ACTION = "action"
ATTR_SERVICE = "service"
ATTR_TARGET = "target"
ATTR_DATA = "data"
ATTR_RETRIES = "retries"
ATTR_DELAY = "delay"
ATTR_BACKOFF = "backoff"
ATTR_MAX_DELAY = "max_delay"
ATTR_EXPECTED_STATE = "expected_state"
ATTR_EXPECTED_STATE_TIMEOUT = "expected_state_timeout"
ATTR_ON_ERROR = "on_error"
ATTR_RAISE_ON_FAILURE = "raise_on_failure"
ATTR_CREATE_REPAIR = "create_repair"

# Services / Actions
SERVICE_CALL = "call"
SERVICE_ACTION = "action"

# Defaults
DEFAULT_RETRIES = 3
DEFAULT_DELAY = 1.0
DEFAULT_BACKOFF = 2.0
DEFAULT_MAX_DELAY = 60.0
DEFAULT_EXPECTED_STATE_TIMEOUT = 2.0
DEFAULT_RAISE_ON_FAILURE = False
DEFAULT_CREATE_REPAIR = False

# Options / Config keys
CONF_DEFAULT_RETRIES = "default_retries"
CONF_DEFAULT_DELAY = "default_delay"
CONF_DEFAULT_BACKOFF = "default_backoff"
CONF_DEFAULT_MAX_DELAY = "default_max_delay"
CONF_DEFAULT_RAISE_ON_FAILURE = "default_raise_on_failure"
