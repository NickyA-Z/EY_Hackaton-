---
doc_id: TS-06
title: Strategy with tide and current
doc_type: team_strategy
condition: tide_current
triggers: current_kt >= 0.5 anywhere on course OR tide_change_during_race = true
synthetic: true
---

# TS-06 Tide and current

> SYNTHETIC DATA for retrieval testing.

## Triggers
- Current of 0.5 kt or more anywhere on the course.
- Tide turns (high/low water) during the race window.
- Current differs across the course (e.g. stronger in deep water than near shore).

## Core idea
Current moves the whole race course under the boats. It changes the **wind the boat feels**, the **laylines**, and the **time to each mark**. When current is ≥ 1 kt it usually decides the favoured side, more than wind shifts.

Rules of thumb:
- **Current against you (foul tide):** sail in **shallower water**, where current is weaker.
- **Current with you (fair tide):** sail in **deeper water**, where current is stronger.
- **Current against the wind** makes waves steeper and the wind feel stronger; current with the wind flattens the water.
- **Tide turns** usually first near the shore.

## Start
- Current pushing over the line → risk of OCS (early start): hold back, be careful at the end where current is strongest.
- Current pushing away from the line → be close to the line; it is easy to be late.
- Check current at **both ends** of the line (it can differ).

## Upwind
- Choose the side with less foul current or more fair current.
- **Laylines move:** cross-current pushes the boat sideways; overstand or understand accordingly.

## Downwind
- Same logic: use fair current in the deep water, avoid foul current.
- Plan the gate choice by current at each gate mark.

## Coach actions
- Measure current at the marks and line ends before the start (drop a drift object or use the coach-boat GPS).
- Give sailors: current direction, strength, and **time of tide turn**.

## Plan B
If the tide turns earlier than forecast (current changes direction at the marks), re-check: the favoured side can flip within one leg.

## Past lessons (synthetic)
- Weymouth 2025: race 3 was won by going inshore on the first beat against 1.2 kt of foul tide; the boats offshore lost 2 minutes.
