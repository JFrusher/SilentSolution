---
title: 'New mission types: shadow, reconnaissance, minelaying, breakout, rescue'
labels: feature, area:content, area:campaign, priority:medium
milestone: v0.5 More Content
---
## Motivation

Every mission is "sink tonnage". The station already supports much more (passive tracking, periscope marks,
silent running, snorkelling), and objectives that use those skills make the game about more than shooting.

## Proposal

New objective types for scenario files ([[38]]), each with a debrief line:

| Mission | Objective | Uses |
|---|---|---|
| **Shadow and report** | Hold a contact (TMA fit under X°) for N minutes without being detected; send a report (new key: `REPORT`) with course and speed within tolerance | TMA, stealth |
| **Harbour reconnaissance** | Get a periscope mark on N marked ships or points inside a defended anchorage; stay unspotted | periscope, exposure meter, shallow water |
| **Minelaying** | Lay a minefield at a set position and depth across a channel; mines later sink passing ships (score after) | navigation, new mine weapon |
| **Breakout** | Slip past a hunter-killer group (escorts in a search line) to an exit area; no shots required | silent running, layer, baffles |
| **Aircrew rescue** | Reach a downed crew's position, surface for a set time, then submerge; aircraft cover may be about ([[33]]) | surfacing risk, timing |

- Objectives are composable (for example "shadow, then sink"); `PatrolRun.met()` generalises to a list of
  objective checkers.
- Each new objective gets its HUD line in the objective tracker ([[17]]).
- New world bits are minimal: mines (a static `Vessel` subclass with a trigger radius), map areas (polygons or
  circles), and a `REPORT` action.

## Acceptance criteria

- [ ] Each mission type has at least one bundled scenario and is completable by a scripted bot in a headless
      test (as `test_tutorial.py` does).
- [ ] The debrief explains success or failure per objective.
- [ ] The objective tracker shows progress for each type.
