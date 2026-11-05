---
doc_id: TS-11
title: Pre-start routine and decision rules
doc_type: team_procedure
condition: every_race_day
triggers: always
synthetic: true
---

# TS-11 Pre-start routine and decision rules

> SYNTHETIC DATA for retrieval testing.

## Timeline
| Time | Who | Action |
|---|---|---|
| 05:30–07:00 | Coach / analyst | Pull forecast + venue data, run Location Agent, draft the briefing |
| 08:00 | Coach + sailors | Team briefing: game plan + plan B (one page) |
| −60 min | Sailors + coach | On the water; start compass log |
| −45 to −15 min | Sailors | Split tacks with a training partner to test sides |
| −30 min | Coach | Current check at marks and line ends |
| −15 min | Sailors | Line bias (head-to-wind, ping both ends) |
| −10 min | Coach → sailors | Final 3 facts (last allowed contact) |
| Between races | Coach → sailors | Side that paid, shift trend, forecast change |
| After racing | Team | Debrief: GPS tracks, results, wind log, notes into Location Agent |

## Decision rules
1. **Favoured side:** go hard to one side only if **two signals** agree (venue history, forecast, compass log, visible pressure, current).
2. **Shift type:**
   - Heading swings back and forth → **oscillating** → tack on headers ≥ 5°.
   - Heading trend > 10° one way in 20 min → **persistent** → sail toward the shift first.
3. **Start end:** bias ≥ 5° → favoured third; bias ≥ 10° → fight for the end (unless strong wind, TS-03).
4. **Plan B trigger:** losing ≥ 5 boat lengths to the other side after the first third of the beat → go back to the middle.

## Which documents to combine
- Read the conditions → pick documents from the index (TS-00).
- Always include TS-01 and the venue playbook.
- Safety rules (TS-03, TS-05) override everything.

## Rules reminder
At Olympic events, coaches may not help sailors while they are racing, and devices such as phones and tablets are not allowed on coach boats. The briefing must be **simple enough to remember**.
