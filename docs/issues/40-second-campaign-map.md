---
title: Second campaign with a patrol-area map and branching outcomes
labels: feature, area:campaign, area:content, priority:medium
milestone: v0.5 More Content
---
## Motivation

The current campaign is a fixed line of six patrols. A map where the player chooses which area to patrol, and
where results change what comes next, gives replay value and makes the career feel like a war rather than a
playlist.

## Proposal

- **Campaign file:** a TOML campaign (`campaigns/*.toml`) listing areas, each with a scenario pool ([[38]]), a
  threat level and an unlock or branch rule. The existing six-patrol campaign is converted to this format.
- **Map page** on the CRT: a vector chart of the theatre with patrol areas as outlined boxes, threat ticks, and
  the boat's home port. Click an area, or use the arrow keys, to choose the next patrol.
- **Branching:**
  - Success in an area can open new ones (a convoy route found, a harbour located).
  - Failure, or a heavily damaged return, closes off or toughens others.
  - Some areas are timed: they expire after N patrols.
- **Persistent consequences:**
  - Damage you return with costs patrols in dock unless repaired.
  - Losses to escorts raise the threat level in that area.
  - Reputation affects which refits are offered.
- **Second campaign content:** for example a northern-waters convoy route (ice limits, heavy weather, short
  visibility) with 8–10 areas and its own ranks and refits.
- The career save stores the campaign id, map state and history; [[21]] (save/load) covers mid-patrol state.

## Acceptance criteria

- [ ] The existing campaign plays identically in the new format (regression).
- [ ] The second campaign is playable start to finish with at least two distinct routes through the map.
- [ ] The map page shows locked, open, completed and failed areas distinctly (not by colour alone).
- [ ] Old `career.json` files migrate or are clearly reset with a message.
