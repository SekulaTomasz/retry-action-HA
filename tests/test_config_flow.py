"""Unit tests for Retry HA config flow and options flow."""
import sys
import unittest
from unittest.mock import MagicMock

# Reuse Home Assistant mocks
import tests.test_retry_logic  # noqa: F401

from custom_components.retry_ha.config_flow import (
    RetryConfigFlow,
    RetryOptionsFlowHandler,
)
from custom_components.retry_ha.const import (
    CONF_DEFAULT_BACKOFF,
    CONF_DEFAULT_DELAY,
    CONF_DEFAULT_RETRIES,
    NAME,
)


class TestRetryHAConfigFlow(unittest.IsolatedAsyncioTestCase):
    """Test suite for config flow."""

    def setUp(self):
        self.flow = RetryConfigFlow()
        self.flow.hass = MagicMock()
        self.flow._async_current_entries = MagicMock(return_value=[])
        self.flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "user"})
        self.flow.async_create_entry = MagicMock(
            side_effect=lambda title, data: {"type": "create_entry", "title": title, "data": data}
        )
        self.flow.async_abort = MagicMock(
            side_effect=lambda reason: {"type": "abort", "reason": reason}
        )

    async def test_step_user_shows_form(self):
        """Test initial form displayed when no input provided."""
        res = await self.flow.async_step_user(user_input=None)
        self.assertEqual(res["type"], "form")
        self.assertEqual(res["step_id"], "user")

    async def test_step_user_creates_entry(self):
        """Test entry created when user confirms."""
        res = await self.flow.async_step_user(user_input={})
        self.assertEqual(res["type"], "create_entry")
        self.assertEqual(res["title"], NAME)

    async def test_step_user_aborts_if_exists(self):
        """Test single instance constraint."""
        self.flow._async_current_entries = MagicMock(return_value=["existing_entry"])
        res = await self.flow.async_step_user(user_input=None)
        self.assertEqual(res["type"], "abort")
        self.assertEqual(res["reason"], "single_instance_allowed")

    async def test_options_flow(self):
        """Test options flow handler saves custom default options."""
        entry = MagicMock()
        entry.options = {CONF_DEFAULT_RETRIES: 5, CONF_DEFAULT_DELAY: 2.0}
        handler = RetryOptionsFlowHandler(entry)
        handler.async_show_form = MagicMock(return_value={"type": "form", "step_id": "init"})
        handler.async_create_entry = MagicMock(
            side_effect=lambda title, data: {"type": "create_entry", "data": data}
        )

        # Initial view
        form_res = await handler.async_step_init(user_input=None)
        self.assertEqual(form_res["type"], "form")

        # Saving new values
        save_res = await handler.async_step_init(
            user_input={CONF_DEFAULT_RETRIES: 10, CONF_DEFAULT_DELAY: 3.0, CONF_DEFAULT_BACKOFF: 1.5}
        )
        self.assertEqual(save_res["type"], "create_entry")
        self.assertEqual(save_res["data"][CONF_DEFAULT_RETRIES], 10)


if __name__ == "__main__":
    unittest.main()
