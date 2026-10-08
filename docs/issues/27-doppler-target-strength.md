---
title: Doppler and aspect-dependent target strength
labels: feature, area:sensors, area:audio, priority:medium
milestone: v0.4 Deeper Realism
---
## Motivation

Echoes all sound the same and differ only in loudness with range. Real active sonar carries more: **Doppler** (up
for closing, down for opening) and **target strength** (beam aspect returns far more than bow or stern), so an
echo tells you aspect and range rate. Passive tonals shift with relative motion too.

## Proposal

**Active**
- Each echo carries range rate (from relative velocity along the line of sight). Play the echo pitch-shifted:
  resample the echo buffer, cached in a few steps such as ±2%, ±5% and ±10%.
- The log reads `ECHO 045R 4,200 YD  UP DOPP` / `DOWN DOPP` / `NO DOPP`.
- Echo strength ∝ the target's projected length (`|sin(aspect)|` blended with a floor) and its class size
  (see [[31]]).

**Passive**
- The spectrum's tonal lines shift by the Doppler factor, so a closing contact's lines sit slightly higher. Make it
  visible on the profile when the dial is locked.

**TDC/TMA**
- When the ping is on the plotted target, give the TMA solver a range-rate constraint (it already takes ranges).

## Acceptance criteria

- [ ] A closing target's echo is audibly higher than an opening one, and labelled in the log.
- [ ] Beam aspect echoes are clearly stronger than end-on.
- [ ] `tma.auto_solve` uses range rate when available (test: fewer ambiguous fits on a single leg).
