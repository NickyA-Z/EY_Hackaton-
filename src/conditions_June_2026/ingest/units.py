"""All unit conversions live here, so every parser converts the same way.

Parsers must call these helpers instead of multiplying by magic numbers.
"""
import pandas as pd

MS_TO_KN = 1.94384      # 1 m/s in knots
KMH_TO_KN = 0.539957    # 1 km/h in knots
MPH_TO_KN = 0.868976    # 1 mph in knots

# Unit label (as written in the source) -> factor to knots.
SPEED_TO_KN = {
    "kn": 1.0, "kt": 1.0, "kts": 1.0, "knots": 1.0,
    "m/s": MS_TO_KN, "mps": MS_TO_KN,
    "km/h": KMH_TO_KN, "kmh": KMH_TO_KN,
    "mph": MPH_TO_KN, "mp/h": MPH_TO_KN,
}


def speed_to_kn(values, unit: str):
    """Convert a scalar or Series of speeds from `unit` to knots."""
    key = unit.strip().lower()
    if key not in SPEED_TO_KN:
        raise ValueError(f"unknown speed unit: {unit!r}")
    return values * SPEED_TO_KN[key]


def ms_to_kn(values):
    return speed_to_kn(values, "m/s")


def temp_to_c(values, unit: str):
    """Convert temperature to degrees Celsius."""
    key = unit.strip().lower().replace("°", "").replace("deg", "")
    if key in ("c", "degc"):
        return values
    if key in ("f", "degf"):
        return (values - 32.0) * 5.0 / 9.0
    raise ValueError(f"unknown temperature unit: {unit!r}")


# METAR sky cover (oktas) -> percent, using the midpoint of each okta band.
SKY_COVER_PCT = {
    "SKC": 0.0, "CLR": 0.0, "NSC": 0.0,
    "FEW": 18.75,   # 1-2 oktas
    "SCT": 43.75,   # 3-4 oktas
    "BKN": 75.0,    # 5-7 oktas
    "OVC": 100.0,   # 8 oktas
    "VV": 100.0,    # sky obscured (vertical visibility)
}


def local_to_utc(naive_times, utc_offset_seconds: int) -> pd.Series:
    """Shift naive local timestamps by a fixed offset and mark them as UTC."""
    t = pd.to_datetime(pd.Series(naive_times))
    return (t - pd.Timedelta(seconds=utc_offset_seconds)).dt.tz_localize("UTC")
