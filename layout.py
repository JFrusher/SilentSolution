"""Workstation geometry: logical 1280x720 screen, scaled to the window. Shared by input and drawing."""
import pygame

from sim import CRUSH_DEPTH


W, H = 1280, 720

# ---------- workstation layout (logical 1280x720, scaled to the window) ----------
MONITOR = pygame.Rect(272, 10, 640, 456)
CRT_RECT = pygame.Rect(302, 38, 580, 400)
SCOPE_PANEL = pygame.Rect(10, 10, 254, 250)
SCOPE_C, SCOPE_R = (137, 132), 104
TDC_PANEL = pygame.Rect(10, 266, 254, 200)
CONSOLE = pygame.Rect(10, 472, 902, 238)
GAUGES = pygame.Rect(920, 10, 350, 364)
TELETYPE = pygame.Rect(920, 380, 350, 330)
PAPER_RECT = pygame.Rect(938, 418, 314, 280)
ORDER_SLIP = pygame.Rect(950, 424, 290, 62)  # tutorial: current order pinned to the paper
GAUGE_R = 76
GAUGE_POS = {"DEPTH": (1008, 104), "BATTERY": (1182, 104), "NOISE": (1008, 282), "HULL": (1182, 282)}
GAUGE_SPECS = {
    "DEPTH": dict(title="DEPTH", lo=0, hi=300, major=50, minor=10, red=(CRUSH_DEPTH, 300), units="METRES"),
    "BATTERY": dict(title="BATTERY", lo=0, hi=100, major=20, minor=5, red=(0, 15), units="% CHARGE"),
    "NOISE": dict(title="SELF NOISE", lo=0, hi=3, major=0.5, minor=0.1, red=(1.2, 3), units="CAVITATION"),
    "HULL": dict(title="HULL", lo=0, hi=100, major=20, minor=5, red=(0, 30), units="% INTEGRITY"),
}
TELEGRAPH_C, TELEGRAPH_R = (118, 650), 94
WHEEL_C, WHEEL_R = (330, 578), 56
RUDDER_BAR = pygame.Rect(250, 656, 160, 9)
DEPTH_C, DEPTH_R = (530, 566), 60
HOLD_BTN, BLOW_BTN, PD_BTN = pygame.Rect(440, 638, 56, 24), pygame.Rect(502, 638, 56, 24), pygame.Rect(564, 638, 56, 24)
SCOPE_LEVER, SNORT_LEVER = (446, 528), (614, 528)  # mast levers either side of the depth-order dial
LOOK_BTN = pygame.Rect(422, 562, 48, 22)
TUBE_SW = ((672, 540), (752, 540))
NMKR_BTN, PING_BTN = pygame.Rect(642, 640, 140, 24), pygame.Rect(642, 674, 140, 24)
LAMPS = ("ENEMY SONAR", "TORPEDO", "CAVITATION", "DIESEL", "MASTS UP", "BROACH", "LEAK", "HULL STRESS", "BELOW LAYER")
LAMP_X, LAMP_Y0, LAMP_DY = 814, 506, 22
TDC_ROW_Y0, TDC_ROW_H = 296, 21

# inside the CRT (local coordinates)
WF_POS = (20, 30)
WF_W, WF_H = 360, 214
SPEC_RECT = pygame.Rect(392, 30, 172, 146)
LIB_RECT = pygame.Rect(392, 198, 172, 46)
LOG_POS = (20, 266)
HYD_POS = (392, 262)

HIGHLIGHTS = {  # tutorial rings: screen rect, or (centre, radius)
    "waterfall": pygame.Rect(CRT_RECT.x + WF_POS[0] - 4, CRT_RECT.y + WF_POS[1] - 4, WF_W + 8, WF_H + 8),
    "spectrum": SPEC_RECT.union(LIB_RECT).move(CRT_RECT.topleft).inflate(10, 22),
    "scope": (SCOPE_C, SCOPE_R + 4),
    "tdc": TDC_PANEL.inflate(-4, -4),
    "gauges": GAUGES.inflate(-4, -4),
    "noise": (GAUGE_POS["NOISE"], GAUGE_R + 4),
    "battery": (GAUGE_POS["BATTERY"], GAUGE_R + 4),
    "telegraph": pygame.Rect(TELEGRAPH_C[0] - TELEGRAPH_R - 6, TELEGRAPH_C[1] - TELEGRAPH_R - 6, 2 * TELEGRAPH_R + 12, TELEGRAPH_R + 36),
    "wheel": pygame.Rect(WHEEL_C[0] - 90, WHEEL_C[1] - 78, 180, 168),
    "depth": pygame.Rect(DEPTH_C[0] - 86, DEPTH_C[1] - DEPTH_R - 8, 172, 140),
    "tubes": pygame.Rect(636, 494, 156, 136),
    "nmkr": NMKR_BTN.inflate(10, 10),
    "ping": PING_BTN.inflate(10, 10),
    "lamps": pygame.Rect(798, 496, 112, 204),
    "masts": pygame.Rect(416, 492, 228, 96),
}

# periscope screen (look mode): the eyepiece and the instruments you can glimpse around it
EYEPIECE_C = (640, 340)
STRIP = pygame.Rect(40, 676, 1200, 36)
