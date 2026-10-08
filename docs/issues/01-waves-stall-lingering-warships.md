---
title: Waves stall for 40–90+ minutes while an enemy sub or escort lingers nearby
labels: bug, area:ai, priority:high
milestone: v0.2.1 Fixes
fixed_in: 8341acd
---
## Summary

A wave only ends when every non-decoy contact has been sunk or has passed the despawn range. Enemy submarines patrol
at about 4 kt, 4–8 km from the boat, and never get past the 9 km late-despawn range. The next wave, and the
tender resupply that comes with it, can be held up for an hour or more while nothing happens.

## Evidence

A headless probe ran `build_world(DIFFICULTY["COMMANDER"])` with the player passive at 60 m (`min_hull = 100`) for
three hours of sim time on four seeds. Wave length in minutes:

| Seed | Wave 1 | Wave 2 | Wave 3 | Wave 4 |
|---|---|---|---|---|
| 1 | 22.6 | **91.8** | 42.1 | still open at 180 min |
| 2 | 19.3 | 15.0 | still open at 180 min, with one `SUB PATROL` at 4.7–6.6 km | |
| 3 | 15.0 | 39.5 | 54.8 | 58.6, with two `SUB PATROL` at 7.4–8.9 km |
| 4 | 26.4 | 34.4 | still open; see [[02]] | |

Waves without submarines clear in 15–26 minutes. The long tail is always warships idling inside 9 km.

## Where

- [`ai.py:535-552`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/ai.py#L535-L552), `ThreatDirector.update`.
  After `WAVE_TIME_LIMIT` it only shrinks the despawn range to `LATE_DESPAWN_RANGE`.
- [`tuning.py:47-51`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/tuning.py#L47-L51):
  `DESPAWN_RANGE = 18000`, `WAVE_TIME_LIMIT = 900`, `LATE_DESPAWN_RANGE = 9000`.
- `SubmarineAI` in `PATROL` cruises at 4 kt on a zig-zag base course, so it takes 30–75 minutes to cover 9 km.
- Related fragility: the resupply trigger is `if self.timer == WAVE_GAP and self.wave` (float equality used as a
  "first quiet tick" flag, `ai.py:544`).

## Proposed approach: late-wave withdrawal

1. Once a wave passes `WAVE_TIME_LIMIT`, tell every warship AI that is **not** holding a fresh contact
   (`since_contact > GIVE_UP`, or in `PATROL`/`SEARCH`) to withdraw: a new `WITHDRAW` state (or a flag) that
   steers directly away from the boat at the AI's top speed.
2. Despawn a withdrawing contact once it is beyond the late range **or** has been withdrawing for N minutes (a
   tuning knob, say 10 min) and is beyond the passive range the boat could reasonably hold.
3. Report it like a sonarman would: `CONTACT 123R OPENING, REVS UP` when the withdrawal starts.
4. Replace the float-equality resupply trigger with an explicit `cleared` flag set when a wave empties.

## Acceptance criteria

- [ ] On the probe above (four seeds, passive player, COMMANDER), no wave stays open longer than about
      `WAVE_TIME_LIMIT` + 15 min.
- [ ] Warships holding a fresh contact on the boat do **not** withdraw; an engaged fight is never cut short.
- [ ] Withdrawal is audible and visible (log line, trace drawing away) rather than contacts popping out.
- [ ] Resupply still fires exactly once per wave (covered by a test).
- [ ] New knobs live in `tuning.py`.
- [ ] Regression test in `test_sim.py`: a wave with an idle submarine ends within the limit.

## Notes

- [[02]] covers a submarine with no torpedoes that never gives up; that one is a separate state-machine bug.
- Campaign patrols end when their last wave clears, so this also stops patrols from dragging.
