---
title: 'Campaign: losing the boat jumps straight to the debrief'
labels: bug, area:campaign, area:ui, priority:low
milestone: v0.2.1 Fixes
---
## Summary

In endless play, losing the boat shows **LOST WITH ALL HANDS** on the CRT while the final teletype message prints.
In a campaign patrol, `PatrolRun.update` returns `LOST` on the same frame `con.dead` becomes true, and `main` swaps
straight to the debrief. The player never sees the boat go down, the hull gauge at zero or the last teleprinter
line.

## Where

- [`campaign.py:120-122`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/campaign.py#L120-L122)
- [`main.py:131-135`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/main.py#L131-L135)

## Proposed fix

When a campaign boat is lost, enter the `OVER` state first (same box as endless, with the patrol name) and go on
to the debrief on any key, or after ~6 s. The world is already frozen when dead, so a short real-time hold in
`main` is enough.

## Acceptance criteria

- [ ] Campaign loss shows the loss screen and the final teletype line before the debrief.
- [ ] Any key or a timeout continues to the debrief; the career records the loss exactly once.
