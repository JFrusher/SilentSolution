---
title: Enemy diesel subs must snorkel to charge, opening windows to hunt them
labels: feature, area:ai, priority:medium
milestone: v0.4 Deeper Realism
---
## Motivation

The player manages battery, snorkel, oxygen and exposure. Enemy submarines have unlimited submerged endurance.
Giving them the same constraint makes them fair and creates a classic hunt: listen for the snorkelling diesel and
attack while they're loud and shallow.

## Proposal

- `SubmarineAI` gets a battery that drains with speed (the same law as the player) and an O₂ budget on harder
  difficulties.
- Below a threshold, an unalerted sub comes to snorkel depth and runs diesels for a period. It is very loud (a
  distinct diesel signature in the spectrum library, `SNORKELLING SUB`) and visible to the player's periscope
  (snorkel head and exhaust smoke) in clear weather.
- It aborts and goes deep when it hears a ping, a launch or a close contact, at the cost of charge.
- Low battery limits its sprint speed when evading.

## Acceptance criteria

- [ ] Over a long wave, enemy subs periodically snorkel, and the player can detect it on the waterfall and profile.
- [ ] A snorkelling sub can be seen through the periscope at a sensible range.
- [ ] A sub with a flat battery can't sprint away from a torpedo.
- [ ] Training or a campaign patrol briefs this behaviour.
