---
title: High-score table fills with 0 GRT failed patrols
labels: bug, area:campaign, priority:low, good first issue
milestone: v0.2.1 Fixes
fixed_in: afe089b
---
## Summary

`Career.record()` adds a high-score entry for every patrol, including failed or lost ones with `0` GRT. Endless
runs that sink nothing are recorded too. The top-ten table can fill with zero rows that push nothing off but add
noise to the career page.

## Where

- [`campaign.py:89-99`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/campaign.py#L89-L99): `record()`
- [`main.py:136-138`](https://github.com/JFrusher/SilentSolution/blob/v0.2.0/main.py#L136-L138): the endless game-over score

## Proposed fix

Make `add_score()` ignore `grt <= 0`. Keep the patrol **log** entry; it's history, not a score.

## Acceptance criteria

- [ ] A 0 GRT patrol or run adds a log line but no high-score row.
- [ ] `campaign.py` self-check covers it.
