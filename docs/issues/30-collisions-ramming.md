---
title: Hull collisions and ramming
labels: feature, area:sim, area:ai, priority:medium
milestone: v0.4 Deeper Realism
---
## Motivation

Hulls never collide. An enemy submarine has been seen sitting **47 m from the boat at the same depth** for 20
minutes ([[02]]), and escorts pass straight over a boat at periscope depth. Ramming was a primary escort weapon
against a submarine near the surface.

## Proposal

- **Collision volumes:** each vessel gets a length, beam and draught (from its class, [[31]]). Two hulls collide
  when their footprints overlap and their depth bands overlap (keel depth against the surface ship's draught, or
  depth ± half height for submarines).
- **Effects:**
  - escort keel against a boat at periscope depth or broached: heavy hull damage, masts carried away (break the
    `PERISCOPE`/`SNORKEL` systems), a loud event
  - submarine against submarine: damage to both, and both alarmed
  - below keel depth: a near miss, heard loudly overhead (screws passing over); worth a log line
- **AI:** an escort in `ATTACK` against a boat known to be shallow (sighted or broached) tries to ram instead of
  rolling charges. Submarines keep a minimum stand-off and never park on the player.

## Acceptance criteria

- [ ] Nothing occupies the same space: no overlap at matching depth in any test scenario.
- [ ] An escort can ram a broached boat; the damage and events are reported.
- [ ] Screws passing overhead are audible and logged when an escort crosses directly above.
- [ ] Training's live-exercise chapter warns about staying shallow near escorts.
