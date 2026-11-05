"""Strategy engine: pure functions over the June 2021-2026 data.

Demo story (same as src/conditions_June_2026): June 2021-2025 is history,
June 2026 is replayed hour by hour as if live.
"""

import json
from pathlib import Path

import pandas as pd

DATA = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "src"
    / "conditions_June_2026"
    / "data"
    / "raw"
)
HISTORY_YEARS = range(2021, 2026)
LIVE_YEAR = 2026

COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
SECTORS = ["S", "SSW", "SW", "WSW", "W"]  # the onshore sectors that matter here
TIME_OF_DAY = {"Morning": 11, "Midday": 13, "Late day": 15}
SEA_BREEZE_KT = 6.0  # speed that counts as "breeze is in" for this venue

VENUES = {
    "Port of LA · San Pedro (LA 2028)": {
        "lat": 33.712, "lon": -118.272, "area": "la_outer_harbor",
        "classes": ["ILCA 7", "ILCA 6", "49er", "49erFX", "470 mixed", "Nacra 17"],
    },
    "Long Beach · Belmont Shore (LA 2028)": {
        "lat": 33.748, "lon": -118.140, "area": "belmont_shore",
        "classes": ["iQFoil men", "iQFoil women", "Formula Kite men", "Formula Kite women"],
    },
}

# ---------- small helpers ----------

def sector(degrees):
    return COMPASS[round(degrees / 22.5) % 16]


def sector_center(name):
    return COMPASS.index(name) * 22.5


def angle_diff(a, b):
    """Signed change from a to b in degrees, -180..180 (positive = veer/right)."""
    return (b - a + 180) % 360 - 180


# ---------- loading ----------

def load_wind(years, point="racecourse_belmont"):
    frames = []
    for year in years:
        path = DATA / "open_meteo" / f"{point}_{year}06.json"
        if path.exists():
            frames.append(pd.DataFrame(json.loads(path.read_text())["hourly"]))
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"])
    df = df.rename(columns={"wind_speed_10m": "speed", "wind_direction_10m": "dir",
                            "wind_gusts_10m": "gust", "cloud_cover": "cloud"})
    df["date"] = df["time"].dt.date
    df["hour"] = df["time"].dt.hour
    return df.dropna(subset=["speed", "dir"])


def load_tides(years=range(2021, 2027)):
    frames = []
    for year in years:
        path = DATA / "noaa_coops" / f"9410660_predictions_{year}06.csv"
        if path.exists():
            frames.append(pd.read_csv(path, skipinitialspace=True))
    df = pd.concat(frames, ignore_index=True)
    df.columns = [column.strip() for column in df.columns]
    # NOAA file is GMT; June in LA is PDT (UTC-7).
    df["time"] = pd.to_datetime(df["Date Time"]) - pd.Timedelta(hours=7)
    return df[["time", "Type"]].sort_values("time").reset_index(drop=True)


# ---------- venue map ----------

def tide_state(tides, when):
    """Flood (rising) or ebb (falling) at a local time, plus when it turns."""
    before = tides[tides["time"] <= when].tail(1)
    after = tides[tides["time"] > when].head(1)
    if before.empty or after.empty:
        return {"state": "Unknown", "turns": None}
    state = "Flood" if before["Type"].iloc[0] == "L" else "Ebb"
    return {"state": state, "turns": after["time"].iloc[0]}


def venue_insight(history, wind_sector, hour):
    """Statistics for days that had this wind sector at this hour."""
    at_hour = history[history["hour"] == hour]
    match_days = set(at_hour.loc[at_hour["dir"].map(sector) == wind_sector, "date"])
    days = history[history["date"].isin(match_days)]
    n_days = len(match_days)
    total_days = history["date"].nunique()
    if n_days == 0:
        return {"n_days": 0, "total_days": total_days, "sector": wind_sector, "hour": hour}

    pivot_dir = days.pivot_table(index="date", columns="hour", values="dir")
    pivot_speed = days.pivot_table(index="date", columns="hour", values="speed")
    start, end = max(hour - 2, 0), min(hour + 2, 23)
    veer_per_day = pivot_dir.apply(
        lambda row: angle_diff(row[start], row[end]) / (end - start), axis=1)
    veer_rate = float(veer_per_day.median())
    hourly_steps = pivot_dir.loc[:, start:end].T.diff().iloc[1:]
    swing = float(hourly_steps.apply(lambda col: col.map(lambda x: abs(angle_diff(0, x)))).median().median())

    speeds = pivot_speed[hour]
    onset = pivot_speed.loc[:, 9:17].apply(
        lambda row: next((h for h, v in row.items() if v >= SEA_BREEZE_KT), None), axis=1).dropna()

    if veer_rate > 1.5:
        side, shift = "Right", "Persistent right"
    elif veer_rate < -1.5:
        side, shift = "Left", "Persistent left"
    else:
        side, shift = "Middle", "Oscillating"
    kept_turning = int(((veer_per_day > 0) if side != "Left" else (veer_per_day < 0)).sum())

    return {
        "sector": wind_sector,
        "hour": hour,
        "n_days": n_days,
        "total_days": total_days,
        "speed": float(speeds.median()),
        "speed_low": float(speeds.quantile(0.25)),
        "speed_high": float(speeds.quantile(0.75)),
        "gust": float(days[days["hour"] == hour]["gust"].median()),
        "veer_rate": veer_rate,
        "swing": swing,
        "side": side,
        "shift": shift,
        "kept_turning": kept_turning,
        "onset_hour": int(onset.median()) if len(onset) else None,
        "late_onset_days": int((onset > 12).sum()),
        "light_days": int((speeds < 6).sum()),
    }


# ---------- briefing ----------

def briefing(insight, tide, venue_class):
    """The four pre-start answers plus the Challenger findings."""
    side = insight["side"]
    rate = insight["veer_rate"]
    onset = insight["onset_hour"]
    onset_text = f"{onset}:00" if onset is not None else "not reliably"
    favoured = {
        "Right": "Right, towards the breakwater: the sea breeze veers right as it builds.",
        "Left": "Left, towards the Palos Verdes shore: the breeze backs left through the day.",
        "Middle": "Neither side is reliable: stay central and sail the shifts.",
    }[side]
    if side == "Middle":
        shift = f"Oscillating, about ±{insight['swing']:.0f}° hour to hour, no clear trend."
    else:
        shift = (f"{insight['shift']} of ~{abs(rate):.0f}°/h, with "
                 f"~{insight['swing']:.0f}° swings between hours.")
    start = {
        "Right": "Committee-boat end, so you can tack onto port early and head right.",
        "Left": "Pin end, to lead the fleet out to the left.",
        "Middle": "Middle of the line with a clear lane; keep options open.",
    }[side]
    plan_b = (f"If the breeze is late (< {SEA_BREEZE_KT:.0f} kt by {onset_text}): "
              "stay in the middle and play the oscillations.")

    challenger = []
    if side != "Middle":
        against = insight["n_days"] - insight["kept_turning"]
        challenger.append((
            f"On {against} of the {insight['n_days']} similar days the wind did not keep turning "
            f"{side.lower()}.", "Covered by plan B" if against < insight["n_days"] / 2 else "Plan at risk"))
    if insight["late_onset_days"]:
        challenger.append((
            f"Breeze arrived after 12:00 on {insight['late_onset_days']} of those days.",
            "Check on the water before start"))
    if insight["light_days"]:
        challenger.append((
            f"Under 6 kt at {insight['hour']}:00 on {insight['light_days']} of those days — "
            f"{venue_class} goes into light-air mode.", "Add light-air setup"))
    challenger.append((
        "Model wind is one grid cell for the whole harbour; it can miss local shifts by the breakwater.",
        "Verify with coach-boat log"))

    agreement = insight["kept_turning"] / insight["n_days"] if side != "Middle" else 0.5
    if insight["n_days"] >= 20 and agreement >= 0.7:
        confidence = "High"
    elif insight["n_days"] >= 8 and agreement >= 0.55:
        confidence = "Medium-high"
    elif insight["n_days"] >= 4:
        confidence = "Medium"
    else:
        confidence = "Low"

    return {
        "cards": {
            "Wind": f"{insight['sector']} {insight['speed_low']:.0f}–{insight['speed_high']:.0f} kt",
            "Sea breeze": f"In by ~{onset_text}",
            "Current": f"{tide['state']}" + (f" until {tide['turns']:%H:%M}" if tide["turns"] is not None else ""),
        },
        "questions": [
            ("Which side pays, and why?", favoured),
            ("Oscillating or persistent shifts?", shift),
            ("Where to start?", start + " Check line bias on the water."),
            ("Plan B – what if the forecast is wrong?", plan_b),
        ],
        "challenger": challenger,
        "confidence": confidence,
    }


# ---------- live ----------

def live_check(plan_sector, plan_low, plan_high, now, upcoming):
    """Compare one live hour (and the next 2 h) with the briefing.

    Returns a status, a coach message and, when the change is >= 1 h away,
    an organisation warning.
    """
    planned = sector_center(plan_sector)

    def off_plan(row):
        direction_off = abs(angle_diff(planned, row["dir"])) > 33.75  # more than 1.5 sectors
        speed_off = row["speed"] < plan_low - 3 or row["speed"] > plan_high + 4
        return direction_off or speed_off

    if off_plan(now):
        turn = angle_diff(planned, now["dir"])
        if now["speed"] < plan_low - 3:
            message = (f"Breeze is only {now['speed']:.0f} kt — below plan. "
                       "Switch to plan B: stay central and play the oscillations.")
        elif now["speed"] > plan_high + 4:
            message = (f"{now['speed']:.0f} kt, well above plan. "
                       "Depower and favour the side with flatter water.")
        else:
            message = (f"Wind is {sector(now['dir'])}, {abs(turn):.0f}° "
                       f"{'right' if turn > 0 else 'left'} of the briefing. "
                       f"New strategy: favour the {'right' if turn > 0 else 'left'}.")
        return {"status": "Change", "message": message, "warning": None}

    ahead = [row for row in upcoming if off_plan(row)]
    if ahead:
        first = ahead[0]
        return {
            "status": "Change coming",
            "message": (f"On plan now, but {sector(first['dir'])} {first['speed']:.0f} kt "
                        f"expected at {first['time']:%H:%M}. Prepare plan B."),
            "warning": (f"Organisation warning: conditions leave the briefing window at "
                        f"{first['time']:%H:%M} (≥ 1 h notice)."),
        }
    trend = angle_diff(planned, now["dir"])
    return {
        "status": "Plan holds",
        "message": (f"{sector(now['dir'])} {now['speed']:.0f} kt, "
                    f"{'veering right' if trend > 0 else 'backing left' if trend < 0 else 'steady'} "
                    "within the plan. Keep going."),
        "warning": None,
    }


def sky(cloud):
    if cloud < 20:
        return "Clear"
    if cloud < 60:
        return "Partly cloudy"
    if cloud < 90:
        return "Mostly cloudy"
    return "Overcast"
