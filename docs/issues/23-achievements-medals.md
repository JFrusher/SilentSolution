---
title: Achievements and medals
labels: feature, area:campaign, priority:low
milestone: v0.3 Polish & UX
---
## Motivation

They reward playing the way the game wants to be played (silent, patient, precise) and give endless players goals
beyond tonnage.

## Proposal

A data table of achievements, checked against world events and patrol stats, shown as ribbons on the career page
with a teletype line when earned. Suggested first set:

| Medal | Condition |
|---|---|
| Silent Service | Complete a patrol without pinging |
| One Fish, One Ship | Sink a ship with a single torpedo, no spread |
| Wire Artist | Sink a ship with a fish that was steered on the wire |
| Rode It Out | Survive a full depth-charge pattern within 60 m |
| Ghost | Finish a wave without being spotted, pinged-and-held or heard |
| Under the Layer | Evade an escort attack by going below the layer |
| Ace | 50,000 GRT in a single endless run |
| Fleet Ace | 200,000 GRT across the career |
| Hunter-Killer | Sink an enemy submarine |
| Damage Controller | Repair five systems in one patrol |
| Flag Rank | Complete the campaign |

- Persisted in `career.json` (with the date earned); the career survives "new career" for medals, or not
  (decide while implementing).
- Needs a small patrol-stats collector (pings, fish fired and hit, wire kills, spotted events), which the
  debrief and [[22]] can also use.

## Acceptance criteria

- [ ] Each medal has a unit test that feeds events and checks it's awarded once.
- [ ] Earned medals are shown on the career page, with locked ones dimmed.
