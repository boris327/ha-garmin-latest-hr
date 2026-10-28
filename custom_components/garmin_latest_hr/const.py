"""Constants for Garmin Latest Heart Rate."""

DOMAIN = "garmin_latest_hr"
SOURCE_INTEGRATION = "garmin_connect"
SYNC_SENSOR = "sensor.garmin_connect_last_synced"
DAILY_HR_URL = (
    "https://connect.garmin.com/gc-api/wellness-service/wellness/dailyHeartRate"
    "/{display_name}"
)
