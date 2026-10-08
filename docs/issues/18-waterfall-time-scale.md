---
title: 'Waterfall time scale: only ~21 s of history is too short to see bearing drift'
labels: enhancement, area:sensors, area:ui, priority:medium
milestone: v0.3 Polish & UX
fixed_in: 6c93032
---
## Motivation

The waterfall adds one row every 0.1 s and is 214 rows tall, so it only shows about **21 seconds** of history. Bearing
rate, the main passive cue for range and target motion, is nearly invisible: a merchant crossing at 8 kt and 5 km
moves about one degree in that window, which is **one pixel** on the 360 px waterfall. Real passive displays scroll over minutes. The TMA plot (F2) shows six
minutes, but the waterfall is where players spend their time.

## Where

- [`displays.py:13`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/displays.py#L13): `ROW_INTERVAL = 0.1`
- `WaterfallDisplay` buffer: `WF_H = 214` rows

## Proposal

- Selectable time scale: **FAST 0.1 s/row (21 s) · MED 0.5 s/row (~1.8 min) · SLOW 2 s/row (~7 min)**, cycled with a
  new bindable key (`WATERFALL SCALE`) or by clicking the time label on the waterfall.
- Show the scale and a time axis (`-1M`, `-2M` ticks) on the left edge, like the TMA plot.
- At slow scales, integrate (average or max) the detections over each row's interval rather than sampling one
  frame, so short transients still show.
- Blips (pings, echoes, detonations) are still painted on the next row at any scale.

## Acceptance criteria

- [ ] At SLOW, a crossing merchant's trace visibly slants over a few minutes.
- [ ] Switching scale keeps the existing history (resample, or start a new row block; don't wipe it).
- [ ] Training mentions the control in the sonar chapter.
