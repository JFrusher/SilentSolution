---
title: Add an MIT licence
labels: chore, area:repo, priority:medium, good first issue
milestone: v0.2.1 Fixes
---
## Summary

The repository has no `LICENSE`, which legally means all rights reserved: nobody can reuse, fork or contribute
with clear terms. We've decided on **MIT**.

## Tasks

- [ ] Add `LICENSE` with the MIT text, `Copyright (c) 2026 Jacob Frusher`.
- [ ] Add `license = "MIT"` (and `license-files = ["LICENSE"]`) to `pyproject.toml`.
- [ ] README: a licence badge and a short "Licence" line in the footer.
- [ ] Make sure the PyInstaller build ships the licence notices for bundled dependencies (pygame-ce is LGPL; NumPy
      is BSD). Add a `THIRD-PARTY-NOTICES.txt` next to the exe in releases.

## Acceptance criteria

- [ ] GitHub shows "MIT license" in the repo sidebar.
- [ ] Release assets include the third-party notices.
