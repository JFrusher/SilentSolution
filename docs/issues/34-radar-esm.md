---
title: Surface-search radar on escorts and aircraft, and an ESM mast for the boat
labels: feature, area:sensors, area:ai, priority:medium
milestone: v0.4 Deeper Realism
---
## Motivation

From late WWII, radar let escorts and aircraft detect a periscope or snorkel head in rain, fog and poor
visibility, when the lookouts can't. The counter was ESM: a mast that hears the radar before the radar sees you.

## Proposal

**Enemy radar**
- Escort classes ([[31]]) and aircraft ([[33]]) may carry radar with a sweep period and a detection range against
  mast cross-section: snorkel > periscope; broached = hull. Reduced by sea clutter (sea state).
- Radar detection feeds the same `_mark` and `alarm` path as sighting.

**Own ESM**
- A third mast, or fitted to the snorkel or scope, raised like the others. While up and clear of the water it
  detects radar emissions at long range (beyond the radar's own detection range), with a bearing and a strength
  trend.
- Station cue: an **ESM** annunciator tile with a warble tone; the log reads
  `ESM: RADAR 080 TRUE, STRENGTH RISING`.
- Lets the player decide to dive before being detected.

## Acceptance criteria

- [ ] In rain or low visibility, radar-fitted escorts can detect a raised snorkel the lookouts would miss.
- [ ] ESM detects radar earlier than radar detects the mast, so a disciplined player can avoid detection.
- [ ] Radar adds to the exposure meter estimate.
- [ ] Training explains ESM.
