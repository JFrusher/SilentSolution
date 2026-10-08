---
title: 'Localisation: move player-facing strings into a translatable table'
labels: feature, area:ui, priority:low
milestone: v0.3 Polish & UX
---
## Motivation

Every player-facing string is an inline literal or f-string: roughly 500 of them across `console.py`, `tutorial.py`,
`campaign.py`, `workstation.py` and `settings.py`. Translating the game, or even copy-editing it, means hunting
through code.

## Proposal

- A `strings/en.toml` (or JSON) table keyed by id, with Python `str.format` placeholders:
  `log.echo = "ECHO {brg:05.1f}R {yd:,.0f} YD"`.
- A tiny `t(key, **kw)` helper; the current language is chosen in Settings.
- Extract in stages: teletype and log lines first (most text), then the tutorial, then station labels (engraved
  labels may need per-language font fitting; `art.button` already auto-fits).
- A check that every key exists in every language file and placeholders match.

## Out of scope

Right-to-left scripts and CJK fonts. The CRT and console fonts would need bundled fonts.

## Acceptance criteria

- [ ] No player-facing literal remains in game code (enforced by a test that greps for uppercase string literals
      outside `strings/`, with an allow-list).
- [ ] A pseudo-locale (`xx`, which wraps every string in `[[ ]]` and pads it 30%) runs the whole tutorial bot
      without errors, which catches layout overflow.
