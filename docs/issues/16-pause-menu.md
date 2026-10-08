---
title: 'Pause menu: resume, settings, quit to title, quit game'
labels: feature, area:ui, area:settings, priority:high
milestone: v0.3 Polish & UX
---
## Motivation

Today <kbd>P</kbd> shows **PATROL PAUSED / [P] RESUME** and nothing else. Settings can only be opened from the
title, so changing the volume or a key binding means abandoning the patrol. There's no way back to the title short
of dying, and <kbd>Esc</kbd> quits the app ([[05]]).

## Proposal

A pause menu on the CRT, opened with <kbd>P</kbd> or <kbd>Esc</kbd> during a patrol:

```
        PATROL PAUSED
   [ENTER]  RESUME
   [S]      SETTINGS        (the existing settings page; Esc returns here)
   [T]      QUIT TO TITLE   (confirm: endless runs are scored, campaign patrols abandoned)
   [Q]      QUIT GAME       (confirm)
```

- Mouse: the same `station.buttons` mechanism as the title and career pages.
- In training, `QUIT TO TITLE` becomes `CHAPTER LIST`.
- The settings page needs a "return to" target (`TITLE` or `PAUSE`); `SettingsMenu.key()` already returns `"BACK"`.
- Settings changed mid-patrol take effect immediately: volumes are read live; key bindings are read on every key
  event; large text applies to new teleprinter lines.

## Acceptance criteria

- [ ] P and Esc open the menu; Enter or P resumes.
- [ ] Settings can be changed mid-patrol and return to the paused patrol.
- [ ] Quit to title and quit game both confirm; endless quits are scored; campaign quits don't count as a loss.
- [ ] Supersedes the minimal confirm box from [[05]].
- [ ] The F1 key card ([[06]]) lists the new menu.
