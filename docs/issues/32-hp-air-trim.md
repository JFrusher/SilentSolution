---
title: High-pressure air bank and trim/buoyancy
labels: feature, area:sim, priority:low
milestone: v0.4 Deeper Realism
---
## Motivation

The emergency blow is free and unlimited, and depth control is just "ordered depth at 1.5 m/s". Real boats had
limited HP air and had to manage trim. Making these resources adds decisions: a blow is a one-shot lifesaver,
and running slow and deep means fighting the trim.

## Proposal

- **HP air bank** (gauge on the dive panel, in %): a blow uses a large chunk; snorkelling recharges it via the
  compressors (noisy). An empty bank means no blow.
- **Trim:** a buoyancy offset (heavy/light) that drifts with depth (hull compression), flooding (leaks) and the
  torpedoes fired. Below ~2 kt the planes lose authority, so the boat slowly rises or sinks unless trimmed. Pumping
  or flooding the trim tanks (a key or the dial) is slow and slightly noisy.
- **Hovering** at very low speed becomes a skill, not a default.
- **Difficulty:** Cadet keeps auto-trim on; Commander and Iron Captain use manual trim.

## Acceptance criteria

- [ ] The blow refuses with `NO AIR` when the bank is empty, and the gauge shows it.
- [ ] At STOP, an untrimmed boat drifts in depth; a trimmed one holds.
- [ ] Leaks and fired torpedoes change trim visibly.
- [ ] A tutorial drill covers trim (Commander and above).
