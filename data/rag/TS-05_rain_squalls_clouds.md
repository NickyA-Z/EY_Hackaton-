---
doc_id: TS-05
title: Strategy with rain, squalls and unstable cloud
doc_type: team_strategy
condition: rain_unstable
triggers: precipitation_mm_h > 0.5 OR cloud_cover_change_pct_h >= 20 OR squall_line_forecast = true
safety_critical: true
synthetic: true
---

# TS-05 Rain, squalls and unstable cloud

> SYNTHETIC DATA for retrieval testing.

## Triggers
- Rain more than 0.5 mm/h, or clouds building/clearing fast (cloud cover changes ≥ 20% per hour).
- Squall line or thunderstorm in the forecast.

## Core idea
Rain clouds change the wind **locally and quickly**. Rules of thumb:
- **In front of an approaching cloud:** more wind, often a shift toward the cloud's direction of travel.
- **Under the rain:** often a sudden gust, then a lull after it passes.
- **Behind a big cloud:** light, shifty wind ("hole").
Shifts become **unpredictable and large (10–30°)**; venue history (TS-10) is less reliable on these days.

## Start
- Keep options open: start where you can tack freely.
- Watch the clouds upwind in the last 5 minutes; a cloud arriving at the start can change the favoured end.

## Upwind
- **Sail toward the leading edge of an approaching cloud** to get its extra pressure.
- Avoid sailing into the area right behind a cloud.
- Shorten the "commit" time: re-evaluate every 2–3 minutes.

## Downwind
- Use the gust in front of the cloud; gybe to stay in it.

## Boat handling
- Visibility drops in rain: know the compass course to the next mark.
- Be ready to depower fast in squalls (see TS-03).

## Coach actions
- Track clouds with radar before racing; give sailors the direction clouds are moving.
- **Safety:** lightning or squall line → follow race committee; inform the organisation at least 1 hour ahead when a squall line is forecast.

## Plan B
If shifts are too random to read, follow TS-01 rule 3: stay with the fleet and minimise risk.

## Past lessons (synthetic)
- Garda 2025, race 6: one cloud gave a 25° right shift and 8 kt extra; boats that saw it coming gained 15 places.
