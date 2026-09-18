"""Retry HA - Custom integration for executing Home Assistant actions with retries and error handling."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

try:
    from homeassistant.core import SupportsResponse
except ImportError:
    SupportsResponse = None

from .const import (
    ATTR_ACTION,
    ATTR_BACKOFF,
    ATTR_CREATE_REPAIR,
    ATTR_DATA,
    ATTR_DELAY,
    ATTR_EXPECTED_STATE,
    ATTR_EXPECTED_STATE_TIMEOUT,
    ATTR_MAX_DELAY,
    ATTR_ON_ERROR,
    ATTR_RAISE_ON_FAILURE,
    ATTR_RETRIES,
    ATTR_SERVICE,
    ATTR_TARGET,
    CONF_DEFAULT_BACKOFF,
    CONF_DEFAULT_DELAY,
    CONF_DEFAULT_MAX_DELAY,
    CONF_DEFAULT_RAISE_ON_FAILURE,
    CONF_DEFAULT_RETRIES,
    DEFAULT_BACKOFF,
    DEFAULT_CREATE_REPAIR,
    DEFAULT_DELAY,
    DEFAULT_EXPECTED_STATE_TIMEOUT,
    DEFAULT_MAX_DELAY,
    DEFAULT_RAISE_ON_FAILURE,
    DEFAULT_RETRIES,
    DOMAIN,
    SERVICE_ACTION,
    SERVICE_CALL,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACTION): vol.Any(cv.string, dict, list),
        vol.Optional(ATTR_SERVICE): vol.Any(cv.string, dict, list),
        vol.Optional(ATTR_TARGET): vol.Any(dict, list, str),
        vol.Optional(ATTR_DATA): dict,
        vol.Optional(ATTR_RETRIES): cv.positive_int,
        vol.Optional(ATTR_DELAY): vol.Coerce(float),
        vol.Optional(ATTR_BACKOFF): vol.Coerce(float),
        vol.Optional(ATTR_MAX_DELAY): vol.Coerce(float),
        vol.Optional(ATTR_EXPECTED_STATE): vol.Any(cv.string, [cv.string]),
        vol.Optional(ATTR_EXPECTED_STATE_TIMEOUT): vol.Coerce(float),
        vol.Optional(ATTR_ON_ERROR): vol.Any(cv.string, dict, list),
        vol.Optional(ATTR_RAISE_ON_FAILURE): cv.boolean,
        vol.Optional(ATTR_CREATE_REPAIR): cv.boolean,
    },
    extra=vol.ALLOW_EXTRA,
)


class ExpectedStateError(HomeAssistantError):
    """Raised when an entity fails to reach the expected state within the timeout."""


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Retry HA via YAML configuration."""
    hass.data.setdefault(DOMAIN, {})
    _async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Retry HA from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    _async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the retry service/action endpoints."""
    if hass.services.has_service(DOMAIN, SERVICE_CALL):
        return

    async def async_handle_service(call: ServiceCall) -> ServiceResponse:
        return await _async_execute_retry(hass, call)

    kwargs: dict[str, Any] = {
        "schema": SERVICE_SCHEMA,
    }
    if SupportsResponse is not None:
        kwargs["supports_response"] = SupportsResponse.OPTIONAL

    hass.services.async_register(DOMAIN, SERVICE_CALL, async_handle_service, **kwargs)
    hass.services.async_register(DOMAIN, SERVICE_ACTION, async_handle_service, **kwargs)
    _LOGGER.debug("Registered services %s.%s and %s.%s", DOMAIN, SERVICE_CALL, DOMAIN, SERVICE_ACTION)


def _extract_entity_ids(target: Any, data: Any) -> list[str]:
    """Extract a list of entity_ids from target or data."""
    entity_ids: set[str] = set()

    def _collect(val: Any) -> None:
        if isinstance(val, str) and "." in val:
            entity_ids.add(val)
        elif isinstance(val, list):
            for item in val:
                _collect(item)
        elif isinstance(val, dict):
            if "entity_id" in val:
                _collect(val["entity_id"])

    _collect(target)
    _collect(data)
    return list(entity_ids)


async def _async_verify_expected_state(
    hass: HomeAssistant,
    entity_ids: list[str],
    expected_state: str | list[str],
    timeout: float,
) -> None:
    """Poll entities until all match the expected state or timeout expires."""
    if not entity_ids:
        return

    expected_states = (
        [expected_state]
        if isinstance(expected_state, str)
        else [str(s) for s in expected_state]
    )

    loop = asyncio.get_running_loop()
    start_time = loop.time()
    poll_interval = 0.2

    while True:
        mismatches: list[str] = []
        for eid in entity_ids:
            state_obj = hass.states.get(eid)
            cur = state_obj.state if state_obj else None
            if cur not in expected_states:
                mismatches.append(f"{eid} is '{cur}' (expected {expected_states})")

        if not mismatches:
            return

        elapsed = loop.time() - start_time
        if elapsed >= timeout:
            raise ExpectedStateError(
                f"State verification failed after {elapsed:.1f}s: {', '.join(mismatches)}"
            )

        sleep_time = min(poll_interval, timeout - elapsed)
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)


async def _async_call_single_action(
    hass: HomeAssistant,
    action_item: dict[str, Any],
    context: Context | None,
    return_response: bool,
) -> Any:
    """Execute a single Home Assistant service call."""
    act = action_item.get("action") or action_item.get("service")
    if not act or not isinstance(act, str) or "." not in act:
        raise ServiceValidationError(
            f"Invalid action format: '{act}'. Expected format 'domain.service' (e.g. 'light.turn_on')."
        )

    domain, service = act.split(".", 1)
    target = action_item.get("target") or None
    data = action_item.get("data") or {}

    # Check if the target service supports return_response
    call_return_response = False
    if return_response and SupportsResponse is not None:
        service_desc = hass.services.async_services().get(domain, {}).get(service)
        if service_desc is not None:
            supported = getattr(service_desc, "supports_response", None)
            if supported in (SupportsResponse.ONLY, SupportsResponse.OPTIONAL):
                call_return_response = True

    return await hass.services.async_call(
        domain=domain,
        service=service,
        service_data=data,
        blocking=True,
        target=target,
        context=context,
        return_response=call_return_response,
    )


async def _async_run_on_error(
    hass: HomeAssistant,
    on_error: Any,
    context: Context | None,
    last_error: Exception | None,
) -> None:
    """Execute fallback actions specified in on_error."""
    try:
        from homeassistant.helpers.script import Script

        if isinstance(on_error, (dict, str)):
            actions = [on_error]
        elif isinstance(on_error, list):
            actions = on_error
        else:
            _LOGGER.warning("Unsupported on_error type: %s", type(on_error))
            return

        script = Script(
            hass,
            actions,
            name=f"{DOMAIN}_on_error",
            domain=DOMAIN,
        )
        await script.async_run(
            run_variables={"error": str(last_error)},
            context=context,
        )
    except Exception as err:
        _LOGGER.error("Failed to execute on_error fallback action: %s", err, exc_info=True)


def _async_create_repair_issue(
    hass: HomeAssistant,
    action_name: str,
    attempts: int,
    error: Exception | None,
) -> None:
    """Create a persistent Home Assistant repair issue on failure."""
    try:
        from homeassistant.helpers import issue_registry as ir

        safe_action_id = action_name.replace(".", "_")
        issue_id = f"retry_failed_{safe_action_id}"
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="action_failed",
            translation_placeholders={
                "action": action_name,
                "attempts": str(attempts),
                "error": str(error),
            },
        )
    except Exception as err:
        _LOGGER.debug("Could not create repair issue: %s", err)


def _async_clear_repair_issue(hass: HomeAssistant, action_name: str) -> None:
    """Clear any active repair issue for this action on success."""
    try:
        from homeassistant.helpers import issue_registry as ir

        safe_action_id = action_name.replace(".", "_")
        issue_id = f"retry_failed_{safe_action_id}"
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    except Exception as err:
        _LOGGER.debug("Could not clear repair issue: %s", err)


def _parse_actions(
    raw_action: Any,
    default_target: Any,
    default_data: Any,
) -> list[dict[str, Any]]:
    """Parse action parameter into a standardized list of action dicts."""
    if isinstance(raw_action, str):
        return [{
            "action": raw_action,
            "target": default_target,
            "data": default_data or {},
        }]

    if isinstance(raw_action, dict):
        # Could be an action dict or service call dict
        act_name = raw_action.get("action") or raw_action.get("service")
        act_target = raw_action.get("target") or default_target
        act_data = {**(raw_action.get("data") or {}), **(default_data or {})}
        return [{
            "action": act_name,
            "target": act_target,
            "data": act_data,
        }]

    if isinstance(raw_action, list):
        parsed = []
        for item in raw_action:
            if isinstance(item, str):
                parsed.append({
                    "action": item,
                    "target": default_target,
                    "data": default_data or {},
                })
            elif isinstance(item, dict):
                act_name = item.get("action") or item.get("service")
                act_target = item.get("target") or default_target
                act_data = {**(item.get("data") or {}), **(default_data or {})}
                parsed.append({
                    "action": act_name,
                    "target": act_target,
                    "data": act_data,
                })
        return parsed

    raise ServiceValidationError(
        f"Unsupported action format: {type(raw_action)}. Must be string, dict, or list."
    )


async def _async_execute_retry(
    hass: HomeAssistant,
    call: ServiceCall,
) -> ServiceResponse:
    """Execute action with retry loop, backoff, state validation, and fallback."""
    call_data = call.data

    # Resolve default options from active config entry (if any)
    def_retries = DEFAULT_RETRIES
    def_delay = DEFAULT_DELAY
    def_backoff = DEFAULT_BACKOFF
    def_max_delay = DEFAULT_MAX_DELAY
    def_raise = DEFAULT_RAISE_ON_FAILURE

    entries = hass.config_entries.async_entries(DOMAIN)
    if entries and entries[0].options:
        opts = entries[0].options
        def_retries = opts.get(CONF_DEFAULT_RETRIES, def_retries)
        def_delay = opts.get(CONF_DEFAULT_DELAY, def_delay)
        def_backoff = opts.get(CONF_DEFAULT_BACKOFF, def_backoff)
        def_max_delay = opts.get(CONF_DEFAULT_MAX_DELAY, def_max_delay)
        def_raise = opts.get(CONF_DEFAULT_RAISE_ON_FAILURE, def_raise)

    # Extract parameters
    raw_action = call_data.get(ATTR_ACTION) or call_data.get(ATTR_SERVICE)
    if not raw_action:
        raise ServiceValidationError("Action or service parameter must be provided.")

    top_target = call_data.get(ATTR_TARGET)
    top_data = call_data.get(ATTR_DATA)

    retries: int = call_data.get(ATTR_RETRIES, def_retries)
    delay: float = call_data.get(ATTR_DELAY, def_delay)
    backoff: float = call_data.get(ATTR_BACKOFF, def_backoff)
    max_delay: float = call_data.get(ATTR_MAX_DELAY, def_max_delay)
    expected_state = call_data.get(ATTR_EXPECTED_STATE)
    expected_state_timeout: float = call_data.get(
        ATTR_EXPECTED_STATE_TIMEOUT, DEFAULT_EXPECTED_STATE_TIMEOUT
    )
    on_error = call_data.get(ATTR_ON_ERROR)
    raise_on_failure: bool = call_data.get(ATTR_RAISE_ON_FAILURE, def_raise)
    create_repair: bool = call_data.get(ATTR_CREATE_REPAIR, DEFAULT_CREATE_REPAIR)

    actions_to_run = _parse_actions(raw_action, top_target, top_data)
    main_action_name = actions_to_run[0].get("action") or "unknown_action"

    # Determine entities for state validation
    entity_ids: list[str] = []
    if expected_state is not None:
        for item in actions_to_run:
            entity_ids.extend(_extract_entity_ids(item.get("target"), item.get("data")))

    max_attempts = retries + 1
    current_delay = delay
    last_error: Exception | None = None
    attempts = 0
    responses: list[Any] = []

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        try:
            responses.clear()
            for action_item in actions_to_run:
                resp = await _async_call_single_action(
                    hass, action_item, call.context, call.return_response
                )
                responses.append(resp)

            if expected_state is not None and entity_ids:
                await _async_verify_expected_state(
                    hass, entity_ids, expected_state, expected_state_timeout
                )

            # Succeeded! Clear repair issue if enabled
            if create_repair:
                _async_clear_repair_issue(hass, main_action_name)

            _LOGGER.debug(
                "Action '%s' completed successfully on attempt %d/%d",
                main_action_name,
                attempt,
                max_attempts,
            )

            result_response = responses[0] if len(responses) == 1 else responses
            return {
                "success": True,
                "attempts": attempts,
                "response": result_response,
            }

        except Exception as err:
            last_error = err
            if attempt < max_attempts:
                _LOGGER.warning(
                    "Attempt %d/%d failed for '%s': %s. Retrying in %.2fs...",
                    attempt,
                    max_attempts,
                    main_action_name,
                    err,
                    current_delay,
                )
                await asyncio.sleep(current_delay)
                current_delay = min(current_delay * backoff, max_delay)
            else:
                _LOGGER.error(
                    "All %d attempts failed for '%s': %s",
                    max_attempts,
                    main_action_name,
                    err,
                )

    # All retry attempts exhausted
    if on_error:
        await _async_run_on_error(hass, on_error, call.context, last_error)

    if create_repair:
        _async_create_repair_issue(hass, main_action_name, attempts, last_error)

    if raise_on_failure:
        raise HomeAssistantError(
            f"Action '{main_action_name}' failed after {attempts} attempts: {last_error}"
        ) from last_error

    return {
        "success": False,
        "attempts": attempts,
        "error": str(last_error),
    }
