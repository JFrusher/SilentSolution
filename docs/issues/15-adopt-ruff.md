---
title: Adopt ruff for lint and format, and fix the existing warnings
labels: tech-debt, area:repo, priority:low
milestone: v0.2.1 Fixes
fixed_in: 33a0850
---
## Summary

Linting is ad hoc (`uvx pyflakes`) and there is no formatter or line-length rule. 20+ lines run past 120
characters (for example `sim.py:58` at 153 characters, `tutorial.py:235` at 173, and `console.py:443`), and there
are small PEP 8 gaps, such as a missing blank line before `def silhouette_class` and an orphaned comment at
`sim.py:53`.

## Tasks

- [ ] Add `[tool.ruff]` to `pyproject.toml`: `line-length = 120`, `target-version = "py311"`, and a sensible rule
      set (`E`, `F`, `W`, `I`, `B`, `UP`; consider leaving out `E731` for the inline-lambda style used in key maps).
- [ ] Run `uvx ruff check --fix` and `uvx ruff format --check`; decide whether to adopt the formatter or lint only.
      The code uses deliberate aligned comments, which the formatter would rewrap, so lint-only may be preferable.
- [ ] Fix the remaining findings by hand.
- [ ] Have `checks.py` (and the CI from [[14]]) run `ruff check`.
- [ ] Update `CLAUDE.md` "Checks" with the lint command.

## Acceptance criteria

- [ ] `uvx ruff check .` is clean.
- [ ] `checks.py` fails on lint errors.
