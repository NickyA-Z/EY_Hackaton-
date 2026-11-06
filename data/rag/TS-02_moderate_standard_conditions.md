---
doc_id: TS-02
title: Strategy in moderate / standard conditions (no challenging weather)
doc_type: team_strategy
condition: moderate_standard
triggers: wind_mean_kt 8–17 AND gust_spread_kt < 6 AND no rain AND current_kt < 0.5
wind_range_kt: [8, 17]
synthetic: true
---

# TS-02 Moderate / standard conditions

> SYNTHETIC DATA for retrieval testing.

## Triggers
- Mean wind 8–17 kt, gusts less than 6 kt above mean.
- Dry, stable cloud cover (cloud cover change < 20% per hour).
- Current below 0.5 kt.

## Core idea
These are "fair" conditions: the whole fleet is fast, so **places are won with good starts and shift-playing**. Shifts are usually **oscillating** (5–12° swings, 3–8 min cycle). Pressure differences are small, so shifts matter more than pressure.

## Start
- Measure line bias. If bias ≥ 5°, start in the favoured third; otherwise start where the first shift sends you.
- Priority: a clean lane for the first 2 minutes. Being able to tack is worth more than being at the end.

## Upwind
- Play the shifts: tack on headers ≥ 5° from the median heading (median from the pre-start compass log).
- Sail on the lifted tack toward the next expected shift.
- Stay within the middle 60% of the course until the last third.

## Downwind
- Gybe on headers; stay in phase with the shifts.
- Keep clear air; avoid sailing in the wind shadow of the group behind.

## Boat handling
- Full power mode. Focus on smooth tacks: each tack costs ~1 boat length in these conditions.

## Coach actions
- Before the start: 15 minutes of compass readings to find the median and the cycle time.
- Tell sailors: "median is X°, cycle about Y min, left/right headers to watch".

## Plan B
If shifts become **persistent** (heading trend > 10° in 20 min one way), switch to TS-07 (sea breeze) or TS-08 (terrain) logic: sail toward the shift first.

## Past lessons (synthetic)
- Medemblik training block, Sept 2026: 70% of top-5 finishes came from boats that tacked within 30 s of a 5°+ header.
