---
title: Maritime patrol aircraft that hunt masts and snorkels
labels: feature, area:ai, priority:medium
milestone: v0.4 Deeper Realism
---
## Motivation

In the WWII and early Cold War era, aircraft were the snorkel's worst enemy. Today the only cost of raising masts
is the lookouts on nearby ships. Aircraft make the battery and snorkel economy a real gamble.

## Proposal

- An **aircraft contact type** that flies search patterns over the patrol area (more over convoys, by difficulty
  and patrol). It's not on sonar; heard faintly through the hull only when very close and shallow.
- **Detection:** visual (masts, wake, smoke) at long range in clear weather, and radar ([[34]]) against
  a raised snorkel or periscope.
- **Attack:** on detection, the aircraft runs in and drops bombs or depth charges at the mast's position (the same
  charge model), then calls in the escorts (`report_contact`).
- **Player cues:** an ESM intercept ([[34]]) and the periscope view of the aircraft (a silhouette in the sky panorama)
  give warning, and a crash dive (<kbd>Q</kbd>/<kbd>E</kbd>, or a new **DIVE** button) is the answer.
- Aircraft endurance, so they come and go.

## Acceptance criteria

- [ ] Snorkelling with aircraft about is visibly riskier; there's an exposure-meter contribution from
      aircraft.
- [ ] Aircraft are drawn in the periscope sky when in view.
- [ ] A crash dive started on an ESM warning usually avoids the attack.
- [ ] Difficulty and patrol data control aircraft presence.
