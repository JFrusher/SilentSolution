---
title: Mid-patrol save and load (campaign and endless)
labels: feature, area:sim, area:campaign, priority:medium
milestone: v0.3 Polish & UX
---
## Motivation

Campaign patrols run 30–60 minutes and endless runs longer. Today closing the game loses the patrol. A save lets
players stop at any point and come back.

## Proposal

- **Save from the pause menu ([[16]]):** one slot per mode (campaign patrol, endless), plus an autosave at each
  wave clear.
- **Format:** JSON in `~/.silent_solution/saves/`, with a `version` field. It serialises:
  - the world: own boat, targets, AIs and their state machines, torpedoes, charges, the ocean, the director
  - the operator side: TDC, TMA log, tubes, damage list, teletype tail, scope settings, the patrol run or
    objectives
  - the RNG state ([[20]])
- **Loading:** offered on the title (**[L] CONTINUE PATROL**) and on the career page.
- **Ironman option for the campaign (optional):** the save is deleted on load, so it can't be save-scummed.

## Design notes

- Most world objects are dataclasses, so `dataclasses.asdict` with a small type tag per object gets most of the
  way. AIs hold references to ships, convoys and torpedoes, so serialise references by id and relink on load.
- Display-only state (waterfall image, spectrum curve, CRT ghost) isn't saved; it refills within seconds.

## Acceptance criteria

- [ ] Save, quit, relaunch, load → the same tactical picture (contacts, AI states, fish in the water, damage list).
- [ ] A round-trip test: save → load → step N seconds matches stepping the original N seconds (needs [[20]]).
- [ ] A save from an older version is refused with a clear message rather than crashing.
