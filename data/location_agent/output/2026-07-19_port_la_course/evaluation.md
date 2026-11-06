# Evaluation - 2026-07-19 (port_la_course)
Strategy: `strategy_anthropic_claude-sonnet-5-5.json` - model claude-sonnet-5-5

Our boat sails the strategy's action plan over the whole course in a simplified simulator (wind from the boats' tacking, the same everywhere; constant speeds measured from the fleet; no other boats). The winners' times are real, so time gaps include that simplification.

## Race 1 (gun 14:15:01)

**Course:** beat -> mark1 → run -> gate3 → beat -> mark2 (uncertain) → run -> gate3 → reach -> finish

### (A) What really paid on the first beat (all real boats)
| | Real fleet | Strategy |
|---|---|---|
| Side | middle (27.0 m) | middle ✅ |
| Start end | middle (-0.07) | left ❌ |
| Shifts | oscillating (trend 14.0°/h, SD 24.9°) | oscillating_with_right_trend ❌ |

### (B) Full race: our boat (simulated) vs the winners (real)
Time from the gun when within 80 m of each mark (m:ss). '–' = the real tracker had no data there.

| Boat | L1 beat→mark1 | L2 run→gate3 | L3 beat→mark2 | L4 run→gate3 | L5 reach→finish | Finish |
|---|---|---|---|---|---|---|
| **Our boat (sim)** | 11:48 | 21:22 | 30:34 | 36:52 | 39:32 | **39:32** |
| Matt Wearn (AUS) (real) | 11:19 | 20:59 | – | 36:49 | 38:39 | 38:39 |
| Elliot Hanson (GBR) (real) | 11:59 | – | – | 20:59 | 39:09 | 39:09 |
| Duko Bos (NED) (real) | 11:49 | – | – | – | 39:29 | 39:29 |
| Lorenzo Brando Chiavarini (ITA) (real) | – | 21:59 | – | – | 40:09 | 40:09 |

- **Race winner (of the 4 winner files):** Matt Wearn (AUS) in 38:39.
- **Our boat:** finish 39:32; 12 tacks/gybes in total; indicative rank 8 of 45 against the real boats whose finish was visible.
- **Gap to each winner (our sim finish − real finish):** Wearn +53 s, Hanson +23 s, Bos +3 s, Chiavarini -37 s
- **Boat model (measured from the fleet):** {'vup_kn': 4.9, 'tack_angle': 84.2, 'vdn_kn': 6.0, 'downwind_twa': 157.35, 'vreach_kn': 5.3, 'tack_loss_s': 6.0, 'gybe_loss_s': 4.0}

Files: `sim/race1_agent.csv` = our positions at the race winner's 192 timestamps (gun → its finish); `sim/race1_agent_full.csv` = our 2 s track; `sim/race1_course.json` = marks; `sim/race1_legs.csv` = leg table.

