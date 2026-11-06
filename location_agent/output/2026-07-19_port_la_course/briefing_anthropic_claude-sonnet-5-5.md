# Race-day briefing - LA28 sailing - Port of LA boat course (outside San Pedro breakwater)
**2026-07-19, racing 13:00-17:00 local - ILCA 7**  
_Mode: backtest: only information available on the race-day morning. Model: claude-sonnet-5-5 (anthropic)._

**Race 1 card**
- Wind: WSW 14-18 kt, sea breeze from 12:00, slow veer about 2.6 deg/h.
- Start: south (left) end, +92 m upwind.
- Beat: stay middle, tack on clear 6 deg headers, avoid the laylines. Current sets you right and back.
- Side: no clear edge, keep a little left.
- If wind goes right of 266 deg, go right.
- If wind is under 8 kt, hunt pressure left-middle.
- Over 18 kt: stay middle, play puffs.

## The four questions
1. **Side:** middle (confidence low)
   - Wind is a steady 14-18 kt WSW sea breeze with a slow veer of only 4 deg over the window. The 1.2 km beat is too short for shifts to separate the sides. No terrain shelter on either side (index 0.0 at 260 deg), so no pressure or bend edge is resolvable.
   - Current is weak (0.26 kn) but sets the fleet toward the right (-75 m across course) and against the mark (-70 m). The model cannot resolve left vs right. Slightly favours keeping a little left or middle to avoid being pushed to the laylines. Right is nearer land (1465 m vs 2025 m) with slightly shallower water.
2. **Shifts:** oscillating_with_right_trend - Slow veer about 2.6 deg/h (12-17h), 1.5 deg/h in the race window. Oscillations are small (SD 2.3 deg), period not resolved (>=30 min).
   - Race-day veer matches the July median and the sea breeze is typical, so the trend is gentle. Swing SD is a bit above median but small in absolute terms. Measured station veer is stronger (7.2 deg/h), but its direction is biased.
3. **Start:** south_left_end
   - The south (left) end is about 92 m more upwind at the forecast wind of 257 deg. It stays favoured with a 5 deg shift either way (64 to 119 m). The veer is slow and would reduce but not remove the bias. Which end is committee vs pin is unknown.
4. **If the forecast is wrong:**
   - *Sea breeze is late or weaker than forecast (light air)* - watch: Wind below about 8 kn from 225-295 deg at 12:00-13:00. Angels Gate morning wind around 5 kn at 10:00 and 8 kn at 11:00 suggests a normal build. - then: In light air pressure beats shifts: sail toward the visible pressure and keep the left-middle side. Be less eager to tack on small headers.
   - *Wind stronger or gustier than forecast (above 18 kt)* - watch: Speed over 18 kt, gusts well above the mean (+1.1 kt forecast), whitecaps. - then: Tack on bigger shifts, play the puffs and stay near the middle. Hiking and boat handling matter more than side.
   - *Wind veers faster or goes further right than forecast* - watch: Direction right of about 265 deg early in the race window, as the measured station veer rate of 7.2 deg/h would imply. - then: Persistent right shift: go right early and stop tacking on small headers.

**First beat:** Start at the south (left) end. Hold starboard briefly, then stay in the middle and tack on clear 6 deg headers. Avoid the laylines. Allow for the slight current set to the right and against the mark. If the wind veers beyond 265 deg, work right.

## Action plan (sailed by the simulator)
- **Start:** 0.10 along the line (0 = left end, 1 = right end), starboard tack, hold 60 s
- **Upwind:** go middle up to 150 m off the rhumb line; tack on headers >= 6 deg held 20 s; overstand laylines 15 m
- **Downwind (every run):** favour middle up to 150 m off the rhumb line; gybe on lifts >= 6 deg; gybe on the layline
- **If** wind_dir_right_of_deg 266 -> side right, tack on 10 deg (A faster veer than forecast means a persistent right shift, so sail toward it.)
- **If** wind_speed_below_kn 8 -> side left, tack on 10 deg (In light air pressure matters more than shifts. Keep left-middle, stay flexible and avoid over-tacking.)

## Uncertainty
- The 1.2 km beat is below HRRR resolution, so left vs right pressure and bend cannot be resolved.
- Swing period is not available. HRRR smooths short oscillations.
- Station direction is biased 25-40 deg left, and its veer rate (7.2 deg/h) conflicts with HRRR (2.6 deg/h).
- The current is a coarse model about 2.5 km from the course and cannot resolve sides.
- Sea temperature is a July median, not race-day data.
- Start line comes from one earlier race. Which end is the committee boat vs the pin is unknown.
- Forecast is a ~24 h HRRR run. Climatology covers only 5 years.
- No rag_insights were provided.
