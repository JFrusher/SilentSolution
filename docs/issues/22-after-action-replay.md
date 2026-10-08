---
title: 2.5D tabletop replay of every patrol
labels: feature, area:ui, area:campaign, area:sim, priority:high
milestone: v0.3 Polish & UX
---
## Motivation

The game is played blind: the player never sees the truth. The best teacher is seeing afterwards what really
happened, in three dimensions: where the escort was when it pinged, how deep the sub really was, why the spread
missed, how close the pattern came.

## Decided

- **Plotting-table style:** a chart table at an angle, painted models on the paper, submarines on depth stalks
  below it, the thermocline as a smoked-glass sheet.
- **Camera:** free orbit (drag), zoom (wheel), pan (right-drag), and presets for plan, side (depth profile),
  oblique and follow-own-boat.
- **Layers:** truth in 3D. Every hull's track with depth, torpedo runs and wire paths, charge patterns sinking and
  bursting, noisemakers, sinkings.
- **Recorded for every patrol** (campaign, endless, training), saved, with the last 10 kept. Opened from the
  debrief, the game-over screen and the career log.

## Plan

The full design is in [`docs/plans/tabletop-replay.md`](../plans/tabletop-replay.md). It covers:
- the recorder (stable body uids, 1 s sampling and events)
- the gzip JSON file format and retention
- the perspective tabletop renderer, with depth exaggeration and a depth scale
- models, tracks and effects
- the REPLAY page with its camera and timeline
- five phases, each with its own tests

## Acceptance criteria

- [ ] Every patrol writes a replay file of about 2 MB or less for an hour; the 10 newest are kept, and corrupt files
      are handled.
- [ ] The recorder doesn't change the world: a test compares world state with and without recording.
- [ ] A round trip reproduces recorded positions within rounding.
- [ ] Plan, side, oblique and follow presets plus free orbit, zoom and pan all work; depth exaggeration is
      adjustable and labelled.
- [ ] The timeline scrubs, plays at 1× / 4× / 16× / 60× and jumps between events.
- [ ] 30 bodies render in under 16 ms.
- [ ] Entry points: debrief, game over, career log, end of training.

## Depends on

- Built on the 3D geometry core and its cross-check suite (`geometry.py`, `test_geometry.py`, v0.2.2).
- The seeded RNG ([[20]]) isn't required: the replay stores truth, it doesn't re-simulate.
