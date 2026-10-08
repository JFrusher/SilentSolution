---
title: 'Torpedo types: steam, electric, pattern-runner and acoustic homer'
labels: feature, area:fire-control, priority:medium
milestone: v0.4 Deeper Realism
---
## Motivation

There's one torpedo: 35 kt, 6,000 yd, a 1,000 yd seeker, wired. Period weapons came with real trade-offs, and
choosing what to load is a tactical decision.

## Proposal

| Type | Speed / range | Wake | Guidance | Trade-off |
|---|---|---|---|---|
| Steam (straight runner) | fast, long | **visible wake**: lookouts spot it and back-plot to you | none (gyro angle only) | cheap, reliable, gives you away |
| Electric | slower, shorter | **wakeless** | none | stealthy, needs a good solution |
| Pattern-runner (FAT/LUT style) | medium | wake | runs a pre-set zig-zag or loop pattern after a straight leg | good against convoys from long range |
| Acoustic homer | slow | wakeless | seeker; easily decoyed; can circle back | fire-and-forget, dangerous to yourself |
| Wire-guided (current) | as now | — | wire + seeker | as now; wire length per type ([[08]]) |

- **Loadout:** pick tube loads before a patrol (campaign) and choose the reload type at sea. Reloading a different
  type takes time.
- **TDC:** type-aware solution (speed and range per type); the pattern-runner gets pattern settings on the TDC.
- **Wakes:** the merchant `WAKE_SIGHTING` check and the periscope `Wake` rendering apply only to wake-making types.
- **Homer:** can acquire the firing boat if it turns back; it shouldn't arm until clear, and the player should be
  able to run from it.

## Acceptance criteria

- [ ] Each type behaves per the table and is selectable per tube.
- [ ] Electric fish leave no wake in the periscope and aren't sighted by lookouts.
- [ ] Pattern-runners can hit an overlapping convoy target fired from outside a direct solution.
- [ ] The tutorial or a campaign briefing introduces the types.
