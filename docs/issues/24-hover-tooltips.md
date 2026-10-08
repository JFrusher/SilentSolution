---
title: Hover tooltips on every control
labels: feature, area:ui, priority:low
milestone: v0.3 Polish & UX
---
## Motivation

The station is dense, and much of it is only explained in training. A tooltip on hover (name, what it does, bound
key) lets players learn in place, especially returning players who skipped the drill.

## Proposal

- Hover a control for ~0.6 s to show a small tape-label tooltip in the station's art style. Example:
  `TUBE 1 · FIRE TUBE 1 [1] · Fires one fish on the TDC solution`.
- Controls are defined once: a table in `layout.py` of `(shape, name, action, description)`, reused by click
  handling. This also removes duplicated hit-test geometry between `console.click` and `layout.HIGHLIGHTS`.
- Covers the gauges, annunciator tiles, TDC rows, waterfall and profile, scope, telegraph, yoke, depth dial,
  buttons and switches.
- Keys come from the bindings ([[06]]); text from the string table ([[25]]) once it exists.
- A setting to turn tooltips off.

## Acceptance criteria

- [ ] Every clickable or readable instrument has a tooltip.
- [ ] Tooltips never cover the control being hovered, and they stay on screen at the edges.
- [ ] No frame-time regression (render the tooltip surface once per hover).
