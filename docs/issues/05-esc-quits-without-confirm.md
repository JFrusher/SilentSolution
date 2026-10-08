---
title: Esc quits the whole game instantly mid-patrol, losing the patrol
labels: bug, area:ui, priority:medium
milestone: v0.2.1 Fixes
fixed_in: 6e75db6
---
## Summary

On the patrol screen, the game-over screen and the title, <kbd>Esc</kbd> closes the application immediately.
There's no confirmation and no way back to the title. A single slip loses a 40-minute campaign patrol (which
doesn't count toward the career) or an endless run (which never reaches the high-score table).

## Where

[`main.py:36-40`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/main.py#L36-L40): `quit_key` exits on Esc
in every state except the `SETTINGS`, `CAREER`, `DEBRIEF` and `CHAPTERS` pages.

## Proposed fix (minimal, for v0.2.1)

- During `PLAY`, Esc pauses and shows a confirm box on the CRT: **QUIT PATROL? [Y] YES  [N] NO**. Yes returns to
  the title (endless runs are scored as they would be on game over).
- On the title, Esc still quits.
- The window close button still quits immediately; that's an explicit OS action.

The full pause menu (resume / settings / quit to title / quit game) is [[16]], which replaces this box.

## Acceptance criteria

- [ ] Esc during a patrol never closes the app without a second confirming key.
- [ ] Confirming quit during an endless patrol records the high score.
- [ ] Confirming quit during a campaign patrol doesn't count it as a loss and doesn't advance the career.
- [ ] Training: Esc offers to return to the chapter list.
