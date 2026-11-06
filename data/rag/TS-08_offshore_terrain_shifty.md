---
doc_id: TS-08
title: Strategy in offshore and terrain-affected (shifty) wind
doc_type: team_strategy
condition: offshore_terrain
triggers: wind_from_land = true OR terrain_height_m_upwind >= 50 within 3 km
synthetic: true
---

# TS-08 Offshore and terrain-affected wind

> SYNTHETIC DATA for retrieval testing.

## Triggers
- Wind blows from the land onto the water (offshore wind).
- Hills, cliffs or tall buildings (≥ 50 m) within about 3 km upwind of the course.

## Core idea
Land makes the wind **gusty and shifty** (big shifts, 10–25°) and creates fixed patterns:
- **Wind shadow:** less wind behind hills/buildings, up to several times their height downwind.
- **Acceleration / funnelling:** more wind through valleys, gaps and around headlands.
- **Wind bend:** wind tends to bend to blow more perpendicular to the coastline; sail to the **inside of the bend**.
- Patterns are **geographic** (they repeat at the same places), so venue history (TS-10) is very useful here.

## Start
- Check if one end of the line sits in a shadow or acceleration zone.
- Start on the side that leads to the acceleration zone or the inside of the bend.

## Upwind
- Use the venue map: go to known acceleration zones; avoid known shadows.
- Expect big, quick shifts: tack on large headers; ignore small ones.

## Downwind
- Gusts come in "streaks" from the gaps between hills: gybe to stay in the streaks.

## Coach actions
- Before racing, sail the course to confirm the shadows and gusts on today's wind direction.
- Compare with the map from previous days with the same wind direction.

## Plan B
If the pattern does not match the venue map (wind direction differs by > 20° from the playbook case), fall back to TS-01: stay connected to the fleet.

## Past lessons (synthetic)
- Port of LA training, SW wind, March 2026: hills on the west side created a clear wind shadow on the left of course A; the left lost on every beat.
