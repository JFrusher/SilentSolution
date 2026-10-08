"""The control room in 3D: procedural meshes lit by the overhead lamps and fogged, rendered offscreen with moderngl and
read back as a pygame Surface. Panels are textures: the sonar console shows the live 2D station, the others carry
panel art built with console_art, and the plot table shows our dead-reckoning track."""
import math

import moderngl
import numpy as np
import pygame

import control_room as cr
from graphics import console_art as art
from layout import H, W

LAMPS = [(0.0, 2.28, z) for z in (-4.2, -1.9, 0.4, 2.7, 4.6)]
LAMP_COLOUR = (1.15, 0.9, 0.62)
SCREEN_GLOW = (0.35, 0.95, 0.55)  # the sonar CRT lights its corner
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

    for s in cr.STATIONS:
        console(m, s)
    trim_valves(m)
    return m.array()


def console(m, s):
    """A console carcass under each panel: desk, housing round the panel, hood; seats at the helm."""
    right, up, n = basis(s.normal)
    c = np.array(s.centre)
    axes = np.column_stack((right, up, n))
    m.box(c - n * 0.14, (s.w + 0.14, s.h + 0.14, 0.26), CONSOLE, axes=axes)  # housing
    m.box(c + up * (s.h / 2 + 0.09) - n * 0.05, (s.w + 0.14, 0.05, 0.22), CONSOLE, axes=axes)  # hood
    flat = np.array([n[0], 0.0, n[2]]) / math.hypot(n[0], n[2])
    level = np.column_stack((right, (0.0, 1.0, 0.0), flat))
    desk_top = c[1] - s.h / 2 * up[1] - 0.06
    m.box(np.array([c[0], desk_top / 2, c[2]]) + flat * 0.1, (s.w + 0.14, desk_top, 0.7), CONSOLE, axes=level)
    m.box(np.array([c[0], desk_top, c[2]]) + flat * 0.38, (s.w + 0.18, 0.04, 0.24), (0.2, 0.2, 0.19), axes=level)
    for k in range(int(s.w / 0.4)):  # lit push-buttons along the desk edge
        x = (k - (int(s.w / 0.4) - 1) / 2) * 0.35
        colour = ((0.9, 0.6, 0.2), (0.3, 0.8, 0.35), (0.85, 0.2, 0.15))[k % 3]
        m.box(np.array([c[0], desk_top + 0.025, c[2]]) + flat * 0.4 + right * x, (0.05, 0.02, 0.04), colour, 2,
              level)
    if s.name == "HELM AND PLANES":
        for side in (-0.6, 0.6):
            seat = np.array([c[0] + side, 0.5, c[2] + 0.75])
            m.cylinder((seat[0], 0, seat[2]), (seat[0], 0.45, seat[2]), 0.05, DARK)
            m.box(seat, (0.48, 0.1, 0.46), (0.3, 0.12, 0.1))
            m.box(seat + (0, 0.35, 0.22), (0.48, 0.6, 0.08), (0.3, 0.12, 0.1))
            m.cylinder((seat[0], 0.95, seat[2] - 0.45), (seat[0], 0.95, seat[2] - 0.75), 0.03, DARK)  # yoke column
            m.wheel((seat[0], 0.95, seat[2] - 0.45), (0, 0, 1), 0.17, DARK, mat=0)


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


def plot_art(track, heading, size=(520, 360), span=4000.0):
    """The dead-reckoning plot: our own track on squared paper, last hour, centred on where we are now."""
    surf = art.texture(size, art.PAPER, grain=2, mottle=6)
    w, h = size
    for k in range(0, w, 26):
        pygame.draw.line(surf, (178, 196, 200), (k, 0), (k, h))
    for k in range(0, h, 26):
        pygame.draw.line(surf, (178, 196, 200), (0, k), (w, k))
    if track:
        x0, y0 = track[-1]
        pts = [(w / 2 + (x - x0) / span * w, h / 2 - (y - y0) / span * w) for x, y in track]
        if len(pts) > 1:
            pygame.draw.lines(surf, art.INK, False, pts, 2)
        for p in pts[::60]:  # a tick every minute
            pygame.draw.circle(surf, art.INK_RED, p, 3)
        hd = math.radians(heading)
        pygame.draw.line(surf, art.INK_RED, (w / 2, h / 2), (w / 2 + 30 * math.sin(hd), h / 2 - 30 * math.cos(hd)), 3)
    art.engrave(surf, "D.R. PLOT  1:4000", (12, 10), 13, art.INK)
    return surf


class RoomRenderer:
    """Owns the GL context and everything uploaded to it; render() gives back a screen-sized pygame Surface."""

    def __init__(self, size=(W, H)):
        self.size = size
        self.ctx = moderngl.create_standalone_context()
        self.ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        self.ctx.disable(moderngl.CULL_FACE)  # the hull and bulkheads are seen from inside; keep every face
        self.solid = self.ctx.program(vertex_shader=SOLID_VS, fragment_shader=SOLID_FS)
        self.flat = self.ctx.program(vertex_shader=PANEL_VS, fragment_shader=PANEL_FS)
        vbo = self.ctx.buffer(build_room().tobytes())
        self.room = self.ctx.vertex_array(self.solid, [(vbo, "3f 3f 3f 1f", "in_pos", "in_norm", "in_col", "in_mat")])
        self.panels = []  # (vertex array, texture, normal, glow, name)
        for s in cr.STATIONS:
            tex_size = (W, H) if s.working else (int(s.w * 400), int(s.h * 400))
            surf = None if s.working else panel_art(s.name, tex_size)
            self._panel(s.centre, s.normal, s.w, s.h, tex_size, surf, glow=1.0 if s.working else 0.0, name=s.name)
        tx, tz, sx, sz = cr.TABLE
        self._panel((tx, cr.TABLE_TOP + 0.03, tz), (0.0, 1.0, 0.0), sx - 0.1, sz - 0.1, (520, 360), None, 0.35,
                    "TABLE")
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

    def render(self, pose, screens=None, plot_surf=None):
        """Draw the room from `pose`. screens: fresh station canvases by name (the rest keep their last picture);
        plot_surf: the plot table, when it has changed."""
        for name, surf in (screens or {}).items():
            self.upload(self.texture(name), surf)
        if plot_surf is not None:
            self.upload(self.texture("TABLE"), plot_surf)
        w, h = self.size
        mvp = perspective(cr.FOVY, w / h, 0.05, 40.0) @ look_at(pose.pos, pose.forward())
        sonar = next(s for s in cr.STATIONS if s.working)
        lights = [*LAMPS, tuple(np.array(sonar.centre) + np.array(sonar.normal) * 0.5)]
        colours = [LAMP_COLOUR] * len(LAMPS) + [tuple(0.6 * c for c in SCREEN_GLOW)]
        for prog in (self.solid, self.flat):
            prog["mvp"].write(mvp.T.astype("f4").tobytes())
            prog["eye"].value = tuple(pose.pos)
            prog["lights"].value = len(lights)
            prog["light_pos"].write(np.array(lights + [(0, 0, 0)] * (8 - len(lights)), "f4").tobytes())
            prog["light_col"].write(np.array(colours + [(0, 0, 0)] * (8 - len(colours)), "f4").tobytes())
            prog["fog_col"].value = FOG
            prog["view"].value = (float(w), float(h))
        self.msaa.use()
        self.ctx.clear(*FOG, depth=1.0)
        self.room.render()
        for vao, tex, n, glow, _ in self.panels:
            tex.use(0)
            self.flat["tex"].value = 0
            self.flat["normal"].value = tuple(n)
            self.flat["glow"].value = glow
            vao.render()
        self.ctx.copy_framebuffer(self.out, self.msaa)
        return pygame.image.frombytes(self.out.read(components=3), self.size, "RGB", True)
