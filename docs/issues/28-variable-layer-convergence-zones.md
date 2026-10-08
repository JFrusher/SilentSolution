---
title: Variable thermal layer, convergence zones and bottom bounce
labels: feature, area:sensors, area:sim, priority:medium
milestone: v0.4 Deeper Realism
---
## Motivation

The ocean has one thermocline, fixed at 100 m, with one transmission factor everywhere. Knowing the water is half
of submarine tactics: where the layer is today, whether there's a surface duct, and where sound comes back at
long range.

## Proposal

- **Per-patrol sound-speed profile:** layer depth (40–200 m) and strength vary with region and season (campaign
  data or scenario files, [[38]]), and slowly with weather (storms mix the surface layer deeper).
- **Bathythermograph:** a BT trace on a CRT page (sound speed against depth), sampled as the boat changes depth.
  The player has to dive through the layer to find it, rather than being told.
- **Convergence zones** in deep water: an annulus of good detection at ~30–35 nm and its multiples. Distant
  contacts appear and fade as the range crosses a zone.
- **Bottom bounce** in moderate depths: reduced loss at medium range; requires a bottom depth for the patrol area.
- Replace `Ocean.transmission(a, b)` with a function of both depths and the range, cached per frame.

## Scale caveat

Convergence zones sit at ~55–65 km, and the world currently spawns waves 7–9.5 km out and despawns at 18 km
(`DESPAWN_RANGE`). CZ detection needs either a larger world for distant contacts (cheap: kinematics only,
no AI beyond a course) or "far contacts" that exist only as sonar sources until they close. Decide which before
building the CZ part. The variable layer and BT trace don't depend on it and can ship first.

## Acceptance criteria

- [ ] Layer depth differs between patrols, and the BT page shows it once measured.
- [ ] A loud convoy is detectable in the first convergence zone but not in the shadow between it and direct path.
- [ ] Performance: the transmission calculation stays vectorised (NumPy) for all contacts.
- [ ] The training chapter explains the BT trace.
