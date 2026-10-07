# Periscope & Snorkel — design and build plan

> **Status: built (all six phases).** Departures from the plan:
> - The sea is shaded at 1/3 resolution, not 1/2: about 9 ms per eyepiece frame, against 15+ ms at 1/2.
> - The sky is a pre-rendered 360° panorama.
> - Exposure is shown in the CRT readout's SEA row, not in the eyepiece strip.
> - Escorts that go on alert now also alarm their convoy, which wasn't in the plan.
> - A depth order now cancels an emergency blow; this fixed a bug found by the tutorial bot.

**Decisions (agreed):** two masts (periscope for the view, snorkel for the diesels), full-screen eyepiece,
daylight + weather only (no day/night), realistic colour.

**One-line pitch:** at periscope depth you can *see* — exact bearings, ranges, ship types, aspect — but every
second a mast is up you can be seen, and the snorkel's diesel makes you deaf and loud. The station stops being
a safe abstraction exactly when you most want information.

---

## 1. Rules of the masts (world side, `sim.py`)

### 1.1 Depth envelope
| Own keel depth `z` | What happens |
|---|---|
| > 18 m | masts can't be raised; raised masts are lowered automatically when you order deeper than 20 m ("LOWERING MASTS") |
| 14–18 m | **periscope depth**. Scope head clears the water by `17 - z` m; snorkel head clear if `z <= 16` |
| 11–14 m | tower awash — **broaching**: visible from very far, warning lamp |
| < 11 m | surfaced |

- Waves move the boat: at periscope depth `z` wobbles by ±0.15 × wave height. In heavy seas the lens dips under
  (view goes green and blank for a moment) and the snorkel head valve shuts.
- **Periscope depth button** on the diving station (key `G`): orders 15 m — the depth almost every mast action wants.
- Replaces today's automatic snorkeling (`z <= 15.5 and battery < 100`) with an explicit mast.

### 1.2 Speed limits
- Periscope up above ~6 kt leaves a **feather** (spray wake, much more visible); above ~10 kt the view shakes and,
  on Iron Captain, the mast can be **damaged** (can't raise until repaired, ~120 s).
- Snorkel up above ~8 kt risks flooding the head: diesels trip, battery stops charging.

### 1.3 Snorkel / diesel
- With the snorkel up and its head clear, the diesels run: battery charge (+0.35 %/s, already exists), O₂ refills.
- Costs:
  - **Loud:** self-noise +0.8 (already exists) and a visible exhaust plume.
  - **Deaf:** your own waterfall noise floor rises by about 40 and hydrophone SNR drops about 3×. The sonar is
    mostly blind while you charge. This is the core tension.
  - **Head valve:** in sea state ≥ 3 waves randomly shut it. The diesels stall for 2–5 s and the crew's ears pop
    (log message + lamp flicker).

### 1.4 Sea state (`Ocean`)
- New `wind` and `sea_state` (0–6). Derived from the existing rain fronts plus a slow random walk.
  - Wave height Hs: 0.2 m (calm) to 4 m (storm).
- New `visibility` (m): clear 12 km, rain 4 km, storm 1.5 km.
- Used by: the periscope picture, depth wobble, head-valve shutting, lookouts (whitecaps hide a feather), spray on
  the lens.

---

## 2. Being seen (world side, `ai.py`)

The current lookout model (`ShipAI._sighted`) is a hard 3 km yes/no switch. It becomes a **probability per second**:

```
p = base[mast] * feather(speed) * alertness * range_factor * weather / (1 + 0.5 * sea_state)
range_factor = clamp(1 - r / reach[mast], 0, 1) ** 2,   reach scaled by visibility
```

| Mast | base /s | reach (clear) | why |
|---|---|---|---|
| periscope | 0.06 | 3 km | small head, feather at speed |
| snorkel | 0.12 | 6 km | bigger head + exhaust smoke |
| both | 0.15 | 6 km | |
| broached / surfaced | 1.0 | 8 km | a hull on the surface |

- `feather = 1 + (kt / 4) ** 2`.
- `alertness`: unaware merchant 0.7, unaware escort 1.5, searching or alert escort 2.5 (they are looking for you).
- Difficulty multiplier: Cadet ×0.5, Commander ×1, Iron Captain ×1.5.
- **When spotted:** the observer marks you accurately (50–150 m); escorts go to ALERT and run at the mast;
  merchants alarm the convoy. All of that is existing behaviour, it just has a new trigger.
- **Signal lamps:** an escort that has spotted you flashes them. That is something you can *see* through the
  scope, so being spotted is observable in every mode, not only on Cadet.
- **Exposure meter** (operator side): an honest estimate from what *you* know — masts up, own speed, sea state,
  range to the nearest ship you can see.
  - Cadet: shows the real probability, plus a "SPOTTED!" banner.
  - Others: estimate only.

---

## 3. What the scope sees (operator side, `main.py` → new `PeriscopeOptics` sensor)

Same decoupling rule as the sonar: the renderer never reads the world, only a list of **sightings** produced by
the optics sensor.

- **Active only when** the scope is up and the lens is above water (wave dips black it out).
- **Visibility limit:** range ≤ weather visibility, with contrast fading into haze.
- **Hull-down:** eye height ~1.5 m puts the horizon about 4.4 km away. Visible height of a ship part is
  `H - max(0, r - d_h)^2 / (2 * R_eff)` (R_eff ≈ 7.6e6 m with refraction).
  - Far ships show only masts and funnel tops; near ships show their whole hull.
- **Each sighting carries:**
  - true bearing (±0.2°, far better than sonar)
  - range, silhouette class, aspect angle (the target's heading relative to the line of sight), speed for the
    bow wave
  - funnel smoke, signal-lamp state, zig-zag and alarm cues
- **Visual events** from a new world-side queue, which also feeds the sonar:
  - ships sinking: a 3-minute settle animation using `world.sunk` with a sinking time
  - water columns from torpedo and depth-charge explosions, depth-charge splashes
  - torpedo wakes (own and hostile) inside 2 km
- **Mark from the scope (`M`)** puts the *exact* bearing into the TDC. Rangefinder: with a ship centred at high
  power, the known mast height of its class over its angular height gives range, with a ±5–10 % error. A
  wrongly identified class gives a wrong range. This is the payoff for exposing yourself.

---

## 4. Drawing the surface (new `graphics/periscope.py`)

Budget: **≤ 8 ms per frame**. The station isn't drawn while you are at the eyepiece, which frees roughly 6 ms.

1. **Sky.** Weather-graded gradient (clear blue to overcast grey), a soft sun glow at a fixed bearing, and a
   pre-rendered 360° cloud strip scrolled by scope bearing (one blit). Rain darkens and flattens it.
2. **Sea.** NumPy at half resolution (about 340×130 px below the horizon) per frame:
   - each pixel row maps to a distance (eye height / tangent of the depression angle) and then to world
     coordinates along its bearing
   - waves are the sum of 3–4 sine swells along the wind; shading comes from slope · light
   - whitecaps where the slope is steep and the sea state high; haze blends into the horizon colour
   - smooth-scaled ×2. The horizon bobs and tilts with the boat's motion in the swell.
3. **Ships.** Per-class silhouette polygons in normalised hull units:
   - **merchant:** fo'c'sle, midships bridge, funnel, two masts with booms
   - **tanker:** bridge aft
   - **escort:** raked bow, gun mounts, low funnel, lattice mast
   - Sizing: projected width = `L*|sin(aspect)| + B*|cos(aspect)|`, mirrored by heading; height from range; parts
     below the horizon clipped for hull-down
   - Detail: dark grey with a haze blend and a lit edge, a little roll and pitch, a bow wave scaled by speed, and
     funnel smoke as alpha puffs drifting downwind
   - **Sinking ships:** they list and settle, with fire glow and a smoke column.
4. **Effects.** Torpedo wakes as white streaks on the water, explosion water columns plus a flash, depth-charge
   splashes, and an escort's flashing signal lamp.
5. **Optics.**
   - circular eyepiece mask, reticle with rangefinder ticks, bearing scale (relative and true), power indicator
     (1.5× / 6×)
   - chromatic edge fringe, vignette
   - rain streaks and droplets on the glass; **wash-over** (green, bubbles, then droplets running off) when a wave
     covers the lens
   - shake when you go too fast with the scope up
6. **Eyepiece warning strip** along the bottom edge:
   - depth / speed / battery
   - TORPEDO, ENEMY SONAR, EXPOSURE and BROACH lamps
   - the latest sonar log line, flashing on new critical events
   - The game stays fully playable muted: every warning has a visual twin.

---

## 5. Station integration (`main.py`)

**Controls** (all also clickable):

| Key | Action |
|---|---|
| `U` | periscope up / down |
| `K` | snorkel up / down |
| `G` | periscope depth (orders 15 m) |
| `V` | look through the scope / back to the station |
| A/D or mouse drag | *(eyepiece)* train the scope |
| mouse wheel or `TAB` | *(eyepiece)* switch power |
| `M` | *(eyepiece)* mark bearing + rangefinder range into the TDC |

Telegraph, helm and depth keys keep working while you look, so you can steer blind.

- **Console:** two mast levers with lamps (SCOPE, SNORT) beside the depth-order dial, and a LOOK button. The
  diving-station row gets a little tighter.
- **Warning lamps:** SNORKEL → **DIESEL**; new **MASTS UP / EXPOSED** (amber when up, flashing red at high
  risk) and **BROACH**. The lamp column gets 8 slots at a tighter pitch.
- **Gauges:** the self-noise gauge reflects the diesel. The exposure meter goes in the eyepiece strip and in the
  CRT hydrophone readout.
- **Audio:**
  - hydraulic whine when a mast moves
  - a diesel rumble loop while snorkeling
  - wind and wave slap while looking
  - a head-valve thunk
- **Teletype:** messages queue while you look; critical ones also flash on the strip.

---

## 6. Difficulty

| | Cadet | Commander | Iron Captain |
|---|---|---|---|
| detection multiplier | ×0.5 | ×1 | ×1.5 |
| exposure meter | true risk + SPOTTED banner | own-factor estimate | own-factor estimate |
| mast damage from speed | no | no | yes |
| head-valve closures | rare | normal | frequent |
| auto-lower when diving | instant | instant | 4 s (still exposed) |

---

## 7. Tutorial

Replace the current "blow and snorkel" drill with a mast sequence:
1. Order periscope depth (G).
2. Raise the scope (U); look (V).
3. Train onto the merchant, switch power, read its aspect.
4. Mark bearing + range (M), then compare it with the sonar range.
5. Lower the scope.
6. Raise the snorkel and charge to 60 %. Notice the waterfall drowning in your own diesel.
7. Lower the snorkel before diving.

The escort drill can then *start* from being spotted on the scope. Update `test_tutorial.py`'s bot to match.

---

## 8. Build phases (each ends runnable and tested)

1. **Mast rules.** Masts, depth envelope, auto-lower, speed limits, snorkel/diesel, head valve, sea state and
   visibility; remove auto-snorkel. Update the tutorial snorkel drill and bot.
   *Tests:* can't raise below 18 m; deep order lowers masts; battery charges only with the snorkel up and its
   head clear; diesel raises self-noise and own-sonar noise; heavy sea shuts the head valve.
2. **Being seen.** Probability-based lookouts, alertness, difficulty multiplier, exposure estimate, signal lamps.
   *Tests (seeded Monte Carlo):* snorkel spotted sooner than the scope; speed raises risk; 5 km in a storm almost
   never spotted in 60 s; an escort at 1 km spots a snorkel within ~20 s and goes ALERT.
3. **Optics sensor + visual events.** Sightings, hull-down, visibility, rangefinder; a sinking/explosion/wake
   effect queue.
   *Tests:* a ship at 15 km is invisible, at 8 km shows masts only, at 3 km shows the full hull; storm visibility
   cuts sightings; scope bearing error ≤ 0.3°; rangefinder within 10 % on a correct class.
4. **Renderer.** Sky, sea, ships, effects, optics.
   *Checks:* headless frame timing ≤ 8 ms; screenshots in calm, rain and storm; ships at several aspects and
   hull-down; a sinking ship; wash-over.
5. **Station.** Mast levers, lamps, LOOK mode, eyepiece strip, scope mark → TDC, audio, F1 card.
   *Checks:* headless playthrough with the scope in use; layout screenshots.
6. **Tutorial and balance.** New drills, updated bot; detection numbers tuned so a careful 30 s look is usually
   safe, while a 2-minute snorkel next to an escort usually isn't.

**Files:** `sim.py`, `ai.py`, `main.py`, `tutorial.py`, `test_sim.py`, `test_tutorial.py`; new
`graphics/periscope.py` and `test_periscope.py`.

---

## 9. Risks and open points

- **Performance:** a full-res NumPy sea would cost 15–20 ms. Half-res plus smooth-scale and skipping the station
  is the plan; fallback is quarter-res sea with more foam detail drawn as sprites.
- **"Real-seeming" has a ceiling with procedural vector art.** Haze, bobbing, smoke, foam and optical artefacts
  carry most of the realism; silhouettes will read as period recognition-manual shapes, not 3D models.
- **Balance:** detection numbers need real playtesting; all constants live in one block in `ai.py`.
- **Behaviour change:** removing auto-snorkel makes battery modes harder (you must choose to expose yourself).
  That's intended, and it changes current play.
- **Console crowding:** the diving station and lamp column get busier; I'll check it with layout screenshots.
- **Not in scope (possible later):** night, enemy aircraft spotting snorkels, radar, surfacing to run on the
  diesels, deck gun.
