"""Config flow for Garmin Latest Heart Rate."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, SOURCE_INTEGRATION


class GarminLatestHrConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Single confirm step; nothing to configure."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Garmin Latest Heart Rate", data={})
        garmin_loaded = bool(self.hass.config_entries.async_entries(SOURCE_INTEGRATION))
        return self.async_show_form(
            step_id="user",
            description_placeholders={
                "garmin_status": "detected" if garmin_loaded else "NOT detected - set up Garmin Connect first"
            },
        )
