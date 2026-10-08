---
title: Rebinding a held action to a key with no name crashes the game every frame
labels: bug, area:settings, priority:high
milestone: v0.2.1 Fixes
fixed_in: 7f79fdf
---
## Summary

`settings.bind()` stores `pygame.key.name(k)`, which is `""` for keys that SDL can't name: some media, OEM or
international keys, and `K_UNKNOWN`. Held actions (train the dial or scope, rudder, TDC adjust) are polled every
frame through `settings.code(action)`, which calls `pygame.key.key_code("")`. That raises `ValueError`, so the
game crashes on the next frame.

## Repro

```python
import pygame; pygame.init(); pygame.display.set_mode((10, 10))
import settings
settings.bind("TRAIN LEFT", 0)   # any key whose pygame.key.name() is ""
settings.code("TRAIN LEFT")      # ValueError: unknown key name
```

In game: **Settings → TRAIN LEFT → Enter → press a media key**, then start a patrol. It crashes immediately.

## Where

- [`settings.py:83-93`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/settings.py#L83-L93): `bind()` only
  refuses `RESERVED` names.
- [`settings.py:67-68`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/settings.py#L67-L68): `code()`.
- [`console.py:468`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/console.py#L468): polled every frame.
- `load()` already drops invalid names (`_valid`), so the crash only lasts for the session it was bound in, but it
  is still a hard crash.

## Proposed fix

- In `bind()`, refuse any key whose name is empty or fails `_valid()`, and return `"KEY CAN'T BE BOUND"`.
- Defence in depth: `code()` falls back to the default binding if the stored name won't resolve.

## Acceptance criteria

- [ ] Pressing an unnamed key while rebinding shows a refusal note and keeps the old binding.
- [ ] `settings.py` self-check gains a case: `bind(action, 0)` returns an error and leaves the binding unchanged.
- [ ] No code path can raise from `settings.code()` with a stored binding.
