"""Balance knobs in one place: tune these when playtesting. Physical constants (speeds, depths, rates) live in
sim.py; behaviour code lives in ai.py and sim.py and only reads these numbers."""

# ---------- difficulty presets ----------
DIFFICULTY = {
    "CADET": dict(layer_loss=0.3, enemy_torp_kt=28, enemy_seeker_yd=0, reload=30.0, battery=False, oxygen=False,
                  leaks=False, beam_width=3.0, cone=35.0, ping_warning=True, zigzag=False, sub_decoys=0,
                  cavitation_instant=False, torp_damage=50.0, spot_mult=0.5, mast_damage=False, lower_delay=0.0),
    "COMMANDER": dict(layer_loss=0.3, enemy_torp_kt=40, enemy_seeker_yd=600, reload=45.0, battery=True, oxygen=False,
                      leaks=False, beam_width=1.5, cone=25.0, ping_warning=False, zigzag=True, sub_decoys=2,
                      cavitation_instant=False, torp_damage=75.0, spot_mult=1.0, mast_damage=False, lower_delay=0.0),
    "IRON CAPTAIN": dict(layer_loss=0.0, enemy_torp_kt=45, enemy_seeker_yd=1200, reload=60.0, battery=True, oxygen=True,
                         leaks=True, beam_width=1.5, cone=20.0, ping_warning=False, zigzag=True, sub_decoys=3,
                         cavitation_instant=True, torp_damage=90.0, spot_mult=1.5, mast_damage=True, lower_delay=4.0),
}

# ---------- being seen (periscope / snorkel lookouts) ----------
# per-second chance at zero range for an alertness-1 observer, and how far it can reach in clear air
SPOT_BASE = {"scope": 0.06, "snorkel": 0.12, "both": 0.15, "broach": 1.0}
SPOT_REACH = {"scope": 3000.0, "snorkel": 6000.0, "both": 6000.0, "broach": 8000.0}
WAKE_SIGHTING = 1200.0    # m, lookouts spot a torpedo wake
LOOKOUT_IDLE, LOOKOUT_ALERT, LOOKOUT_MERCHANT = 1.5, 2.5, 0.7  # alertness: escort unaware / hunting, merchant

# ---------- what enemies hear ----------
PING_HEARING = 15000.0    # m, warships hear our ping
LAUNCH_HEARING = 6000.0   # m, torpedo launch transient
TORPEDO_HEARING = 2000.0  # m, an incoming fish
EXPLOSION_HEARING = 12000.0  # m, a ship going up is heard a long way off
ALARM_HEARING = 10000.0   # m, merchants hear a ping

# ---------- escorts hunting ----------
GIVE_UP = 150.0           # s without contact (once on scene) before searching instead
PING_INTERVAL = 8.0       # s between escort pings while searching or hunting
SONAR_RANGE = 4000.0      # m escort active sonar holds a sub on its side of the layer
BLIND_RANGE = 300.0       # m from datum: hull sonar loses a sub this close, final run is blind
RUN_OUT = 45.0            # s holding course after a pattern before coming round again
SEARCH_TIME = 300.0       # s of searching once at the datum, then back to the screen
CHARGE_LETHAL = 12.0     # m, inside this the hull goes
CHARGE_REACH = 120.0     # m, damage falls to zero here

# ---------- merchants ----------
SCATTER_RANGE = 6000.0    # m, a sinking this close scatters a convoy
SCATTER_TIME = (300.0, 600.0)  # s of running before settling to an independent course
CALM_TIME = 600.0         # s without new alarms before revs come down

# ---------- waves ----------
DESPAWN_RANGE = 18000.0   # m, contacts beyond this have slipped away
WAVE_GAP = 30.0           # s of quiet between waves
TONNAGE = {"MERCHANT": 6500, "ESCORT": 1600, "SUB": 1100}
WAVE_TIME_LIMIT = 900.0       # s; after this a wave's far-off stragglers count as gone
LATE_DESPAWN_RANGE = 9000.0   # m, the despawn range once a wave is over its time limit
LATE_MERCHANT_RANGE = 6000.0  # m; once a wave is late, unalarmed merchants beyond this no longer hold it open

# Wire guidance: the spool is shorter than the run, so the seeker finishes the job on its own
WIRE_LENGTH = 4000.0  # m of guidance wire (the fish runs 5,486 m)

# Damage control: seconds one repair party needs per system. It works the top of the list first.
REPAIR_TIME = {"HYDROPHONES": 90.0, "ACTIVE SONAR": 60.0, "PLANES": 75.0, "RUDDER": 60.0, "TUBE 1": 90.0,
               "TUBE 2": 90.0, "PERISCOPE": 120.0, "SNORKEL": 90.0, "BATTERY": 150.0, "MOTORS": 120.0}
DAMAGED_HYDROPHONES = 0.3  # passive levels with a hydrophone array knocked out
DAMAGED_PLANES = 0.25      # dive rate with the planes jammed
DAMAGED_RUDDER = 0.3       # turn rate with the steering gear damaged
DAMAGED_MOTOR_KT = 5.0     # top speed on one motor
DAMAGED_BATTERY = 2.0      # drain with cracked cells
