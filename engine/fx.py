"""Effekte: Partikel, Lichtstrahlen, Tempolinien, Schockwelle, Blitz, Übergänge. Alles deterministisch aus seed und t."""
from __future__ import annotations
import math
import numpy as np
import skia
from . import anim as A
from .color import with_alpha, mix

_CACHE: dict = {}


def _rand(seed: int, n: int, cols: int = 8) -> np.ndarray:
    key = (seed, n, cols)
    if key not in _CACHE:
        _CACHE[key] = np.random.RandomState(seed + 7919).rand(n, cols)
    return _CACHE[key]


def particles(c, fmt, t, kind='dust', theme=None, seed=0, n=40, alpha=0.6, area=None, color=None, size=1.0, speed=1.0):
    """Partikelfeld. kind: dust, confetti, sparks, bubbles, snow, embers, stars, rain. area = (x, y, w, h), Standard ganzes Bild."""
    th = theme or {}
    x0, y0, w, h = area if area else (-100, -100, fmt.W + 200, fmt.H + 200)
    R = _rand(seed + hash(kind) % 1000, n)
    accent, accent2, glow, ink = th.get('accent', '#FFC14A'), th.get('accent2', '#5FF2C2'), th.get('glow', '#FFD98A'), th.get('ink', '#FFFFFF')
    for i in range(n):
        r = R[i]
        if kind == 'dust':
            px = x0 + ((r[0] * w + 12 * speed * t * (0.3 + r[2])) % w)
            py = y0 + ((r[1] * h - 7 * speed * t * (0.4 + r[3])) % h)
            rad = (1.5 + 3.5 * r[4]) * size
            a = alpha * (0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * (0.6 + r[5]) + r[6] * 6.28)))
            c.circle(px + 6 * math.sin(t * 0.7 + r[7] * 6.28), py, rad, color or ink, a, blur=rad * 0.6)
        elif kind == 'stars':
            px, py = x0 + r[0] * w, y0 + r[1] * h
            tw = 0.5 + 0.5 * math.sin(t * (1.0 + 2.0 * r[2]) + r[3] * 6.28)
            rad = (0.8 + 2.2 * r[4]) * size
            c.circle(px, py, rad, color or ink, alpha * (0.3 + 0.7 * tw))
            if r[5] > 0.85:
                c.circle(px, py, rad * 3, glow, alpha * 0.25 * tw, blur=rad * 2)
        elif kind == 'confetti':
            fall = (r[1] * h + speed * t * (220 + 180 * r[2])) % h
            px = x0 + r[0] * w + 40 * math.sin(t * (1.2 + r[3]) + r[4] * 6.28)
            py = y0 + fall
            col = [accent, accent2, glow, ink][i % 4]
            rot = (t * (180 + 240 * r[5]) + r[6] * 360) % 360
            sz = (10 + 10 * r[7]) * size
            c.rect_c(px, py, sz, sz * 0.6, color or col, r=2, alpha=alpha, rot=rot)
        elif kind == 'snow':
            fall = (r[1] * h + speed * t * (60 + 60 * r[2])) % h
            px = x0 + r[0] * w + 25 * math.sin(t * (0.5 + r[3]) + r[4] * 6.28)
            rad = (2 + 4 * r[5]) * size
            c.circle(px, y0 + fall, rad, color or ink, alpha * (0.5 + 0.5 * r[6]), blur=rad * 0.5)
        elif kind == 'bubbles':
            rise = (r[1] * h - speed * t * (50 + 90 * r[2])) % h
            px = x0 + r[0] * w + 18 * math.sin(t * (0.8 + r[3]) + r[4] * 6.28)
            rad = (4 + 14 * r[5]) * size
            c.circle(px, y0 + rise, rad, color or accent2, alpha * 0.6, stroke=max(1.5, rad * 0.18))
            c.circle(px - rad * 0.35, y0 + rise - rad * 0.35, rad * 0.22, ink, alpha * 0.7)
        elif kind == 'embers':
            rise = (r[1] * h - speed * t * (40 + 70 * r[2])) % h
            px = x0 + r[0] * w + 30 * math.sin(t * (0.9 + r[3]) + r[4] * 6.28)
            fl = 0.5 + 0.5 * math.sin(t * (6 + 8 * r[5]) + r[6] * 6.28)
            rad = (1.5 + 3 * r[7]) * size
            col = color or mix(accent, th.get('danger', '#FF5B3A'), r[5])
            c.circle(px, y0 + rise, rad, col, alpha * (0.4 + 0.6 * fl))
            c.circle(px, y0 + rise, rad * 3, col, alpha * 0.25 * fl, blur=rad * 2)
        elif kind == 'sparks':
            life = (t * (1.2 + r[2]) * speed + r[3]) % 1.0
            px = x0 + r[0] * w + (r[4] - 0.5) * 120 * life
            py = y0 + r[1] * h - 160 * life * (0.5 + r[5])
            rad = (1 + 2.5 * r[6]) * size * (1 - life)
            c.line(px, py, px - (r[4] - 0.5) * 14, py + 14, color or glow, rad * 1.2, alpha * (1 - life))
        elif kind == 'rain':
            fall = (r[1] * h + speed * t * (900 + 500 * r[2])) % h
            px = x0 + r[0] * w
            ln = (30 + 40 * r[3]) * size
            c.line(px, y0 + fall, px - 4, y0 + fall + ln, color or ink, 1.5, alpha * (0.3 + 0.4 * r[4]))


def light_rays(c, x, y, t, theme=None, n=7, length=900, alpha=0.18, spread=18.0, speed=4.0, color=None):
    """Weiche, langsam drehende Lichtstrahlen (additiv) um einen Punkt."""
    th = theme or {}
    col = color or th.get('glow', '#FFD98A')
    for i in range(n):
        a = (i * 360.0 / n + t * speed + 12 * math.sin(t * 0.3 + i)) % 360
        w = spread * (0.6 + 0.4 * math.sin(t * 0.7 + i * 1.3))
        with c.tf(rot=a, px=x, py=y):
            c.poly([(x, y), (x + length, y - length * math.tan(math.radians(w / 2))), (x + length, y + length * math.tan(math.radians(w / 2)))],
                   shader=c.linear(x, y, x + length, y, [(0.0, with_alpha(col, 1.0)), (1.0, with_alpha(col, 0.0))]), alpha=alpha, blend='add')


def speed_lines(c, fmt, t, k=1.0, theme=None, n=28, seed=1, color=None, inner=0.35):
    """Radiale Tempolinien vom Bildzentrum nach außen, Stärke k 0..1."""
    if k <= 0:
        return
    th = theme or {}
    R = _rand(seed + 31, n)
    col = color or th.get('ink', '#FFFFFF')
    cx, cy = fmt.cx, fmt.cy
    rmax = math.hypot(fmt.W, fmt.H) * 0.55
    for i in range(n):
        r = R[i]
        a = r[0] * 360 + 20 * math.sin(t * 3 + i)
        r0 = rmax * (inner + 0.25 * r[1]) + 40 * math.sin(t * 9 + r[2] * 6)
        r1 = r0 + rmax * (0.15 + 0.35 * r[3]) * k
        x0, y0 = cx + r0 * math.cos(math.radians(a)), cy + r0 * math.sin(math.radians(a))
        x1, y1 = cx + r1 * math.cos(math.radians(a)), cy + r1 * math.sin(math.radians(a))
        c.line(x0, y0, x1, y1, col, (1.5 + 3 * r[4]) * k, 0.35 * k * (0.5 + 0.5 * r[5]), cap='round')


def shockwave(c, x, y, t, t0, theme=None, r_max=600, dur=0.7, width=14, color=None, alpha=0.8):
    """Expandierender Ring ab t0, verblasst."""
    if t < t0 or t > t0 + dur:
        return
    u = A.out_cubic((t - t0) / dur)
    th = theme or {}
    col = color or th.get('accent', '#FFC14A')
    c.ring(x, y, 20 + (r_max - 20) * u, width * (1 - u * 0.7) + 1, col, alpha * (1 - u))
    c.ring(x, y, 20 + (r_max - 20) * u, width * 3, col, alpha * 0.35 * (1 - u), blur=width * 2, blend='add')


def flash(c, fmt, t, t0, color='#FFFFFF', dur=0.25, peak=0.85):
    """Kurzer Blitz über das ganze Bild ab t0."""
    if t < t0 or t > t0 + dur:
        return
    u = (t - t0) / dur
    a = peak * (1 - u) ** 2
    c.fill(color, a)


def confetti_burst(c, x, y, t, t0, theme=None, n=60, seed=5, dur=2.2, alpha=1.0, power=900):
    """Konfetti-Explosion aus einem Punkt mit Schwerkraft."""
    if t < t0 or t > t0 + dur:
        return
    th = theme or {}
    cols = [th.get('accent', '#FFC14A'), th.get('accent2', '#5FF2C2'), th.get('glow', '#FFD98A'), th.get('ink', '#FFFFFF'), th.get('danger', '#FF5B3A')]
    R = _rand(seed + 77, n)
    u = t - t0
    fade = 1 - A.in_quad(max(0.0, (u - dur * 0.6) / (dur * 0.4)))
    for i in range(n):
        r = R[i]
        ang = math.radians(-90 + (r[0] - 0.5) * 140)
        v = power * (0.4 + 0.6 * r[1])
        px = x + math.cos(ang) * v * u * (1 - 0.3 * u)
        py = y + math.sin(ang) * v * u + 0.5 * 1800 * u * u
        rot = (r[2] * 360 + u * (300 + 400 * r[3])) % 360
        sz = 10 + 12 * r[4]
        c.rect_c(px, py, sz, sz * 0.55, cols[i % len(cols)], r=2, alpha=alpha * fade, rot=rot)


def floor_shadow(c, x, y, w, alpha=0.3, color='#000000'):
    """Weicher Bodenschatten unter einer Figur oder einem Objekt."""
    c.ellipse(x, y, w * 0.5, w * 0.11, color, alpha, blur=w * 0.08)


# ---------------- Übergänge ----------------

def transition(c, fmt, kind, k, theme, draw_old, draw_new):
    """Zeichnet alte und neue Szene nach Übergangsart; k 0..1 (0 = nur alt, 1 = nur neu).
    draw_old/draw_new: Callbacks, die auf c zeichnen (dürfen None sein)."""
    th = theme or {}
    W, H = fmt.W, fmt.H
    if k <= 0.0:
        if draw_old: draw_old(c)
        return
    if k >= 1.0 or kind == 'cut':
        if draw_new: draw_new(c)
        return
    if kind == 'fade':
        if draw_old: draw_old(c)
        with c.layer(alpha=A.in_out_sine(k)):
            if draw_new: draw_new(c)
    elif kind == 'wipe':
        # Diagonaler Wischer mit leuchtender Kante
        e = A.in_out_cubic(k)
        if draw_old: draw_old(c)
        off = -0.25 * W + e * (1.5 * W)
        pts = [(off - 0.35 * W, -200), (off + 0.35 * W, -200), (off - 0.35 * W + 0.0, H + 200), (off - 1.05 * W, H + 200)]
        # Neue Szene links der Kante
        with c.clip_poly([(-W, -200), (pts[1][0], -200), (pts[2][0], H + 200), (-W, H + 200)]):
            if draw_new: draw_new(c)
        band = 26 + 50 * (1 - abs(2 * e - 1))
        c.polyline([(pts[1][0], -200), (pts[2][0], H + 200)], th.get('accent', '#FFC14A'), band, 0.9)
        c.polyline([(pts[1][0], -200), (pts[2][0], H + 200)], th.get('glow', '#FFD98A'), band * 2.2, 0.5, blur=band)
    elif kind == 'slide':
        e = A.in_out_cubic(k)
        with c.tf(y=-e * H):
            if draw_old: draw_old(c)
        with c.tf(y=(1 - e) * H):
            if draw_new: draw_new(c)
    elif kind == 'slide_x':
        e = A.in_out_cubic(k)
        with c.tf(x=-e * W):
            if draw_old: draw_old(c)
        with c.tf(x=(1 - e) * W):
            if draw_new: draw_new(c)
    elif kind == 'iris':
        e = A.in_out_cubic(k)
        if draw_old: draw_old(c)
        r = e * math.hypot(W, H) * 0.6
        with c.clip_circle(fmt.cx, fmt.cy, r):
            if draw_new: draw_new(c)
        c.ring(fmt.cx, fmt.cy, r, 18, th.get('accent', '#FFC14A'), 0.9 * (1 - e))
    elif kind == 'zoom':
        e = A.in_out_cubic(k)
        with c.layer(alpha=1 - e):
            with c.tf(sx=1 + 0.35 * e, px=fmt.cx, py=fmt.cy):
                if draw_old: draw_old(c)
        with c.layer(alpha=e):
            with c.tf(sx=0.82 + 0.18 * e, px=fmt.cx, py=fmt.cy):
                if draw_new: draw_new(c)
    elif kind == 'flip':
        if k < 0.5:
            e = A.in_cubic(k * 2)
            with c.tf(sx=max(0.001, 1 - e), px=fmt.cx, py=fmt.cy):
                if draw_old: draw_old(c)
        else:
            e = A.out_cubic((k - 0.5) * 2)
            with c.tf(sx=max(0.001, e), px=fmt.cx, py=fmt.cy):
                if draw_new: draw_new(c)
    elif kind == 'peel':
        # Sticker-Peel (STIL.md 1.6): die alte Seite löst sich an der unteren Kante, kippt und fliegt nach oben weg;
        # darunter liegt die neue Seite. Schattenband an der Ablösekante.
        e = A.in_cubic(k) if k < 0.5 else 0.125 + A.out_cubic((k - 0.5) * 2) * 0.875
        if draw_new: draw_new(c)
        with c.layer(alpha=1.0):
            with c.tf(y=-e * (H + 400), rot=-9 * e, px=W * 0.15, py=H * 0.95, kx=0.0):
                if draw_old: draw_old(c)
                c.rect(-200, H - 60, W + 400, 300, shader=c.linear(0, H - 60, 0, H + 120, [(0.0, (0, 0, 0, 0.0)), (1.0, (0, 0, 0, 0.45 * (1 - e)))]))
        c.rect(-200, H - e * (H + 400) - 10, W + 400, 70, shader=c.linear(0, H - e * (H + 400) - 10, 0, H - e * (H + 400) + 60, [(0.0, (0, 0, 0, 0.35)), (1.0, (0, 0, 0, 0.0))]), alpha=1 - e)
    elif kind == 'deck':
        # Kartendeck: alte Seite rutscht nach links hinten (kleiner, dunkler), neue kommt von rechts
        e = A.in_out_cubic(k)
        with c.layer(alpha=1 - 0.6 * e):
            with c.tf(x=-e * W * 0.35, sx=1 - 0.12 * e, px=fmt.cx, py=fmt.cy):
                if draw_old: draw_old(c)
        with c.tf(x=(1 - e) * W * 1.05, rot=(1 - e) * 6, px=fmt.cx, py=H):
            if draw_new: draw_new(c)
    elif kind == 'blinds':
        e = A.in_out_cubic(k)
        if draw_old: draw_old(c)
        n = 7
        bh = H / n
        path = skia.Path()
        for i in range(n):
            path.addRect(skia.Rect.MakeXYWH(-200, i * bh, W + 400, bh * e + 1))
        with c.clip_path(path):
            if draw_new: draw_new(c)
    else:
        if draw_old: draw_old(c)
        with c.layer(alpha=A.in_out_sine(k)):
            if draw_new: draw_new(c)


TRANSITIONS = ['cut', 'fade', 'wipe', 'slide', 'slide_x', 'iris', 'zoom', 'flip', 'blinds', 'peel', 'deck']
