"""Turns what the dashboard knows into the inputs of the AI layer. The only place that mapping lives.

``Conditions`` (``backend.rag.triggers``) already has the right semantics: ``None`` means "not provided" and is
never treated as 0. So there is no second snapshot type; this module only fills it from the UI.
"""

from __future__ import annotations

from collections.abc import Mapping

from backend.rag.triggers import Conditions


def conditions_from_insight(insight: Mapping) -> Conditions:
    """From ``strategy.venue_insight``: the median wind and gust (kt) of past days with this wind sector at this hour.

    Only those two are known to the dashboard. Everything else stays ``None`` so the brief says "not provided"
    instead of guessing, and the document selection skips the rules that need it.
    """
    if not insight.get("n_days"):
        return Conditions()
    return Conditions(wind_mean_kt=round(float(insight["speed"]), 1), gust_kt=round(float(insight["gust"]), 1))


def context_text(state: Mapping) -> str:
    """The dashboard selection as plain text for the model. Numbers the user chose are allowed in answers."""
    parts = [
        ("venue", state.get("venue")),
        ("boat class", state.get("boat_class")),
        ("race day", state.get("race_day")),
        ("wind sector", state.get("wind_sector")),
        ("hour (local)", state.get("map_hour")),
    ]
    return "Dashboard selection: " + "; ".join(f"{k}: {v}" for k, v in parts if v is not None)


def conditions_from_pack(pack: Mapping) -> Conditions:
    """From a Location Agent briefing pack: the race-window mean wind and gust (kt) of its race-day forecast.

    A backtest pack only holds what was known on the race morning, so this adds no hindsight to the RAG text
    built from it. Everything the pack does not state stays ``None``.
    """
    day = pack["building_blocks"]["4_pressure"]["evidence"]["race_day"]
    mean = day.get("race_window_speed_kn_mean")
    if mean is None:
        return Conditions()
    extra = day.get("gust_minus_mean_kn")
    return Conditions(wind_mean_kt=round(float(mean), 1),
                      gust_kt=None if extra is None else round(float(mean) + float(extra), 1))
