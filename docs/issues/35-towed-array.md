---
title: Towed passive array
labels: feature, area:sensors, priority:low
milestone: v0.4 Deeper Realism
---
## Motivation

A towed array trails a long hydrophone line astern: far better low-frequency gain and coverage of the hull array's
baffles ([[26]]). It brings its own trade-offs: **left/right ambiguity**, a long time to stream and recover, and
uselessness during tight turns. It stretches the era (1970s onward), so make it a **refit or difficulty option**,
not a default.

## Proposal

- **Stream/recover** with a key or switch on the masts panel. It takes ~60 s each way; speed limited while streamed
  (wire strain above ~12 kt).
- **Second waterfall** (a CRT page or split view): bearings are relative to the array axis, and every contact
  appears twice, mirrored about the axis (port/starboard ambiguity). A course change resolves it: the true trace
  moves the right way.
- **Array instability:** during and shortly after a turn, the array is noisy and inaccurate until it straightens.
- **Low-frequency bias:** better against quiet subs and distant merchants; worse against high-frequency torpedoes.
- A campaign refit (alongside the existing `campaign.UPGRADES`) or a scenario option.

## Acceptance criteria

- [ ] Streaming and recovering take time and are shown on the masts panel.
- [ ] The towed waterfall shows mirrored traces, and a turn resolves the ambiguity.
- [ ] It covers the hull array's baffles.
- [ ] Turning hard degrades it temporarily; going too fast parts it.
