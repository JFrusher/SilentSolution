"""All CRT drawing primitives and the phosphor post-processing pass."""
import numpy as np
import pygame

PHOSPHOR = (70, 255, 120)
DIM = (25, 110, 50)
RED = (255, 50, 40)
MONO = "consolas,couriernew,monospace"


class CRTRenderer:
    def __init__(self, size, ghosting=True, ghost_decay=140):
        self.size = size
        self.ghosting = ghosting
        self.ghost_decay = ghost_decay  # 0-255 multiplier per frame; higher = longer phosphor trail
        self.font = pygame.font.SysFont(MONO, 15)
        self.big = pygame.font.SysFont(MONO, 20, bold=True)
        self.small = pygame.font.SysFont(MONO, 12)
        self.huge = pygame.font.SysFont(MONO, 34, bold=True)
        self._text_cache = {}
        self.scanlines = self._scanlines()
        self.vignette = self._vignette()
        self.prev = None

    # --- pre-rendered overlays (built once) ---
    def _scanlines(self):
        s = pygame.Surface(self.size, pygame.SRCALPHA)
        alpha = pygame.surfarray.pixels_alpha(s)
        alpha[:, ::2] = 70
        del alpha  # release surface lock
        return s

    def _vignette(self):
        w, h = self.size
        x = np.linspace(-1, 1, w)[:, None]
        y = np.linspace(-1, 1, h)[None, :]
        tube = (x ** 8 + y ** 8) ** 0.125         # superellipse = rounded CRT tube edge
        edge = np.clip((tube - 0.97) / 0.03, 0, 1) ** 2
        falloff = np.clip(np.hypot(x, y) - 0.6, 0, 1) * 0.4
        s = pygame.Surface(self.size, pygame.SRCALPHA)
        alpha = pygame.surfarray.pixels_alpha(s)
        alpha[:] = (np.maximum(edge, falloff) * 255).astype(np.uint8)
        del alpha
        return s

    # --- vector primitives ---
    def line(self, surf, a, b, color=PHOSPHOR, width=1):
        pygame.draw.line(surf, color, a, b, width)

    def lines(self, surf, points, color=PHOSPHOR, width=1):
        if len(points) > 1:
            pygame.draw.lines(surf, color, False, points, width)

    def circle(self, surf, centre, radius, color=PHOSPHOR, width=1):
        pygame.draw.circle(surf, color, centre, radius, width)

    def rect(self, surf, rect, color=PHOSPHOR, width=0):
        pygame.draw.rect(surf, color, rect, width)

    def frame(self, surf, rect, title=None, color=DIM):
        pygame.draw.rect(surf, color, rect, 1)
        if title:
            label = self.font.render(f" {title} ", True, PHOSPHOR, (0, 0, 0))
            surf.blit(label, (rect[0] + 10, rect[1] - label.get_height() // 2))

    def text(self, surf, msg, pos, color=PHOSPHOR, big=False, small=False, huge=False, center=False):
        key = (msg, color, big, small, huge)
        label = self._text_cache.get(key)
        if label is None:
            if len(self._text_cache) > 800:
                self._text_cache.clear()
            font = self.huge if huge else self.big if big else self.small if small else self.font
            label = self._text_cache[key] = font.render(msg, True, color)
        surf.blit(label, label.get_rect(center=pos) if center else pos)

    # --- post-processing ---
    def apply_post_processing(self, screen):
        if self.ghosting:
            if self.prev is not None:
                screen.blit(self.prev, (0, 0), special_flags=pygame.BLEND_RGB_MAX)
            self.prev = screen.copy()  # ghost the picture, not the tint, or the tint piles up to tint/(1-decay)
            d = self.ghost_decay
            self.prev.fill((d, d, d), special_flags=pygame.BLEND_RGB_MULT)
        screen.fill((10, 30, 15, 15), special_flags=pygame.BLEND_ADD)
        screen.blit(self.scanlines, (0, 0))
        screen.blit(self.vignette, (0, 0))
