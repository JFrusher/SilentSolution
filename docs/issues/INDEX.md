# Issue drafts

Drafts from the v0.2.0 repository scan: bugs found and confirmed with headless probes, improvements, and the
feature roadmap. Each file is one GitHub issue (front matter: title, labels, milestone). `[[NN]]` in a body is a
cross-reference to another draft; the script turns it into a real `#number`.

🟢 = good first issue.

## Create them on GitHub

```powershell
winget install --id GitHub.cli -e        # once; then reopen the terminal
gh auth login                            # GitHub.com, HTTPS, login with a web browser
gh auth refresh -s project               # adds the Project-board scope
uv run docs/issues/create_issues.py      # from the repo root
```

It creates 21 labels, 4 milestones and 41 issues, links the cross-references, and adds every issue to a
**Silent Solution Roadmap** Project board linked to the repo. It's safe to re-run: existing labels, milestones and
issues (by title) are reused, and it only edits issues that still have unresolved `⟦draft NN⟧` placeholders.
Once the issues exist, this folder can be deleted.

### v0.2.1 Fixes (15)

| # | Issue | Type | Priority | Areas |
|:-:|---|---|---|---|
| 01 | [Waves stall for 40–90+ minutes while an enemy sub or escort lingers nearby](01-waves-stall-lingering-warships.md) | bug | high | ai |
| 02 | [Enemy sub with no torpedoes left shadows the boat forever (47 m away, same depth)](02-empty-sub-shadows-forever.md) | bug | high | ai |
| 03 | [Rebinding a held action to a key with no name crashes the game every frame](03-rebind-unnamed-key-crash.md) | bug | high | settings |
| 04 | [F1 key card drops the game to ~14 FPS and its paper shimmers](04-key-card-fps-shimmer.md) 🟢 | bug | medium | ui |
| 05 | [Esc quits the whole game instantly mid-patrol, losing the patrol](05-esc-quits-without-confirm.md) | bug | medium | ui |
| 06 | [Key card and training text ignore rebound keys, and the key card is out of date](06-key-card-ignores-bindings.md) | bug | medium | ui, settings, tutorial |
| 07 | [Clicking or scrolling on the TMA plot moves the hydrophone dial to a wrong bearing](07-tma-click-moves-dial.md) 🟢 | bug | low | sensors, ui |
| 08 | ["END OF SPOOL" can never happen: the wire is longer than the torpedo's run](08-end-of-spool-unreachable.md) 🟢 | bug | low | fire-control |
| 09 | [Firing is allowed when the solution is beyond torpedo range](09-fire-beyond-range.md) 🟢 | enhancement | low | fire-control |
| 10 | [Misleading messages: resupply amounts and "[R] NEW PATROL"](10-misleading-messages.md) 🟢 | bug | low | ui |
| 11 | [Campaign: losing the boat jumps straight to the debrief](11-campaign-loss-skips-sinking.md) | bug | low | campaign, ui |
| 12 | [High-score table fills with 0 GRT failed patrols](12-high-scores-zero-grt.md) 🟢 | bug | low | campaign |
| 13 | [Add an MIT licence](13-add-mit-license.md) 🟢 | chore | medium | repo |
| 14 | [CI: run checks.py headless on every push and pull request](14-ci-run-checks.md) | chore | medium | repo |
| 15 | [Adopt ruff for lint and format, and fix the existing warnings](15-adopt-ruff.md) | tech-debt | low | repo |

### v0.3 Polish & UX (10)

| # | Issue | Type | Priority | Areas |
|:-:|---|---|---|---|
| 16 | [Pause menu: resume, settings, quit to title, quit game](16-pause-menu.md) | feature | high | ui, settings |
| 17 | [Objective tracker and a "return to base" cue for campaign patrols](17-objective-tracker.md) | feature | medium | campaign, ui |
| 18 | [Waterfall time scale: only ~21 s of history is too short to see bearing drift](18-waterfall-time-scale.md) | enhancement | medium | sensors, ui |
| 19 | [Damage alarm lamp and audible alarm when systems are knocked out](19-damage-alarm.md) 🟢 | enhancement | low | damage, ui |
| 20 | [Seeded per-world RNG instead of the global random module](20-seeded-world-rng.md) | tech-debt | medium | sim |
| 21 | [Mid-patrol save and load (campaign and endless)](21-mid-patrol-save-load.md) | feature | medium | sim, campaign |
| 22 | [After-action replay plot at the debrief](22-after-action-replay.md) | feature | medium | ui, campaign |
| 23 | [Achievements and medals](23-achievements-medals.md) | feature | low | campaign |
| 24 | [Hover tooltips on every control](24-hover-tooltips.md) | feature | low | ui |
| 25 | [Localisation: move player-facing strings into a translatable table](25-localisation.md) | feature | low | ui |

### v0.4 Deeper Realism (12)

| # | Issue | Type | Priority | Areas |
|:-:|---|---|---|---|
| 26 | [Own-ship flow noise and baffles (and escort sonar degraded at speed)](26-flow-noise-baffles.md) | feature | high | sensors, ai |
| 27 | [Doppler and aspect-dependent target strength](27-doppler-target-strength.md) | feature | medium | sensors, audio |
| 28 | [Variable thermal layer, convergence zones and bottom bounce](28-variable-layer-convergence-zones.md) | feature | medium | sensors, sim |
| 29 | [Enemy diesel subs must snorkel to charge, opening windows to hunt them](29-enemy-subs-snorkel.md) | feature | medium | ai |
| 30 | [Hull collisions and ramming](30-collisions-ramming.md) | feature | medium | sim, ai |
| 31 | [Ship classes and names, with class-specific tonnage, speed, sonar and weapons](31-ship-classes-names.md) | feature | medium | sim, ai, content |
| 32 | [High-pressure air bank and trim/buoyancy](32-hp-air-trim.md) | feature | low | sim |
| 33 | [Maritime patrol aircraft that hunt masts and snorkels](33-patrol-aircraft.md) | feature | medium | ai |
| 34 | [Surface-search radar on escorts and aircraft, and an ESM mast for the boat](34-radar-esm.md) | feature | medium | sensors, ai |
| 35 | [Towed passive array](35-towed-array.md) | feature | low | sensors |
| 36 | [Torpedo types: steam, electric, pattern-runner and acoustic homer](36-torpedo-types.md) | feature | medium | fire-control |
| 37 | [Leaks should join the damage-control queue instead of repairing in parallel](37-leaks-in-damage-queue.md) | enhancement | low | damage |

### v0.5 More Content (4)

| # | Issue | Type | Priority | Areas |
|:-:|---|---|---|---|
| 38 | [Data-driven scenario files and a Quick Battle setup screen](38-scenarios-quick-battle.md) | feature | high | content |
| 39 | [New mission types: shadow, reconnaissance, minelaying, breakout, rescue](39-new-mission-types.md) | feature | medium | content, campaign |
| 40 | [Second campaign with a patrol-area map and branching outcomes](40-second-campaign-map.md) | feature | medium | campaign, content |
| 41 | [Neutral shipping and rules of engagement](41-neutrals-roe.md) | feature | medium | ai, content |
