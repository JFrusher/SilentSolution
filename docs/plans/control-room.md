# Control room — design and build plan

> **Status: planned.** The walkable room exists (`control_room.py`, `graphics/room3d.py`, PR #5); everything
> below splits the all-in-one console into crewed, job-specific stations.

**Decisions (agreed):**
- You are the **captain**, and an AI **crew** mans every station.
- **Conning orders work from anywhere**, through a radial menu plus hotkeys. The crew carries them out.
- You can **take over any station**: sit down and work its full 2D close-up. The camera glides in, with the same invisible cut the sonar console has now.
- **Getting about:** walk, or use quick-glide keys.
- **Knowing what's happening:** every crewed station has a **large screen readable from across the room**, plus repeaters in the room and crew callouts.
- **Your home** is the **conn**: the periscope stand and plot table in the middle.
- The old console is **split fully**. There is one way to play.
- **Crew:** skilled but human. Correct, after a short reaction delay; the sonarman can misclassify a weak contact.
- **Crew figures:** simple procedural seated figures.
- **TMA:** the live attack plot is on the **plot table**; detailed work happens at **fire control**.
- **Training** is rewritten for the room once the stations exist.

**One-line pitch:** the boat is a crew, not a screen. From the conn you see every station's screen and give
orders; when it matters you take a station yourself, and the boat keeps fighting while you walk.

---

## 1. Stations and what moves where

| Station | Place | Crewed by | Big screen (readable from the room) | Taken from today's console |
|---|---|---|---|---|
| **Sonar** | port, fwd | sonarman | waterfall | waterfall, acoustic profile and class library, hydrophone dial, MARK bearing to the TDC, active ping, self-noise, ENEMY SONAR and TORPEDO lamps |
| **Fire control** | port, mid | fire-control man | solution: bearing / range / gyro / run | TDC fields, solution, auto-solve, TMA page, tube switches and spread, torpedo and decoy counts, tactical PPI with wire steering, noisemaker |
| **Radio** | port, aft | radioman | teleprinter paper (large type) | teleprinter, wave and score; later ESM (#34) |
| **Helm and planes** | forward bulkhead | helmsman and planesman | depth / heading / speed, ordered and actual | engine telegraph, rudder yoke and heading, depth order with HOLD and P.D., depth and speed gauges, cavitation lamp |
| **Ballast** | stbd, fwd | chief of the watch | hull openings board, battery, O₂ | emergency blow, snorkel and diesels, battery and O₂ gauges, BROACH, LEAK, HULL STRESS and DIESEL lamps |
| **Damage control** | stbd, mid (replaces "trim") | DC party lead | damage list in work order | damage board and repair order, hull integrity, leaks |
| **Navigation** | stbd, aft | (unmanned) | sea state, weather, own position | chart and sea readout (set dressing to start) |
| **Periscope stand** | centre | you | — | scope and snorkel levers, look, mark with range into the TDC, high/low power, exposure warning |
| **Plot table** | centre | you | the table itself | D.R. track plus the attack plot: our bearings as lines, the TDC's solution track |

- **In the room:**
  - a caged orange alarm lamp over every station and one on the periscope barrel; they flash for a torpedo, enemy
    sonar, a leak or hull stress
  - a small tile panel at the conn names which alarm it is
  - the klaxon sounds when a torpedo is first heard
- **Each 2D close-up** is built for its own job: bigger, more detailed, and readable. Most use the existing `console_art` and `crt_renderer` pieces.
- **The big screens** are the stations' own live textures. A screen you look at updates every frame; others update at 10 Hz.

## 2. Crew (operator side, new `crew.py`)

- **Shape:** each station has a `Crewman` with a reaction delay. Difficulty sets the delay: Cadet 0.6 s, Commander 1.2 s, Iron 2 s.
- **Orders:** an order is queued, acknowledged ("RIGHT FULL RUDDER, AYE"), then carried out through the same `Console` methods a player uses. Nothing gains a back door into the world.
- **What each crewman does:**
  - **Helmsman:** steers to an **ordered course**. This is new: rudder from heading error, eased off near the course. He also holds the ordered depth and speed, which the planes and telegraph already do.
  - **Sonarman:** keeps the dial on the loudest contact (today's tracker servo), and reports new contacts, classification, launches, and enemy pings. Reports go through `Console.report`, which already writes most of these lines.
  - **Fire control:** keeps the TDC bearing updated from sonar marks, and runs auto-solve where the difficulty allows it. He fires only on your order.
  - **Chief of the watch:** carries out blow, snorkel and masts on order, and calls out broach, leaks and stress.
  - **DC lead:** works the damage list. You or he can reorder it.
- **Taking over:** sit at a station and its crewman stands aside; your inputs drive it. When you get up, he takes it back and carries on from where you left it.

## 3. Conning orders

- **Radial menu**, held on a key. The top level is **HELM / ENGINES / DEPTH / WEAPONS / EMERGENCY**:
  - HELM: left or right 10 / 20 / full rudder, steady, come to a course (wheel picker)
  - ENGINES: stop through flank
  - DEPTH: P.D., 60, 100, 150, 200, deeper / shallower 10, hold
  - WEAPONS: fire tube 1 / 2 / salvo on the current solution, noisemaker, ping
  - EMERGENCY: crash dive, emergency blow, flank and hard rudder
- **Hotkeys**, all rebindable, for the urgent orders: flank, crash dive, noisemaker, blow, all stop, plus today's engine, depth and rudder keys, now working from anywhere.

## 4. Getting about

- Walk with WASD, Shift to run, the mouse to look.
- **Quick-glide:** number keys (or a station wheel) glide you to a station's standing spot in about 1 s; a double press sits you down.
- **R** stands you up from any station. **E** uses or sits at the thing you're facing.

## 5. Milestones

Each milestone ships with its tests; the golden run is regenerated only where play is meant to change.

1. **Crew and orders core** (`crew.py`, no new visuals)
   - Ordered-course autopilot.
   - Order queue with reaction delays and acknowledgements.
   - Hotkeys work from anywhere; the radial menu goes in as a 2D overlay.
   - **Tests:** an order is carried out after its delay; the ordered course is reached and held; nothing a crewman does bypasses `Console`.
2. **Split the console into station close-ups**
   - One 2D view per station, built from today's panels, with each station's own click and scroll mapping.
   - All station panels become 16:9 and seatable.
   - Big screens are live in the room; the patrol starts at the conn.
   - **Tests:** every station sits and stands with the invisible cut; clicks reach the right control; WASD never leaks into a station.
3. **Alarms and the attack plot** (built)
   - Caged orange alarm lamps, one per station plus one at the conn, a small legend panel at the conn, the klaxon.
     (An overhead board with repeaters was tried and dropped: not realistic.)
   - The plot table is tracing paper over a printed sea chart, worked in pencil: own track with times, bearing lines,
     convoy and sonar reports, the TDC target in red. A parallel ruler, dividers, pencils and a rubber lie on it.
   - **Tests:** the klaxon sounds once; the lamps follow the four alarms; the legend lights the cause; marks,
     solution and reports show on the plot.
4. **Crew figures**
   - Procedural seated crewmen whose arms reach the controls; they stand aside when you take over.
5. **Quick-glide and polish**
   - Station keys and a wheel; "rig for red" lighting at battle stations; spatial audio for callouts.
6. **Training rewritten for the room**
   - Chapters walk you station to station, with 3D highlights and the crew explaining their jobs.

## 6. Risks

- **Drawing cost.** Several live screens plus the 3D frame. Plan: screens out of view update at 10 Hz and are drawn smaller; measure before optimising.
- **Many orders from many places** could fight each other, e.g. you turning the wheel while an ordered course is in force. **Rule:** a hand on a control cancels the standing order for it, and the crew reports "CONN, HELM: COURSE ORDER CANCELLED".
- **The tutorial and `HIGHLIGHTS`** assume the old layout. They stay working on the old console until milestone 6 replaces them.
