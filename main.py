#!/usr/bin/env python3
"""
Minimal Bubble Snake
--------------------
A tiny, clean Snake game for desktop (testing) and Android (Pygame).

Controls
  Touch : swipe anywhere to steer, tap buttons
  Keys  : arrows / WASD steer, P or Space pause, R restart, Esc back/pause
"""

import json
import os
import random
import sys

import pygame

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
BG = (0, 0, 0)
DOT = (40, 40, 40)
BORDER = (30, 30, 30)
TEXT = (232, 232, 232)
MUTED = (125, 125, 125)
LINE = (85, 85, 85)

PALETTE = [
    ("Blue", (30, 144, 255)),
    ("Sky", (110, 195, 255)),
    ("Cyan", (0, 220, 230)),
    ("Green", (70, 220, 120)),
    ("Yellow", (250, 212, 60)),
    ("Orange", (255, 140, 45)),
    ("Red", (240, 75, 85)),
    ("Pink", (255, 115, 200)),
    ("Purple", (165, 105, 255)),
    ("White", (235, 235, 235)),
]
STYLES = ("solid", "outline")

TARGET_CELLS = 16      # cells across the short side of the play area
SPEED_START = 0.15     # seconds per grid step at score 0
SPEED_MIN = 0.08       # fastest allowed step
SPEED_STEP = 0.003     # speed-up per point
FADE_MIN_LEN = 10      # trail fades over at least this many bubbles
SUPERSAMPLE = 3        # sprite anti-aliasing factor

MENU, PLAYING, PAUSED, OVER, SETTINGS = "menu", "playing", "paused", "over", "settings"

UP, DOWN, LEFT, RIGHT = (0, -1), (0, 1), (-1, 0), (1, 0)

DEFAULTS = {
    "snake_color": 0,
    "snake_style": "solid",
    "food_color": 1,
    "food_style": "solid",
    "best": 0,
}


# --------------------------------------------------------------------------- #
# Saving / loading (settings + best score)
# --------------------------------------------------------------------------- #
def save_path():
    try:
        from android.storage import app_storage_path  # only exists on Android
        base = app_storage_path()
    except Exception:
        base = os.path.expanduser("~")
    return os.path.join(base, "bubble_snake_save.json")


def load_cfg():
    cfg = dict(DEFAULTS)
    try:
        with open(save_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in DEFAULTS:
            if key in data:
                cfg[key] = data[key]
    except Exception:
        pass
    for key in ("snake_color", "food_color"):
        v = cfg[key]
        if not (isinstance(v, int) and 0 <= v < len(PALETTE)):
            cfg[key] = DEFAULTS[key]
    for key in ("snake_style", "food_style"):
        if cfg[key] not in STYLES:
            cfg[key] = DEFAULTS[key]
    if not (isinstance(cfg["best"], int) and cfg["best"] >= 0):
        cfg["best"] = 0
    return cfg


# --------------------------------------------------------------------------- #
# Game logic (no drawing in here)
# --------------------------------------------------------------------------- #
class Game:
    def __init__(self, cols, rows):
        self.cols = cols
        self.rows = rows
        self.reset()

    def reset(self):
        cx, cy = self.cols // 2, self.rows // 2
        self.snake = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]   # head first
        self.prev = list(self.snake)    # positions before the last step (for smooth motion)
        self.dir = RIGHT
        self.queue = []                 # buffered turns
        self.score = 0
        self.acc = 0.0                  # time accumulated toward next step
        self.alive = True
        self.food = self.spawn_food()

    def step_time(self):
        return max(SPEED_MIN, SPEED_START - SPEED_STEP * self.score)

    def spawn_food(self):
        taken = set(self.snake)
        free = [(x, y) for x in range(self.cols) for y in range(self.rows)
                if (x, y) not in taken]
        return random.choice(free) if free else None

    def turn(self, d):
        last = self.queue[-1] if self.queue else self.dir
        if d == last or (d[0] == -last[0] and d[1] == -last[1]):
            return
        if len(self.queue) < 2:
            self.queue.append(d)

    def update(self, dt):
        if not self.alive:
            return
        self.acc += dt
        st = self.step_time()
        while self.acc >= st and self.alive:
            self.acc -= st
            self._step()

    def _step(self):
        if self.queue:
            self.dir = self.queue.pop(0)
        hx, hy = self.snake[0]
        nx, ny = hx + self.dir[0], hy + self.dir[1]
        ate = (nx, ny) == self.food
        body = self.snake if ate else self.snake[:-1]   # the tail moves out of the way
        if not (0 <= nx < self.cols and 0 <= ny < self.rows) or (nx, ny) in body:
            self.alive = False
            return
        self.prev = list(self.snake)
        self.snake.insert(0, (nx, ny))
        if ate:
            self.score += 1
            self.food = self.spawn_food()
            if self.food is None:       # board is full: you win
                self.alive = False
        else:
            self.snake.pop()


# --------------------------------------------------------------------------- #
# App: input, states and drawing
# --------------------------------------------------------------------------- #
class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Bubble Snake")
        if "ANDROID_ARGUMENT" in os.environ:
            pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            pygame.display.set_mode((480, 854), pygame.RESIZABLE)

        self.cfg = load_cfg()
        self.cache = {}
        self.hits = []              # (rect, callback) rebuilt every frame
        self.game = None
        self.state = MENU
        self.return_state = MENU
        self.press = None
        self.swiped = False
        self.running = True

        self.resize_events = tuple(
            getattr(pygame, n) for n in ("VIDEORESIZE", "WINDOWSIZECHANGED")
            if hasattr(pygame, n))
        self.background_events = tuple(
            getattr(pygame, n) for n in ("APP_WILLENTERBACKGROUND", "WINDOWFOCUSLOST")
            if hasattr(pygame, n))
        self.layout()

    # ------------------------------------------------------------------ layout
    def layout(self):
        self.screen = pygame.display.get_surface()
        w, h = self.screen.get_size()
        self.w, self.h = w, h
        self.hud_h = max(44, int(min(w, h) * 0.11))
        avail_h = h - self.hud_h
        self.cell = cell = max(14, min(w, avail_h) // TARGET_CELLS)
        cols = max(8, w // cell)
        rows = max(8, avail_h // cell)
        self.ox = (w - cols * cell) // 2
        self.oy = self.hud_h + (avail_h - rows * cell) // 2
        self.swipe_min = max(18, int(cell * 0.6))

        self.font_big = pygame.font.Font(None, int(cell * 1.7))
        self.font = pygame.font.Font(None, int(cell * 1.0))
        self.font_small = pygame.font.Font(None, int(cell * 0.75))
        self.cache.clear()

        self.shade = pygame.Surface((w, h), pygame.SRCALPHA)
        self.shade.fill((0, 0, 0, 175))

        # static background: black + faint dot grid + very faint border
        self.bg = pygame.Surface((w, h))
        self.bg.fill(BG)
        dot_r = max(1, cell // 22)
        for gx in range(cols):
            for gy in range(rows):
                c = (self.ox + gx * cell + cell // 2, self.oy + gy * cell + cell // 2)
                pygame.draw.circle(self.bg, DOT, c, dot_r)
        pygame.draw.rect(self.bg, BORDER,
                         (self.ox - 1, self.oy - 1, cols * cell + 2, rows * cell + 2), 1)

        if self.game is None or (cols, rows) != (self.game.cols, self.game.rows):
            self.game = Game(cols, rows)
            if self.state == SETTINGS:
                self.return_state = MENU
            else:
                self.state = MENU

    # ------------------------------------------------------------ state changes
    def start_game(self):
        self.game.reset()
        self.state = PLAYING

    def pause(self):
        if self.state == PLAYING:
            self.state = PAUSED

    def resume(self):
        if self.state == PAUSED:
            self.state = PLAYING

    def open_settings(self):
        self.return_state = PAUSED if self.state == PLAYING else self.state
        self.state = SETTINGS

    def close_settings(self):
        self.state = self.return_state

    def end_game(self):
        if self.game.score > self.cfg["best"]:
            self.cfg["best"] = self.game.score
            self.save()
        self.state = OVER

    def set_cfg(self, key, value):
        self.cfg[key] = value
        self.save()

    def save(self):
        try:
            with open(save_path(), "w", encoding="utf-8") as f:
                json.dump(self.cfg, f)
        except Exception:
            pass

    # -------------------------------------------------------------------- input
    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type in self.resize_events:
            self.layout()
        elif e.type in self.background_events:
            self.pause()
        elif e.type == pygame.KEYDOWN:
            self.on_key(e.key)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.press = e.pos
            self.swiped = False
        elif e.type == pygame.MOUSEMOTION and self.press is not None:
            if self.state == PLAYING:
                dx = e.pos[0] - self.press[0]
                dy = e.pos[1] - self.press[1]
                if max(abs(dx), abs(dy)) >= self.swipe_min:
                    if abs(dx) > abs(dy):
                        self.game.turn(RIGHT if dx > 0 else LEFT)
                    else:
                        self.game.turn(DOWN if dy > 0 else UP)
                    self.swiped = True
                    self.press = e.pos      # allows chained swipes without lifting
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.press is not None and not self.swiped:
                self.tap(e.pos)
            self.press = None

    def tap(self, pos):
        for rect, callback in reversed(self.hits):
            if rect.collidepoint(pos):
                callback()
                return

    def on_key(self, key):
        dirs = {pygame.K_UP: UP, pygame.K_w: UP, pygame.K_DOWN: DOWN, pygame.K_s: DOWN,
                pygame.K_LEFT: LEFT, pygame.K_a: LEFT, pygame.K_RIGHT: RIGHT, pygame.K_d: RIGHT}
        back = getattr(pygame, "K_AC_BACK", None)     # Android back button
        if key in dirs:
            if self.state == PLAYING:
                self.game.turn(dirs[key])
        elif key in (pygame.K_SPACE, pygame.K_p, pygame.K_RETURN):
            if self.state in (MENU, OVER):
                self.start_game()
            elif self.state == PLAYING:
                self.pause()
            elif self.state == PAUSED:
                self.resume()
        elif key == pygame.K_r:
            if self.state in (PLAYING, PAUSED, OVER):
                self.start_game()
        elif key == pygame.K_ESCAPE or (back is not None and key == back):
            if self.state == PLAYING:
                self.pause()
            elif self.state == PAUSED:
                self.resume()
            elif self.state == SETTINGS:
                self.close_settings()
            elif self.state == OVER:
                self.state = MENU
            else:
                self.running = False

    # ------------------------------------------------------------------ sprites
    def sprite(self, style, color, diameter, alpha):
        key = (style, color, diameter, alpha)
        spr = self.cache.get(key)
        if spr is None:
            big_d = diameter * SUPERSAMPLE
            big = pygame.Surface((big_d, big_d), pygame.SRCALPHA)
            width = 0 if style == "solid" else max(2, diameter // 9) * SUPERSAMPLE
            pygame.draw.circle(big, (*color, alpha), (big_d // 2, big_d // 2), big_d // 2, width)
            spr = pygame.transform.smoothscale(big, (diameter, diameter))
            self.cache[key] = spr
        return spr

    def blit_center(self, spr, x, y):
        self.screen.blit(spr, (round(x - spr.get_width() / 2), round(y - spr.get_height() / 2)))

    # ------------------------------------------------------------------ drawing
    def text(self, s, font, color, center):
        img = font.render(s, True, color)
        self.screen.blit(img, img.get_rect(center=center))

    def button(self, label, center, w, h, callback, primary=False):
        rect = pygame.Rect(0, 0, w, h)
        rect.center = center
        pygame.draw.rect(self.screen, TEXT if primary else LINE, rect, 2, border_radius=h // 2)
        self.text(label, self.font, TEXT, rect.center)
        self.hits.append((rect, callback))

    def button_column(self, items, y0):
        bw = int(min(self.w * 0.7, self.cell * 10))
        bh = int(self.cell * 1.9)
        for i, (label, callback) in enumerate(items):
            self.button(label, (self.w // 2, int(y0 + i * bh * 1.3)), bw, bh, callback, i == 0)

    def icon_button(self, rect, kind, callback):
        pygame.draw.rect(self.screen, LINE, rect, 2, border_radius=rect.w // 3)
        cx, cy = rect.center
        u = rect.w / 5
        if kind == "pause":
            for dx in (-0.8 * u, 0.8 * u):
                bar = pygame.Rect(0, 0, max(2, int(u * 0.9)), int(u * 2.6))
                bar.center = (round(cx + dx), cy)
                pygame.draw.rect(self.screen, TEXT, bar)
        else:
            for dy in (-u, 0, u):
                pygame.draw.line(self.screen, TEXT, (cx - 1.5 * u, cy + dy),
                                 (cx + 1.5 * u, cy + dy), max(2, int(u * 0.5)))
        self.hits.append((rect.inflate(int(rect.w * 0.4), int(rect.h * 0.4)), callback))

    def draw_hud(self, interactive):
        img = self.font_big.render(str(self.game.score), True, TEXT)
        self.screen.blit(img, img.get_rect(midleft=(int(self.cell * 0.7), self.hud_h // 2)))
        if interactive:
            size = int(self.hud_h * 0.6)
            margin = int(self.cell * 0.5)
            cy = self.hud_h // 2
            pause = pygame.Rect(0, 0, size, size)
            pause.center = (self.w - margin - size // 2, cy)
            menu = pygame.Rect(0, 0, size, size)
            menu.center = (self.w - margin * 2 - size - size // 2, cy)
            self.icon_button(pause, "pause", self.pause)
            self.icon_button(menu, "menu", self.open_settings)

    def draw_game(self):
        g, cell = self.game, self.cell
        t = 1.0 if not g.alive else min(1.0, g.acc / g.step_time())

        # interpolated pixel centres, head first
        pts = []
        for i, (bx, by) in enumerate(g.snake):
            ax, ay = g.prev[min(i, len(g.prev) - 1)]
            gx = ax + (bx - ax) * t
            gy = ay + (by - ay) * t
            pts.append((self.ox + (gx + 0.5) * cell, self.oy + (gy + 0.5) * cell))

        # food
        if g.food:
            fd = int(cell * 0.76)
            spr = self.sprite(self.cfg["food_style"], PALETTE[self.cfg["food_color"]][1], fd, 255)
            self.blit_center(spr, self.ox + (g.food[0] + 0.5) * cell,
                             self.oy + (g.food[1] + 0.5) * cell)

        # snake body: tail -> head so the head sits on top; alpha fades toward the tail
        style = self.cfg["snake_style"]
        color = PALETTE[self.cfg["snake_color"]][1]
        n = len(pts)
        span = max(n - 1, FADE_MIN_LEN)
        for i in range(n - 1, -1, -1):
            if i == 0:
                alpha = 255
            else:
                alpha = int(255 - 215 * min(1.0, i / span))
                alpha = max(32, (alpha >> 4) << 4)      # bucket alphas so sprites get cached
            self.blit_center(self.sprite(style, color, cell, alpha), *pts[i])

        # eyes
        dx, dy = g.dir
        px, py = -dy, dx
        hx, hy = pts[0]
        fwd, side = cell * 0.14, cell * 0.22
        eye_r = max(3, round(cell * 0.19))
        pupil_r = max(2, round(eye_r * 0.5))
        for s in (-1, 1):
            ex = hx + dx * fwd + px * side * s
            ey = hy + dy * fwd + py * side * s
            pygame.draw.circle(self.screen, (250, 250, 250), (round(ex), round(ey)), eye_r)
            pygame.draw.circle(self.screen, (10, 10, 10),
                               (round(ex + dx * eye_r * 0.35), round(ey + dy * eye_r * 0.35)),
                               pupil_r)

    # --- settings screen
    def draw_swatches(self, key, cx, y, pw, slot):
        x0 = cx - pw / 2 + slot / 2
        r = int(slot * 0.34)
        for i, (_, col) in enumerate(PALETTE):
            c = (int(x0 + i * slot), int(y))
            pygame.draw.circle(self.screen, col, c, r)
            if self.cfg[key] == i:
                pygame.draw.circle(self.screen, TEXT, c, r + max(3, int(r * 0.3)), 2)
            hit = pygame.Rect(0, 0, int(slot), int(slot))
            hit.center = c
            self.hits.append((hit, lambda i=i: self.set_cfg(key, i)))

    def draw_style_buttons(self, key, color_key, cx, y, pw, rh):
        bw, bh = int(pw * 0.46), int(rh * 0.95)
        color = PALETTE[self.cfg[color_key]][1]
        for k, style in enumerate(STYLES):
            rect = pygame.Rect(0, 0, bw, bh)
            rect.center = (int(cx + (k - 0.5) * pw * 0.5), int(y))
            selected = self.cfg[key] == style
            pygame.draw.rect(self.screen, TEXT if selected else LINE, rect,
                             3 if selected else 2, border_radius=bh // 2)
            pr = int(bh * 0.22)
            pc = (rect.left + int(bh * 0.55), rect.centery)
            pygame.draw.circle(self.screen, color, pc, pr, 0 if style == "solid" else 3)
            self.text(style.capitalize(), self.font_small, TEXT if selected else MUTED,
                      (rect.centerx + int(bh * 0.2), rect.centery))
            self.hits.append((rect, lambda s=style: self.set_cfg(key, s)))

    def draw_settings(self):
        self.screen.fill(BG)
        w, h = self.w, self.h
        pw = min(w * 0.92, h * 0.9)
        slot = pw / len(PALETTE)
        rh = min(h / 12.5, slot * 1.6)
        cx = w // 2
        y0 = max(h * 0.02, (h - 11.1 * rh) / 2)
        y = y0 + rh * 0.5
        self.text("SETTINGS", self.font, TEXT, (cx, int(y)))
        y += rh * 1.3
        sections = [("Snake colour", "snake_color", None), ("Snake style", "snake_style", "snake_color"),
                    ("Food colour", "food_color", None), ("Food style", "food_style", "food_color")]
        for label, key, color_key in sections:
            self.text(label, self.font_small, MUTED, (cx, int(y)))
            y += rh * 0.85
            if color_key is None:
                self.draw_swatches(key, cx, y, pw, slot)
            else:
                self.draw_style_buttons(key, color_key, cx, y, pw, rh)
            y += rh * 1.25
        self.button("Back", (cx, int(y + rh * 0.3)), int(min(pw * 0.6, self.cell * 8)),
                    int(rh * 1.1), self.close_settings, True)

    # --- main draw
    def draw(self):
        self.hits = []
        if self.state == SETTINGS:
            self.draw_settings()
            return
        scr, w, h, cell = self.screen, self.w, self.h, self.cell
        scr.blit(self.bg, (0, 0))
        if self.state != MENU:          # menu shows only the dotted board
            self.draw_game()
            self.draw_hud(self.state == PLAYING)
        if self.state == PLAYING:
            return
        scr.blit(self.shade, (0, 0))
        cx = w // 2
        if self.state == MENU:
            self.text("BUBBLE SNAKE", self.font_big, TEXT, (cx, int(h * 0.26)))
            self.text("swipe to steer", self.font_small, MUTED, (cx, int(h * 0.26 + cell * 1.6)))
            self.button_column([("Play", self.start_game), ("Settings", self.open_settings)], h * 0.5)
        elif self.state == PAUSED:
            self.text("PAUSED", self.font_big, TEXT, (cx, int(h * 0.28)))
            self.button_column([("Resume", self.resume), ("Restart", self.start_game),
                                ("Settings", self.open_settings)], h * 0.45)
        elif self.state == OVER:
            self.text("GAME OVER", self.font_big, TEXT, (cx, int(h * 0.22)))
            self.text("Score  %d" % self.game.score, self.font, TEXT, (cx, int(h * 0.22 + cell * 2)))
            self.text("Best  %d" % self.cfg["best"], self.font_small, MUTED,
                      (cx, int(h * 0.22 + cell * 3.3)))
            self.button_column([("Play again", self.start_game), ("Settings", self.open_settings)], h * 0.52)

    # ---------------------------------------------------------------- main loop
    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            dt = min(clock.tick(60) / 1000.0, 0.05)
            for e in pygame.event.get():
                self.handle_event(e)
            if self.state == PLAYING:
                self.game.update(dt)
                if not self.game.alive:
                    self.end_game()
            self.draw()
            pygame.display.flip()
        self.save()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    App().run()
