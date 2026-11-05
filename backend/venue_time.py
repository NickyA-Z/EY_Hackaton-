"""Venue clock: turn source timestamps into Los Angeles local wall-clock time.

Why this exists: Open-Meteo labels its hourly `time` with ONE fixed offset for the
whole response (`utc_offset_seconds`). For our June files it is -28800 (GMT-8),
apparently the offset valid when the data was downloaded (November), although LA
is on PDT (GMT-7) in June. Reading those labels as local time puts every value
one hour early. NOAA files are GMT. Both are converted here with the real
America/Los_Angeles rules, so wind, tides and the map share one clock.
"""
import pandas as pd

VENUE_TZ = "America/Los_Angeles"


def utc_to_local(times) -> pd.Series:
    """Naive UTC/GMT timestamps -> naive LA local time (DST-aware)."""
    t = pd.to_datetime(pd.Series(times))
    return t.dt.tz_localize("UTC").dt.tz_convert(VENUE_TZ).dt.tz_localize(None)


def open_meteo_to_local(times, utc_offset_seconds) -> pd.Series:
    """Open-Meteo `hourly.time` labels + the response's offset -> naive LA local time."""
    t = pd.to_datetime(pd.Series(times))
    if utc_offset_seconds is None:          # no offset given: labels are already local
        return t
    return utc_to_local(t - pd.to_timedelta(int(utc_offset_seconds), unit="s"))


def open_meteo_to_local_labels(times, utc_offset_seconds) -> list[str]:
    """Same as open_meteo_to_local, formatted back to Open-Meteo's 'YYYY-MM-DDTHH:MM'."""
    return open_meteo_to_local(times, utc_offset_seconds).dt.strftime("%Y-%m-%dT%H:%M").tolist()
