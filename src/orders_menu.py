"""The captain's order wheel: hold the right mouse button, drag toward a heading, let go; then pick the order the
same way. Works seated or on your feet. Gives back a crew order (name, argument) for crew.Crew.order."""
import math

import pygame

from graphics import console_art as art
from sim import TELEGRAPH

MENU = (
    ("HELM", (("AMIDSHIPS", ("RUDDER", 0)), ("RIGHT 10", ("RUDDER", 10)), ("RIGHT 20", ("RUDDER", 20)),  # drag the
              ("RIGHT FULL", ("RUDDER", 30)), ("STEADY", ("STEADY", None)), ("LEFT FULL", ("RUDDER", -30)),  # way you
              ("LEFT 20", ("RUDDER", -20)), ("LEFT 10", ("RUDDER", -10)))),  # want her head to go
    ("COURSE", tuple((f"{c:03d}", ("COURSE", c)) for c in range(0, 360, 45))),
    ("ENGINES", tuple((name, ("ENGINES", i)) for i, (name, _) in enumerate(TELEGRAPH))),
    ("DEPTH", (("P.D.", ("PERISCOPE DEPTH", None)), ("60 M", ("DEPTH", 60)), ("100 M", ("DEPTH", 100)),
               ("150 M", ("DEPTH", 150)), ("200 M", ("DEPTH", 200)), ("HOLD", ("HOLD DEPTH", None)))),
    ("WEAPONS", (("SALVO", ("FIRE", None)), ("TUBE 1", ("FIRE", 0)), ("TUBE 2", ("FIRE", 1)),
                 ("NOISEMAKER", ("NOISEMAKER", None)), ("PING", ("PING", None)))),
    ("MASTS", (("PERISCOPE", ("SCOPE", None)), ("SNORKEL", ("SNORKEL", None)))),
    ("EMERGENCY", (("CRASH DIVE", ("CRASH DIVE", None)), ("BLOW", ("BLOW", None)), ("EVADE LEFT", ("EVADE", -1)),
                   ("EVADE RIGHT", ("EVADE", 1)))),
)
DEAD_ZONE = 45.0  # px of drag before anything is pointed at
RING = 150        # px from the centre to the labels


class OrderWheel:
    def __init__(self):
        self.items = None   # what's on the ring: MENU, or one heading's orders
        self.title = ""
        self.vec = [0.0, 0.0]

    @property
    def open(self):
        return self.items is not None

    def press(self):
        if not self.open:
            self.items, self.title, self.vec = MENU, "ORDERS", [0.0, 0.0]

    def motion(self, dx, dy):
        self.vec[0] += dx
        self.vec[1] += dy
        r = math.hypot(*self.vec)
        if r > RING:  # the pointer never wanders off the ring
            self.vec = [self.vec[0] * RING / r, self.vec[1] * RING / r]

    def pointed(self):
        """Index on the ring the drag points at (0 at the top, clockwise), or None inside the dead zone."""
        if math.hypot(*self.vec) < DEAD_ZONE:
            return None
        a = math.degrees(math.atan2(self.vec[0], -self.vec[1])) % 360
        return int((a + 180 / len(self.items)) // (360 / len(self.items))) % len(self.items)

    def release(self):
        """Let go: a heading opens its orders; an order is given (returned); nothing pointed at closes the wheel."""
        k = self.pointed()
        if k is None:
            self.items = None
            return None
        label, what = self.items[k]
        if self.items is MENU:
            self.items, self.title, self.vec = what, label, [0.0, 0.0]
            return None
        self.items = None
        return what

    def draw(self, surf, centre):
        cx, cy = centre
        shade = pygame.Surface((RING * 2 + 160, RING * 2 + 80), pygame.SRCALPHA)
        pygame.draw.circle(shade, (0, 0, 0, 205), shade.get_rect().center, RING + 70)
        surf.blit(shade, shade.get_rect(center=centre))
        font, big = art.mono(15, True), art.mono(18, True)
        k = self.pointed()
        for i, (label, _) in enumerate(self.items):
            a = math.radians(i * 360 / len(self.items))
            pos = (cx + RING * math.sin(a), cy - RING * math.cos(a))
            colour = (255, 196, 90) if i == k else (210, 204, 180)
            text = font.render(label, True, colour)
            surf.blit(text, text.get_rect(center=pos))
        title = big.render(self.title, True, (240, 226, 190))
        surf.blit(title, title.get_rect(center=centre))
        pygame.draw.line(surf, (255, 196, 90), centre, (cx + self.vec[0], cy + self.vec[1]), 2)
