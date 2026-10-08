# Control room — design and build plan

> **Status: built (all six milestones, PR #5).** Departures from the plan are noted on each milestone.

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
  - **captions** at the foot of the screen, everywhere but the full console: every crew call and teleprinter signal
    with its caller named, and every sound that comes with nothing said, in brackets (`[ENEMY SONAR PING 120R]`,
    `[EXPLOSION 045R]`, `[HULL CREAKS]`, `[KLAXON]`; SOUND CAPTIONS in settings). A hit or a near charge shakes
    the room and flares its lights, so nothing in the boat is heard only.
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
4. **Crew figures** (built)
   - Procedural crewmen seated at each station with their hands on the desk; the helmsman and planesman sit in the
     helm seats. A station's crewman stands aside while the camera carries you to or from his seat.
     (No animation yet; they hold their pose.)
5. **Quick travel** (built)
   - A STATIONS ring on the order wheel: a dip to black, then you're carried into the station (or to the eyepiece).
     The number keys stayed weapon keys, so there are no station hotkeys. "Rig for red" and spatial callouts were
     left out: the orange alarm lamps already change the room's light in a crisis.
6. **Training in the room** (built)
   - Training starts at the conn like a patrol. An instructor's card shows the order, his last words, and which
     station to take (worked out from the step's highlighted parts); rings land on the right pieces of a station's
     view. Drill texts explain the room; the drills' own goals and checks are unchanged, so the scripted trainee in
     `tests/test_tutorial.py` still passes them all.

7. **Detail: stations** (built)
   - The look is the Oberon class (1960s RN):
     - grey hammertone consoles round worn black bezels, cream-on-black traffolyte name plates
     - a sloped switch rail of bakelite tumblers, knobs, lit buttons, guarded firing keys and blow levers, each engraved
     - lino desk tops with a chrome nosing, cabinet doors, louvres, rivets, a brass maker's plate
     - sound-powered telephones, armoured cable looms into a tray under the deckhead
     - the watch's clutter: headphones, log books, clipboards, mugs, an ashtray, a radio clock, a first-aid box and an
       extinguisher
   - Built in code by `graphics/models.py` and saved as `.glb` under `assets/`, so a better model can be dropped in;
     `graphics/gltf.py` reads them. The live panel stays the 2D station, so the seated cut is still invisible.
8. **Detail: crew** (built)
   - Stylised-realistic RN ratings, each his own man:
     - smooth bodies; a sculpted head (brow, nose, cheekbones, chin, ears), eyes, a soft painted hairline with a
       shell for body, beards and a moustache, hands with fingers on the desk or round the yoke's grips
     - the submariner's white roll-neck sweater, the navy jumper over a shirt collar, working dress with rolled
       sleeves, a boiler suit; headsets on the sonarman and radioman
   - Seated men sit on stools at knee holes in their desks (footrests); the helmsman and planesman hold their columns;
     a man you relieve stands aside.
   - Idle life (breathing, a slow shift of weight, glances about his work). When a caption names him ("CONN, SONAR",
     "HELM, AYE", "CHIEF, AYE") he looks round at you as he says it.

9. **Stations rethought, instruments in 2.5D** (built)
   - Each station is laid out for its own man and only his controls take a click:
     - sonar: the waterfall CRT, the self-noise gauge, ENEMY SONAR and TORPEDO lamps, ACTIVE PING
     - fire control: PPI, TDC, the TMA CRT, a firing panel (guarded tube switches, ready lamps, torpedoes and decoys
       left, NOISEMAKER), the TORPEDO lamp
     - helm and planes: the depth and self-noise gauges, the telegraph, a rudder angle indicator, the depth-order dial
       with HOLD and P.D., the CAVITATION / BROACH / BELOW LAYER lamps
     - ballast: battery (with O2) and depth gauges, the mast levers, EMERGENCY BLOW, DIESEL / MASTS UP / LEAK /
       HULL STRESS lamps
     - damage control: the state board with the boat's state beside it (no sonar picture), a white-faced hull gauge,
       LEAK and HULL STRESS lamps
   - Dials, switches, buttons and lamps are drawn natively at the station's size: switches, buttons, lamps and gauge
     bezels are 3D models (the room's `Builder`) rendered into cached sprites with soft shadows; faces are black with
     cream figures, or white enamel for the hull gauge; needles throw a shadow; glass catches the light.
   - The green screens are unchanged, each under a plate naming its job. The panels carry no key hints: hover over a
     control to see its keys, or press F1.

## 6. Risks

- **Drawing cost.** Several live screens plus the 3D frame. Plan: screens out of view update at 10 Hz and are drawn smaller; measure before optimising.
- **Many orders from many places** could fight each other, e.g. you turning the wheel while an ordered course is in force. **Rule:** a hand on a control cancels the standing order for it, and the crew reports "CONN, HELM: COURSE ORDER CANCELLED".
- **The tutorial and `HIGHLIGHTS`** assume the old layout. They stay working on the old console until milestone 6 replaces them.
