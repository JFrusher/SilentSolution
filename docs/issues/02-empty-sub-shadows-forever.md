---
title: Enemy sub with no torpedoes left shadows the boat forever (47 m away, same depth)
labels: bug, area:ai, priority:high
milestone: v0.2.1 Fixes
fixed_in: 8341acd
---
## Summary

Once a `SubmarineAI` has fired all its torpedoes, nothing ever makes it give up. Close enough to hear the boat on
every listen tick, it stays in `ALERT`, keeps re-marking the boat's position and steers onto the datum. It ends up
parked on top of the player and the wave never ends.

## Evidence

Seed 4, COMMANDER, passive player at 60 m (`min_hull = 100` so the boat survives), stepped for 175 sim minutes:

```
sub state=ALERT torpedoes=0 reload=0 range=47 m since_contact=0 depth 60 vs own 60; launches=4 hits=3
```

The sub sat 41–47 m from the boat, at the same depth, for over 20 minutes. (The hulls overlap; [[30]] covers
collisions.)

## Where

- [`ai.py:463-505`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/ai.py#L463-L505),
  `SubmarineAI.update`. `ALERT` only leaves for `PATROL` when `since_contact > GIVE_UP`, which can't happen
  while `_listen` keeps hearing the boat at close range. Firing needs `self.torpedoes`, and nothing else
  changes when the racks are empty.
- `ai.py:498`: the firing condition.

## Proposed approach: withdraw

- When `torpedoes == 0` (and no reload pending), switch to a withdraw behaviour. Open the range at top speed,
  directly away from the datum, choosing a depth across the layer when `layer_sensitivity` says it knows the
  trick. Despawn once out of contact (same rule as [[01]]).
- Optional: have the sub drop a decoy if the boat is close behind when it breaks off.
- Log what a sonarman would hear when it bolts: `CONTACT 210R REVS UP, OPENING`.

## Acceptance criteria

- [ ] A sub that has fired its last torpedo opens the range and leaves within a few minutes.
- [ ] A sub that still has torpedoes behaves exactly as now.
- [ ] Regression test: a `SubmarineAI` with `torpedoes=0` and a fresh datum ends up beyond 6 km within N minutes.
- [ ] Re-running the seed-4 probe, wave 3 closes.

## Notes

Shares a withdrawal behaviour with [[01]]; implement them together if convenient.
