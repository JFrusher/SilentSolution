"""Silent Solution: game loop and screen states (title, settings, career, play, pause, debrief, game over)."""
import datetime
import traceback
from pathlib import Path

import pygame

import campaign
from audio import AudioSynthesizer
from console import Console
from layout import CRT_RECT, H, W
from tutorial import CHAPTERS, TRAINING, Tutorial
from version import __version__
from workstation import Workstation
import settings
from tuning import DIFFICULTY

FPS = 60
CRASH_LOG = Path.home() / ".silent_solution" / "crash.log"

def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption(f"SILENT SOLUTION {__version__}")
    clock = pygame.time.Clock()
    audio = AudioSynthesizer()
    settings.load()
    station = Workstation()
    station.career = career = campaign.Career()
    console, state, paused, show_help = None, "TITLE", False, False
    run = None  # the campaign patrol at sea, if any

    while True:
        dt = min(clock.tick(FPS) / 1000.0, 0.1)
        for e in pygame.event.get():
            pages = ("SETTINGS", "CAREER", "DEBRIEF", "CHAPTERS")  # Esc means "back" on these
            quit_key = e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE and state not in pages
            if e.type == pygame.QUIT or quit_key:
                pygame.quit()
                return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_F1:
                show_help = not show_help
            elif state == "SETTINGS":
                back = None
                if e.type == pygame.KEYDOWN:
                    back = station.menu.key(e.key)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    back = station.menu.click(e.pos[0] - CRT_RECT.x, e.pos[1] - CRT_RECT.y)
                elif e.type == pygame.MOUSEWHEEL:
                    station.menu.scroll(e.y)
                if back:
                    state = "TITLE"
            elif state == "CHAPTERS":
                choice = None
                if e.type == pygame.KEYDOWN:
                    choice = "BACK" if e.key == pygame.K_ESCAPE else e.key - pygame.K_1
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    choice = next((name for rect, name in station.buttons if rect.collidepoint(e.pos)), None)
                if choice == "BACK":
                    state = "TITLE"
                elif isinstance(choice, int) and 0 <= choice < len(CHAPTERS):
                    console, state = Console("TRAINING", audio, TRAINING), "PLAY"
                    Tutorial(console, choice)
            elif state in ("CAREER", "DEBRIEF"):
                choice = None
                if e.type == pygame.KEYDOWN:
                    offer = station.debrief["offer"] if state == "DEBRIEF" else []
                    picks = {pygame.K_1: 0, pygame.K_2: 1}
                    choice = (offer[picks[e.key]] if e.key in picks and picks[e.key] < len(offer) else
                              {pygame.K_RETURN: "SAIL" if state == "CAREER" else "CONTINUE", pygame.K_n: "NEW CAREER",
                               pygame.K_ESCAPE: "BACK"}.get(e.key))
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    choice = next((name for rect, name in station.buttons if rect.collidepoint(e.pos)), None)
                if state == "DEBRIEF":
                    if choice in campaign.UPGRADES:
                        career.fit(choice)
                        state = "CAREER"
                    elif choice == "CONTINUE" and not station.debrief["offer"]:
                        state = "CAREER"
                elif choice == "NEW CAREER" and not career.note:
                    career.note = "PRESS N AGAIN TO RESIGN AND START A NEW CAREER (HIGH SCORES ARE KEPT)"
                elif choice:
                    if choice == "NEW CAREER":
                        career.new()
                    elif choice == "BACK":
                        state = "TITLE"
                    elif choice == "SAIL" and not career.finished:
                        (console, run), state = campaign.sail(career, audio), "PLAY"
                    career.note = ""
            elif state == "TITLE":
                choice = None
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    choice = list(DIFFICULTY)[e.key - pygame.K_1]
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_t:
                    choice = "TRAINING"
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_s:
                    choice = "SETTINGS"
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_c:
                    choice = "CAMPAIGN"
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    choice = next((name for rect, name in station.buttons if rect.collidepoint(e.pos)), None)
                if choice == "CAMPAIGN":
                    state = "CAREER"
                elif choice == "SETTINGS":
                    station.menu, state = settings.SettingsMenu(), "SETTINGS"
                elif choice == "TRAINING":
                    state = "CHAPTERS"
                elif choice:
                    console, state = Console(choice, audio), "PLAY"
            elif state == "OVER":
                if e.type == pygame.KEYDOWN and e.key == pygame.K_r:
                    console, state = None, "TITLE"
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_p:
                paused = not paused
            elif not paused:
                if e.type == pygame.KEYDOWN:
                    console.key(e.key)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    console.click(e.pos)
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    console.dragging = None
                elif e.type == pygame.MOUSEMOTION and console.dragging:
                    console.drag(e.pos)
                elif e.type == pygame.MOUSEWHEEL:
                    console.scroll(pygame.mouse.get_pos(), e.y)
        if console and not paused:
            console.update(dt, pygame.key.get_pressed())
            if console.tutorial:
                console.tutorial.update(dt)
                if console.tutorial.finished:
                    console, state = None, "TITLE"
            elif run:
                if run.update(console):
                    station.debrief = career.record(run, console)
                    console, run, state = None, None, "DEBRIEF"
            elif console.dead and state == "PLAY":
                state = "OVER"
                career.add_score(console.level, console.score, console.wave)
        station.draw(screen, console, state, paused, show_help, dt)
        pygame.display.flip()


if __name__ == "__main__":
    try:
        main()
    except Exception:  # the packaged build has no console: leave the trace where a player can send it
        CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with CRASH_LOG.open("a", encoding="utf-8") as f:
            f.write(f"--- {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  v{__version__}\n{traceback.format_exc()}\n")
        raise
