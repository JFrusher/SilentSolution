---
title: 'Misleading messages: resupply amounts and "[R] NEW PATROL"'
labels: bug, area:ui, priority:low, good first issue
milestone: v0.2.1 Fixes
fixed_in: a6a3e74
---
## Summary

Two small text bugs that tell the player something untrue.

1. **Resupply.** The wave-clear teletype always says `TENDER RESUPPLY: +4 TORPEDOES, +2 NOISEMAKERS`, but the
   director caps the racks at 12 torpedoes and 6 noisemakers. With full racks the player gets nothing and is told
   otherwise.
2. **Game over.** The endless game-over box says `[R] NEW PATROL`, but <kbd>R</kbd> returns to the title screen.

## Where

- [`ai.py:545-546`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/ai.py#L545-L546): the caps.
- [`console.py:560-561`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/console.py#L560-L561): the message.
- [`workstation.py:279-281`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/workstation.py#L279-L281) and
  [`main.py:110-112`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/main.py#L110-L112): the game-over box and the R handler.

## Proposed fix

1. Have the director put the actual amounts added into the `WAVE_CLEAR` event and print those (`+2 TORPEDOES
   (RACKS FULL)`).
2. Either make <kbd>R</kbd> start a new patrol at the same difficulty and add **[T] TITLE**, or relabel it
   `[R] TITLE`. A restart is the more useful option.

## Acceptance criteria

- [ ] Resupply text matches what was actually loaded (test with full racks).
- [ ] The game-over box describes what each key does.
