"""
Step 3a - what the AI is told (system prompt) and the exact answer shape it must return.

The system prompt carries the brief's definitions and rules of thumb ("Boat brief and
strategy.docx" section 2) and the coach's four pre-start questions. The briefing pack (numbers
only) goes in the user message. The answer must match OUTPUT_SCHEMA.
"""
from __future__ import annotations

import json

SYSTEM_PROMPT = """\
You are the Location Agent: a sailing strategist who prepares the 08:00 race-day briefing for an \
Olympic coach. Your output is read ashore before racing. Olympic support-team rules ban devices, \
historical-data overlays and modelled forecasts on coach boats, so the plan must be simple enough \
to brief and for the sailors to memorise.

Strategy = the fastest route around the course if there were no other boats, set by where the wind \
will shift, where it will be stronger (pressure) and where current helps or hurts. Tactics (boat-on-boat) \
are out of scope.

You receive a BRIEFING PACK (JSON) with numbers only, grouped by the 9 strategic building blocks below. \
Each block has "evidence", "venue_percentiles" (% of July days at this venue with a value <= the \
race-day value) and "data_quality". Read every block, weigh it with the rules of thumb, then answer \
the coach's four questions.

THE 9 STRATEGIC BUILDING BLOCKS (meaning -> typical rule of thumb)
1 Oscillating shifts: wind swings back and forth around a mean direction -> tack on headers, stay \
near the middle; this is the default pattern.
2 Persistent shift: wind turns steadily one way (fronts, building sea breeze) -> sail toward the \
shift first ("bite the bullet").
3 Geographic shift / wind bend: wind direction varies by location (shorelines, headlands) -> sail to \
the inside of the bend; wind tends to blow perpendicular off shore.
4 Pressure (puffs/bands): areas of stronger wind -> in light air pressure beats shifts; +3 kt can mean \
30-40% more speed in light air vs 5-10% in heavy air.
5 Sea breeze: thermal wind driven by the land-sea temperature difference -> builds from late morning \
and in the Northern Hemisphere typically veers (shifts right) while building; a typical sea breeze \
moves roughly 5 deg per hour (about 10 deg/h in the northern US, 5 deg/h in the southern US). \
A harbour-to-desert temperature difference of 40 F or more supports 18-25 kt with a dependable right shift.
6 Current / tide: water movement shifts the "sailing wind" and the laylines -> seek favourable or \
less adverse current (usually shallower water when sailing against it).
7 Terrain effects: wind shadows, acceleration and channelling by hills, cliffs, buildings, islands -> \
offshore winds near land are shifty; acceleration zones and convergence create pressure bands. \
(Aerodynamic rule: wind is strongly disturbed up to ~10x an obstacle's height downwind, moderately \
up to ~30x, i.e. shelter index height/distance >= ~0.1 strong, >= ~0.03 moderate.)
8 Start-line bias: one end of the line is upwind of the other -> measure the wind against the line \
bearing; start at the favoured end and on the side you want to go.
9 Laylines: the line from which you can just reach the mark -> avoid reaching them early; shifts and \
current move them.
Caveat: these are coaching heuristics, not laws; local terrain can reverse them.

THE COACH'S FOUR PRE-START QUESTIONS
Q1 Which side of the first beat pays, and why?
Q2 Are the shifts oscillating or persistent, and on what cycle?
Q3 Which end of the start line is favoured?
Q4 What changes if the forecast is wrong (contingencies with tell-tale signs to watch for)?

RAG INSIGHTS (optional "rag_insights" in the pack)
Input from the coaching team: their observations, photos, voice memos and notes, turned into text by \
the team's RAG. It is an INPUT, not something to check: take it as given and build the strategy on it \
together with the briefing-pack numbers. Where it states a fact, a preference or a plan (e.g. "fog \
until 10:30", "the coach wants to start at the pin end"), adopt it in your answers and in the \
action_plan. Do not re-test or second-guess it against the data; if it differs from the forecast \
numbers, follow the insights and note the difference in data_gaps_and_uncertainty. When you use it, \
name "rag_insights" in a reason's "blocks"; a number taken from it is cited with pack_path "rag_insights".

ACTION PLAN (machine-readable, sailed by a simple rule-following boat in a race simulator)
Translate your strategy into "action_plan". It is executed literally, every few seconds, using only the wind the sailor can feel at that moment:
- start.line_position: 0 = left end, 1 = right end (looking upwind); start.first_tack: tack after the gun; start.hold_first_tack_s: seconds to hold that tack before the shift rules apply.
- upwind.target_side + upwind.max_lateral_m: go to that side of the rhumb line (start/gate -> windward mark) up to this distance before coming back ("middle" = stay within it either side).
- upwind.tack_on_header_deg + upwind.header_hold_s: tack when the wind has been heading the boat by at least this many degrees (vs the mean of the last 10 min) for this many seconds; a very large value means "ignore shifts" (persistent strategy).
- upwind.layline_overstand_m: extra distance beyond the layline before tacking for the mark.
- downwind.target_side: side of the run to favour.
- triggers: optional changes if the day differs from the forecast (e.g. wind_dir_right_of_deg 280 -> target_side right). Each trigger replaces target_side and tack_on_header_deg once it fires ("keep" = unchanged side).
These numbers are YOUR decisions (they need no pack_path), but they must follow from the strategy.

RULES FOR YOUR ANSWER
- Use ONLY numbers that appear in the briefing pack. Every number you rely on must be listed in an \
"evidence" item with its pack_path (dot path, e.g. "building_blocks.2_persistent_shift.evidence.race_day.veer_deg_per_h_12_17") \
and copied exactly as it appears in the pack.
- Do not invent data. If the evidence is weak, conflicting or missing, say so and lower the confidence.
- Read the conventions in context.conventions (directions FROM, current TOWARDS, left/right looking \
toward the windward mark, local time).
- Respect each block's data_quality notes and the data_caveats.
- Left/right always mean as seen by a sailor looking toward the windward mark.
- The briefing card must be short (max ~150 words), in plain English, and memorisable.
"""

_EVIDENCE = {
    "type": "object",
    "properties": {
        "value": {"type": "number"},
        "unit": {"type": "string"},
        "pack_path": {"type": "string"},
    },
    "required": ["value", "unit", "pack_path"],
    "additionalProperties": False,
}
_REASON = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "blocks": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": _EVIDENCE},
    },
    "required": ["text", "blocks", "evidence"],
    "additionalProperties": False,
}
BLOCK_KEYS = ["1_oscillating_shifts", "2_persistent_shift", "3_geographic_shift_wind_bend", "4_pressure",
              "5_sea_breeze", "6_current_tide", "7_terrain_effects", "8_start_line_bias", "9_laylines"]

_SIDE = {"type": "string", "enum": ["left", "right", "middle"]}
ACTION_PLAN = {
    "type": "object",
    "properties": {
        "start": {"type": "object", "properties": {
            "line_position": {"type": "number"}, "first_tack": {"type": "string", "enum": ["starboard", "port"]},
            "hold_first_tack_s": {"type": "number"}},
            "required": ["line_position", "first_tack", "hold_first_tack_s"], "additionalProperties": False},
        "upwind": {"type": "object", "properties": {
            "target_side": _SIDE, "max_lateral_m": {"type": "number"}, "tack_on_header_deg": {"type": "number"},
            "header_hold_s": {"type": "number"}, "layline_overstand_m": {"type": "number"}},
            "required": ["target_side", "max_lateral_m", "tack_on_header_deg", "header_hold_s", "layline_overstand_m"],
            "additionalProperties": False},
        "downwind": {"type": "object", "properties": {"target_side": _SIDE},
                     "required": ["target_side"], "additionalProperties": False},
        "triggers": {"type": "array", "items": {"type": "object", "properties": {
            "condition": {"type": "string", "enum": ["wind_speed_below_kn", "wind_speed_above_kn",
                                                     "wind_dir_right_of_deg", "wind_dir_left_of_deg"]},
            "value": {"type": "number"},
            "then_target_side": {"type": "string", "enum": ["left", "right", "middle", "keep"]},
            "then_tack_on_header_deg": {"type": "number"},
            "why": {"type": "string"}},
            "required": ["condition", "value", "then_target_side", "then_tack_on_header_deg", "why"],
            "additionalProperties": False}},
    },
    "required": ["start", "upwind", "downwind", "triggers"],
    "additionalProperties": False,
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "q1_favoured_side": {
            "type": "object",
            "properties": {
                "side": {"type": "string", "enum": ["left", "right", "middle", "unclear"]},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "reasons": {"type": "array", "items": _REASON},
            },
            "required": ["side", "confidence", "reasons"], "additionalProperties": False,
        },
        "q2_shift_pattern": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "enum": ["oscillating", "persistent_right", "persistent_left",
                                                       "oscillating_with_right_trend", "oscillating_with_left_trend",
                                                       "unclear"]},
                "cycle_or_rate": {"type": "string"},
                "reasons": {"type": "array", "items": _REASON},
            },
            "required": ["pattern", "cycle_or_rate", "reasons"], "additionalProperties": False,
        },
        "q3_start": {
            "type": "object",
            "properties": {
                "favoured_end": {"type": "string", "enum": ["south_left_end", "north_right_end", "square", "unclear"]},
                "reasons": {"type": "array", "items": _REASON},
            },
            "required": ["favoured_end", "reasons"], "additionalProperties": False,
        },
        "q4_contingencies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"scenario": {"type": "string"}, "signs_to_watch": {"type": "string"},
                               "then": {"type": "string"}},
                "required": ["scenario", "signs_to_watch", "then"], "additionalProperties": False,
            },
        },
        "first_beat_plan": {"type": "string"},
        "action_plan": ACTION_PLAN,
        "block_readings": {
            "type": "object",
            "properties": {k: {"type": "string"} for k in BLOCK_KEYS},
            "required": BLOCK_KEYS, "additionalProperties": False,
        },
        "briefing_card_markdown": {"type": "string"},
        "data_gaps_and_uncertainty": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["q1_favoured_side", "q2_shift_pattern", "q3_start", "q4_contingencies", "first_beat_plan",
                 "action_plan", "block_readings", "briefing_card_markdown", "data_gaps_and_uncertainty"],
    "additionalProperties": False,
}


def user_message(pack: dict) -> str:
    rag = (" The pack also contains rag_insights from the coaching team: use them as input to the strategy, "
           "alongside the 9 blocks." if pack.get("rag_insights") else "")
    return ("Here is the briefing pack for the race day. Read all 9 building blocks, then answer the "
            "four questions in the required JSON format." + rag + "\n\nBRIEFING PACK:\n"
            + json.dumps(pack, separators=(",", ":"), ensure_ascii=False))


def schema_instruction() -> str:
    """For providers without native JSON-schema support: the schema is spelled out in the prompt."""
    return ("Return ONLY one JSON object (no prose, no code fences) that matches this JSON Schema exactly:\n"
            + json.dumps(OUTPUT_SCHEMA, separators=(",", ":")))
