"""Deterministic document selection from numeric conditions.

The corpus triggers are thresholds (``wind_mean_kt >= 18``, ``current_kt >= 0.5``, ...). Embedding
similarity cannot evaluate a threshold, so document choice is plain code; vectors are used only for
free-form questions. A test asserts every corpus document has a rule here, so adding a document
without a rule fails loudly instead of being silently never selected.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields

VENUE_PORT_OF_LA = "port_of_la"

# Order = priority (highest first). Tiers follow 00_README "Priority order". TS-09 and TS-11 are not
# placed by the index; the placement below (waves with the wind-type docs, procedure last) is an assumption.
PRIORITY: tuple[tuple[str, int], ...] = (
    ("TS-03", 1),  # safety
    ("TS-05", 1),  # safety
    ("TS-10", 2),  # venue playbook
    ("TS-06", 3),  # current
    ("TS-04", 4),  # wind-type
    ("TS-07", 4),
    ("TS-08", 4),
    ("TS-09", 4),  # assumption: not placed by the index
    ("TS-02", 5),  # defaults
    ("TS-01", 5),
    ("TS-11", 6),  # assumption: procedure, always last
)


@dataclass(frozen=True)
class Conditions:
    """Inputs for the trigger rules. ``None`` = not provided (never silently treated as 0)."""

    venue: str | None = VENUE_PORT_OF_LA
    wind_mean_kt: float | None = None
    gust_kt: float | None = None
    wind_rise_kt_2h: float | None = None
    precipitation_mm_h: float | None = None
    cloud_cover_pct: float | None = None
    cloud_cover_change_pct_h: float | None = None
    squall_line_forecast: bool | None = None
    current_kt: float | None = None
    tide_change_during_race: bool | None = None
    land_sea_temp_diff_c: float | None = None
    gradient_wind_kt: float | None = None
    wind_from_land: bool | None = None
    terrain_height_m_upwind: float | None = None
    wave_height_m: float | None = None
    swell_direction_diff_deg: float | None = None

    @classmethod
    def from_dict(cls, data: dict) -> Conditions:
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:  # a typo like "wind_kt" must not silently become "no wind info"
            raise ValueError(f"unknown condition keys: {unknown}; valid keys: {sorted(known)}")
        return cls(**data)

    def missing(self) -> tuple[str, ...]:
        return tuple(f.name for f in fields(self) if f.name != "venue" and getattr(self, f.name) is None)


@dataclass(frozen=True)
class Selection:
    doc_ids: tuple[str, ...]  # priority order, highest first
    reasons: dict[str, str]
    missing: tuple[str, ...]
    tiers: dict[str, int]


def _ge(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def _rule_ts03(c: Conditions) -> str | None:
    if _ge(c.wind_mean_kt, 18):
        return f"mean wind {c.wind_mean_kt:g} kt >= 18"
    if _ge(c.gust_kt, 24):
        return f"gusts {c.gust_kt:g} kt >= 24"
    if _ge(c.wind_rise_kt_2h, 6):
        return f"wind rising {c.wind_rise_kt_2h:g} kt within 2 h (prepare early)"
    return None


def _rule_ts02(c: Conditions) -> str | None:
    # Corpus says 8-17 kt; TS-03 starts at 18, so a mean of 17.5 would match neither. Close the gap: [8, 18).
    if c.wind_mean_kt is None or not 8 <= c.wind_mean_kt < 18:
        return None
    if c.gust_kt is not None and c.gust_kt - c.wind_mean_kt >= 6:
        return None
    if (c.precipitation_mm_h is not None and c.precipitation_mm_h > 0.5) or _ge(c.current_kt, 0.5):
        return None
    return f"steady {c.wind_mean_kt:g} kt, no rain, current < 0.5 kt"


def _rule_ts04(c: Conditions) -> str | None:
    if c.wind_mean_kt is not None and c.wind_mean_kt < 8:
        return f"mean wind {c.wind_mean_kt:g} kt < 8"
    return None


def _rule_ts05(c: Conditions) -> str | None:
    if c.precipitation_mm_h is not None and c.precipitation_mm_h > 0.5:
        return f"precipitation {c.precipitation_mm_h:g} mm/h > 0.5"
    if _ge(c.cloud_cover_change_pct_h, 20):
        return f"cloud cover changing {c.cloud_cover_change_pct_h:g} %/h >= 20"
    if c.squall_line_forecast:
        return "squall line forecast"
    return None


def _rule_ts06(c: Conditions) -> str | None:
    if _ge(c.current_kt, 0.5):
        return f"current {c.current_kt:g} kt >= 0.5"
    if c.tide_change_during_race:
        return "tide changes during the race window"
    return None


def _rule_ts07(c: Conditions) -> str | None:
    if (
        c.cloud_cover_pct is not None
        and c.cloud_cover_pct < 40
        and _ge(c.land_sea_temp_diff_c, 5)
        and c.gradient_wind_kt is not None
        and c.gradient_wind_kt < 12
    ):
        return f"clear ({c.cloud_cover_pct:g} % cloud), land {c.land_sea_temp_diff_c:g} C warmer, light gradient"
    return None


def _rule_ts08(c: Conditions) -> str | None:
    if c.wind_from_land:
        return "wind blowing off the land"
    if _ge(c.terrain_height_m_upwind, 50):
        return f"terrain {c.terrain_height_m_upwind:g} m high upwind"
    return None


def _rule_ts09(c: Conditions) -> str | None:
    if _ge(c.wave_height_m, 1.0):
        return f"wave height {c.wave_height_m:g} m >= 1.0"
    if _ge(c.swell_direction_diff_deg, 30):
        return f"swell {c.swell_direction_diff_deg:g} deg off the wind >= 30"
    return None


def _always(reason: str) -> Callable[[Conditions], str | None]:
    return lambda _c: reason


def _rule_ts10(c: Conditions) -> str | None:
    return "venue is Port of LA" if c.venue == VENUE_PORT_OF_LA else None


RULES: dict[str, Callable[[Conditions], str | None]] = {
    "TS-01": _always("default, every day"),
    "TS-02": _rule_ts02,
    "TS-03": _rule_ts03,
    "TS-04": _rule_ts04,
    "TS-05": _rule_ts05,
    "TS-06": _rule_ts06,
    "TS-07": _rule_ts07,
    "TS-08": _rule_ts08,
    "TS-09": _rule_ts09,
    "TS-10": _rule_ts10,
    "TS-11": _always("every race day"),
}


def select_documents(conditions: Conditions) -> Selection:
    reasons: dict[str, str] = {}
    tiers: dict[str, int] = {}
    ordered: list[str] = []
    for doc_id, tier in PRIORITY:
        reason = RULES[doc_id](conditions)
        if reason is not None:
            reasons[doc_id] = reason
            tiers[doc_id] = tier
            ordered.append(doc_id)
    return Selection(tuple(ordered), reasons, conditions.missing(), tiers)
