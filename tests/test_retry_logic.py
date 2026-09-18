"""Unit tests for Retry HA custom integration."""
import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock

# Create mock homeassistant modules so tests can run in environments without HA installed
if "homeassistant" not in sys.modules:
    ha_mod = types.ModuleType("homeassistant")
    ha_core = types.ModuleType("homeassistant.core")
    ha_exceptions = types.ModuleType("homeassistant.exceptions")
    ha_config_entries = types.ModuleType("homeassistant.config_entries")
    ha_data_entry_flow = types.ModuleType("homeassistant.data_entry_flow")
    ha_helpers = types.ModuleType("homeassistant.helpers")
    ha_helpers_cv = types.ModuleType("homeassistant.helpers.config_validation")
    ha_helpers_typing = types.ModuleType("homeassistant.helpers.typing")
    ha_helpers_script = types.ModuleType("homeassistant.helpers.script")
    ha_helpers_ir = types.ModuleType("homeassistant.helpers.issue_registry")

    class MockHomeAssistantError(Exception):
        pass

    class MockServiceValidationError(MockHomeAssistantError):
        pass

    class MockSupportsResponse:
        OPTIONAL = "optional"
        ONLY = "only"
        NONE = "none"

    ha_exceptions.HomeAssistantError = MockHomeAssistantError
    ha_exceptions.ServiceValidationError = MockServiceValidationError
    ha_core.HomeAssistantError = MockHomeAssistantError
    ha_core.ServiceValidationError = MockServiceValidationError
    ha_core.SupportsResponse = MockSupportsResponse
    ha_core.Context = MagicMock()
    ha_core.HomeAssistant = MagicMock
    ha_core.ServiceCall = MagicMock
    ha_core.ServiceResponse = dict
    ha_core.callback = lambda f: f

    class MockConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    class MockOptionsFlow:
        pass

    ha_config_entries.ConfigFlow = MockConfigFlow
    ha_config_entries.OptionsFlow = MockOptionsFlow
    ha_config_entries.ConfigEntry = MagicMock
    ha_data_entry_flow.FlowResult = dict

    ha_helpers_cv.string = str
    ha_helpers_cv.boolean = bool
    ha_helpers_cv.positive_int = int
    ha_helpers_typing.ConfigType = dict

    class MockScript:
        def __init__(self, hass, sequence, name, domain):
            self.hass = hass
            self.sequence = sequence
            self.name = name
            self.domain = domain
        async def async_run(self, run_variables=None, context=None):
            return None

    ha_helpers_script.Script = MockScript

    # Mock voluptuous if not present
    if "voluptuous" not in sys.modules:
        vol_mod = types.ModuleType("voluptuous")
        class MockSchema:
            def __init__(self, *args, **kwargs):
                pass
            def __call__(self, val):
                return val
        vol_mod.Schema = MockSchema
        vol_mod.Optional = lambda k, default=None: k
        vol_mod.Required = lambda k, default=None: k
        vol_mod.Any = lambda *args: args
        vol_mod.All = lambda *args: args
        vol_mod.Coerce = lambda t: t
        vol_mod.Range = lambda **kwargs: kwargs
        vol_mod.ALLOW_EXTRA = "ALLOW_EXTRA"
        sys.modules["voluptuous"] = vol_mod

    sys.modules["homeassistant"] = ha_mod
    sys.modules["homeassistant.core"] = ha_core
    sys.modules["homeassistant.exceptions"] = ha_exceptions
    sys.modules["homeassistant.config_entries"] = ha_config_entries
    sys.modules["homeassistant.data_entry_flow"] = ha_data_entry_flow
    sys.modules["homeassistant.helpers"] = ha_helpers
    sys.modules["homeassistant.helpers.config_validation"] = ha_helpers_cv
    sys.modules["homeassistant.helpers.typing"] = ha_helpers_typing
    sys.modules["homeassistant.helpers.script"] = ha_helpers_script
    sys.modules["homeassistant.helpers.issue_registry"] = ha_helpers_ir

from custom_components.retry_ha import (
    ExpectedStateError,
    _async_execute_retry,
    _async_verify_expected_state,
    _extract_entity_ids,
    _parse_actions,
)
from custom_components.retry_ha.const import (
    ATTR_ACTION,
    ATTR_DELAY,
    ATTR_EXPECTED_STATE,
    ATTR_ON_ERROR,
    ATTR_RAISE_ON_FAILURE,
    ATTR_RETRIES,
    ATTR_TARGET,
)


class TestRetryHA(unittest.IsolatedAsyncioTestCase):
    """Test suite for Retry HA integration logic."""

    def setUp(self):
        self.hass = MagicMock()
        self.hass.data = {}
        self.hass.config_entries.async_entries.return_value = []
        self.hass.services.async_services.return_value = {}

    def test_parse_actions_string(self):
        """Test parsing string action."""
        res = _parse_actions(
            "light.turn_on",
            {"entity_id": "light.kitchen"},
            {"brightness": 100},
        )
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["action"], "light.turn_on")
        self.assertEqual(res[0]["target"], {"entity_id": "light.kitchen"})
        self.assertEqual(res[0]["data"], {"brightness": 100})

    def test_parse_actions_dict(self):
        """Test parsing dictionary action with overrides."""
        res = _parse_actions(
            {
                "action": "switch.turn_on",
                "target": {"entity_id": "switch.plug"},
                "data": {"extra": 1},
            },
            {"entity_id": "light.fallback"},
            {"base": 2},
        )
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["action"], "switch.turn_on")
        self.assertEqual(res[0]["target"], {"entity_id": "switch.plug"})
        self.assertEqual(res[0]["data"], {"extra": 1, "base": 2})

    def test_parse_actions_list(self):
        """Test parsing action list."""
        actions = [
            "light.turn_off",
            {"action": "switch.turn_off", "target": {"entity_id": "switch.plug"}},
        ]
        res = _parse_actions(actions, {"entity_id": "light.all"}, {})
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["action"], "light.turn_off")
        self.assertEqual(res[0]["target"], {"entity_id": "light.all"})
        self.assertEqual(res[1]["action"], "switch.turn_off")
        self.assertEqual(res[1]["target"], {"entity_id": "switch.plug"})

    def test_extract_entity_ids(self):
        """Test entity_id extraction from target and data."""
        target = {"entity_id": ["light.living_room", "light.bedroom"]}
        data = {"entity_id": "light.hallway"}
        eids = _extract_entity_ids(target, data)
        self.assertIn("light.living_room", eids)
        self.assertIn("light.bedroom", eids)
        self.assertIn("light.hallway", eids)
        self.assertEqual(len(eids), 3)

    async def test_retry_success_first_try(self):
        """Test action that succeeds on first attempt."""
        self.hass.services.async_call = AsyncMock(return_value={"result": "ok"})

        call = MagicMock()
        call.data = {
            ATTR_ACTION: "light.turn_on",
            ATTR_TARGET: {"entity_id": "light.desk"},
            ATTR_RETRIES: 3,
            ATTR_DELAY: 0.01,
        }
        call.return_response = True
        call.context = None

        result = await _async_execute_retry(self.hass, call)
        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(self.hass.services.async_call.call_count, 1)

    async def test_retry_recovers_after_failures(self):
        """Test action that fails once then succeeds on attempt 2."""
        call_count = 0

        async def mock_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("Temporary network timeout")
            return {"status": "success"}

        self.hass.services.async_call = AsyncMock(side_effect=mock_call)

        call = MagicMock()
        call.data = {
            ATTR_ACTION: "switch.turn_on",
            ATTR_TARGET: {"entity_id": "switch.heater"},
            ATTR_RETRIES: 3,
            ATTR_DELAY: 0.01,
        }
        call.return_response = False
        call.context = None

        result = await _async_execute_retry(self.hass, call)
        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(call_count, 2)

    async def test_retry_exhausted_with_fallback(self):
        """Test action that exhausts all retries and runs on_error."""
        self.hass.services.async_call = AsyncMock(side_effect=RuntimeError("Device unreachable"))

        call = MagicMock()
        call.data = {
            ATTR_ACTION: "light.turn_on",
            ATTR_TARGET: {"entity_id": "light.garden"},
            ATTR_RETRIES: 2,
            ATTR_DELAY: 0.01,
            ATTR_RAISE_ON_FAILURE: False,
            ATTR_ON_ERROR: "notify.persistent_notification",
        }
        call.return_response = False
        call.context = None

        result = await _async_execute_retry(self.hass, call)
        self.assertFalse(result["success"])
        self.assertEqual(result["attempts"], 3)  # Initial try + 2 retries
        self.assertIn("Device unreachable", result["error"])

    async def test_expected_state_verification_success(self):
        """Test state verification succeeds when state reaches target."""
        state_obj = MagicMock()
        state_obj.state = "on"
        self.hass.states.get.return_value = state_obj

        # Should complete without error
        await _async_verify_expected_state(
            self.hass, ["light.test"], expected_state="on", timeout=0.1
        )

    async def test_expected_state_verification_timeout(self):
        """Test state verification raises ExpectedStateError when state doesn't match."""
        state_obj = MagicMock()
        state_obj.state = "off"
        self.hass.states.get.return_value = state_obj

        with self.assertRaises(ExpectedStateError):
            await _async_verify_expected_state(
                self.hass, ["light.test"], expected_state="on", timeout=0.05
            )


if __name__ == "__main__":
    unittest.main()
