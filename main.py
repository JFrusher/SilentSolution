"""Silent Solution: game loop and screen states (title, play, pause, game over)."""
import pygame

from audio import AudioSynthesizer
from console import Console
from layout import H, W
from tutorial import TRAINING, Tutorial
from workstation import Workstation
from tuning import DIFFICULTY

FPS = 60

def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("SILENT SOLUTION")
    clock = pygame.time.Clock()
    audio = AudioSynthesizer()
    station = Workstation()
    console, state, paused, show_help = None, "TITLE", False, False

    while True:
        dt = min(clock.tick(FPS) / 1000.0, 0.1)
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                pygame.quit()
                return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_F1:
                show_help = not show_help
            elif state == "TITLE":
                choice = None
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    choice = list(DIFFICULTY)[e.key - pygame.K_1]
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_t:
                    choice = "TRAINING"
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    choice = next((name for rect, name in station.title_buttons if rect.collidepoint(e.pos)), None)
                if choice == "TRAINING":
                    console, state = Console(choice, audio, TRAINING), "PLAY"
                    Tutorial(console)
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
            elif console.dead and state == "PLAY":
                state = "OVER"
        station.draw(screen, console, state, paused, show_help, dt)
        pygame.display.flip()


if __name__ == "__main__":
    main()
