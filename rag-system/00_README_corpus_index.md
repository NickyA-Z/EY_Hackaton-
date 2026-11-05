---
doc_id: TS-00
title: Team strategy corpus – index and retrieval guide
doc_type: index
synthetic: true
version: 0.1 (hackathon, Nov 2026)
---

# Team strategy corpus – index

> SYNTHETIC DATA. Written for the Location Agent hackathon to test retrieval. Not real Team Allianz / Watersportverbond material. All numbers are plausible but invented.

## How the agent should use this corpus

1. Read the day's conditions (forecast + hourly API data): mean wind, gusts, direction, rain / cloud cover, tide phase and current strength, wave height, air–water temperature difference.
2. Match each condition to the **Triggers** section of the documents below. Several documents can apply at once (e.g. strong wind + tide).
3. Always combine with **TS-01 Team strategy philosophy** (the default) and **TS-10 Venue playbook** for the chosen venue.
4. When documents conflict, follow the **Priority order** below. A higher-priority document overrides a lower one.
5. Output a briefing that answers the four pre-start questions: favoured side and why, shift type, start plan, plan B.

## Documents

| ID | Title | Use when (short) |
|---|---|---|
| TS-01 | Team strategy philosophy | Always (default) |
| TS-02 | Moderate / standard conditions | 8–17 kt, steady, no rain, current < 0.5 kt |
| TS-03 | Strong wind | Mean ≥ 18 kt or gusts ≥ 24 kt |
| TS-04 | Light wind | Mean < 8 kt |
| TS-05 | Rain, squalls and unstable cloud | Rain, cumulus / cloud cover changing, squall lines |
| TS-06 | Tide and current | Current ≥ 0.5 kt anywhere on the course |
| TS-07 | Sea-breeze days | Clear sky, land warmer than water by ≥ 5 °C, light gradient |
| TS-08 | Offshore and shifty wind (terrain) | Wind blowing off the land, hills or buildings upwind |
| TS-09 | Waves and swell | Significant wave height ≥ 1 m or swell crossing the wind |
| TS-10 | Venue playbook – Port of LA (San Pedro) | Racing or training at the LA 2028 venue |
| TS-11 | Pre-start routine and decision rules | Every race day |

## Priority order (when documents disagree)

1. Safety (TS-03 strong-wind safety rules, TS-05 squall rules)
2. Venue playbook (TS-10) – local knowledge beats general rules
3. Current (TS-06) – when current ≥ 1 kt it usually decides the side
4. Wind-type documents (TS-04, TS-07, TS-08)
5. Default documents (TS-02, TS-01)

## Common keys used in all documents

`condition`, `triggers`, `wind_range_kt`, `classes`, `favoured_side_rule`, `start_rule`, `plan_b`. Section headings are the same in every document so chunks line up: Triggers · Core idea · Start · Upwind · Downwind · Boat handling · Coach actions · Plan B · Past lessons.
