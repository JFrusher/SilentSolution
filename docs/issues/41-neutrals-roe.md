---
title: Neutral shipping and rules of engagement
labels: feature, area:ai, area:content, priority:medium
milestone: v0.5 More Content
---
## Motivation

Today every contact is a legitimate target, so classification ends at "merchant or warship". Neutral shipping
(hospital ships, flagged neutrals, fishing boats) forces positive identification before firing, which is exactly
what the periscope and the recognition work are for. Getting it wrong should hurt.

## Proposal

- **New contact flag:** `allegiance = enemy | neutral | protected` (hospital ship), set per ship or per group in
  scenarios ([[38]]). Neutrals sail independent or on their own routes and are not alarmed by convoys.
- **Identification:**
  - Sonar alone can't tell a neutral freighter from an enemy one.
  - The periscope at high power shows flags or markings (neutral colours painted on the hull, hospital crosses),
    and a stadimeter mark on a neutral logs `NEUTRAL MARKINGS`.
  - Lighting is constant, so markings are visible within the visibility range; rain and range limit it.
- **ROE per scenario:** `weapons_free`, `positive_id` (must mark before firing at merchants) or `no_merchants`.
- **Consequences:**
  - Sinking a neutral or protected ship subtracts heavily from the patrol score.
  - It's flagged in the debrief ("SS *Nordstern*, neutral: COURT OF INQUIRY").
  - In the campaign it can cost promotion or the patrol.
- **TDC safety:** with `positive_id` ROE, firing at an unidentified merchant needs a double press, with the warning
  `TARGET NOT IDENTIFIED`.

## Acceptance criteria

- [ ] Neutral ships appear in scenarios, look different through the periscope at high power, and sound the same as
      enemy merchants on sonar.
- [ ] Sinking a neutral is penalised and called out in the debrief.
- [ ] ROE modes behave as specified (tests for each).
- [ ] The training periscope chapter includes an identification drill.
