---
title: Clicking or scrolling on the TMA plot moves the hydrophone dial to a wrong bearing
labels: bug, area:sensors, area:ui, priority:low, good first issue
milestone: v0.2.1 Fixes
---
## Summary

The waterfall's click rule (x position → relative bearing 0–360°) also applies while the left of the monitor
shows the **TMA plot**, whose x axis is a ±20° window of **true** bearing. Clicking the plot throws the dial to an
unrelated bearing and drops the hydrophone lock. The mouse wheel over the CRT nudges the dial whatever page is
showing.

## Where

- [`console.py:415-416`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/console.py#L415-L416): `elif wf.collidepoint(pos): self.dial = ...`
  has no `crt_page` check. (The damage-board branch above it is guarded.)
- [`console.py:459-460`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/console.py#L459-L460): wheel over `CRT_RECT`.

## Proposed fix

- Only map clicks to the dial when `crt_page == "SONAR"`.
- On the TMA page, a click could instead set the dial to the clicked **true** bearing minus heading. That's
  useful: "listen there". Or do nothing; either is fine.
- The wheel nudges the dial only on the sonar page.

## Acceptance criteria

- [ ] Clicking the TMA plot never produces a dial bearing outside the plotted window.
- [ ] Clicking the damage board and the TMA plot behave as documented; the waterfall is unchanged.
