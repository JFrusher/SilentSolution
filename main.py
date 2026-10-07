"""Phase 1 headless check: perfect TDC solution hits, 2 kt speed error at 4000 yd misses."""
from sim import KNOT, YARD, Vessel, World, intercept_heading, range_from_delay


def engagement(speed_error_kts):
    w = World(Vessel(0, 0, 0, 0), [Vessel(0, 4000 * YARD, 90, 12 * KNOT)])
    rng = range_from_delay(w.ping()[0])
    t = w.targets[0]
    est_speed = t.speed + speed_error_kts * KNOT
    torp_speed = 45 * KNOT
    sol = intercept_heading(0, 0, 0, rng, t.heading, est_speed, torp_speed)
    assert sol, "no firing solution"
    w.fire(sol[0], torp_speed)
    while w.torpedoes:
        w.step(0.05)
    return bool(w.sunk), sol


if __name__ == "__main__":
    hit, (gyro, eta) = engagement(0)
    print(f"perfect TDC: gyro {gyro:05.1f} deg, eta {eta:.0f}s -> {'HIT' if hit else 'MISS'}")
    assert hit
    miss, _ = engagement(2)
    print(f"+2 kt error: {'HIT' if miss else 'MISS'}")
    assert not miss
    print("ok")
