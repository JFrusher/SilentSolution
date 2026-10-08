---
title: Leaks should join the damage-control queue instead of repairing in parallel
labels: enhancement, area:damage, priority:low
milestone: v0.4 Deeper Realism
---
## Motivation

The damage model says "one party works the list, top first", but leaks (Iron Captain) all count down in parallel
on their own timers (`LEAK_REPAIR = 60 s` each, `sim.py:295`) and never appear on the F5 board. Flooding is the
most urgent repair aboard, and choosing between plugging a leak and freeing the planes is exactly the decision the
queue exists for.

## Proposal

- A leak becomes a damage-list entry (`LEAK 1`, `LEAK 2`…) with its own repair time, placed at the **top** of the
  list by default (the party goes to flooding first) but movable like any other line.
- While unplugged, leaks keep making the boat heavy and draining the hull, as now.
- The pumps (if [[32]] adds trim) slow the weight gain but don't stop it.

## Acceptance criteria

- [ ] Leaks show on the damage board and are repaired one at a time with the other systems.
- [ ] Moving a system above a leak delays the leak repair (test).
- [ ] The LEAK annunciator still reflects any unplugged leak.
