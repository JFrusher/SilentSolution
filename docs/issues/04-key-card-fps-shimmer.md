---
title: F1 key card drops the game to ~14 FPS and its paper shimmers
labels: bug, area:ui, priority:medium, good first issue
milestone: v0.2.1 Fixes
fixed_in: e9b6d18
---
## Summary

`draw_help()` calls `art.texture(...)` every frame to make the card's paper. The texture is random NumPy noise
plus two mottle passes, so it costs about 70 ms per frame, and because it is re-rolled each frame the paper visibly
crawls.

## Evidence

Headless benchmark on the live station (COMMANDER, mid-wave):

| Frame | Cost |
|---|---|
| Station draw | 10.3 ms |
| Periscope draw | 13.1 ms |
| **Station draw with the F1 card** | **75.9 ms** (about 13 FPS) |
| `art.texture((600, 614), PAPER, grain=3)` alone | 69.6 ms |

## Where

[`workstation.py:787-790`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/workstation.py#L787-L790)

## Proposed fix

Render the whole card (paper and engraved rows) once, cache the surface on the `Workstation`, and rebuild it only
when the key bindings or text size change (see [[06]]). Blit the cached surface each frame.

## Acceptance criteria

- [ ] With F1 open, frame cost stays within about 1 ms of the normal station draw.
- [ ] The paper no longer shimmers.
- [ ] The cache rebuilds after a key is rebound (once [[06]] makes the card read bindings).
