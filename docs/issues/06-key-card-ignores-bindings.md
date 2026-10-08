---
title: Key card and training text ignore rebound keys, and the key card is out of date
labels: bug, area:ui, area:settings, area:tutorial, priority:medium
milestone: v0.2.1 Fixes
fixed_in: e9b6d18
---
## Summary

Every console key can be rebound, but the F1 key card and the training text are hard-coded with the default
keys. A player who moves FIRE to <kbd>G</kbd> is still told to press <kbd>F</kbd>. The card has also fallen
behind the game.

## Stale or wrong entries on the key card

[`workstation.py:793-804`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/workstation.py#L793-L804)

- `F 1 2: fire next / tube 1 / tube 2`. <kbd>F</kbd> now fires a **salvo** across SPREAD.
- `T: tactical scope range / click scope`. A click on the scope now steers a wired fish when one is selected.
- <kbd>F6</kbd> (skip drill) is missing.
- `P / F1 / ESC` says Esc quits; after [[05]] it confirms.

## Training text with literal keys

`tutorial.py` briefs and goals mention `(M)`, `SPACE`, `F2`, `F4`, `F5`, `(N)`, `(T)` and more, for example
[`tutorial.py:194-211`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/tutorial.py#L194-L211).

## Proposed approach

- Add `settings.label(action)`, returning the bound key's display name (`F`, `SPACE`, `F5`, `[`).
- Build the key card from a table of `(action(s), description, mouse hint)`, filled in from the bindings. Cache
  the rendered card ([[04]]) and rebuild it when the bindings change.
- In the training script, write keys as tokens such as `{FIRE}` or `{TMA PAGE}` and format them at brief time.
- Fix the stale descriptions listed above.

## Acceptance criteria

- [ ] Rebinding FIRE to G makes the key card and every training mention say G.
- [ ] The key card lists every action in `settings.KEYS`, with no stale text.
- [ ] `test_tutorial.py` still passes; add a check that no brief contains an unformatted `{...}` token.
