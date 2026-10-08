---
title: '"END OF SPOOL" can never happen: the wire is longer than the torpedo''s run'
labels: bug, area:fire-control, priority:low, good first issue
milestone: v0.2.1 Fixes
---
## Summary

`WIRE_LENGTH` is 8,000 m but `TORP_MAX_RUN` is 6,000 yd (5,486 m). A torpedo runs out of fuel and is removed long
before `torp.run > WIRE_LENGTH`, so the "END OF SPOOL" branch is dead. The only test that covers it sets
`run = 8001` by hand.

## Where

- [`sim.py:17`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/sim.py#L17): `TORP_MAX_RUN = 6000 * YARD`
- [`sim.py:49`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/sim.py#L49): `WIRE_LENGTH = 8000.0`
- [`sim.py:487`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/sim.py#L487): the check
- [`console.py:568`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/console.py#L568): the message

## Proposed fix

Make the wire shorter than the run so it matters. A real spool was a fraction of the torpedo's range: say
`WIRE_LENGTH = 4000` m, which leaves the last ~1.5 km to the seeker. Move it to `tuning.py` as a balance knob.
Update the test to run a real fish past the spool instead of poking `run`.

## Acceptance criteria

- [ ] A torpedo fired and left alone reports `WIRE PARTED - END OF SPOOL` before `FUEL OUT`.
- [ ] `test_sim.py` covers it without setting `run` by hand.
- [ ] README numbers ("parts past 8,000 m of run") updated.

## Notes

[[36]] (torpedo types) will give each type its own wire length.
