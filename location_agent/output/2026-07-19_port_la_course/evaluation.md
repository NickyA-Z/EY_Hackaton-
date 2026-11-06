# Evaluation - 2026-07-19 (port_la_course)
Strategy: `strategy_mock_mock.json` - model mock

First beat of each race (gun -> windward mark 1). Race 1 = tuning, races 2-3 = check. The plan is made once in the morning and used for every race. Same day, same weather, so this is weak proof.

| Race | Role | Real: side paid | Strategy side | Real: end paid | Strategy end | Real shifts | Strategy shifts | Sim rank | Gap to best ghost | Gap to winners | Sim calibrated |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | tuning | middle | right ❌ | left | left ✅ | oscillating | unclear ❌ | 17/45 | 34.0 s | Chiavarini +12s, Bos +28s, Hanson +22s, Wearn +10s | 2.9 % (ok) |
| 2 | check | left | right ❌ | left | left ✅ | persistent_right | unclear ❌ | 2/45 | 6.0 s | Chiavarini -16s, Bos -8s, Hanson -18s, Wearn -26s | 3.3 % (ok) |
| 3 | check | right | right ✅ | middle | left ❌ | persistent_right | unclear ❌ | 21/45 | 24.0 s | Chiavarini +20s, Bos -6s, Hanson +14s, Wearn +6s | 4.9 % (ok) |

## Detail
### Race 1 (14:15, tuning)
- **Real fleet:** 43 boats ranked by upwind distance to go to mark 1 at 579 s (agrees with the real rounding order of 32 boats: Spearman 0.86). Leaders minus rest: lateral -34.0 m (+ = right), line position -0.15 (+ = right end). Leaders: Rasmus Granzin (SWE), Matt Wearn (AUS), Lawson McAullay (AUS), Dimitri Peroni (ITA), Willem Wiersema (NED).
- **Real wind:** trend 7.0 deg/h, swing SD 18.7 deg → oscillating.
- **Our boat (sim):** 738.0 s, 3 tacks, mean lateral -3 m, 47 % of the time right. Rank 17/45.
- **Winners (sim / real):** Lorenzo Brando Chiavarini (ITA) 726.0 / None s, line pos 0.436, lateral 239 m; Duko Bos (NED) 710.0 / 709.0 s, line pos 0.025, lateral -140 m; Elliot Hanson (GBR) 716.0 / 719.0 s, line pos 0.49, lateral 53 m; Matt Wearn (AUS) 728.0 / 679.0 s, line pos 0.938, lateral 349 m
- **Course:** rhumb 271.0 deg; mark 1 clean roundings (±38 m). Boat model {'upwind_kn': 4.87, 'tack_angle_deg': 84.0, 'tack_loss_s': 6}.

### Race 2 (15:24, check)
- **Real fleet:** 33 boats ranked by upwind distance to go to mark 1 at 639 s (agrees with the real rounding order of 6 boats: Spearman 0.89). Leaders minus rest: lateral -103.0 m (+ = right), line position -0.22 (+ = right end). Leaders: Elliot Hanson (GBR), Jeemin HA (KOR), Pavlos Kontides (CYP), Willem Wiersema (NED), Dimitri Peroni (ITA).
- **Real wind:** trend 19.3 deg/h, swing SD 6.3 deg → persistent_right.
- **Our boat (sim):** 726.0 s, 3 tacks, mean lateral 0 m, 49 % of the time right. Rank 2/45.
- **Winners (sim / real):** Lorenzo Brando Chiavarini (ITA) 742.0 / None s, line pos 0.351, lateral -51 m; Duko Bos (NED) 734.0 / None s, line pos -0.036, lateral -415 m; Elliot Hanson (GBR) 744.0 / None s, line pos 0.537, lateral -70 m; Matt Wearn (AUS) 752.0 / None s, line pos 0.704, lateral 127 m
- **Course:** rhumb 278.0 deg; mark 1 leading quarter of first-beat tops (tracker gaps at the mark) (±138 m). Boat model {'upwind_kn': 4.82, 'tack_angle_deg': 84.0, 'tack_loss_s': 6}.

### Race 3 (16:30, check)
- **Real fleet:** 27 boats ranked by upwind distance to go to mark 1 at 559 s (agrees with the real rounding order of 5 boats: Spearman None). Leaders minus rest: lateral 101.0 m (+ = right), line position 0.03 (+ = right end). Leaders: Pavlos Kontides (CYP), Finn Lynch (IRL), Dimitri Peroni (ITA), Zac Littlewood (AUS), Elliot Hanson (GBR).
- **Real wind:** trend 15.0 deg/h, swing SD 4.1 deg → persistent_right.
- **Our boat (sim):** 690.0 s, 2 tacks, mean lateral -56 m, 41 % of the time right. Rank 21/45.
- **Winners (sim / real):** Lorenzo Brando Chiavarini (ITA) 670.0 / 639.0 s, line pos 0.485, lateral -32 m; Duko Bos (NED) 696.0 / None s, line pos 0.981, lateral 300 m; Elliot Hanson (GBR) 676.0 / 639.0 s, line pos 0.458, lateral -43 m; Matt Wearn (AUS) 684.0 / None s, line pos 0.412, lateral -105 m
- **Course:** rhumb 286.0 deg; mark 1 leading quarter of first-beat tops (tracker gaps at the mark) (±103 m). Boat model {'upwind_kn': 4.74, 'tack_angle_deg': 85.0, 'tack_loss_s': 6}.

Tracks of our boat and the winners' ghosts: `sim/` (SailSync CSV format).
