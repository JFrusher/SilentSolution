---
title: 'CI: run checks.py headless on every push and pull request'
labels: chore, area:repo, priority:medium
milestone: v0.2.1 Fixes
---
## Summary

All six suites run headless in about 40 s (`uv run checks.py`, SDL dummy drivers), but only when someone remembers
to run them. Add a GitHub Actions workflow that runs them on every push to `develop` / `main` and on every pull
request, so a regression can't be merged into `develop` unnoticed. Tests only: no builds or releases.

## Proposed workflow

`.github/workflows/checks.yml`:

```yaml
name: checks
on:
  push: { branches: [develop, main] }
  pull_request:
jobs:
  checks:
    runs-on: ubuntu-latest
    env: { SDL_VIDEODRIVER: dummy, SDL_AUDIODRIVER: dummy }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv run checks.py
```

## Things to verify

- [ ] `pygame-ce` wheels install on `ubuntu-latest`, and the dummy audio driver initialises (otherwise
      `AudioSynthesizer` already falls back to silent).
- [ ] `test_periscope.py` asserts eyepiece frame time under 40 ms. CI runners are slower and noisy, so relax it
      under `CI=true` or report it as a warning.
- [ ] Fonts: `SysFont` falls back to pygame's default font on Linux; any test that depends on text metrics must
      still pass.

## Acceptance criteria

- [ ] The workflow is green on `develop`.
- [ ] A status badge is added to the README.
- [ ] Branch protection on `main` requires the check (manual repo setting; note it in the PR).
