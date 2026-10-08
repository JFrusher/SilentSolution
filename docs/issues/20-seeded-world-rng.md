---
title: Seeded per-world RNG instead of the global random module
labels: tech-debt, area:sim, priority:medium
milestone: v0.3 Polish & UX
---
## Motivation

The world, the AI, the sensors and the director all draw from the global `random` and `np.random`. That makes runs
impossible to reproduce: a bug report can't be replayed, and save/load ([[21]]) and the after-action replay ([[22]])
can't rebuild state deterministically. `silhouette_class` even uses `id(ship) % 3`, so a ship's class (tanker or
freighter) depends on memory addresses and changes between runs.

## Proposal

- Give `WorldSimulation` a `seed` and an `rng = random.Random(seed)` (plus `np_rng = np.random.default_rng(seed)`)
  and pass it, or the world, to everything that rolls dice: `ai.py`, `sim.py` (`Ocean` swells, damage),
  `sensors.py` (noise), `ThreatDirector`.
- Keep a separate RNG for presentation-only randomness (CRT grain, art wear, audio), so drawing doesn't change the
  simulation.
- Replace `id(ship) % 3` with a class chosen from the world RNG at spawn and stored on the vessel (this becomes
  [[31]]).
- Print the seed in the F3 debug overlay and in `crash.log`.

## Acceptance criteria

- [ ] Same seed + same inputs → identical world state after N minutes (test: step two worlds in lockstep and
      compare positions and events).
- [ ] Rendering at a different frame rate doesn't change the simulation, given the same fixed-step inputs.
- [ ] The existing tests still pass (they seed `random`; switch them to world seeds).
