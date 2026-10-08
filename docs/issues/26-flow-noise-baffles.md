---
title: Own-ship flow noise and baffles (and escort sonar degraded at speed)
labels: feature, area:sensors, area:ai, priority:high
milestone: v0.4 Deeper Realism
---
## Motivation

Today the boat hears exactly as well at FLANK as at STOP, and in every direction. Only the snorkelling diesels
deafen the hydrophones (`DIESEL_DEAFNESS`). That removes the central tension of submarine sonar: **you can go fast,
or you can listen**. Escorts are the same: they hold contact while pinging at 24 kt.

## Proposal

**Own boat**
- **Flow noise:** passive detection level falls with own speed above ~6 kt (for example
  `levels /= 1 + ((kt - 6) / 6) ** 2` above 6 kt), and the waterfall noise floor rises. Cavitation adds a further
  hit.
- **Baffles:** a blind arc astern (about ±30° around 180° relative) where contacts are heavily attenuated. Drawn
  as a shaded band on the waterfall. Clearing the baffles (a turn to look astern) becomes a real manoeuvre.
- The HYD readout shows `OWN NOISE HIGH` when flow noise dominates.

**Escorts and enemy subs**
- Their listen and ping detection ranges scale down with their own speed, so they sprint and drift: run in fast,
  slow down to listen.
- `EscortAI` runs in on the datum at `ESCORT_FULL` and should slow to search speed inside `SONAR_RANGE` before
  pinging.

## Where

- `sensors.PassiveSonar.listen` (levels),
  [`console.py:522-528`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/console.py#L522-L528) (diesel
  deafness precedent)
- `ai.ShipAI._listen`, `EscortAI._ping`, the `EscortAI` ALERT/ATTACK speed

## Acceptance criteria

- [ ] At FLANK, a merchant that's a solid trace at SLOW is weak or lost; at STOP it's clearest.
- [ ] Contacts in the baffles fade; turning 90° brings them back.
- [ ] Escorts that slow to listen hold contact better than ones that stay at flank (test).
- [ ] Balance knobs in `tuning.py`; the training sonar chapter teaches sprint-and-drift and clearing baffles.
- [ ] Waterfall shows the baffle band.

## Notes

The towed array ([[35]]) is the counter to the baffles.
