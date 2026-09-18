"""Config flow and options flow for Retry HA integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_DEFAULT_BACKOFF,
    CONF_DEFAULT_DELAY,
    CONF_DEFAULT_MAX_DELAY,
    CONF_DEFAULT_RAISE_ON_FAILURE,
    CONF_DEFAULT_RETRIES,
    DEFAULT_BACKOFF,
    DEFAULT_DELAY,
    DEFAULT_MAX_DELAY,
    DEFAULT_RAISE_ON_FAILURE,
    DEFAULT_RETRIES,
    DOMAIN,
    NAME,
)


class RetryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Retry HA."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle initial user setup step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title=NAME, data=user_input)

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow handler for Retry HA."""
        return RetryOptionsFlowHandler(config_entry)


class RetryOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Retry HA options modification."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DEFAULT_RETRIES,
                    default=options.get(CONF_DEFAULT_RETRIES, DEFAULT_RETRIES),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
                vol.Optional(
                    CONF_DEFAULT_DELAY,
                    default=options.get(CONF_DEFAULT_DELAY, DEFAULT_DELAY),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=3600.0)),
                vol.Optional(
                    CONF_DEFAULT_BACKOFF,
                    default=options.get(CONF_DEFAULT_BACKOFF, DEFAULT_BACKOFF),
                ): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=10.0)),
                vol.Optional(
                    CONF_DEFAULT_MAX_DELAY,
                    default=options.get(CONF_DEFAULT_MAX_DELAY, DEFAULT_MAX_DELAY),
                ): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=3600.0)),
                vol.Optional(
                    CONF_DEFAULT_RAISE_ON_FAILURE,
                    default=options.get(
                        CONF_DEFAULT_RAISE_ON_FAILURE, DEFAULT_RAISE_ON_FAILURE
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
