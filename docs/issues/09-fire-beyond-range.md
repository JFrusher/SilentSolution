---
title: Firing is allowed when the solution is beyond torpedo range
labels: enhancement, area:fire-control, priority:low, good first issue
milestone: v0.2.1 Fixes
fixed_in: 54eab29
---
## Summary

When the TDC solution's run exceeds `TORP_MAX_RUN`, the only cue is the solution lamp turning red. <kbd>F</kbd>
still fires, and the fish runs out of fuel short of the target. That wastes torpedoes and gives away the boat's
position (launch transients alarm escorts) for nothing.

## Where

- [`workstation.py:704-708`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/workstation.py#L704-L708): the red lamp
- [`console.py:229-249`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/console.py#L229-L249): `fire()`, no range check

## Proposed change

- On a beyond-range solution, the first <kbd>F</kbd> logs `SOLUTION BEYOND RANGE: RUN 6,800 YD. FIRE AGAIN TO
  SHOOT` and does nothing. A second press within ~3 s fires anyway (a "long shot" is a legitimate tactic with
  wire guidance).
- Show `RUN` in red on the drum counter as well as the lamp.

## Acceptance criteria

- [ ] A single press never wastes a fish on a beyond-range solution.
- [ ] Double press fires as now.
- [ ] Test covering both paths.
