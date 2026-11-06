---
doc_id: TS-07
title: Strategy on sea-breeze days
doc_type: team_strategy
condition: sea_breeze
triggers: cloud_cover_pct < 40 AND (land_temp_c - sea_temp_c) >= 5 AND gradient_wind_kt < 12
synthetic: true
---

# TS-07 Sea-breeze days

> SYNTHETIC DATA for retrieval testing.

## Triggers
- Sunny / few clouds (cloud cover < 40%).
- Land warmer than the sea by 5 °C or more.
- Light gradient (synoptic) wind under 12 kt that does not blow strongly against the sea breeze.

## Core idea
The sea breeze is a thermal wind: the land heats up, warm air rises, and cooler sea air flows in. It typically:
- **starts late morning** (often 11:00–13:00),
- **builds** through the early afternoon (peak about 14:00–17:00),
- **veers (turns right) as it builds** in the Northern Hemisphere, about 5° per hour,
- is often **stronger close to the shore** where the land heating is strongest.

This makes the shift **persistent**, not oscillating: sail toward the expected shift first.

## Start
- When the breeze is veering: start toward the **right/committee end** and get to the right early.
- Before the sea breeze is established: use TS-04 (light wind).

## Upwind
- Go toward the **persistent shift** (usually right) and toward the shore-side pressure.
- Do not over-stand: as the wind veers, the right layline moves.

## Downwind
- Stay in the pressure close to shore if it is stronger.

## Boat handling
- Waves build with the breeze; adapt mode as wind rises (see TS-09 if waves ≥ 1 m).

## Coach actions
- Watch the start of the breeze: temperature drop, cumulus over land, dark line coming from the sea.
- Give sailors: expected onset time, expected direction change per hour.

## Plan B
**Sea breeze late or does not come** (cloud over land, gradient wind against it): treat as light, oscillating wind (TS-04 / TS-02), stay in the middle.

## Past lessons (synthetic)
- Port of LA test event, July 2026: on 6 of 8 days the right side paid on the first beat after 13:00.
