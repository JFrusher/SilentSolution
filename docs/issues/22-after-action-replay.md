---
title: After-action replay plot at the debrief
labels: feature, area:ui, area:campaign, priority:medium
milestone: v0.3 Polish & UX
---
## Motivation

The game is played blind: the player never sees the truth. The best teacher is seeing afterwards what actually
happened: where the escort really was when it pinged, why the spread missed, how close the pattern came. Today
the debrief shows totals only.

## Proposal

- **Record:** while a patrol runs, sample the truth every ~2 s: own track and depth, every contact's track,
  kind and AI state, torpedo runs (and wire aims), charge patterns, pings, sightings and hits. Keep it compact; a
  60-minute patrol at 2 s is about 1,800 frames.
- **Replay page** on the CRT from the debrief (**[A] AFTER ACTION**): a top-down vector plot like the tactical PPI
  but in truth coordinates. A time scrubber (← →, drag), play/pause at 10×/60×, and event markers on the timeline
  (pings, launches, hits, patterns).
- **Overlays:** the player's TDC estimate against the truth for the target they shot at, and the escort datum
  (where the escort thought you were).
- Optionally export the plot as a PNG next to the career file.

## Acceptance criteria

- [ ] Every campaign debrief and endless game-over can open the replay.
- [ ] Scrubbing is smooth (pre-built polylines, no re-simulation).
- [ ] Memory stays bounded for long endless runs (ring buffer, or downsample old history).
- [ ] Training chapter 4 offers the replay after the escort exercise.
