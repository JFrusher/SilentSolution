"""The control room in 3D: procedural meshes lit by the overhead lamps and fogged, rendered offscreen with moderngl and
read back as a pygame Surface. Panels are textures: the sonar console shows the live 2D station, the others carry
panel art built with console_art, and the plot table shows our dead-reckoning track."""
import math
import random

import moderngl
import numpy as np
import pygame

import control_room as cr
from graphics import console_art as art
from graphics import gltf
from graphics.models import (
    ASSETS,
    COXSWAIN_FILE,
    CREW_FILES,
    HELM_SEATS,
    SEAT_OUT,
    STATION_FILES,
    WHEEL_ANGLES,
    build_all,
)
from layout import H, W
from sim import KNOT

LAMPS = [(0.0, 2.28, z) for z in (-4.2, -1.9, 0.4, 2.7, 4.6)]
LAMP_COLOUR = (1.15, 0.9, 0.62)
REACH_TIME = 0.9  # s a crewman's hand takes out to his switches and back
STEP_TIME = 0.8   # s a crewman takes to get up and stand aside (or sit back down)
COXSWAIN_AT = (0.95, 0.0, 1.35)  # where the coxswain stands in training: aft of the periscope rail, to starboard
SCREEN_GLOW = (0.35, 0.95, 0.55)  # the sonar CRT lights its corner
ALERT_COLOUR = (1.0, 0.42, 0.06)  # orange alarm lenses
FOG = (0.02, 0.024, 0.026)

LIGHTING = """
uniform vec3 eye;
uniform vec3 light_pos[8];
uniform vec3 light_col[8];
uniform int lights;
uniform vec3 fog_col;
uniform vec2 view;

float hash(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
float noise(vec3 p) {
    vec3 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    vec2 e = vec2(1, 0);
    float lo = mix(mix(hash(i), hash(i + e.xyy), f.x), mix(hash(i + e.yxy), hash(i + e.xxy), f.x), f.y);
    float hi = mix(mix(hash(i + e.yyx), hash(i + e.xyx), f.x), mix(hash(i + e.yxx), hash(i + e.xxx), f.x), f.y);
    return mix(lo, hi, f.z);
}
vec3 lit(vec3 base, vec3 pos, vec3 n, float shine) {
    vec3 v = normalize(eye - pos);
    vec3 c = base * 0.045;  // the room never goes fully black
    for (int k = 0; k < lights; k++) {
        vec3 d = light_pos[k] - pos;
        float r = length(d);
        vec3 l = d / r;
        float fall = 1.0 / (1.0 + 1.1 * r * r);
        float diff = max(dot(n, l), 0.0);
        float spec = pow(max(dot(n, normalize(l + v)), 0.0), 24.0) * shine;
        c += (base * diff + spec) * light_col[k] * fall;
    }
    return c;
}
vec3 finish(vec3 c, vec3 pos) {
    float f = exp(-0.13 * length(eye - pos));
    vec2 q = gl_FragCoord.xy / view - 0.5;
    float vignette = 1.0 - 0.9 * dot(q, q);
    return pow(mix(fog_col, c, f) * vignette, vec3(1.0 / 2.2));
}
"""

SOLID_VS = """#version 330
uniform mat4 mvp;
in vec3 in_pos; in vec3 in_norm; in vec3 in_col; in float in_mat;
out vec3 pos; out vec3 norm; out vec3 col; flat out int mat;
void main() {
    pos = in_pos; norm = in_norm; col = in_col; mat = int(in_mat + 0.5);
    gl_Position = mvp * vec4(in_pos, 1.0);
}
"""
SOLID_FS = "#version 330\n" + LIGHTING + """
uniform float alert;  // 0..1: the alarm lenses, dark or lit
in vec3 pos; in vec3 norm; in vec3 col; flat in int mat;
out vec4 frag;
void main() {
    vec3 n = normalize(norm);
    if (!gl_FrontFacing) n = -n;
    vec3 base = col * (0.78 + 0.38 * noise(pos * 3.1)) * (0.92 + 0.12 * noise(pos * 23.0));  // paint and wear
    base *= mix(0.55, 1.0, smoothstep(0.0, 0.45, pos.y));  // grime gathers low down
    float shine = 0.25;
    if (mat == 1) {  // deck plates: a diamond tread and the seams between plates
        vec2 g = fract(pos.xz * 9.0 + vec2(pos.z, -pos.x) * 9.0);
        base *= 0.8 + 0.35 * step(0.82, max(g.x, g.y));
        vec2 seam = abs(fract(pos.xz / vec2(1.1, 1.2)) - 0.5);
        base *= 1.0 - 0.6 * step(0.485, max(seam.x, seam.y));
        shine = 0.6;
    }
    if (mat == 2) { frag = vec4(pow(col, vec3(1.0 / 2.2)), 1.0); return; }  // lamps and lit indicators
    if (mat == 4) { frag = vec4(pow(col * mix(0.08, 1.0, alert), vec3(1.0 / 2.2)), 1.0); return; }  // alarm lenses
    if (mat == 3) shine = 1.2;  // bright-work
    frag = vec4(finish(lit(base, pos, n, shine), pos), 1.0);
}
"""
PANEL_VS = """#version 330
uniform mat4 mvp;
in vec3 in_pos; in vec2 in_uv;
out vec3 pos; out vec2 uv;
void main() { pos = in_pos; uv = in_uv; gl_Position = mvp * vec4(in_pos, 1.0); }
"""
PANEL_FS = "#version 330\n" + LIGHTING + """
uniform sampler2D tex;
uniform vec3 normal;
uniform float glow;  // 1: a screen, drawn exactly as the 2D station draws it; 0: a printed or painted face
in vec3 pos; in vec2 uv;
out vec4 frag;
void main() {
    vec3 t = texture(tex, uv).rgb;
    vec3 c = finish(lit(pow(t, vec3(2.2)), pos, normal, 0.35), pos);
    frag = vec4(mix(c, t, glow), 1.0);
}
"""
MODEL_VS = """#version 330
uniform mat4 mvp;
uniform mat4 model;  // a rotation and a place: normals turn with it unscaled
in vec3 in_pos; in vec3 in_norm; in vec2 in_uv; in vec3 in_col;
out vec3 pos; out vec3 opos; out vec3 norm; out vec2 uv; out vec3 col;
void main() {
    vec4 w = model * vec4(in_pos, 1.0);
    pos = w.xyz; opos = in_pos; norm = mat3(model) * in_norm; uv = in_uv; col = in_col;
    gl_Position = mvp * w;
}
"""
MODEL_FS = "#version 330\n" + LIGHTING + """
uniform sampler2D tex;
uniform bool textured;
uniform vec3 factor;
uniform bool emissive;  // lamps and lit caps: their own colour, unlit
uniform float shine;
uniform float wear;     // painted steel: mottle and grime, fixed to the model so it doesn't swim when it moves
in vec3 pos; in vec3 opos; in vec3 norm; in vec2 uv; in vec3 col;
out vec4 frag;
void main() {
    vec3 base = col * factor;
    if (textured) base *= pow(texture(tex, uv).rgb, vec3(2.2));
    if (emissive) { frag = vec4(pow(base, vec3(1.0 / 2.2)), 1.0); return; }
    base *= mix(1.0, (0.8 + 0.34 * noise(opos * 3.1)) * (0.93 + 0.12 * noise(opos * 23.0)), wear);
    base *= mix(0.55, 1.0, smoothstep(0.0, 0.45, pos.y));
    frag = vec4(finish(lit(base, pos, normalize(norm), shine), pos), 1.0);
}
"""


def perspective(fovy, aspect, near, far):
    f = 1 / math.tan(math.radians(fovy) / 2)
    return np.array([[f / aspect, 0, 0, 0], [0, f, 0, 0],
                     [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)], [0, 0, -1, 0]])


def look_at(eye, forward):
    f = forward / np.linalg.norm(forward)
    s = np.cross(f, (0.0, 1.0, 0.0))
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.identity(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def basis(normal):
    """Panel axes: right, up, out. `up` leans with the panel; right stays level."""
    n = np.asarray(normal, float)
    right = np.cross((0.0, 1.0, 0.0), n)
    right /= np.linalg.norm(right)
    return right, np.cross(n, right), n


IDENTITY = np.identity(3)


class Mesh:
    """Triangles for the solid shader: position, normal, colour (0..1) and material."""

    def __init__(self):
        self.rows = []

    def quad(self, a, b, c, d, colour, mat=0):
        """a, b, c, d counter-clockwise seen from the front."""
        a, b, c, d = (np.asarray(p, float) for p in (a, b, c, d))
        n = np.cross(b - a, d - a)
        n /= np.linalg.norm(n)
        for p in (a, b, c, a, c, d):
            self.rows.append((*p, *n, *colour, mat))

    def tri(self, a, b, c, colour, mat=0):
        a, b, c = (np.asarray(p, float) for p in (a, b, c))
        n = np.cross(b - a, c - a)
        n /= np.linalg.norm(n)
        for p in (a, b, c):
            self.rows.append((*p, *n, *colour, mat))

    def box(self, centre, size, colour, mat=0, axes=IDENTITY):
        """axes: columns are the box's x, y, z directions."""
        c, h = np.asarray(centre, float), np.asarray(size, float) / 2
        x, y, z = (axes[:, i] * h[i] for i in range(3))
        corner = {(i, j, k): c + i * x + j * y + k * z for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)}
        faces = (((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)), ((-1, -1, 1), (-1, 1, 1), (-1, 1, -1), (-1, -1, -1)),
                 ((-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)), ((-1, -1, 1), (-1, -1, -1), (1, -1, -1), (1, -1, 1)),
                 ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)), ((1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1)))
        for f in faces:
            self.quad(*(corner[k] for k in f), colour, mat)

    def cylinder(self, a, b, r, colour, mat=0, seg=14, caps=True):
        a, b = np.asarray(a, float), np.asarray(b, float)
        axis = (b - a) / np.linalg.norm(b - a)
        u = np.cross(axis, (0.0, 1.0, 0.0) if abs(axis[1]) < 0.9 else (1.0, 0.0, 0.0))
        u /= np.linalg.norm(u)
        v = np.cross(axis, u)
        ring = [math.cos(t) * u + math.sin(t) * v for t in np.linspace(0, 2 * math.pi, seg + 1)]
        for k in range(seg):
            p, q = ring[k], ring[k + 1]
            side = ((a, p), (b, p), (b, q), (a, p), (b, q), (a, q))
            for end, n in side:
                self.rows.append((*(end + n * r), *n, *colour, mat))
            if caps:
                for end, n in ((a, -axis), (b, axis)):
                    tri = (end, end + p * r, end + q * r) if n is axis else (end, end + q * r, end + p * r)
                    for pt in tri:
                        self.rows.append((*pt, *n, *colour, mat))

    def wheel(self, centre, normal, r, colour, mat=3):
        """A hand wheel: rim of short bars, four spokes, a hub."""
        right, up, n = basis(normal) if abs(normal[1]) < 0.9 else (np.array((1.0, 0, 0)), np.array((0, 0, -1.0)),
                                                                     np.array(normal, float))
        c = np.asarray(centre, float)
        pts = [c + r * (math.cos(t) * right + math.sin(t) * up) for t in np.linspace(0, 2 * math.pi, 17)]
        for p, q in zip(pts, pts[1:]):
            self.cylinder(p, q, 0.016, colour, mat, seg=6, caps=False)
        for t in (0.4, 0.4 + math.pi / 2, 0.4 + math.pi, 0.4 + 3 * math.pi / 2):
            self.cylinder(c, c + r * (math.cos(t) * right + math.sin(t) * up), 0.011, colour, mat, seg=5, caps=False)
        self.cylinder(c - n * 0.03, c + n * 0.03, 0.035, colour, mat, seg=8)

    def array(self):
        return np.array(self.rows, "f4")


# ---------- the room ----------
PAINT = (0.5, 0.55, 0.49)       # pale green-grey deckhead and hull
CONSOLE = (0.33, 0.35, 0.34)    # grey-green console steel
DARK = (0.12, 0.12, 0.12)
DECK = (0.32, 0.31, 0.29)
PIPES = ((0.55, 0.16, 0.12), (0.72, 0.72, 0.68), (0.3, 0.42, 0.55), (0.58, 0.5, 0.2), (0.62, 0.62, 0.6))
BRASS = (0.7, 0.55, 0.25)


def build_room():
    m = Mesh()
    half, w0 = cr.LENGTH / 2, cr.deck_half_width(0.0)
    m.quad((-w0, 0, half), (w0, 0, half), (w0, 0, -half), (-w0, 0, -half), DECK, mat=1)
    lo = math.acos(cr.HULL_Y / cr.HULL_R)  # where the hull meets the deck, from straight down
    arc = np.linspace(lo, 2 * math.pi - lo, 41)

    def hull(t, r=cr.HULL_R):
        return np.array([r * math.sin(t), cr.HULL_Y - r * math.cos(t)])
    for t0, t1 in zip(arc, arc[1:]):  # the pressure hull, seen from inside
        (x0, y0), (x1, y1) = hull(t0), hull(t1)
        m.quad((x0, y0, -half), (x1, y1, -half), (x1, y1, half), (x0, y0, half), PAINT)
    for z in np.arange(-half + 0.45, half, 0.8):  # frames
        for t0, t1 in zip(arc, arc[1:]):
            (x0, y0), (x1, y1) = hull(t0, cr.HULL_R - 0.09), hull(t1, cr.HULL_R - 0.09)
            (X0, Y0), (X1, Y1) = hull(t0), hull(t1)
            m.quad((x0, y0, z - 0.04), (x1, y1, z - 0.04), (x1, y1, z + 0.04), (x0, y0, z + 0.04), PAINT)
            m.quad((X0, Y0, z - 0.04), (X1, Y1, z - 0.04), (x1, y1, z - 0.04), (x0, y0, z - 0.04), PAINT)
            m.quad((x0, y0, z + 0.04), (x1, y1, z + 0.04), (X1, Y1, z + 0.04), (X0, Y0, z + 0.04), PAINT)
    for z, sign in ((-half, 1), (half, -1)):  # bulkheads
        rim = [hull(t) for t in arc]
        for (x0, y0), (x1, y1) in zip(rim, rim[1:]):
            a, b = (x0, y0, z), (x1, y1, z)
            m.tri((0, 0, z), *((a, b) if sign < 0 else (b, a)), PAINT)
    door_z = half - 0.03  # the watertight door aft: a dark oval and its frame
    m.box((0, 1.0, door_z), (0.75, 1.55, 0.04), (0.2, 0.21, 0.2))
    for x in (-0.42, 0.42):
        m.box((x, 1.0, door_z - 0.02), (0.08, 1.7, 0.08), CONSOLE)
    for y in (0.12, 1.88):
        m.box((0, y, door_z - 0.02), (0.92, 0.08, 0.08), CONSOLE)
    m.wheel((0.0, 1.05, door_z - 0.08), (0, 0, -1), 0.17, (0.6, 0.6, 0.56))
    for i, (x, y, r) in enumerate(((-1.3, 2.45, 0.07), (-0.9, 2.62, 0.05), (-0.45, 2.55, 0.09), (0.35, 2.6, 0.06),
                                   (0.8, 2.48, 0.08), (1.25, 2.4, 0.05), (1.6, 2.2, 0.04), (-1.65, 2.2, 0.045))):
        m.cylinder((x, y, -half), (x, y, half), r, PIPES[i % len(PIPES)])  # the runs overhead
        for z in np.arange(-half + 0.85, half, 1.6):  # hangers
            m.box((x, y + r + 0.08, z), (0.03, 0.16, 0.03), DARK)
    for x, y, z in LAMPS:
        m.box((x, y + 0.04, z), (0.34, 0.06, 0.2), DARK)
        m.box((x, y, z), (0.28, 0.025, 0.14), LAMP_COLOUR, mat=2)

    px, pz = cr.PERISCOPE  # the periscope: well rail, barrel, eyepiece box and training handles
    m.cylinder((px, 0.0, pz), (px, 2.7, pz), 0.11, (0.42, 0.44, 0.42), mat=3)
    m.cylinder((px, 0.0, pz), (px, 0.12, pz), cr.PERISCOPE_R + 0.05, DARK)
    eye_y = cr.EYEPIECE_Y
    m.box((px, eye_y - 0.02, pz + 0.12), (0.34, 0.42, 0.3), (0.24, 0.25, 0.24))
    m.cylinder((px, eye_y, pz + 0.26), (px, eye_y, pz + 0.32), 0.05, (0.05, 0.05, 0.05))  # rubber eyecup
    m.cylinder((px, eye_y, pz + 0.3205), (px, eye_y, pz + 0.321), 0.028, (0.06, 0.12, 0.14), mat=2)  # the glass
    for side in (-1, 1):
        m.cylinder((px + side * 0.17, eye_y - 0.1, pz + 0.12), (px + side * 0.42, eye_y - 0.1, pz + 0.12), 0.03,
                   DARK)
    rail = [(px + cr.PERISCOPE_R * math.sin(t), pz + cr.PERISCOPE_R * math.cos(t))
            for t in np.linspace(0, 2 * math.pi, 25)]
    for (x0, z0), (x1, z1) in zip(rail, rail[1:]):
        m.cylinder((x0, 0.95, z0), (x1, 0.95, z1), 0.022, CONSOLE, mat=3, seg=6, caps=False)
    for x, z in rail[::4]:
        m.cylinder((x, 0.1, z), (x, 0.95, z), 0.02, CONSOLE, seg=6, caps=False)

    tx, tz, sx, sz = cr.TABLE  # the plot table: cabinet, rim (the glass top is a panel)
    m.box((tx, cr.TABLE_TOP / 2 - 0.02, tz), (sx - 0.08, cr.TABLE_TOP - 0.04, sz - 0.08), CONSOLE)
    for dx, dz, lx, lz in ((0, -1, sx, 0.05), (0, 1, sx, 0.05), (-1, 0, 0.05, sz), (1, 0, 0.05, sz)):
        m.box((tx + dx * sx / 2, cr.TABLE_TOP, tz + dz * sz / 2), (lx, 0.05, lz), DARK)
    m.cylinder((tx, 1.95, tz), (tx, 2.3, tz), 0.01, DARK, seg=4)
    m.box((tx, 1.93, tz), (0.3, 0.08, 0.3), DARK)
    m.box((tx, 1.89, tz), (0.24, 0.01, 0.24), (0.9, 0.35, 0.2), mat=2)  # a red chart lamp

    trim_valves(m)
    for pos, out in ALERT_LAMPS:
        alert_lamp(m, pos, out)
    lx, ly, lz = LEGEND_AT  # the alarm legend's post
    m.cylinder((lx, 0.0, lz - 0.02), (lx, ly - 0.2, lz - 0.02), 0.02, CONSOLE, mat=3, seg=8)
    m.box((lx, ly, lz - 0.03), (0.24, 0.42, 0.04), CONSOLE)
    table_props(m)
    return m.array()


def watch_spot(s):
    """Where a station's crewman sits (floor point) and faces, and where he stands aside when the captain takes over."""
    c, n = np.array(s.centre), np.array(s.normal)
    flat = np.array([n[0], 0.0, n[2]]) / math.hypot(n[0], n[2])
    seat = np.array([c[0], 0.0, c[2]]) + flat * SEAT_OUT
    side = np.cross(flat, (0.0, 1.0, 0.0))
    return seat, -flat, seat + side * (s.w / 2 + 0.25) + flat * 0.15


def _alert_lamps():
    """Where the alarm lamps hang: over each station's panel, toward the hull, and on the periscope barrel."""
    lamps = []
    for s in cr.STATIONS:
        c, n = np.array(s.centre), np.array(s.normal)
        flat = np.array([n[0], 0.0, n[2]]) / math.hypot(n[0], n[2])
        lamps.append((tuple(c - flat * 0.18 + np.array([0.0, s.h / 2 + 0.38, 0.0])), tuple(flat)))
    px, pz = cr.PERISCOPE
    lamps.append(((px, 2.4, pz + 0.12), (0.0, 0.0, 1.0)))
    return tuple(lamps)


ALERT_LAMPS = _alert_lamps()
LEGEND_AT = (0.62, 1.42, cr.PERISCOPE[1] + 0.5)  # the alarm legend panel by the periscope stand, facing aft


def alert_lamp(m, pos, out):
    """A caged orange lens on a dark base, pointing into the room."""
    p, o = np.array(pos), np.array(out)
    m.cylinder(p - o * 0.03, p, 0.06, DARK, seg=10)
    m.cylinder(p, p + o * 0.07, 0.045, ALERT_COLOUR, mat=4, seg=12)
    up = np.array([0.0, 1.0, 0.0]) if abs(o[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    side = np.cross(o, up)
    for a in np.linspace(0, 2 * math.pi, 5)[:-1]:  # the cage
        r = (math.cos(a) * up + math.sin(a) * side) * 0.058
        m.cylinder(p + r, p + r + o * 0.085, 0.004, DARK, seg=4, caps=False)
    m.cylinder(p + o * 0.085, p + o * 0.088, 0.06, DARK, seg=10)


def table_props(m):
    """On the plot table: a parallel ruler, brass dividers, pencils and a rubber."""
    tx, tz, sx, sz = cr.TABLE
    y = cr.TABLE_TOP + 0.04
    for dz in (0.3, 0.345):  # parallel ruler, off the plot's centre and the rose: two ebony rules on brass links
        m.box((tx - 0.05, y, tz + dz), (0.3, 0.006, 0.028), (0.08, 0.07, 0.06))
    for dx in (-0.15, 0.05):
        m.box((tx + dx, y + 0.004, tz + 0.3225), (0.012, 0.003, 0.06), BRASS, mat=3)
    apex = (tx - 0.42, y + 0.02, tz - 0.22)  # dividers
    for leg in ((tx - 0.27, y, tz - 0.31), (tx - 0.3, y, tz - 0.13)):
        m.cylinder(apex, leg, 0.004, BRASS, mat=3, seg=5)
    for (a, b, colour) in (((tx - 0.5, y, tz + 0.28), (tx - 0.34, y, tz + 0.34), (0.86, 0.7, 0.12)),
                           ((tx - 0.48, y, tz + 0.36), (tx - 0.33, y, tz + 0.4), (0.62, 0.12, 0.08))):
        m.cylinder(a, b, 0.0045, colour, seg=6)  # a pencil and a red pencil
        m.cylinder(a, np.array(a) + (np.array(a) - np.array(b)) * 0.07, 0.0045, (0.85, 0.55, 0.55), seg=6)
    m.box((tx + 0.3, y, tz + 0.33), (0.05, 0.012, 0.025), (0.86, 0.6, 0.58))  # rubber


def trim_valves(m):
    """The trim manifold's valve wheels and the pipes they sit on, to the left of its panel."""
    s = next(s for s in cr.STATIONS if s.name == "DAMAGE CONTROL")
    x, z = s.centre[0] + 0.1, s.centre[2] - s.w / 2 - 0.45
    m.cylinder((x, 0.6, z - 0.35), (x, 0.6, z + 0.35), 0.06, PIPES[0])
    m.cylinder((x, 1.0, z - 0.35), (x, 1.0, z + 0.35), 0.06, PIPES[2])
    for k, zz in enumerate((z - 0.2, z + 0.2)):
        for y in (0.6, 1.0):
            m.cylinder((x, y, zz), (x - 0.18, y, zz), 0.025, BRASS, mat=3)
            m.wheel((x - 0.2, y, zz), (-1, 0, 0), 0.1, PIPES[(k + 1) % 2 * 3], mat=0)


# ---------- panel faces ----------
def panel_art(name, size):
    """Set dressing for a station nobody mans yet: a worn faceplate with a readout, lamps and its name."""
    surf = art.texture(size, art.FACE, grain=3)
    w, h = size
    art.label_plate(surf, (w // 2, 18), name, 13)
    art.faceplate(surf, pygame.Rect(30, 50, w - 60, h // 2 - 20))
    for i in range(8):
        art.lamp(surf, (60 + i * (w - 120) // 7, h // 2 + 70), i % 3 == 0, art.AMBER, 7)
    art.counter(surf, (w // 2 - 50, 90), "00 00 00", 18)
    art.engrave(surf, name, (w // 2, h - 40), 12, center=True)
    return surf


def stamp(t):
    """Patrol time as a navigator writes it: minutes and seconds run together."""
    return f"{int(t // 60) % 100:02d}{int(t % 60):02d}"


SEA = (204, 220, 226)
PRINT = (86, 112, 134)      # the chart's own printing
MAGENTA = (150, 64, 120)    # compass rose
PENCIL = (64, 64, 70)
RED_PENCIL = (170, 44, 32)
_SMUDGE_RNG = random.Random(7)  # drawing's own dice: the rubbed-out patches sit in the same places every time
SMUDGES = [(_SMUDGE_RNG.uniform(0.1, 0.9), _SMUDGE_RNG.uniform(0.1, 0.9)) for _ in range(3)]


# ---------- the chart under the plot: the Iceland-Faroes gap ----------
DATUM = (63.5, -10.0)       # where the patrol's origin lies: 63°30'N 10°00'W, on the Iceland-Faroe Ridge
VARIATION = -18.0           # magnetic variation there in 1965, deg (west)
MILE = 1852.0


def latlon(x, y):
    """Patrol metres (x east, y north of the datum) to latitude and longitude, deg (east +)."""
    lat = DATUM[0] + y / 111320.0
    return lat, DATUM[1] + x / (111320.0 * math.cos(math.radians(lat)))


DEPTHS_LAT = np.arange(61.0, 66.01, 0.5)   # the depth grid's rows, deg N
DEPTHS_LON = np.arange(-16.0, -3.99, 1.0)  # and its columns, deg E (west negative)
DEPTHS = np.array([  # metres, hand-entered from Admiralty chart and GEBCO figures for the gap; 0 is land
    # -16   -15   -14   -13   -12   -11   -10    -9    -8    -7    -6    -5    -4
    [2400, 2400, 2300, 2300, 2200, 2000, 1600, 600, 150, 700, 500, 900, 1000],   # 61.0: Faroe Bank, its channel
    [2200, 2200, 2200, 2100, 2000, 1800, 1500, 1100, 800, 50, 150, 600, 1100],   # 61.5: the Faroe Bank Channel
    [1900, 2000, 2000, 2000, 1900, 1700, 1400, 1000, 400, 0, 120, 700, 1200],    # 62.0: the Faroes
    [1500, 1700, 1800, 1800, 1700, 1500, 1300, 1000, 400, 150, 200, 900, 1400],  # 62.5: the ridge meets the plateau
    [500, 1000, 1300, 1500, 1500, 1300, 1000, 460, 500, 900, 1300, 1600, 1700],  # 63.0
    [150, 400, 900, 1200, 1100, 800, 470, 600, 1000, 1300, 1700, 2000, 2100],    # 63.5: the patrol's datum, the crest
    [0, 150, 250, 500, 450, 430, 900, 1400, 1800, 2100, 2300, 2500, 2600],       # 64.0
    [0, 0, 120, 250, 420, 800, 1300, 1700, 2000, 2300, 2500, 2700, 2800],        # 64.5: the ridge leaves Iceland
    [0, 0, 0, 180, 500, 1100, 1600, 1900, 2200, 2500, 2700, 2800, 2900],         # 65.0: east Iceland
    [0, 0, 0, 250, 800, 1400, 1800, 2000, 2300, 2600, 2800, 2900, 3000],         # 65.5
    [0, 50, 200, 700, 1300, 1700, 1900, 2100, 2400, 2700, 2900, 3000, 3100],     # 66.0: the Norway Basin
], float)
FATHOM = 1.8288


def sounding(x, y):
    """The charted depth there, in fathoms, from the grid, with the seabed's small rises and hollows; 0 on land."""
    lat, lon = latlon(x, y)
    i = float(np.interp(lat, DEPTHS_LAT, np.arange(len(DEPTHS_LAT))))
    j = float(np.interp(lon, DEPTHS_LON, np.arange(len(DEPTHS_LON))))
    i0, j0 = min(int(i), len(DEPTHS_LAT) - 2), min(int(j), len(DEPTHS_LON) - 2)
    fi, fj = i - i0, j - j0
    d = DEPTHS[i0:i0 + 2, j0:j0 + 2]
    m = (d[0, 0] * (1 - fj) + d[0, 1] * fj) * (1 - fi) + (d[1, 0] * (1 - fj) + d[1, 1] * fj) * fi
    if m <= 5:
        return 0.0
    lumps = 14 * math.sin(x / 2300.0 + 1.3) * math.cos(y / 3100.0) + 6 * math.sin((x + y) / 900.0)
    return max(1.0, m / FATHOM + lumps * 0.3)


def dms(deg, pos, neg):
    """63.517 -> 63°31'N"""
    d = abs(deg)
    m = round((d - int(d)) * 60)
    return f"{int(d) + m // 60:d}°{m % 60:02d}'{pos if deg >= 0 else neg}"


def plot_art(track, heading, bearings=(), solution=None, notes=(), size=(1040, 720), span=8000.0):
    """The attack plot: tracing paper over a printed sea chart, worked in pencil. Our dead-reckoning track with time
    marks, each bearing ruled from where we took it, the reports, and the TDC's target in red. Centred on where we
    are, north up, `span` metres across. track: (t, x, y); bearings: (t, true brg, kind, range); solution:
    (x, y, vx, vy) relative to us; notes: (t, own x, own y, true brg, range or None, text)."""
    w, h = size
    k = w / span  # px per metre
    x0, y0 = (track[-1][1], track[-1][2]) if track else (0.0, 0.0)

    def at(x, y):
        return (w / 2 + (x - x0) * k, h / 2 - (y - y0) * k)
    chart = pygame.Surface(size)
    chart.fill(SEA)
    small, tiny = art.mono(13), art.mono(11)
    lat0, lon0 = latlon(x0, y0)
    per_lon = 111320.0 * math.cos(math.radians(lat0))  # metres per degree of longitude here
    half = span / 2
    for minute in range(math.floor((lat0 - half / 111320) * 60), math.ceil((lat0 + half / 111320) * 60) + 1):
        py = at(0, (minute / 60 - DATUM[0]) * 111320)[1]  # a parallel every minute of latitude
        pygame.draw.line(chart, PRINT, (0, py), (w, py))
        chart.blit(small.render(dms(minute / 60, "N", "S"), True, PRINT), (4, py + 2))
    for m2 in range(math.floor((lon0 - half / per_lon) * 30), math.ceil((lon0 + half / per_lon) * 30) + 1):
        px = at((m2 / 30 - DATUM[1]) * per_lon, 0)[0]  # a meridian every two minutes of longitude
        pygame.draw.line(chart, PRINT, (px, 0), (px, h))
        chart.blit(small.render(dms(m2 / 30, "E", "W"), True, PRINT), (px + 3, h - 18))
    for sx in range(int((x0 - span / 2) // 700) * 700, int(x0 + span / 2) + 700, 700):  # soundings, fixed to the sea
        for sy in range(int((y0 - span / 2) // 700) * 700, int(y0 + span / 2) + 700, 700):
            depth = sounding(sx, sy)
            if depth:
                chart.blit(tiny.render(f"{depth:.0f}", True, PRINT), at(sx + 120 * math.sin(sy), sy))
    rose, r = (w - 120, h - 130), 92  # the printed compass rose
    for rr in (r, r - 14):
        pygame.draw.circle(chart, MAGENTA, rose, rr, 1)
    for d in range(0, 360, 10):
        a = math.radians(d)
        inner = r - (12 if d % 30 == 0 else 6)
        pygame.draw.line(chart, MAGENTA, (rose[0] + inner * math.sin(a), rose[1] - inner * math.cos(a)),
                         (rose[0] + r * math.sin(a), rose[1] - r * math.cos(a)))
    pygame.draw.polygon(chart, MAGENTA, [(rose[0], rose[1] - r + 16), (rose[0] - 8, rose[1]), (rose[0] + 8, rose[1])])
    chart.blit(small.render("N", True, MAGENTA), (rose[0] - 4, rose[1] - r - 18))
    v = math.radians(VARIATION)  # the magnetic rose inside it, turned by the local variation
    tip = (rose[0] + (r - 30) * math.sin(v), rose[1] - (r - 30) * math.cos(v))
    pygame.draw.line(chart, MAGENTA, rose, tip, 2)
    pygame.draw.circle(chart, MAGENTA, tip, 4, 1)
    for k, line in enumerate((f"VAR {abs(VARIATION):.0f}°W (1965)", "DECREASING 10' ANNUALLY")):
        label = tiny.render(line, True, MAGENTA)
        chart.blit(label, label.get_rect(center=(rose[0], rose[1] + 24 + 13 * k)))
    paper = art.texture(size, art.PAPER, grain=2, mottle=6)  # tracing paper: the chart shows through
    paper.set_alpha(105)
    chart.blit(paper, (0, 0))
    for fx, fy in SMUDGES:  # old work rubbed out
        smudge = pygame.Surface((160, 70), pygame.SRCALPHA)
        pygame.draw.ellipse(smudge, (120, 120, 118, 30), smudge.get_rect())
        chart.blit(smudge, (fx * w - 80, fy * h - 35))
    pen = art.hand(17)
    if track:
        def where(t):
            return min(track, key=lambda r: abs(r[0] - t))[1:3]
        labelled = -1e9
        for t, brg, _, _ in bearings:  # each bearing ruled from where we took it; a time on one a minute
            ox, oy = where(t)
            b = math.radians(brg)
            end = at(ox + 0.4 * span * math.sin(b), oy + 0.4 * span * math.cos(b))
            pygame.draw.line(chart, PENCIL, at(ox, oy), end)
            if t - labelled >= 60:
                labelled = t
                chart.blit(pen.render(stamp(t), True, PENCIL), (end[0] + 2, end[1] - 10))
        pts = [at(x, y) for _, x, y in track]
        if len(pts) > 1:
            pygame.draw.lines(chart, PENCIL, False, pts, 3)
        last = -1e9
        for t, x, y in track:  # a tick and the time every three minutes
            if t - last >= 180:
                last = t
                q = at(x, y)
                pygame.draw.circle(chart, PENCIL, q, 4, 2)
                chart.blit(pen.render(stamp(t), True, PENCIL), (q[0] + 8, q[1] - 22))
        hd = math.radians(heading)
        pygame.draw.circle(chart, PENCIL, (w / 2, h / 2), 7, 2)
        pygame.draw.line(chart, PENCIL, (w / 2, h / 2), (w / 2 + 40 * math.sin(hd), h / 2 - 40 * math.cos(hd)), 3)
        for t, ox, oy, brg, rng, text in notes:  # reports: a cross where placed, else a note along the bearing
            b = math.radians(brg)
            d = rng if rng is not None else 2500.0
            q = at(ox + d * math.sin(b), oy + d * math.cos(b))
            if rng is not None:
                pygame.draw.line(chart, PENCIL, (q[0] - 9, q[1] - 9), (q[0] + 9, q[1] + 9), 2)
                pygame.draw.line(chart, PENCIL, (q[0] - 9, q[1] + 9), (q[0] + 9, q[1] - 9), 2)
            chart.blit(pen.render(f"{stamp(t)} {text}", True, PENCIL), (q[0] + 12, q[1] + 2))
        if solution:  # the TDC's target, in red pencil: where, and where in five minutes
            tx, ty, vx, vy = solution
            here, later = at(x0 + tx, y0 + ty), at(x0 + tx + vx * 300, y0 + ty + vy * 300)
            pygame.draw.circle(chart, RED_PENCIL, here, 10, 2)
            pygame.draw.line(chart, RED_PENCIL, here, later, 3)
            crs, spd = math.degrees(math.atan2(vx, vy)) % 360, math.hypot(vx, vy) / KNOT
            chart.blit(art.hand(19).render(f"TGT C{crs:03.0f} S{spd:.0f}", True, RED_PENCIL),
                       (here[0] + 14, here[1] + 8))
    bar = w * MILE / span  # a nautical mile in cables, and the chart's title, bottom and top left
    pygame.draw.line(chart, PRINT, (90, h - 70), (90 + bar, h - 70), 3)
    for c in range(11):
        pygame.draw.line(chart, PRINT, (90 + bar * c / 10, h - (78 if c % 5 == 0 else 74)), (90 + bar * c / 10, h - 66),
                         2 if c % 5 == 0 else 1)
    chart.blit(tiny.render("0     5 CABLES      1 N.MILE", True, PRINT), (86, h - 62))
    chart.blit(small.render("ICELAND - FAROE RIDGE.  SOUNDINGS IN FATHOMS", True, PRINT), (w - 420, 12))
    chart.blit(art.hand(22).render("ATTACK PLOT", True, PENCIL), (20, 12))
    return chart


def legend_art(alarms, size=(200, 360)):
    """The small alarm panel at the conn: which thing the orange lamps are for."""
    surf = art.texture(size, art.FACE, grain=3)
    w, h = size
    art.label_plate(surf, (w // 2, 22), "ALARM", 12)
    for i, (name, on, _) in enumerate(alarms):
        art.annunciator(surf, pygame.Rect(16, 52 + i * 74, w - 32, 58), name, on, art.AMBER)
    return surf


def placement(s):
    """Model space to the room for station s: its floor point, x to the panel's right, z into the room."""
    c, n = np.array(s.centre), np.array(s.normal)
    z = np.array([n[0], 0.0, n[2]]) / math.hypot(n[0], n[2])
    y = np.array([0.0, 1.0, 0.0])
    m = np.identity(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = np.cross(y, z), y, z, (c[0], 0.0, c[2])
    return m


def standing_at(base, facing):
    """Model space to the room for a figure with his feet at `base`, facing level along `facing`."""
    z = np.asarray(facing, float)
    y = np.array([0.0, 1.0, 0.0])
    m = np.identity(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = np.cross(y, z), y, z, base
    return m


def rot_y(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def reach(age):
    """Where a man's arm is between its poses (0 rest, 1 half, 2 full) `age` s after he put his hand to his
    controls: out and back, smoothly."""
    return 0.0 if age is None or age >= REACH_TIME else 2 * math.sin(math.pi * age / REACH_TIME)


def wheel_pose(angle):
    """A wheel turn as a place between the posed turns (a fraction, for the arms) and the angle itself, kept to them."""
    a = float(np.clip(angle, WHEEL_ANGLES[0], WHEEL_ANGLES[-1]))
    return float(np.interp(a, WHEEL_ANGLES, np.arange(len(WHEEL_ANGLES)))), a


def rot_x(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def head_turn(place, pivot, eye, t, phase, age=None):
    """How a crewman holds his head: idle glances about his work, and round to look at you (`eye`) while he makes a
    call (`age`: seconds since he spoke, None if not lately)."""
    d = place[:3, :3].T @ (np.asarray(eye, float) - (place[:3, :3] @ pivot + place[:3, 3]))
    yaw_eye = max(-80.0, min(80.0, math.degrees(math.atan2(d[0], d[2]))))
    pitch_eye = max(-30.0, min(35.0, math.degrees(math.atan2(d[1], math.hypot(d[0], d[2])))))
    yaw = 14.0 * math.sin(0.21 * t + phase) * math.sin(0.083 * t + 2.0 * phase)
    pitch = 4.0 + 4.0 * math.sin(0.17 * t + 3.0 * phase)
    if age is not None:
        def smooth(a, b, x):
            k = min(max((x - a) / (b - a), 0.0), 1.0)
            return k * k * (3 - 2 * k)
        w = smooth(0.0, 0.45, age) * (1.0 - smooth(2.6, 3.3, age))
        yaw, pitch = yaw + (yaw_eye - yaw) * w, pitch + (pitch_eye - pitch) * w
    return rot_y(yaw) @ rot_x(-pitch)


def crew_places():
    """{crewman: (seated, stood aside or None)}: where each keeps his watch, and where he waits while you take it."""
    places = {}
    for s in cr.STATIONS:
        if s.working and s.name != "HELM AND PLANES":
            seat, facing, aside = watch_spot(s)
            places[s.name] = (standing_at(seat, facing), standing_at(aside, facing))
    helm = placement(next(s for s in cr.STATIONS if s.name == "HELM AND PLANES"))
    for key, (x, out) in zip(("HELM", "PLANES"), HELM_SEATS):
        places[key] = (helm @ standing_at((x, 0.0, out), (0.0, 0.0, -1.0)), None)
    return places


class Model:
    """A .glb on the GPU: its parts' primitives, each with its texture and material."""

    def __init__(self, ctx, prog, path):
        self.parts = {}
        loaded = gltf.load(path)
        poses = sorted((n for n in loaded if n.startswith("arms_")), key=lambda n: int(n[5:]))
        # arm poses share one mesh, so they blend: one dynamic buffer per primitive, written as the pose moves
        self.arm_poses = [[v for v, *_ in loaded[n][1]] for n in poses]
        if any([v.shape for v in p] != [v.shape for v in self.arm_poses[0]] for p in self.arm_poses):
            raise ValueError(f"{path.name}: its arms_N poses must be the same mesh, posed differently, to blend")
        self.arm_at = None
        self.arm_vbos = []
        for name, (pivot, prims) in loaded.items():
            if name.startswith("arms_") and name != "arms_0":
                continue
            draws = []
            for verts, idx, mat, img in prims:
                vbo, ibo = ctx.buffer(verts.tobytes(), dynamic=name == "arms_0"), ctx.buffer(idx.astype("u4").tobytes())
                if name == "arms_0":
                    self.arm_vbos.append(vbo)
                vao = ctx.vertex_array(prog, [(vbo, "3f 3f 2f 3f", "in_pos", "in_norm", "in_uv", "in_col")], ibo, 4)
                tex = None
                if img is not None:
                    tex = ctx.texture(img.get_size(), 3, pygame.image.tobytes(img.convert(24) if img.get_bitsize()
                                                                              != 24 else img, "RGB"))
                    tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
                    tex.anisotropy = 8.0
                    tex.build_mipmaps()
                shine = (1.0 - mat["rough"]) * 1.6 + 0.4 * mat["metal"]
                draws.append((vao, tex, tuple(mat["color"][:3]), any(mat["emissive"]), shine, mat["wear"]))
            self.parts[name] = (pivot, draws)
        self.triangles = sum(d[0].vertices // 3 for _, ds in self.parts.values() for d in ds)

    def render(self, prog, place, turns=None, arms=0):
        """place: model to room (4x4); turns: {part: 3x3 rotation about the part's pivot}; arms: the arm pose, a
        fraction between two posed ones blending them."""
        if self.arm_poses and arms != self.arm_at:
            self.arm_at = arms
            k = min(int(arms), len(self.arm_poses) - 1)
            f, k1 = arms - k, min(k + 1, len(self.arm_poses) - 1)
            for vbo, a, b in zip(self.arm_vbos, self.arm_poses[k], self.arm_poses[k1]):
                vbo.write((a * (1 - f) + b * f).astype("f4").tobytes())
        for name, (pivot, draws) in self.parts.items():
            m = place
            if turns and name in turns:
                t = np.identity(4)
                t[:3, :3] = turns[name]
                t[:3, 3] = pivot - turns[name] @ pivot
                m = place @ t
            prog["model"].write(m.T.astype("f4").tobytes())
            for vao, tex, factor, emissive, shine, wear in draws:
                prog["textured"].value = tex is not None
                if tex is not None:
                    tex.use(0)
                    prog["tex"].value = 0
                prog["factor"].value = factor
                prog["emissive"].value = emissive
                prog["shine"].value = shine
                prog["wear"].value = wear
                vao.render()


class RoomRenderer:
    """Owns the GL context and everything uploaded to it; render() gives back a screen-sized pygame Surface."""

    def __init__(self, size=(W, H)):
        self.size = size
        self.ctx = moderngl.create_standalone_context()
        self.ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        self.ctx.disable(moderngl.CULL_FACE)  # the hull and bulkheads are seen from inside; keep every face
        self.solid = self.ctx.program(vertex_shader=SOLID_VS, fragment_shader=SOLID_FS)
        self.flat = self.ctx.program(vertex_shader=PANEL_VS, fragment_shader=PANEL_FS)
        self.model = self.ctx.program(vertex_shader=MODEL_VS, fragment_shader=MODEL_FS)
        build_all()  # the models live outside git: build any that are missing (once, about two seconds)
        self.consoles = [(Model(self.ctx, self.model, ASSETS / STATION_FILES[s.name]), placement(s))
                         for s in cr.STATIONS]
        vbo = self.ctx.buffer(build_room().tobytes())
        self.room = self.ctx.vertex_array(self.solid, [(vbo, "3f 3f 3f 1f", "in_pos", "in_norm", "in_col", "in_mat")])
        self.panels = []  # (vertex array, texture, normal, glow, name)
        self.crew = {}    # crewman -> (seated model, its place, standing model or None, its place)
        self.stepping = {}  # crewman -> (stood aside?, when he last got up or sat down): his step aside, animated
        self.coxswain = Model(self.ctx, self.model, ASSETS / COXSWAIN_FILE)
        for key, (sat, stood) in crew_places().items():
            seated = Model(self.ctx, self.model, ASSETS / CREW_FILES[key])
            standing = Model(self.ctx, self.model, ASSETS / CREW_FILES[key].replace("seated", "standing")) \
                if stood is not None else None
            self.crew[key] = (seated, sat, standing, stood)
        for s in cr.STATIONS:
            tex_size = (W, H) if s.working else (int(s.w * 400), int(s.h * 400))
            surf = None if s.working else panel_art(s.name, tex_size)
            self._panel(s.centre, s.normal, s.w, s.h, tex_size, surf, glow=1.0 if s.working else 0.0, name=s.name)
        tx, tz, sx, sz = cr.TABLE
        self._panel((tx, cr.TABLE_TOP + 0.03, tz), (0.0, 1.0, 0.0), sx - 0.1, sz - 0.1, (1040, 720), None, 0.35,
                    "TABLE")
        self._panel(LEGEND_AT, (0.0, 0.1, 0.995), 0.2, 0.36, (200, 360), None, 1.0, "ALARMS")
        self.msaa = self.ctx.framebuffer(self.ctx.renderbuffer(size, samples=4),
                                         self.ctx.depth_renderbuffer(size, samples=4))
        self.out = self.ctx.framebuffer(self.ctx.renderbuffer(size))

    def _panel(self, centre, normal, w, h, tex_size, surf, glow, name):
        if abs(normal[1]) > 0.9:  # the table: lies flat, top of the picture toward the bow
            right, up, n = np.array((1.0, 0, 0)), np.array((0, 0, -1.0)), np.array(normal, float)
        else:
            right, up, n = basis(normal)
        c = np.array(centre) + n * cr.PANEL_LIFT
        corners = [c + right * (sx * w / 2) + up * (sy * h / 2) for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1))]
        uv = ((0, 0), (1, 0), (1, 1), (0, 1))  # textures are uploaded top row first
        rows = [(*corners[i], *uv[i]) for i in (0, 3, 2, 0, 2, 1)]
        vbo = self.ctx.buffer(np.array(rows, "f4").tobytes())
        tex = self.ctx.texture(tex_size, 3)
        tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        tex.anisotropy = 8.0
        if surf is not None:
            self.upload(tex, surf)
        self.panels.append((self.ctx.vertex_array(self.flat, [(vbo, "3f 2f", "in_pos", "in_uv")]), tex, n, glow, name))

    @staticmethod
    def upload(tex, surf):
        tex.write(pygame.image.tobytes(surf, "RGB"))
        tex.build_mipmaps()

    def texture(self, name):
        return next(p[1] for p in self.panels if p[4] == name)

    def render(self, pose, screens=None, plot_surf=None, legend_surf=None, alert=0.0, aside=(), t=0.0, speaking=None,
               working=None, wheels=(0.0, 0.0), coxswain=None):
        """Draw the room from `pose`. screens: fresh station canvases by name (the rest keep their last picture);
        plot_surf: the plot table, when it has changed; legend_surf: the alarm legend; alert: the orange lamps, 0..1;
        aside: stations whose crewman has stood aside for the captain; t: seconds, for the crew's idle life;
        speaking: {crewman: seconds since his last call}, so he looks round at you; working: {crewman: seconds since
        he put his hand to his controls}; wheels: how far the helmsman's and planesman's wheels are turned, deg;
        coxswain: in training, the station he's sending you to ("" for none); None when he isn't aboard."""
        for name, surf in (screens or {}).items():
            self.upload(self.texture(name), surf)
        if legend_surf is not None:
            self.upload(self.texture("ALARMS"), legend_surf)
        if plot_surf is not None:
            self.upload(self.texture("TABLE"), plot_surf)
        w, h = self.size
        mvp = perspective(cr.FOVY, w / h, 0.05, 40.0) @ look_at(pose.pos, pose.forward())
        sonar = next(s for s in cr.STATIONS if s.working)
        lights = [*LAMPS, tuple(np.array(sonar.centre) + np.array(sonar.normal) * 0.5),
                  ALERT_LAMPS[-1][0], ALERT_LAMPS[3][0]]  # the conn's and the helm's alarm lamps throw light too
        colours = [LAMP_COLOUR] * len(LAMPS) + [tuple(0.6 * c for c in SCREEN_GLOW)] + \
            [tuple(1.4 * alert * c for c in ALERT_COLOUR)] * 2
        for prog in (self.solid, self.flat, self.model):
            prog["mvp"].write(mvp.T.astype("f4").tobytes())
            prog["eye"].value = tuple(pose.pos)
            prog["lights"].value = len(lights)
            prog["light_pos"].write(np.array(lights + [(0, 0, 0)] * (8 - len(lights)), "f4").tobytes())
            prog["light_col"].write(np.array(colours + [(0, 0, 0)] * (8 - len(colours)), "f4").tobytes())
            prog["fog_col"].value = FOG
            prog["view"].value = (float(w), float(h))
        self.solid["alert"].value = alert
        self.msaa.use()
        self.ctx.clear(*FOG, depth=1.0)
        self.room.render()
        turned = [wheel_pose(a) for a in wheels]  # the wheels and the men's arms both at the nearest posed turn
        # the helm's model space faces the men, so a turn to their right is the other way about its +z
        spin = {f"wheel_{k}": rot_z(-a) for k, (_, a) in enumerate(turned)}
        for model, place in self.consoles:
            model.render(self.model, place, spin)
        for k, (key, (seated, sat, standing, stood)) in enumerate(self.crew.items()):
            now_aside = key in aside and standing is not None
            was, since = self.stepping.get(key, (now_aside, -1e9))
            if was != now_aside:
                self.stepping[key] = (now_aside, t)
                since = t
            f = ease((t - since) / STEP_TIME)
            if f < 1:  # getting up and stepping aside, or back to his seat: on his feet between the two
                go = f if now_aside else 1 - f
                model, place = standing, sat.copy()
                place[:3, 3] = sat[:3, 3] + (stood[:3, 3] - sat[:3, 3]) * go
            else:
                model, place = (standing, stood) if now_aside else (seated, sat)
            arms = 0
            if model is seated:
                arms = turned[["HELM", "PLANES"].index(key)][0] if key in ("HELM", "PLANES") else \
                    reach((working or {}).get(key))
            phase = 1.7 * k
            sway = np.identity(4)  # breathing and shifting his weight: a degree or less, about his feet
            sway[:3, :3] = rot_x(0.5 * math.sin(t * 1.45 + phase)) @ rot_y(1.2 * math.sin(t * 0.13 + phase))
            place = place @ sway
            pivot = model.parts["head"][0]
            age = (speaking or {}).get(key)
            model.render(self.model, place, {"head": head_turn(place, pivot, pose.pos, t, phase, age)}, arms)
        if coxswain is not None:  # he turns to the station he's sending you to and points; otherwise he faces you
            base = np.array(COXSWAIN_AT)
            goal = crew_places()[coxswain][0][:3, 3] if coxswain else pose.pos
            face = np.array([goal[0] - base[0], 0.0, goal[2] - base[2]])
            place = standing_at(base, face / max(np.linalg.norm(face), 1e-6))
            pivot = self.coxswain.parts["head"][0]
            turn = head_turn(place, pivot, pose.pos, t, 0.7, (speaking or {}).get("COXSWAIN"))
            self.coxswain.render(self.model, place, {"head": turn}, 1 if coxswain else 0)
        for vao, tex, n, glow, _ in self.panels:
            tex.use(0)
            self.flat["tex"].value = 0
            self.flat["normal"].value = tuple(n)
            self.flat["glow"].value = glow
            vao.render()
        self.ctx.copy_framebuffer(self.out, self.msaa)
        return pygame.image.frombytes(self.out.read(components=3), self.size, "RGB", True)
