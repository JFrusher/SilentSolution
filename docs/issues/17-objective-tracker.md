---
title: Objective tracker and a "return to base" cue for campaign patrols
labels: feature, area:campaign, area:ui, priority:medium
milestone: v0.3 Polish & UX
---
## Motivation

Campaign objectives (for example "19,500 GRT in 3 waves", or "6,500 GRT and a submarine sunk") appear only in the
opening teleprinter message. Once it scrolls away, the player has to remember them. When they're met, one line of
teletype says "RETURN TO BASE WHEN READY (ENTER)", which is easy to miss. Nothing shows waves remaining.

## Proposal

- A small objectives card clipped to the teleprinter frame (under the WAVE/GRT counters), styled like the training
  order slip:
  `PATROL 3 · THE NARROWS  ·  WAVE 2/3  ·  GRT 13,000 / 19,500  ·  SUB ✓`
- When the objectives are met: a lit **RTB** lamp on the slip, plus the key hint (`ENTER: RETURN TO BASE`, using
  the bound key from [[06]]).
- Endless shows the wave number and best score instead.

## Acceptance criteria

- [ ] Objective progress is visible on the station throughout the patrol and updates live.
- [ ] The RTB state is unmistakable: the lamp, the slip text and a teletype line.
- [ ] Doesn't overlap the teletype paper at either text size.
