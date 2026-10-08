---
title: Ship classes and names, with class-specific tonnage, speed, sonar and weapons
labels: feature, area:sim, area:ai, area:content, priority:medium
milestone: v0.4 Deeper Realism
---
## Motivation

Every merchant scores 6,500 GRT, every escort is identical (24 kt, 15 charges, the same sonar), and the visual
class (`merchant`/`tanker`) is picked by `id(ship) % 3`, which is effectively random per run and unrelated to
anything else. Named ships with real differences make target selection a decision: the tanker or the troopship?
The fast frigate or the old corvette?

## Proposal

A `classes` table (in `tuning.py` or data files, [[38]]) defining, per class:

| Field | Examples |
|---|---|
| silhouette / length / beam / mast / draught | feeds the periscope renderer and stadimeter |
| GRT | tanker 10,000 · freighter 6,500 · troopship 12,000 · coaster 1,500 |
| speed range, noise, spectral template variant | old coal-burner louder and slower; motor ship quieter |
| escorts: max speed, sonar range, charges, pattern size, turn rate, radar ([[34]]) | corvette slow and nimble; destroyer fast, more charges |

- **Names:** each ship gets a name from a per-nation list. It's shown in the debrief ("SS *Harrowgate*, tanker,
  10,000 GRT"), in the periscope recognition card after a stadimeter mark, and in the teletype when confirmed sunk.
- **Director:** compose convoys from a class mix by wave and patrol.
- The class is stored on the vessel at spawn (fixes `silhouette_class` nondeterminism; see [[20]]).
- Collision dimensions for [[30]] come from here.

## Acceptance criteria

- [ ] Sinking a tanker scores more than a coaster, and the debrief lists names and classes.
- [ ] Escort classes measurably differ (speed, charges, sonar range) and the waterfall and periscope show the
      difference.
- [ ] `silhouette_class` reads the stored class; there's no `id()` anywhere.
