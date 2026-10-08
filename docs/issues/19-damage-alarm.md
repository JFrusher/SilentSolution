---
title: Damage alarm lamp and audible alarm when systems are knocked out
labels: enhancement, area:damage, area:ui, priority:low, good first issue
milestone: v0.3 Polish & UX
---
## Motivation

When a hit breaks systems, the only cues are a teletype line and the F5 board. The alarm panel has a LEAK tile
but nothing for **system damage**, so a player on the waterfall can miss that the planes are jammed until the boat
won't level off.

## Proposal

- Add a **DAMAGE** annunciator tile: flashing while any system is down, steady while the party is working, off
  when everything is repaired. Swap it in for a lower-value tile, or add a tenth tile (layout permitting).
- A short procedural alarm (two-tone klaxon) on new damage, in the effects volume category.
- Optional: clicking the DAMAGE tile opens the F5 board.

## Where

- `layout.LAMPS` / `ANNUNCIATORS`, and the annunciator states in `workstation.draw_controls`
  ([`workstation.py:689-697`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/workstation.py#L689-L697))
- `console.report("DAMAGE")`

## Acceptance criteria

- [ ] New damage flashes a labelled tile (colour is never the only cue) and sounds an alarm.
- [ ] Works with colour-blind lamps.
