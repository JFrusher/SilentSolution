"""The stations' instruments in 2.5D: switches, push-buttons, lamps and gauge bezels are real 3D models (built with
graphics/models.Builder, like the room's desks) rendered once with moderngl into cached sprites with soft shadows;
gauge faces are painted, needles cast a shadow on them, and curved glass catches the light on top.
Drawn natively at each station's size, so nothing is blown up from the old one-screen console."""
import functools
import math

import moderngl
import numpy as np
import pygame
import pygame.gfxdraw

from graphics import console_art as art
from graphics.models import BAKELITE, CHROME, RED, Builder, frame
from settings import SETTINGS

SPRITE_VS = """#version 330
uniform mat4 mvp;
in vec3 in_pos; in vec3 in_norm; in vec3 in_col;
out vec3 n; out vec3 c;
void main() { n = in_norm; c = in_col; gl_Position = mvp * vec4(in_pos, 1.0); }
"""
SPRITE_FS = """#version 330
uniform mat3 turn;      // the model's tilt, so the light stays where the room's lamps are
uniform int kind;       // 0: paint or bakelite, 1: metal, 2: lit (its own colour)
uniform float rough;
in vec3 n; in vec3 c;
out vec4 f;
vec3 env(vec3 r) {      // a studio of a dim room with one lamp strip up and to the left
    vec3 e = mix(vec3(0.02), vec3(0.75, 0.73, 0.68), smoothstep(-0.35, 0.85, r.y));
    return e + vec3(1.6) * exp(-pow((r.x + 0.35) / 0.16, 2.0)) * smoothstep(0.15, 0.7, r.y);
}
void main() {
    vec3 N = normalize(turn * n), V = vec3(0.0, 0.0, 1.0), L = normalize(vec3(-0.45, 0.7, 0.55));
    vec3 R = reflect(-V, N);
    float d = max(dot(N, L), 0.0);
    float s = pow(max(dot(N, normalize(L + V)), 0.0), mix(10.0, 120.0, 1.0 - rough));
    vec3 col;
    if (kind == 2) col = c;
    else if (kind == 1) col = c * env(R) + vec3(s) * 0.7;
    else {
        float fres = pow(1.0 - max(N.z, 0.0), 3.0);
        col = c * (0.16 + 0.95 * d) + vec3(s) * (1.0 - rough) * 0.8 + env(R) * (0.03 + 0.3 * fres) * (1.0 - rough);
    }
    f = vec4(pow(col, vec3(1.0 / 2.2)), 1.0);
}
"""
_GL = {}


def _gl():
    if not _GL:
        ctx = moderngl.create_standalone_context()
        _GL.update(ctx=ctx, prog=ctx.program(vertex_shader=SPRITE_VS, fragment_shader=SPRITE_FS))
    return _GL["ctx"], _GL["prog"]


def _surface(rgba):
    """(h, w, 4) uint8 -> an alpha pygame Surface."""
    h, w = rgba.shape[:2]
    surf = pygame.image.frombuffer(np.ascontiguousarray(rgba).tobytes(), (w, h), "RGBA")
    return surf.convert_alpha() if pygame.display.get_surface() else surf.copy()


def render(b, size, extent, tilt=22.0):
    """A Builder's model seen head-on from a little above, as an RGBA Surface `size` px; extent: the half-width and
    half-height in metres in frame. The model's x is right, y up, z out of the panel toward you."""
    ctx, prog = _gl()
    w, h = size
    ex, ey = extent
    t = math.radians(tilt)
    turn = np.array([[1, 0, 0], [0, math.cos(t), -math.sin(t)], [0, math.sin(t), math.cos(t)]])  # look down on it
    m = np.identity(4)
    m[:3, :3] = turn
    proj = np.diag([1 / ex, 1 / ey, -1 / (4 * max(ex, ey)), 1.0])
    mvp = (proj @ m).T.astype("f4")
    fbo = ctx.framebuffer(ctx.renderbuffer(size, 4, samples=4), ctx.depth_renderbuffer(size, samples=4))
    out = ctx.framebuffer(ctx.renderbuffer(size, 4))
    fbo.use()
    ctx.enable(moderngl.DEPTH_TEST)
    ctx.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)
    prog["mvp"].write(mvp.tobytes())
    prog["turn"].write(turn.T.astype("f4").tobytes())
    made = []
    for _, prims in b.mesh().values():
        for mat, verts, idx in prims:
            spec = b.materials[mat]
            vbo, ibo = ctx.buffer(verts.tobytes()), ctx.buffer(idx.astype("u4").tobytes())
            vao = ctx.vertex_array(prog, [(vbo, "3f 3f 8x 3f", "in_pos", "in_norm", "in_col")], ibo, 4)
            prog["kind"].value = 2 if any(spec.get("emissive", (0, 0, 0))) else 1 if spec.get("metal") else 0
            prog["rough"].value = spec.get("rough", 0.8)
            vao.render()
            made += [vao, vbo, ibo]
    ctx.copy_framebuffer(out, fbo)
    rgba = np.frombuffer(out.read(components=4), np.uint8).reshape(h, w, 4)[::-1].astype(float)
    for obj in made + [fbo, out]:
        obj.release()
    a = rgba[..., 3:] / 255.0
    rgba[..., :3] = np.where(a > 0, rgba[..., :3] / np.maximum(a, 1e-3), 0)  # un-premultiply the antialiased edge
    return _surface(np.clip(rgba, 0, 255).astype(np.uint8))


def shadow(surf, offset, blur=4, strength=0.55):
    """A soft dark copy of surf's silhouette, as cast on the panel by a lamp above and to the left."""
    w, h = surf.get_size()
    a = pygame.surfarray.array_alpha(surf).astype(float) * strength
    small = pygame.Surface((max(1, w // blur), max(1, h // blur)), pygame.SRCALPHA)
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    mask.fill((0, 0, 0, 255))
    pygame.surfarray.pixels_alpha(mask)[:] = a.astype(np.uint8)
    small = pygame.transform.smoothscale(mask, small.get_size())
    soft = pygame.transform.smoothscale(small, (w, h))
    out = pygame.Surface((w + abs(offset[0]), h + abs(offset[1])), pygame.SRCALPHA)
    out.blit(soft, offset)
    return out


def _with_shadow(sprite, depth=0.06):
    """The sprite over its own shadow, on one surface, the sprite's centre at the surface's centre."""
    w, h = sprite.get_size()
    off = (max(2, round(w * depth * 0.6)), max(2, round(h * depth)))
    sh = shadow(sprite, off)
    out = pygame.Surface((w + 2 * off[0], h + 2 * off[1]), pygame.SRCALPHA)
    out.blit(sh, off)
    out.blit(sprite, off)
    return out


def blit_centred(surf, sprite, c):
    surf.blit(sprite, sprite.get_rect(center=(round(c[0]), round(c[1]))))


# ---------- switches ----------
@functools.cache
def toggle_sprite(up, guard, px):
    """A bakelite-mounted tumbler: knurled chrome nut, a bat handle thrown up or down; a red flip guard, propped open,
    over a firing switch."""
    b = Builder()
    b.lathe((0, 0, 0), (0, 0, 1), [(0, 0), (0.019, 0), (0.019, 0.002), (0.016, 0.003), (0, 0.003)], BAKELITE,
            "bakelite", seg=20)
    b.lathe((0, 0, 0.003), (0, 0, 1), [(0.0125, 0), (0.0125, 0.007), (0.009, 0.009), (0, 0.009)], CHROME, "metal",
            seg=6)  # hex nut
    side = 1 if up else -1
    root, tip = np.array((0, 0, 0.011)), np.array((0, side * 0.026, 0.03))
    pts = [root + (tip - root) * k for k in np.linspace(0, 1, 6)]
    b.tube(pts, np.linspace(0.0042, 0.003, 6), CHROME, "metal", seg=10)
    b.blob(tip, frame((0, side, 1)), (0.0048, 0.0048, 0.0048), CHROME, "metal", nu=12, nv=8)
    if guard:
        hinge = np.array((0, 0.026, 0.004))
        fr = frame((0, 0.2, 1))
        b.box(hinge + (0, 0.004, 0.024), (0.036, 0.004, 0.05), RED, "bakelite", fr, r=0.003)
        for x in (-0.017, 0.017):
            b.box(hinge + (x, -0.012, 0.012), (0.003, 0.03, 0.022), RED, "bakelite", r=0.001)
        b.cylinder(hinge + (-0.02, 0, 0), hinge + (0.02, 0, 0), 0.003, CHROME, "metal", seg=8)
    return _with_shadow(render(b, (px, px), (0.034, 0.034), tilt=8.0))


@functools.cache
def button_sprite(w, h, colour, lit):
    """A square backlit push-button: a chrome bezel round a translucent cap, the bulb behind it on or off."""
    b = Builder()
    ex, ey = 0.02 * w / max(w, h), 0.02 * h / max(w, h)
    t = 0.0022
    for y in (-1, 1):
        b.box((0, y * (ey - t), 0.003), (2 * ex, 2 * t, 0.006), CHROME, "metal", r=0.0015)
    for x in (-1, 1):
        b.box((x * (ex - t), 0, 0.003), (2 * t, 2 * ey, 0.006), CHROME, "metal", r=0.0015)
    cap = tuple(min(1.0, v / 255 * 1.15) for v in colour) if lit else tuple(0.05 + v / 255 * 0.12 for v in colour)
    b.box((0, 0, 0.004), (2 * (ex - 2 * t), 2 * (ey - 2 * t), 0.008), cap, "glow" if lit else "bakelite", r=0.002)
    if lit:
        b.box((0, 0, 0.0081), (2 * (ex - 3 * t), 2 * (ey - 3 * t), 0.0005), tuple(min(1.0, v * 1.15) for v in cap),
              "glow")
    return render(b, (w, h), (ex * 1.04, ey * 1.04), tilt=10.0)


def button(surf, rect, legend, lit, colour):
    """A push-button filling rect, its legend engraved on the cap: dark on a lit cap, the cap's colour on a dark one."""
    colour = art.SAFE.get(colour, colour) if SETTINGS["colorblind"] else colour
    r = pygame.Rect(rect)
    if lit:
        halo = art._glow(colour, max(4, min(r.w, r.h) // 3))
        surf.blit(pygame.transform.smoothscale(halo, (r.w * 2, r.h * 2)), (r.x - r.w // 2, r.y - r.h // 2))
    sprite = button_sprite(r.w, r.h, colour, lit)
    surf.blit(shadow(sprite, (3, 5), strength=0.5), (r.x, r.y))
    surf.blit(sprite, r.topleft)
    size = max(9, min(r.h // 3, 22))
    while size > 8 and art.sans(size, True).size(legend)[0] > r.w * 0.8:
        size -= 1
    ink = (30, 24, 16) if lit else tuple(min(255, 90 + v // 2) for v in colour)
    art.engrave(surf, legend, r.center, size, ink, center=True)


@functools.cache
def lamp_sprite(colour, lit, px):
    """A jewelled pilot lamp: a knurled chrome bezel and a faceted glass dome, lit or dark."""
    b = Builder()
    b.lathe((0, 0, 0), (0, 0, 1), [(0, 0), (0.014, 0), (0.014, 0.004), (0.011, 0.006), (0.0105, 0.0065)], CHROME,
            "metal", seg=24)
    dome = tuple(min(1.0, v / 255 * 1.2) for v in colour) if lit else tuple(0.04 + v / 255 * 0.14 for v in colour)
    b.lathe((0, 0, 0.005), (0, 0, 1), [(0.0105, 0), (0.0098, 0.003), (0.008, 0.006), (0.0045, 0.0085), (0, 0.009)],
            dome, "glow" if lit else "bakelite", seg=8)  # eight facets round
    return _with_shadow(render(b, (px, px), (0.016, 0.016), tilt=10.0), 0.04)


def lamp(surf, c, lit, colour, px):
    colour = art.SAFE.get(colour, colour) if SETTINGS["colorblind"] else colour
    if lit:
        blit_centred(surf, art._glow(colour, px // 4), c)
    blit_centred(surf, lamp_sprite(colour, lit, px), c)


def lamp_strip(surf, rect, lamps):
    """A column of jewel lamps, each with its engraved traffolyte legend: a lamp reads by its words, not its colour."""
    r = pygame.Rect(rect)
    row = r.h / max(len(lamps), 1)
    px = int(min(row * 0.8, 46))
    for i, (name, lit, colour) in enumerate(lamps):
        y = r.y + row * (i + 0.5)
        lamp(surf, (r.x + px * 0.75, y), lit, colour, px)
        plate = pygame.Rect(0, 0, r.w - px * 1.7, min(row * 0.62, 34))
        plate.midleft = (r.x + px * 1.55, y)
        pygame.draw.rect(surf, (12, 12, 11), plate.move(2, 3), border_radius=3)
        pygame.draw.rect(surf, (26, 26, 25), plate, border_radius=3)
        pygame.draw.rect(surf, (80, 78, 72), plate, 1, border_radius=3)
        art.engrave(surf, name, plate.center, int(plate.h * 0.55), art.LEGEND if lit else art.LEGEND_DIM,
                    center=True)


# ---------- gauges ----------
BLACK_FACE, WHITE_FACE = ((22, 22, 20), art.LEGEND), ((228, 224, 208), (22, 20, 18))


@functools.cache
def face_art(radius, title, lo, hi, major, minor, red, units, white):
    """A gauge's face, painted at twice its size and brought down so every tick is clean: black-faced with cream
    figures for the electrical and navigation instruments, white enamel with black figures for pressure."""
    ground, ink = WHITE_FACE if white else BLACK_FACE
    R = radius * 2
    size = R * 2 + 4
    x, y = np.ogrid[:size, :size]
    c = size / 2
    d = np.hypot(x - c, y - c)
    shade = 1.08 - 0.3 * (d / R) ** 2 - 0.06 * ((y - c) / R)  # a little light from above, darker toward the rim
    rgb = np.array(ground, float)[None, None, :] * shade[..., None] + np.random.default_rng(radius).normal(
        0, 2.5, (size, size, 1))
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = np.clip(rgb, 0, 255).astype(np.uint8)
    pygame.surfarray.pixels_alpha(surf)[:] = np.where(d <= R, 255, 0).astype(np.uint8)
    cc = (c, c)
    rr = R * 0.86
    if red:
        a0, a1 = (art.value_angle(v, lo, hi) for v in red)
        band = [art.polar(cc, rr, a0 + (a1 - a0) * k / 40) for k in range(41)]
        band += [art.polar(cc, rr - R * 0.07, a1 + (a0 - a1) * k / 40) for k in range(41)]
        pygame.draw.polygon(surf, (190, 40, 28), band)
    for v in np.arange(lo, hi + minor / 2, minor):
        a = art.value_angle(v, lo, hi)
        big = abs((v - lo) / major - round((v - lo) / major)) < 1e-6
        p0, p1 = art.polar(cc, rr, a), art.polar(cc, rr - R * (0.13 if big else 0.06), a)
        wdt = R * (0.022 if big else 0.009)
        n = (math.sin(math.radians(a)) * wdt, math.cos(math.radians(a)) * wdt)
        pygame.draw.polygon(surf, ink, [(p0[0] - n[0], p0[1] - n[1]), (p0[0] + n[0], p0[1] + n[1]),
                                        (p1[0] + n[0], p1[1] + n[1]), (p1[0] - n[0], p1[1] - n[1])])
        if big:
            label = art.sans(int(R * 0.15), True).render(f"{v:g}", True, ink)
            surf.blit(label, label.get_rect(center=art.polar(cc, rr - R * 0.27, a)))
    if title:
        label = art.sans(int(R * 0.13), True).render(title, True, ink)
        surf.blit(label, label.get_rect(center=(c, c + R * 0.3)))
    if units:
        label = art.sans(int(R * 0.09), False).render(units, True, (200, 60, 40) if white else art.WARN)
        surf.blit(label, label.get_rect(center=(c, c + R * 0.46)))
    arrow = [(c - R * 0.04, c - R * 0.38), (c, c - R * 0.46), (c + R * 0.04, c - R * 0.38)]  # the broad arrow
    pygame.draw.lines(surf, ink, False, arrow, max(1, R // 70))
    pygame.draw.line(surf, ink, (c, c - R * 0.46), (c, c - R * 0.34), max(1, R // 70))
    return pygame.transform.smoothscale(surf, (size // 2, size // 2))


@functools.cache
def case_sprites(radius):
    """The gauge's black case with its shadow (under the face), and the chrome bezel ring (over the glass)."""
    m = 0.05 / radius  # metres per pixel: every gauge is the same model, scaled
    px = 2 * round(radius * 1.16) + 8
    b = Builder()
    b.lathe((0, 0, -0.004), (0, 0, 1), [(0, 0), (0.05 + 0.006, 0), (0.05 + 0.006, 0.004), (0, 0.004)], BAKELITE,
            "bakelite", seg=48)
    case = _with_shadow(render(b, (px, px), (px / 2 * m, px / 2 * m), tilt=0.0), 0.035)
    b = Builder()
    b.lathe((0, 0, 0), (0, 0, 1), [(0.0495, 0.0), (0.0525, 0.001), (0.0555, 0.004), (0.0555, 0.006), (0.0535, 0.0085),
                                   (0.0505, 0.0088), (0.0495, 0.007)], CHROME, "metal", seg=64, crisp=False)
    bezel = render(b, (px, px), (px / 2 * m, px / 2 * m), tilt=0.0)
    hub = Builder()
    hub.lathe((0, 0, 0), (0, 0, 1), [(0, 0), (0.0065, 0), (0.006, 0.002), (0.0035, 0.004), (0, 0.0045)], BAKELITE,
              "metal", seg=20, crisp=False)
    hpx = max(8, round(0.016 / m))
    return case, bezel, render(hub, (hpx, hpx), (0.008, 0.008), tilt=0.0)


@functools.cache
def glass_art(radius):
    """Curved glass over the face: a broad sheen from the lamp up to the left, a crisp window reflection, the rim
    dark where it bends the light, and a film of grime."""
    size = 2 * radius
    x, y = np.ogrid[:size, :size]
    c = radius
    u, v = (x - c) / radius, (y - c) / radius
    d = np.hypot(u, v)
    sheen = np.exp(-((u + 0.35) ** 2 + (v + 0.4) ** 2) / 0.22) * 46
    crescent = np.exp(-((np.hypot(u + 0.12, v + 0.15) - 0.78) / 0.05) ** 2) * (np.clip(-u - v, 0, 1) ** 1.5) * 90
    rim = np.clip((d - 0.86) / 0.14, 0, 1) ** 2 * 120
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    rgb = pygame.surfarray.pixels3d(surf)
    rgb[:] = 255
    rgb[(rim > sheen + crescent)[..., None].repeat(3, -1)] = 0
    del rgb
    alpha = np.where(d < 1, np.maximum(sheen + crescent + 10, rim), 0)
    pygame.surfarray.pixels_alpha(surf)[:] = np.clip(alpha, 0, 255).astype(np.uint8)
    return surf


def needle(surf, c, deg, length, colour, width, tail=0.18):
    """A tapered needle with its counterweight, and the shadow it throws on the face just below it."""
    def shape(dx, dy):
        pts = [art.polar(c, length, deg), art.polar(c, width, deg + 90), art.polar(c, -length * tail, deg + 180 - 8),
               art.polar(c, -length * tail, deg + 180 + 8), art.polar(c, width, deg - 90)]
        return [(px + dx, py + dy) for px, py in pts]
    off = max(2, length / 22)
    pygame.gfxdraw.filled_polygon(surf, shape(off * 0.6, off), (0, 0, 0, 80))
    pts = shape(0, 0)
    pygame.gfxdraw.filled_polygon(surf, pts, colour)
    pygame.gfxdraw.aapolygon(surf, pts, colour)


def gauge(surf, centre, radius, spec, needles, white=False):
    """A whole instrument at `centre`: case and shadow, face, needles [(value, colour, width, length 0..1)], hub,
    glass and bezel."""
    case, bezel, hub = case_sprites(radius)
    blit_centred(surf, case, centre)
    face = face_art(radius, spec.get("title", ""), spec["lo"], spec["hi"], spec["major"], spec["minor"],
                    spec.get("red"), spec.get("units", ""), white)
    blit_centred(surf, face, centre)
    for value, colour, width, reach in needles:
        needle(surf, centre, art.value_angle(value, spec["lo"], spec["hi"]), radius * 0.86 * reach, colour,
               max(2, radius * width / 100))
    blit_centred(surf, hub, centre)
    blit_centred(surf, glass_art(radius), centre)
    blit_centred(surf, bezel, centre)
