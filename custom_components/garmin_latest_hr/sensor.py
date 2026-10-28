"""Latest heart-rate sample sensor for the HACS Garmin Connect integration.

Reads Garmin's dailyHeartRate endpoint through the live, already-authorized
client of the installed `garmin_connect` integration. No credentials are
stored, copied or refreshed here: the source integration keeps full ownership
of the session, including token rotation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event, EventStateChangedData
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import DAILY_HR_URL, DOMAIN, SOURCE_INTEGRATION, SYNC_SENSOR

_LOGGER = logging.getLogger(__name__)

SAFETY_INTERVAL = timedelta(hours=1)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor."""
    async_add_entities([GarminLatestHrSensor(hass, entry)], update_before_add=True)


class GarminLatestHrSensor(SensorEntity):
    """Most recent timestamped heart-rate sample of the day."""

    _attr_name = "Garmin latest heart rate"
    _attr_icon = "mdi:heart-pulse"
    _attr_native_unit_of_measurement = "bpm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_latest_hr"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"note": "no fetch yet"}

    async def async_added_to_hass(self) -> None:
        """Subscribe to the source integration's poll rhythm."""
        await self._async_fetch()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [SYNC_SENSOR], self._handle_source_sync
            )
        )
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._handle_safety_tick, SAFETY_INTERVAL
            )
        )

    async def _handle_source_sync(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Refresh when the Garmin integration reports a new cloud poll."""
        await self._async_fetch()
        self.async_write_ha_state()

    async def _handle_safety_tick(self, now: datetime) -> None:
        """Hourly fallback in case the sync sensor stalls."""
        await self._async_fetch()
        self.async_write_ha_state()

    def _get_client(self):
        """Return the live Garmin client of the source integration, if any."""
        for source_entry in self.hass.config_entries.async_entries(SOURCE_INTEGRATION):
            runtime_data = getattr(source_entry, "runtime_data", None)
            if runtime_data is None:
                continue
            candidates = [getattr(runtime_data, "core", None)]
            if hasattr(runtime_data, "__dict__"):
                candidates.extend(vars(runtime_data).values())
            for coordinator in candidates:
                client = getattr(coordinator, "client", None)
                if client is not None and hasattr(client, "_request") and hasattr(
                    client, "get_user_profile"
                ):
                    return client
        return None

    def _set_unknown(self, note: str) -> None:
        """Publish an honest unknown state with the reason attached."""
        self._attr_available = True
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "note": note,
            "source": "Garmin watch via Garmin Connect dailyHeartRate",
        }

    async def _async_fetch(self) -> None:
        """Fetch today's heart-rate samples and keep the latest valid one."""
        client = self._get_client()
        if client is None:
            self._attr_available = False
            self._attr_native_value = None
            self._attr_extra_state_attributes = {
                "note": "garmin_connect integration not loaded"
            }
            return
        try:
            profile = await client.get_user_profile()
            display_name = getattr(profile, "display_name", None)
            if not display_name:
                self._set_unknown("Garmin display name unavailable")
                return
            today = dt_util.now().date().isoformat()
            url = DAILY_HR_URL.format(display_name=quote(str(display_name), safe=""))
            data = await client._request("GET", url, params={"date": today})
        except Exception as err:  # noqa: BLE001 - never fake a value on failure
            _LOGGER.warning("Garmin latest HR fetch failed: %s", err)
            self._set_unknown(f"fetch error: {type(err).__name__}")
            return

        values = (data or {}).get("heartRateValues") or []
        samples = [
            (ts, bpm)
            for ts, bpm in values
            if isinstance(ts, (int, float)) and isinstance(bpm, (int, float)) and bpm
        ]
        if not samples:
            self._set_unknown("no heart-rate samples received today")
            self._attr_extra_state_attributes["samples_today"] = 0
            return

        ts_ms, bpm = max(samples, key=lambda pair: pair[0])
        sample_dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        age = datetime.now(timezone.utc) - sample_dt

        self._attr_available = True
        self._attr_native_value = int(bpm)
        self._attr_extra_state_attributes = {
            "sample_time_utc": sample_dt.isoformat(),
            "sample_age_minutes": round(age.total_seconds() / 60, 1),
            "samples_today": len(samples),
            "source": "Garmin watch via Garmin Connect dailyHeartRate",
            "timestamp_basis": "heartRateValues epoch milliseconds (GMT)",
            "rides_on": SYNC_SENSOR,
        }
