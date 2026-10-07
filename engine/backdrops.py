"""Kulissen („Peel & Pop“, STIL.md 1.3, 1.4 und 7): ganzflächige Hintergründe, die 200 px über jeden Bildrand hinausreichen.

Jede Kulisse ist eine Funktion fn(c, g, p, t, seed, kw): g = Geo (Maße, Überhang, Bodenlinie, Hero-/Odd-Anker), p = Pal
(Themenfarben), t = Zeit in Sekunden. Der Aufbau ist immer gleich: Verlauf bg0 (oben) -> bg1 (unten), darauf Silhouetten
ohne Sticker-Rand in drei bg2-Stufen (far = mix(bg2, bg1, 0.7), mid = mix(bg2, bg1, 0.4), near = bg2), Böden in einer
dunkleren Fläche (deep), Lampen nur als additives Licht (glow bzw. candle im Respekt-Modus, alpha <= 0.35), zuletzt Korn
0.045 über die ganze Kulissenebene. Alles ist ruhig genug für Schrift und Sticker darüber: kein Element hat mehr Kontrast
als bg2 auf bg1, die einzigen Farben außerhalb der bg-Stufen sind Licht, Wasser (water/foam) und ein kleiner Zweitakzent.
Bewegung ist eine reine Funktion von t (Licht wandert, Partikel über fx.particles, Wolken ziehen, Tropfen fallen),
nichts zappelt, nichts blinkt schneller als 1 Hz. Beide Formate: alle Maße hängen an Geo (Breite, Höhe, Bodenlinie,
Anker), so dass jede Komposition im Hochformat 1080 x 1920 und im Querformat 1920 x 1080 funktioniert.
Unbekannte Namen zeichnen 'plain' (Verlauf mit Korn), nie einen Fehler.
"""
from __future__ import annotations
import math
import os
import numpy as np
import skia
from . import anim as A
from . import fonts as F
from . import theme as TH
from . import color as CO
from . import fx
from .canvas import rounded_poly_path, smooth_path

OVER = 200.0            # Überhang über jeden Bildrand (Übergänge schieben/skalieren die Kulisse)
GRAIN = 0.045           # Korn der Kulissenebene (STIL.md 1.3)
TWO_PI = 2 * math.pi

BACKDROPS: dict = {}    # name -> fn(c, g, p, t, seed, kw)
ALIASES: dict = {}      # alias -> name
SHEET_THEME: dict = {}  # name -> Thema für den Bogen
DOC: dict = {}          # name -> Kurzbeschreibung


def backdrop(name, *aliases, theme='curious'):
    """Registriert eine Kulisse unter name (und Aliasnamen) mit dem Thema, in dem der Bogen sie zeigt."""
    def deco(fn):
        BACKDROPS[name] = fn
        SHEET_THEME[name] = theme
        DOC[name] = (fn.__doc__ or '').strip().split('\n')[0]
        for a in aliases:
            ALIASES[a] = name
        return fn
    return deco


# ---------------------------------------------------------------- Maße und Farben

class Geo:
    """Maße einer Kulisse: Bildgröße, Überhang, Bodenlinie und die Anker des Layouts (STIL.md 1.4), alles in Pixeln."""

    def __init__(self, fmt):
        W, H = float(fmt.W), float(fmt.H)
        self.fmt = fmt
        self.W, self.H = W, H
        self.portrait = bool(fmt.portrait)
        self.x0, self.y0, self.x1, self.y1 = -OVER, -OVER, W + OVER, H + OVER
        self.w, self.h = W + 2 * OVER, H + 2 * OVER
        self.cx, self.cy = W / 2, H / 2
        self.u = min(W, H) / 1080.0                       # Einheit (1.0 in beiden Standardformaten)
        self.area = (self.x0, self.y0, self.w, self.h)     # Partikelfläche
        st = fmt.stage
        if self.portrait:
            self.floor = st.y + 0.83 * st.h                  # 1178: Odd steht bei 1209
            self.hero = (st.x + 0.69 * st.w, st.y + 0.60 * st.h)
            self.odd = (st.x + 0.28 * st.w, st.y + 0.86 * st.h)
            self.sky = (0.64 * W, 0.22 * H)                  # Sonne/Mond: unter Album-Leiste, über Kopfzeile
        else:
            self.floor = st.y + 0.89 * st.h                  # 820: Odd steht bei 844
            self.hero = (st.x + 0.62 * st.w, st.y + 0.56 * st.h)
            self.odd = (st.x + 0.14 * st.w, st.y + 0.92 * st.h)
            self.sky = (0.66 * W, 0.22 * H)

    def fx(self, a):
        return self.x0 + a * self.w

    def fy(self, a):
        return self.y0 + a * self.h


class Pal:
    """Kurznamen der Themenfarben für Kulissen: drei bg2-Stufen, Bodenfläche, Licht (glow; candle im Respekt-Modus)."""

    def __init__(self, th):
        self.th = th
        g = th.get
        self.bg0, self.bg1, self.bg2 = g('bg0', '#1E1838'), g('bg1', '#2E2250'), g('bg2', '#41336C')
        self.far = CO.hexs(CO.mix(self.bg2, self.bg1, 0.7))
        self.mid = CO.hexs(CO.mix(self.bg2, self.bg1, 0.4))
        self.near = self.bg2
        self.deep = CO.hexs(CO.mix(self.bg1, self.bg0, 0.55))       # Böden, Schattenseiten (dunkler als bg1)
        self.levels = [self.far, self.mid, self.near]
        self.respect = bool(g('respect_mode'))
        self.light = g('glow') or g('candle', '#FFD8A0')
        self.lk = 0.6 if self.respect else 1.0                       # Kerzenmodus: Licht 60 %
        self.ink, self.soft, self.line = g('ink', '#F7F1E6'), g('ink_soft', '#C9C2D6'), g('line', '#FFFFFF')
        self.foam, self.water, self.chalk = g('foam', '#DDF3F5'), g('water', '#5FD3F2'), g('chalk', '#E9E4DA')
        self.accent2 = g('ink_soft', '#C9C2D6') if self.respect else g('accent2', '#5FD9B8')
        self.ok = g('ok', '#5FD9B8')
        self.candle = g('candle', '#FFD8A0')
        self.pane = CO.hexs(CO.mix(self.near, self.light, 0.22))    # Fensterscheibe mit Licht dahinter


_RND: dict = {}


def _rand(seed, n, cols=8) -> np.ndarray:
    """Deterministische Zufallszahlen (n x cols in 0..1), modulweit gecacht."""
    key = (int(seed), int(n), int(cols))
    if key not in _RND:
        _RND[key] = np.random.RandomState(4242 + int(seed)).rand(n, cols)
    return _RND[key]


def _theme(theme):
    if theme is None:
        return TH.get('curious')
    if isinstance(theme, str):
        return TH.get(theme)
    return theme


# ---------------------------------------------------------------- Pfade

def P_rrect(x, y, w, h, r=0.0):
    p = skia.Path()
    p.addRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(float(x), float(y), float(w), float(h)), float(r), float(r)))
    return p


def P_circle(x, y, r):
    p = skia.Path()
    p.addCircle(float(x), float(y), float(max(0.0, r)))
    return p


def P_oval(x, y, rx, ry):
    p = skia.Path()
    p.addOval(skia.Rect.MakeLTRB(x - rx, y - ry, x + rx, y + ry))
    return p


def P_arch(x, y, w, h, r_bottom=0.0):
    """Rechteck mit halbrundem Kopf (Fenster, Tür, Glaskuppel)."""
    rr = skia.RRect()
    rr.setRectRadii(skia.Rect.MakeXYWH(float(x), float(y), float(w), float(h)), [(w / 2, w / 2), (w / 2, w / 2), (r_bottom, r_bottom), (r_bottom, r_bottom)])
    p = skia.Path()
    p.addRRect(rr)
    return p


def P_union(*paths):
    """Vereinigung mehrerer Pfade (gleiche Laufrichtung, Winding-Füllung): eine Fläche ohne Überlappungsnähte."""
    p = skia.Path()
    for q in paths:
        p.addPath(q)
    return p


def P_cloud(x, y, s):
    """Wolke aus vier Kreisen und einem Sockel (Breite 2 s), Mitte (x, y) an der Unterkante."""
    return P_union(P_rrect(x - s, y - 0.34 * s, 2 * s, 0.34 * s, 0.17 * s),
                   P_circle(x - 0.52 * s, y - 0.3 * s, 0.3 * s), P_circle(x - 0.1 * s, y - 0.46 * s, 0.46 * s),
                   P_circle(x + 0.36 * s, y - 0.36 * s, 0.36 * s), P_circle(x + 0.66 * s, y - 0.22 * s, 0.24 * s))


# ---------------------------------------------------------------- Grundflächen und Licht

def _base(c, g, p, top=None, bottom=None):
    """Verlauf bg0 (oben) -> bg1 (unten) über die ganze Fläche inklusive Überhang."""
    c.rect(g.x0, g.y0, g.w, g.h, shader=c.linear(0, 0, 0, g.H, [top or p.bg0, bottom or p.bg1]))


def _floor(c, g, p, y=None, color=None):
    """Bodenfläche von der Bodenlinie bis unter den Rand."""
    y = g.floor if y is None else y
    c.rect(g.x0, y, g.w, g.y1 - y, color or p.deep)


def _grain(c, g, amount):
    """Korn (Luminanzrauschen, overlay) über die ganze Kulissenebene einschließlich Überhang."""
    if amount <= 0:
        return
    sh = skia.PerlinNoiseShader.MakeTurbulence(0.9, 0.9, 1, 3.0)
    c.rect(g.x0, g.y0, g.w, g.h, shader=sh, alpha=float(amount), blend='overlay')


def _light(c, x, y, r, color, alpha, squash=1.0, blend='add'):
    """Weicher Lichtfleck (radialer Verlauf, additiv); squash < 1 drückt ihn zur Bodenellipse."""
    if alpha <= 0 or r <= 0:
        return
    sh = c.radial(x, y, r, [(0.0, CO.with_alpha(color, 1.0)), (0.42, CO.with_alpha(color, 0.42)), (1.0, CO.with_alpha(color, 0.0))])
    if squash != 1.0:
        with c.tf(sx=1.0, sy=squash, px=x, py=y):
            c.rect(x - r, y - r, 2 * r, 2 * r, shader=sh, alpha=alpha, blend=blend)
    else:
        c.rect(x - r, y - r, 2 * r, 2 * r, shader=sh, alpha=alpha, blend=blend)


def _cone(c, x, y_top, y_bot, w_top, w_bot, color, alpha, blur=22.0, tail=0.12, skew=0.0):
    """Lichtkegel (Trapez mit vertikalem Verlauf, additiv, weiche Kanten); skew verschiebt die Unterkante seitlich."""
    if alpha <= 0:
        return
    pts = [(x - w_top / 2, y_top), (x + w_top / 2, y_top), (x + skew + w_bot / 2, y_bot), (x + skew - w_bot / 2, y_bot)]
    sh = c.linear(x, y_top, x, y_bot, [(0.0, CO.with_alpha(color, 1.0)), (1.0, CO.with_alpha(color, tail))])
    c.poly(pts, shader=sh, alpha=alpha, blend='add', blur=blur)


def _hills(c, g, y, amp, wl, color, seed=0, phase=0.0, bottom=None, alpha=1.0):
    """Weicher Hügelzug (zwei überlagerte Sinus) von Rand zu Rand, gefüllt bis zum unteren Rand."""
    pts = []
    x = g.x0 - 60
    while x <= g.x1 + 60:
        yy = y + amp * (0.62 * math.sin(TWO_PI * x / wl + phase + seed * 0.9) + 0.38 * math.sin(TWO_PI * x / (wl * 0.47) + phase * 1.7 + seed * 2.3))
        pts.append((x, yy))
        x += 48
    path = smooth_path(pts, 0.5, closed=False)
    yb = g.y1 + 20 if bottom is None else bottom
    path.lineTo(g.x1 + 60, yb)
    path.lineTo(g.x0 - 60, yb)
    path.close()
    c.path(path, color, alpha)


def _wave_top(c, g, y, amp, wl, color, shift=0.0, alpha=1.0):
    """Wellenlinie, nach oben bis über den Rand gefüllt (Wasseroberfläche von unten gesehen)."""
    pts = []
    x = g.x0 - 60
    while x <= g.x1 + 60:
        pts.append((x, y + amp * math.sin(TWO_PI * (x + shift) / wl) + 0.4 * amp * math.sin(TWO_PI * (x - 0.6 * shift) / (wl * 0.61))))
        x += 40
    path = smooth_path(pts, 0.5, closed=False)
    path.lineTo(g.x1 + 60, g.y0 - 20)
    path.lineTo(g.x0 - 60, g.y0 - 20)
    path.close()
    c.path(path, color, alpha)


def _tiles(c, g, color, size, gap, y_from, y_to, r=12.0, alpha=1.0, x_from=None, x_to=None):
    """Fliesenraster (abgerundete Quadrate) zwischen y_from und y_to."""
    x_from = g.x0 if x_from is None else x_from
    x_to = g.x1 if x_to is None else x_to
    y = y_from
    while y < y_to:
        x = x_from
        while x < x_to:
            c.rect(x, y, size, min(size, y_to - y), color, r=r, alpha=alpha)
            x += size + gap
        y += size + gap


def _tree(c, x, y, h, color, t=0.0, seed=0.0):
    """Laubbaum: Stamm und zwei Blob-Kronen, die kaum merklich wabern (0.03 Hz)."""
    c.rect(x - 0.05 * h, y - 0.5 * h, 0.1 * h, 0.52 * h, color, r=0.04 * h)
    c.blob(x + 0.14 * h, y - 0.46 * h, 0.2 * h, color, n=7, wob=0.07, seed=seed + 2.0, t=t, speed=0.03)
    c.blob(x, y - 0.63 * h, 0.33 * h, color, n=8, wob=0.07, seed=seed, t=t, speed=0.03)


def _pine(c, x, y, h, color):
    """Tanne: Stamm und drei gestapelte abgerundete Dreiecke (Radius 10)."""
    path = P_rrect(x - 0.05 * h, y - 0.3 * h, 0.1 * h, 0.32 * h, 0.03 * h)
    for k in range(3):
        apex = y - h + k * 0.2 * h
        base = apex + 0.44 * h
        hw = (0.16 + 0.1 * k) * h
        path.addPath(rounded_poly_path([(x, apex), (x + hw, base), (x - hw, base)], 10))
    c.path(path, color)


def _skyline(c, g, color, y_base, hmin, hmax, wmin, wmax, seed, p=None, windows=False, t=0.0, gap=16.0):
    """Reihe flacher Hochhäuser von Rand zu Rand (Dachkanten Radius 12, Antennen, Wassertanks); windows=True setzt
    ein Fensterraster in glow (alpha 0.35), drei Fenster schalten langsam (<= 0.5 Hz)."""
    R = _rand(seed, 160)
    x = g.x0 - 40
    i = 0
    while x < g.x1 + 40:
        r = R[i % 160]
        w = wmin + (wmax - wmin) * r[0]
        h = hmin + (hmax - hmin) * r[1]
        top = y_base - h
        c.rrect_mixed(x, top, w, h + 40, (12, 12, 0, 0), color)
        if r[2] > 0.72:
            c.rect(x + w * 0.5 - 7, top - 0.22 * h, 14, 0.22 * h + 10, color, r=7)
        elif r[2] > 0.45:
            c.rect(x + w * 0.62, top - 36, 44, 36, color, r=10)
        if windows and p is not None:
            cw, chh, sx, sy = 24, 32, 54, 66
            nx = int((w - 44) / sx)
            ny = int((h - 60) / sy)
            ox = x + (w - (nx - 1) * sx - cw) / 2
            for ix in range(nx):
                for iy in range(ny):
                    hsh = (i * 7919 + ix * 1301 + iy * 613) % 101
                    if hsh < 48:
                        a = 0.35
                        if hsh % 17 == 3:
                            a *= A.smoothstep(0.5 + 2.0 * math.sin(TWO_PI * 0.22 * t + hsh))
                        c.rect(ox + ix * sx, top + 36 + iy * sy, cw, chh, p.light, r=4, alpha=a * p.lk)
        x += w + gap * (0.5 + r[3])
        i += 1


def _sun(c, g, p, x, y, r, alpha_disc=0.9, halo=0.22, pulse=0.0):
    """Sonne/Mond: Scheibe in Lichtfarbe mit weichem Hof, der leicht atmet."""
    _light(c, x, y, r * 4.2, p.light, (halo + 0.06 * pulse) * p.lk)
    c.circle(x, y, r, p.light, alpha_disc * p.lk)


def _dust(c, g, p, t, seed, kw, n=16, alpha=0.3, area=None, kind='dust', color=None, speed=1.0, size=1.0):
    """Partikel über fx.particles (<= 40, alpha <= 0.5), abschaltbar über kw['particles']=False."""
    if not kw.get('particles', True):
        return
    fx.particles(c, g.fmt, t, kind, p.th, seed=seed + 101, n=n, alpha=min(0.5, alpha), area=area or g.area, color=color or p.light, speed=speed, size=size)


# ---------------------------------------------------------------- Öffentliche API

def names() -> list:
    """Alle Kulissennamen (ohne Aliasse), alphabetisch."""
    return sorted(BACKDROPS)


def has(name) -> bool:
    """True, wenn name (oder Alias) eine Kulisse ist; unbekannte Namen zählen nicht, obwohl draw sie als 'plain' zeichnet."""
    n = str(name or '').strip().lower()
    return ALIASES.get(n, n) in BACKDROPS


def resolve(name) -> str:
    """Aliasse auflösen; unbekannt -> 'plain'."""
    n = str(name or 'plain').strip().lower()
    n = ALIASES.get(n, n)
    return n if n in BACKDROPS else 'plain'


def draw(c, name, fmt, t=0.0, theme=None, **kw):
    """Kulisse ganzflächig zeichnen, 200 px über jeden Rand hinaus. theme: Theme-dict oder Name (None -> curious).
    kw: seed (Streuung der Silhouetten/Partikel), grain (Korn, Standard 0.045; 0 = aus), particles (False = keine
    Partikel), light (Faktor für alle Lichtquellen, Standard 1.0). Unbekannte Namen zeichnen 'plain'."""
    th = _theme(theme)
    fn = BACKDROPS[resolve(name)]
    g, p = Geo(fmt), Pal(th)
    seed = int(kw.get('seed', 0) or 0)
    _base(c, g, p)
    fn(c, g, p, float(t), seed, kw)
    grain = kw.get('grain', GRAIN)
    if grain and grain > 0:
        _grain(c, g, float(grain))


def _L(p, kw):
    return p.lk * float(kw.get('light', 1.0))


# ================================================================ Kulissen

@backdrop('plain', 'none', 'gradient')
def _plain(c, g, p, t, seed, kw):
    """Verlauf bg0 -> bg1 mit Korn; ein kaum sichtbarer Lichthauch wandert langsam (0.05 Hz), damit nichts stillsteht."""
    x = g.cx + 0.2 * g.W * math.sin(TWO_PI * 0.05 * t + seed)
    y = 0.38 * g.H + 0.05 * g.H * math.cos(TWO_PI * 0.03 * t)
    _light(c, x, y, 0.55 * max(g.W, g.H), p.light, 0.08 * _L(p, kw))


@backdrop('spotlight', 'spot')
def _spotlight(c, g, p, t, seed, kw):
    """Leerer Boden, Lichtkegel von oben (schwenkt +-3° bei 0.08 Hz), Lichtinsel am Boden, 24 Staubteilchen im Kegel."""
    L = _L(p, kw)
    _floor(c, g, p)
    ang = 3.0 * math.sin(TWO_PI * 0.08 * t + seed * 0.7)
    src = g.y0 - 120
    with c.tf(rot=ang, px=g.cx, py=src):
        _cone(c, g.cx, src, g.floor + 80, 90 * g.u, 0.74 * g.W, p.light, 0.16 * L)
    px = g.cx + math.tan(math.radians(ang)) * (g.floor - src)
    _light(c, px, g.floor + 16, 0.42 * g.W, p.light, 0.26 * L, squash=0.26)
    _dust(c, g, p, t, seed, kw, n=24, alpha=0.35 * L, area=(g.cx - 0.32 * g.W, 0.12 * g.H, 0.64 * g.W, g.floor - 0.12 * g.H))


@backdrop('cabinet', 'wunderkammer', 'curio')
def _cabinet(c, g, p, t, seed, kw):
    """Wunderkammer-Regal: Bretter über die Breite mit Glaskuppeln, Gläsern, Globus, Büchern und Kästchen als Silhouetten
    (drei Stufen), Lichtinsel in der Mitte, die langsam wandert, 12 Staubteilchen."""
    L = _L(p, kw)
    R = _rand(seed + 3, 160)
    gap = 300 * g.u
    n_boards = int((g.floor - g.y0) / gap) + 1
    for bi in range(n_boards):
        by = g.floor - 36 * g.u - bi * gap
        x = g.x0 + 10
        i = 0
        while x < g.x1:
            r = R[(bi * 23 + i) % 160]
            kind = int(r[0] * 5)
            col = p.levels[int(r[1] * 3)]
            w = (80 + 90 * r[2]) * g.u
            h = (110 + 110 * r[3]) * g.u
            cx = x + w / 2
            if kind == 0:      # Glaskuppel auf Sockel
                c.path(P_arch(cx - w / 2, by - h, w, h, 6), col)
                c.rect(cx - w / 2 - 10, by - 14 * g.u, w + 20, 14 * g.u, p.mid, r=6)
                c.ellipse(cx, by - 0.3 * h, 0.22 * w, 0.26 * h, p.far if col != p.far else p.mid)
            elif kind == 1:    # Glas mit Deckel
                c.rect(cx - w * 0.36, by - h * 0.8, w * 0.72, h * 0.8, col, r=18 * g.u)
                c.rect(cx - w * 0.3, by - h * 0.8 - 18 * g.u, w * 0.6, 22 * g.u, col, r=8)
            elif kind == 2:    # Globus
                rr = min(w, h) * 0.42
                c.rect(cx - 0.3 * rr, by - 0.5 * rr, 0.6 * rr, 0.5 * rr, col, r=8)
                c.circle(cx, by - 1.1 * rr, rr, col)
            elif kind == 3:    # Bücher
                bx = cx - w / 2
                k = 0
                while bx < cx + w / 2 - 20:
                    bw = (28 + 24 * R[(bi * 7 + i * 3 + k) % 160][4]) * g.u
                    bh = (90 + 80 * R[(bi * 7 + i * 3 + k) % 160][5]) * g.u
                    c.rect(bx, by - bh, bw, bh, p.levels[(int(r[1] * 3) + k) % 3], r=6)
                    bx += bw + 4
                    k += 1
            else:              # Kästchen
                c.rect(cx - w / 2, by - 0.6 * h, w, 0.6 * h, col, r=12)
                c.rect(cx - w / 2 - 6, by - 0.6 * h - 16 * g.u, w + 12, 20 * g.u, col, r=8)
            x += w + (24 + 50 * r[6]) * g.u
            i += 1
        c.rect(g.x0, by, g.w, 24 * g.u, p.mid, r=6)
        c.rect(g.x0, by + 24 * g.u, g.w, 12 * g.u, p.deep, alpha=0.6)
    _floor(c, g, p)
    lx = g.cx + 0.06 * g.W * math.sin(TWO_PI * 0.04 * t)
    _light(c, lx, 0.5 * g.H, 0.5 * g.W, p.light, 0.10 * L)
    _dust(c, g, p, t, seed, kw, n=12, alpha=0.28 * L)


@backdrop('vault', 'safe_room', theme='heist')
def _vault(c, g, p, t, seed, kw):
    """Tresorwand: Reihen quadratischer Schließfächer (mid) mit Zifferblatt (far) und Griff (near), dazu eine große runde
    Tresortür mit Bolzenkranz und Rad, das langsam dreht (3°/s); ein Lichtschein wandert über die Wand (24-s-Periode)."""
    L = _L(p, kw)
    cell, gap = 148 * g.u, 16 * g.u
    step = cell + gap
    cols = int(g.w / step) + 2
    rows = int((g.floor - g.y0) / step) + 1
    for i in range(rows):
        y = g.floor - 24 * g.u - (i + 1) * step + gap
        for j in range(cols):
            x = g.x0 + j * step
            c.rect(x, y, cell, cell, p.mid, r=12)
            c.circle(x + cell * 0.5, y + cell * 0.4, cell * 0.16, p.far)
            c.rect(x + cell * 0.5 - cell * 0.18, y + cell * 0.7, cell * 0.36, 16 * g.u, p.near, r=8)
    _floor(c, g, p)
    if g.portrait:
        dx, dy, r = 0.62 * g.W, 0.28 * g.H, 0.28 * g.W
    else:
        dx, dy, r = 0.5 * g.W, 0.46 * g.H, 0.3 * g.H
    c.circle(dx, dy, r, p.near)
    for k in range(10):
        a = math.radians(k * 36 + 18)
        c.circle(dx + 0.9 * r * math.cos(a), dy + 0.9 * r * math.sin(a), 0.045 * r, p.far)
    c.circle(dx, dy, 0.78 * r, p.mid)
    c.rect(dx + 0.98 * r, dy - 0.34 * r, 0.18 * r, 0.16 * r, p.near, r=0.05 * r)
    c.rect(dx + 0.98 * r, dy + 0.18 * r, 0.18 * r, 0.16 * r, p.near, r=0.05 * r)
    with c.tf(rot=3.0 * t + seed * 20, px=dx, py=dy):
        c.ring(dx, dy, 0.4 * r, 0.075 * r, p.near)
        for k in range(3):
            with c.tf(rot=k * 120, px=dx, py=dy):
                c.rect(dx - 0.04 * r, dy - 0.4 * r, 0.08 * r, 0.8 * r, p.near, r=0.04 * r)
        c.circle(dx, dy, 0.13 * r, p.near)
        c.circle(dx, dy, 0.06 * r, p.mid)
    sx = g.cx + 0.42 * g.W * math.sin(TWO_PI * t / 24.0 + seed)
    _light(c, sx, 0.4 * g.H, 0.5 * g.W, p.light, 0.06 * L)


@backdrop('warehouse', 'storage', theme='heist')
def _warehouse(c, g, p, t, seed, kw):
    """Lagerhalle: Palettenregale über die Breite (Pfosten und Träger mid; Kisten, Fässer, Säcke in drei Stufen),
    Deckenlampe an der Schnur mit Kegel (alpha 0.15), die sanft pendelt (0.2 Hz), 16 Staubteilchen im Licht."""
    L = _L(p, kw)
    R = _rand(seed + 5, 200)
    bay, lvl = 470 * g.u, 300 * g.u
    nb = int(g.w / bay) + 2
    n_rows = int((g.floor - g.y0) / lvl) + 1
    for j in range(nb):
        c.rect(g.x0 + j * bay - 14 * g.u, g.y0, 28 * g.u, g.floor - g.y0 + 10, p.mid)
    for i in range(n_rows):
        by = g.floor - i * lvl
        for j in range(nb):
            bx = g.x0 + j * bay + 34 * g.u
            x = bx
            k = 0
            while x < bx + bay - 90 * g.u:
                r = R[(i * 31 + j * 7 + k) % 200]
                col = p.levels[int(r[0] * 3)]
                kind = int(r[1] * 3)
                w = (100 + 70 * r[2]) * g.u
                h = (120 + 90 * r[3]) * g.u
                if kind == 0:      # Kiste
                    c.rect(x, by - 24 * g.u - h * 0.85, w, h * 0.85, col, r=12)
                elif kind == 1:    # Fass
                    c.path(P_union(P_rrect(x, by - 24 * g.u - h, w, h, 0.26 * w), P_oval(x + w / 2, by - 24 * g.u - h / 2, 0.56 * w, 0.44 * h)), col)
                else:              # Sack
                    c.path(P_union(P_oval(x + w / 2, by - 24 * g.u - 0.42 * h, 0.5 * w, 0.42 * h), P_circle(x + w / 2, by - 24 * g.u - 0.86 * h, 0.16 * w)), col)
                x += w + (16 + 30 * r[4]) * g.u
                k += 1
        c.rect(g.x0, by - 24 * g.u, g.w, 24 * g.u, p.mid, r=6)
    _floor(c, g, p)
    lx = 0.62 * g.W
    head = 0.17 * g.H
    sway = 2.0 * math.sin(TWO_PI * 0.2 * t + seed)
    with c.tf(rot=sway, px=lx, py=g.y0):
        c.rect(lx - 7 * g.u, g.y0, 14 * g.u, head - g.y0, p.near, r=7)
        c.path(rounded_poly_path([(lx - 40 * g.u, head), (lx + 40 * g.u, head), (lx + 120 * g.u, head + 70 * g.u), (lx - 120 * g.u, head + 70 * g.u)], 12), p.near)
        c.circle(lx, head + 74 * g.u, 22 * g.u, p.light, 0.9 * L)
        _cone(c, lx, head + 70 * g.u, g.floor + 60, 230 * g.u, 0.7 * g.W, p.light, 0.15 * L)
    _light(c, lx + math.tan(math.radians(sway)) * (g.floor - g.y0), g.floor + 10, 0.36 * g.W, p.light, 0.2 * L, squash=0.26)
    _dust(c, g, p, t, seed, kw, n=16, alpha=0.3 * L, area=(lx - 0.3 * g.W, head, 0.6 * g.W, g.floor - head))


@backdrop('night_city', 'night', 'city', 'skyline', theme='heist')
def _night_city(c, g, p, t, seed, kw):
    """Nächtliche Skyline in drei Stufen (far hoch, mid, near niedrig mit Fensterraster), Mond r 90 mit Hof,
    30 Sterne, drei Fenster schalten langsam (<= 0.5 Hz)."""
    L = _L(p, kw)
    _dust(c, g, p, t, seed, kw, n=30, alpha=0.4, kind='stars', area=(g.x0, g.y0, g.w, 0.45 * g.H + OVER), color=p.ink)
    mx, my = g.sky
    _sun(c, g, p, mx, my, 90 * g.u, 0.92, 0.2, math.sin(TWO_PI * 0.05 * t))
    _skyline(c, g, p.far, g.floor + 10, 0.22 * g.H, 0.36 * g.H, 90 * g.u, 170 * g.u, seed + 21, gap=10)
    _skyline(c, g, p.mid, g.floor + 10, 0.14 * g.H, 0.3 * g.H, 120 * g.u, 240 * g.u, seed + 22, gap=14)
    _skyline(c, g, p.near, g.floor + 10, 0.06 * g.H, 0.17 * g.H, 150 * g.u, 300 * g.u, seed + 23, p=p, windows=True, t=t, gap=20)
    _floor(c, g, p)


@backdrop('museum', 'gallery', theme='heist')
def _museum(c, g, p, t, seed, kw):
    """Galeriewand: leere Rahmen (Radius 24; Rahmen near, Innenfeld far) mit Bilderleuchten, deren Licht nacheinander
    anschwillt (0.07 Hz, versetzt), Sockel mit Glaskuppel, Absperrpfosten mit Kordel, Fußleiste."""
    L = _L(p, kw)
    _floor(c, g, p)
    c.rect(g.x0, g.floor - 30 * g.u, g.w, 30 * g.u, p.far)
    if g.portrait:
        frames = [(0.28 * g.W, 0.27 * g.H, 330 * g.u, 290 * g.u), (0.72 * g.W, 0.27 * g.H, 330 * g.u, 290 * g.u)]
        ped_x = 0.5 * g.W
    else:
        frames = [(0.22 * g.W, 0.37 * g.H, 360 * g.u, 300 * g.u), (0.5 * g.W, 0.37 * g.H, 360 * g.u, 300 * g.u), (0.78 * g.W, 0.37 * g.H, 360 * g.u, 300 * g.u)]
        ped_x = 0.36 * g.W
    for i, (fx_, fy_, fw, fh) in enumerate(frames):
        pulse = 0.5 + 0.5 * math.sin(TWO_PI * 0.07 * t + i * 2.1 + seed)
        c.rect(fx_ - fw / 2, fy_ - fh / 2, fw, fh, p.near, r=24)
        c.rect(fx_ - fw / 2 + 28 * g.u, fy_ - fh / 2 + 28 * g.u, fw - 56 * g.u, fh - 56 * g.u, p.far, r=12)
        ly = fy_ - fh / 2 - 44 * g.u
        c.rect(fx_ - 0.28 * fw, ly - 10 * g.u, 0.56 * fw, 20 * g.u, p.near, r=10)
        c.rect(fx_ - 8 * g.u, ly - 36 * g.u, 16 * g.u, 30 * g.u, p.near, r=8)
        _cone(c, fx_, ly + 10 * g.u, fy_ + fh / 2 + 20, 0.5 * fw, 1.2 * fw, p.light, (0.05 + 0.08 * pulse) * L, blur=16)
    c.rect(ped_x - 110 * g.u, g.floor - 180 * g.u, 220 * g.u, 190 * g.u, p.mid, r=12)
    c.rect(ped_x - 130 * g.u, g.floor - 204 * g.u, 260 * g.u, 26 * g.u, p.near, r=8)
    c.path(P_arch(ped_x - 72 * g.u, g.floor - 204 * g.u - 180 * g.u, 144 * g.u, 180 * g.u, 6), p.far)
    c.ellipse(ped_x, g.floor - 204 * g.u - 50 * g.u, 30 * g.u, 40 * g.u, p.mid)
    for sx_ in (ped_x - 240 * g.u, ped_x + 240 * g.u):
        c.rect(sx_ - 11 * g.u, g.floor - 130 * g.u, 22 * g.u, 130 * g.u, p.near, r=10)
        c.rect(sx_ - 30 * g.u, g.floor - 14 * g.u, 60 * g.u, 14 * g.u, p.near, r=7)
        c.circle(sx_, g.floor - 140 * g.u, 20 * g.u, p.near)
    rope = skia.Path()
    rope.moveTo(ped_x - 240 * g.u, g.floor - 128 * g.u)
    rope.quadTo(ped_x, g.floor - 60 * g.u, ped_x + 240 * g.u, g.floor - 128 * g.u)
    c.path(rope, p.mid, stroke=14 * g.u)


@backdrop('cave', 'cavern', theme='cave')
def _cave(c, g, p, t, seed, kw):
    """Höhle: Deckenmasse mit Stalaktiten (abgerundete Dreiecke, Radius 6) in drei Stufen, Stalagmiten am Boden, dunkler
    Boden mit Wasserlache (water), zwei Tropfen fallen im Takt (2.6 s) und schlagen Ringe, warmes Lampenlicht wandert."""
    L = _L(p, kw)
    R = _rand(seed + 11, 120)
    _floor(c, g, p)
    _hills(c, g, g.y0 + 0.08 * g.H, 0.035 * g.H, 0.5 * g.W, p.far, seed, bottom=g.y0 - 20)
    if g.portrait:
        drops = [0.5 * g.W, 0.9 * g.W]
    else:
        drops = [0.57 * g.W, 0.9 * g.W]
    tips = []
    specs = ((p.far, 16, 0.12, 0.3, 50, 90), (p.mid, 10, 0.1, 0.26, 70, 120), (p.near, 6, 0.08, 0.2, 90, 150))
    for li, (col, n, lmin, lmax, wmin, wmax) in enumerate(specs):
        for i in range(n):
            r = R[(li * 20 + i) % 120]
            x = g.x0 + (i + 0.5 + (r[0] - 0.5) * 0.8) * g.w / n
            if li == 2 and i < len(drops):
                x = drops[i]
            ln = (lmin + (lmax - lmin) * r[1]) * g.H
            w = (wmin + (wmax - wmin) * r[2]) * g.u
            top = g.y0 + 0.03 * g.H * r[3]
            c.path(rounded_poly_path([(x - w / 2, top), (x + w / 2, top), (x + 0.06 * w, top + ln)], 6), col)
            if li == 2 and i < len(drops):
                tips.append((x + 0.06 * w, top + ln))
        for i in range(max(3, n // 2)):
            r = R[(60 + li * 15 + i) % 120]
            x = g.x0 + (i + 0.5 + (r[4] - 0.5) * 0.9) * g.w / max(3, n // 2)
            ln = (0.4 * lmin + 0.5 * (lmax - lmin) * r[5]) * g.H
            w = (wmin + (wmax - wmin) * r[6]) * g.u
            c.path(rounded_poly_path([(x - w / 2, g.floor + 12), (x + 0.05 * w, g.floor - ln), (x + w / 2, g.floor + 12)], 6), col)
    lx = 0.45 * g.W + 0.05 * g.W * math.sin(TWO_PI * 0.04 * t + seed)
    ly = 0.55 * g.H + 0.03 * g.H * math.cos(TWO_PI * 0.03 * t)
    _light(c, lx, ly, 0.6 * g.W, p.light, 0.16 * L)
    for k, (tx, ty) in enumerate(tips):
        pool_y = g.floor + 40 * g.u
        c.ellipse(tx, pool_y, (120 + 60 * k) * g.u, 24 * g.u, p.water, 0.28)
        period = 2.6 + 0.9 * k
        u = ((t + k * 1.3 + seed * 0.4) / period) % 1.0
        if u < 0.12:
            c.circle(tx, ty + 6, 12 * g.u * (u / 0.12), p.water, 0.9)
        else:
            v = (u - 0.12) / 0.88
            yy = ty + (pool_y - ty) * v * v
            if yy < pool_y - 8:
                c.ellipse(tx, yy, 11 * g.u, 14 * g.u, p.water, 0.9)
        wv = (u + 0.02) / 0.3
        if wv < 1.0:
            c.ellipse(tx, pool_y, (30 + 110 * wv) * g.u, (8 + 28 * wv) * g.u, p.water, 0.5 * (1 - wv), stroke=14 * g.u)


@backdrop('forest', 'jungle', 'woods', theme='animal')
def _forest(c, g, p, t, seed, kw):
    """Wald: gestaffelte Laubbäume (Blob-Kronen, die kaum merklich wabern) in drei Stufen, Büsche am Boden, drei
    Lichtflecken, die langsam über den Boden wandern, 10 Glühwürmchen."""
    L = _L(p, kw)
    R = _rand(seed + 13, 80)
    _hills(c, g, g.floor - 0.12 * g.H, 0.03 * g.H, 0.8 * g.W, p.far, seed + 5)
    _floor(c, g, p)
    layers = ((p.far, 8, 240, 320, -0.02 * g.H), (p.mid, 5, 340, 440, 0.01 * g.H))
    for li, (col, n, hmin, hmax, dy) in enumerate(layers):
        for i in range(n):
            r = R[(li * 9 + i) % 80]
            x = g.x0 + (i + 0.5 + (r[0] - 0.5) * 0.7) * g.w / n
            h = (hmin + (hmax - hmin) * r[1]) * g.u
            _tree(c, x, g.floor + dy, h, col, t, seed + li * 7 + i)
        for i in range(n + 2):
            r = R[(40 + li * 9 + i) % 80]
            x = g.x0 + (i + 0.5 + (r[2] - 0.5)) * g.w / (n + 2)
            c.ellipse(x, g.floor + dy + 10, (60 + 60 * r[3]) * g.u, (30 + 26 * r[4]) * g.u, col)
    for i, fx_ in enumerate((0.0 * g.W, 1.0 * g.W)):
        r = R[(20 + i) % 80]
        h = (520 + 90 * r[1]) * g.u
        _tree(c, fx_, g.floor + 0.04 * g.H, h, p.near, t, seed + 40 + i)
    for i in range(3):
        r = R[(50 + i) % 80]
        x = 0.2 * g.W + 0.6 * g.W * r[5] + 30 * g.u * math.sin(TWO_PI * 0.05 * t + i * 2.0)
        _light(c, x, g.floor + 30 * g.u, (140 + 90 * r[6]) * g.u, p.light, 0.1 * L, squash=0.3)
    _dust(c, g, p, t, seed, kw, n=10, alpha=0.35 * L, area=(g.x0, 0.3 * g.H, g.w, g.floor - 0.3 * g.H), speed=0.6, size=1.4)


@backdrop('ocean', 'seabed', 'underwater', 'sea', theme='ocean')
def _ocean(c, g, p, t, seed, kw):
    """Unterwasser: helle Oberfläche mit laufender Welle und Schaumsaum, vier Lichtschäfte (additiv, schwingen 0.06 Hz),
    Sandboden mit Felsen, Seetang, der sich wiegt (0.2 Hz), 16 Blasen (foam) steigen auf."""
    L = _L(p, kw)
    R = _rand(seed + 17, 60)
    c.rect(g.x0, g.y0, g.w, 0.3 * g.H + OVER, shader=c.linear(0, g.y0, 0, 0.3 * g.H, [(0.0, CO.with_alpha(p.near, 0.85)), (1.0, CO.with_alpha(p.near, 0.0))]))
    ys = 0.065 * g.H
    _wave_top(c, g, ys + 22 * g.u, 16 * g.u, 300 * g.u, p.foam, shift=60 * t, alpha=0.22)
    _wave_top(c, g, ys, 18 * g.u, 320 * g.u, p.near, shift=70 * t)
    for i in range(4):
        r = R[i]
        x = (0.14 + 0.24 * i) * g.W + 40 * g.u * (r[0] - 0.5)
        ang = 2.0 * math.sin(TWO_PI * 0.06 * t + i * 1.7 + seed)
        with c.tf(rot=ang, px=x, py=ys):
            _cone(c, x, ys, 0.78 * g.H, (70 + 60 * r[1]) * g.u, (260 + 100 * r[2]) * g.u, p.light, 0.07 * L, blur=26, tail=0.0, skew=110 * g.u)
    _hills(c, g, g.floor - 10, 24 * g.u, 0.7 * g.W, p.far, seed + 1)
    for i in range(3):
        r = R[10 + i]
        x = g.x0 + (i + 0.5 + (r[3] - 0.5) * 0.5) * g.w / 3
        c.ellipse(x, g.floor + 14, (80 + 80 * r[4]) * g.u, (40 + 40 * r[5]) * g.u, p.mid)
    weeds = [(0.05, 0.3, p.near), (0.11, 0.22, p.mid), (0.48, 0.18, p.far), (0.92, 0.26, p.mid), (0.98, 0.34, p.near)]
    for i, (ax, ah, col) in enumerate(weeds):
        _seaweed(c, g.x0 + ax * g.w if ax < 0.5 else g.x0 + ax * g.w, g.floor + 20, ah * g.H, col, t, i + seed)
    _dust(c, g, p, t, seed, kw, n=16, alpha=0.45, kind='bubbles', area=(g.x0, 0.2 * g.H, g.w, g.y1 - 0.2 * g.H), color=p.foam, speed=0.8, size=0.9)


def _seaweed(c, x, y, h, color, t, seed=0):
    """Seetangblatt: zur Spitze verjüngte Form entlang einer sich wiegenden Rückenlinie (0.2 Hz)."""
    n = 7
    sway = math.sin(TWO_PI * 0.2 * t + seed * 1.3)
    left, right = [], []
    for k in range(n + 1):
        u = k / n
        yy = y - h * u
        xx = x + (0.18 * h * sway + 0.05 * h * math.sin(TWO_PI * 0.2 * t * 1.3 + seed)) * u * u
        w = (0.11 * h) * (1 - u) + 10
        left.append((xx - w / 2, yy))
        right.append((xx + w / 2, yy))
    c.smooth_poly(left + right[::-1], color, tension=0.5)


@backdrop('space', 'stars', 'cosmos', theme='space')
def _space(c, g, p, t, seed, kw):
    """Weltraum: 40 Sterne (funkeln), zwei weiche Nebel (bg2, accent2), Ringplanet in Zwei-Ton (near/mid, Ring far),
    der kaum merklich schwebt (0.04 Hz), alle 9 s eine Sternschnuppe."""
    L = _L(p, kw)
    c.circle(0.22 * g.W, 0.6 * g.H, 0.32 * min(g.W, g.H), p.near, alpha=0.35, blur=140)
    c.circle(0.72 * g.W, 0.78 * g.H, 0.26 * min(g.W, g.H), p.accent2, alpha=0.09, blur=160)
    _dust(c, g, p, t, seed, kw, n=40, alpha=0.5, kind='stars', color=p.ink, size=1.1)
    px, py = g.sky
    py += 6 * g.u * math.sin(TWO_PI * 0.04 * t + seed)
    r = (0.13 * g.W) if g.portrait else (0.14 * g.H)
    shade = CO.hexs(CO.mix(p.near, p.mid, 0.5))
    with c.tf(rot=-18, px=px, py=py):
        c.ellipse(px, py, 2.1 * r, 0.55 * r, p.mid, stroke=0.2 * r)
    c.circle(px, py, r, p.near)
    with c.clip_circle(px, py, r):
        c.circle(px + 0.32 * r, py + 0.3 * r, r, shade)
    with c.tf(rot=-18, px=px, py=py):
        with c.clip_rect(px - 2.6 * r, py, 5.2 * r, 2 * r):
            c.ellipse(px, py, 2.1 * r, 0.55 * r, p.mid, stroke=0.2 * r)
    c.circle(px, py, r * 1.6, p.light, 0.12 * L, blur=r * 0.8, blend='add')
    period = 9.0
    u = ((t + seed * 0.37) % period) / 0.8
    if u < 1.0:
        sx = 0.12 * g.W + 0.3 * g.W * u
        sy = 0.4 * g.H + 0.16 * g.H * u
        c.line(sx, sy, sx - 140 * g.u * (1 - 0.5 * u), sy - 72 * g.u * (1 - 0.5 * u), p.light, 14 * g.u, 0.7 * (1 - u) * L)


@backdrop('desert', 'savanna', 'dunes', theme='history')
def _desert(c, g, p, t, seed, kw):
    """Wüste: Sonnenscheibe mit atmendem Hof (0.06 Hz), drei Dünenzüge (weiche Hügel in far/mid/near), ein Kaktus und
    Steine, feiner Staub treibt."""
    L = _L(p, kw)
    R = _rand(seed + 19, 20)
    sx, sy = g.sky
    _sun(c, g, p, sx, sy, 100 * g.u, 0.9, 0.22, math.sin(TWO_PI * 0.06 * t))
    _hills(c, g, g.floor - 0.1 * g.H, 0.05 * g.H, 0.95 * g.W, p.far, seed + 1)
    _hills(c, g, g.floor - 0.025 * g.H, 0.04 * g.H, 0.7 * g.W, p.mid, seed + 2, phase=1.2)
    cx_ = 0.88 * g.W if g.portrait else 0.9 * g.W
    cy_ = g.floor - 0.03 * g.H
    hh = 0.17 * g.H
    c.path(P_union(P_rrect(cx_ - 0.1 * hh, cy_ - hh, 0.2 * hh, hh + 20, 0.1 * hh),
                   P_rrect(cx_ - 0.42 * hh, cy_ - 0.72 * hh, 0.16 * hh, 0.4 * hh, 0.08 * hh), P_rrect(cx_ - 0.42 * hh, cy_ - 0.42 * hh, 0.4 * hh, 0.14 * hh, 0.07 * hh),
                   P_rrect(cx_ + 0.26 * hh, cy_ - 0.84 * hh, 0.16 * hh, 0.46 * hh, 0.08 * hh), P_rrect(cx_ + 0.04 * hh, cy_ - 0.5 * hh, 0.38 * hh, 0.14 * hh, 0.07 * hh)), p.mid)
    _hills(c, g, g.floor + 30 * g.u, 0.03 * g.H, 0.55 * g.W, p.near, seed + 3, phase=2.4)
    for i in range(3):
        r = R[i]
        x = 0.1 * g.W + 0.8 * g.W * r[0]
        c.ellipse(x, g.floor + (60 + 40 * r[1]) * g.u, (30 + 30 * r[2]) * g.u, (16 + 14 * r[3]) * g.u, p.mid)
    _dust(c, g, p, t, seed, kw, n=10, alpha=0.25 * L, color=p.chalk, speed=1.6, size=1.2)


@backdrop('snow', 'winter', theme='heist')
def _snow(c, g, p, t, seed, kw):
    """Winter: Mond mit Hof, zwei Hügelzüge, Tannen (gestapelte abgerundete Dreiecke) in drei Stufen, 36 Schneeflocken
    (foam) fallen langsam."""
    L = _L(p, kw)
    R = _rand(seed + 23, 40)
    mx, my = g.sky
    _sun(c, g, p, mx, my, 70 * g.u, 0.9, 0.18, math.sin(TWO_PI * 0.05 * t))
    _hills(c, g, g.floor - 0.08 * g.H, 0.04 * g.H, 0.8 * g.W, p.far, seed + 1)
    for i in range(7):
        r = R[i]
        x = g.x0 + (i + 0.5 + (r[0] - 0.5) * 0.7) * g.w / 7
        _pine(c, x, g.floor - 0.08 * g.H + 0.02 * g.H * math.sin(x * 0.004), (0.14 + 0.08 * r[1]) * g.H, p.far)
    _hills(c, g, g.floor - 0.01 * g.H, 0.03 * g.H, 0.6 * g.W, p.mid, seed + 2, phase=1.5)
    for i in range(4):
        r = R[10 + i]
        x = g.x0 + (i + 0.5 + (r[0] - 0.5) * 0.7) * g.w / 4
        _pine(c, x, g.floor + 0.01 * g.H, (0.2 + 0.1 * r[1]) * g.H, p.mid)
    _hills(c, g, g.floor + 0.05 * g.H, 0.025 * g.H, 0.5 * g.W, p.near, seed + 3, phase=0.7)
    for x, hh in ((0.04 * g.W, 0.42), (0.97 * g.W, 0.36)):
        _pine(c, x, g.floor + 0.09 * g.H, hh * g.H, p.near)
    _dust(c, g, p, t, seed, kw, n=36, alpha=0.45, kind='snow', color=p.foam, speed=0.7)


@backdrop('lab', 'laboratory', theme='medical')
def _lab(c, g, p, t, seed, kw):
    """Labor: Fliesenwand (far, Raster 120 px), Deckenleuchte mit weichem Licht, Labortisch mit Reagenzglas-Ständer
    (vier Gläser, Flüssigkeit in ok) und Erlenmeyer-Kolben (accent2), in dem Blasen aufsteigen (2.4-s-Schleife)."""
    L = _L(p, kw)
    _tiles(c, g, p.far, 118 * g.u, 10 * g.u, g.y0, g.floor - 40 * g.u, alpha=0.75)
    c.rect(g.x0, g.floor - 40 * g.u, g.w, 40 * g.u, p.mid)
    _floor(c, g, p)
    lx, ly = 0.4 * g.W, 0.1 * g.H
    c.rect(lx - 220 * g.u, ly - 11 * g.u, 440 * g.u, 22 * g.u, p.light, r=11 * g.u, alpha=0.55 * L)
    _light(c, lx, ly + 40 * g.u, 0.5 * g.W, p.light, 0.09 * L, squash=0.5)
    bx = 0.4 * g.W if g.portrait else 0.5 * g.W
    top = g.floor - 170 * g.u
    c.rect(bx, top, g.x1 - bx, 170 * g.u + 10, p.mid)
    c.rect(bx - 12 * g.u, top - 26 * g.u, g.x1 - bx + 12 * g.u, 26 * g.u, p.near, r=8)
    x = bx + 40 * g.u
    while x < g.x1:
        c.rect(x, top + 30 * g.u, 150 * g.u, 120 * g.u, p.far, r=10)
        x += 170 * g.u
    rx = bx + 0.2 * (g.x1 - bx)
    ry = top - 26 * g.u
    c.rect(rx - 110 * g.u, ry - 26 * g.u, 220 * g.u, 26 * g.u, p.near, r=8)
    for i in range(4):
        tx = rx - 78 * g.u + i * 52 * g.u
        tube = P_rrect(tx - 17 * g.u, ry - 180 * g.u, 34 * g.u, 160 * g.u, 17 * g.u)
        c.path(tube, p.far)
        with c.clip_path(tube):
            fill = (0.35 + 0.15 * ((i * 7) % 3)) * 160 * g.u
            c.rect(tx - 20 * g.u, ry - 20 * g.u - fill, 40 * g.u, fill + 20, p.ok, alpha=0.55)
    fx_ = rx + 300 * g.u
    fy_ = ry
    body = rounded_poly_path([(fx_ - 30 * g.u, fy_ - 170 * g.u), (fx_ + 30 * g.u, fy_ - 170 * g.u), (fx_ + 95 * g.u, fy_), (fx_ - 95 * g.u, fy_)], 16)
    flask = P_union(body, P_rrect(fx_ - 28 * g.u, fy_ - 215 * g.u, 56 * g.u, 60 * g.u, 10 * g.u))
    c.path(flask, p.far)
    with c.clip_path(flask):
        c.rect(fx_ - 110 * g.u, fy_ - 78 * g.u, 220 * g.u, 90 * g.u, p.accent2, alpha=0.5)
        for k in range(3):
            u = ((t * 0.42 + k * 0.33 + seed * 0.1) % 1.0)
            by = fy_ - 10 * g.u - u * 64 * g.u
            bxk = fx_ + (k - 1) * 26 * g.u + 6 * g.u * math.sin(TWO_PI * t * 0.5 + k)
            c.circle(bxk, by, 12 * g.u * (0.6 + 0.4 * u), p.accent2, alpha=0.6 * (1 - u * u))


@backdrop('hospital', 'clinic', theme='medical')
def _hospital(c, g, p, t, seed, kw):
    """Klinik: Wand mit Fenster und Jalousie (Lamellen 24 px), Lichtfächer vom Fenster auf den Boden (atmet 0.05 Hz),
    Deckenleuchte, Bett mit Kopfteil und Infusionsständer rechts, Vorhang am Rand, 12 Staubteilchen im Licht."""
    L = _L(p, kw)
    _floor(c, g, p)
    c.rect(g.x0, g.floor - 30 * g.u, g.w, 30 * g.u, p.far)
    if g.portrait:
        wx, wy, ww, wh = 0.62 * g.W, 0.25 * g.H, 360 * g.u, 300 * g.u
        bx = 0.78 * g.W
    else:
        wx, wy, ww, wh = 0.45 * g.W, 0.3 * g.H, 400 * g.u, 340 * g.u
        bx = 0.82 * g.W
    pulse = 0.5 + 0.5 * math.sin(TWO_PI * 0.05 * t + seed)
    c.rect(wx - ww / 2, wy - wh / 2, ww, wh, p.near, r=16)
    c.rect(wx - ww / 2 + 18 * g.u, wy - wh / 2 + 18 * g.u, ww - 36 * g.u, wh - 36 * g.u, p.pane, r=8)
    y = wy - wh / 2 + 30 * g.u
    while y < wy + wh / 2 - 30 * g.u:
        c.rect(wx - ww / 2 + 30 * g.u, y, ww - 60 * g.u, 24 * g.u, p.mid, r=6)
        y += 38 * g.u
    pts = [(wx - ww / 2 + 18 * g.u, wy + wh / 2), (wx + ww / 2 - 18 * g.u, wy + wh / 2), (wx + ww / 2 - 200 * g.u, g.floor + 60), (wx - ww / 2 - 440 * g.u, g.floor + 60)]
    c.poly(pts, shader=c.linear(wx, wy + wh / 2, wx, g.floor, [(0.0, CO.with_alpha(p.light, 0.9)), (1.0, CO.with_alpha(p.light, 0.1))]), alpha=(0.06 + 0.03 * pulse) * L, blend='add', blur=30)
    lx, ly = 0.3 * g.W, 0.1 * g.H
    c.rect(lx - 150 * g.u, ly - 11 * g.u, 300 * g.u, 22 * g.u, p.light, r=11 * g.u, alpha=0.5 * L)
    _light(c, lx, ly + 40 * g.u, 0.4 * g.W, p.light, 0.08 * L, squash=0.5)
    c.rect(bx - 190 * g.u, g.floor - 90 * g.u, 380 * g.u, 40 * g.u, p.mid, r=10)
    for lxk in (bx - 170 * g.u, bx + 150 * g.u):
        c.rect(lxk, g.floor - 60 * g.u, 26 * g.u, 60 * g.u, p.mid, r=8)
    c.rect(bx - 200 * g.u, g.floor - 190 * g.u, 400 * g.u, 110 * g.u, p.near, r=24)
    c.rect(bx + 110 * g.u, g.floor - 180 * g.u, 90 * g.u, 50 * g.u, p.far, r=18)
    c.rect(bx + 180 * g.u, g.floor - 300 * g.u, 44 * g.u, 300 * g.u, p.near, r=16)
    ix = bx - 270 * g.u
    c.rect(ix - 45 * g.u, g.floor - 16 * g.u, 90 * g.u, 16 * g.u, p.mid, r=8)
    c.rect(ix - 8 * g.u, g.floor - 430 * g.u, 16 * g.u, 430 * g.u, p.mid, r=8)
    c.rect(ix - 40 * g.u, g.floor - 438 * g.u, 80 * g.u, 16 * g.u, p.mid, r=8)
    c.rect(ix - 20 * g.u, g.floor - 420 * g.u, 60 * g.u, 110 * g.u, p.far, r=22 * g.u)
    cx0 = g.W - 150 * g.u
    c.rect(cx0, 0.12 * g.H, g.x1 - cx0, g.floor - 0.12 * g.H + 10, p.mid, r=20)
    for k in range(4):
        c.rect(cx0 + 30 * g.u + k * 70 * g.u, 0.13 * g.H, 36 * g.u, g.floor - 0.13 * g.H, p.far, r=18)
    c.rect(cx0 - 30 * g.u, 0.12 * g.H - 10 * g.u, g.x1 - cx0 + 30 * g.u, 20 * g.u, p.near, r=10)
    _dust(c, g, p, t, seed, kw, n=12, alpha=0.3 * L, area=(wx - ww, wy, 1.4 * ww, g.floor - wy))


@backdrop('courtroom', 'court', theme='crime')
def _courtroom(c, g, p, t, seed, kw):
    """Gerichtssaal: Holzpaneele (far/mid im Wechsel), Richterbank mit Pult (near/mid) vor einer schmalen hohen Rückwand,
    darüber die Waage als Silhouette, die sanft pendelt (0.15 Hz), zwei Wandleuchten mit weichem Licht."""
    L = _L(p, kw)
    pw = 180 * g.u
    x = g.x0
    k = 0
    while x < g.x1:
        c.rect(x + 6, g.y0, pw - 12, g.floor - g.y0 + 10, p.far if k % 2 == 0 else p.mid, r=10)
        x += pw
        k += 1
    c.rect(g.x0, 0.6 * g.H if g.portrait else 0.64 * g.H, g.w, 22 * g.u, p.near, r=6)
    _floor(c, g, p)
    bw = 0.5 * g.W if g.portrait else 0.36 * g.W
    top = (0.2 if g.portrait else 0.18) * g.H
    c.rect(g.cx - bw * 0.3, top, bw * 0.6, g.floor - top, p.mid, r=24)
    c.rect(g.cx - bw * 0.3 - 16 * g.u, top - 16 * g.u, bw * 0.6 + 32 * g.u, 32 * g.u, p.near, r=12)
    c.rect(g.cx - bw / 2, g.floor - 230 * g.u, bw, 230 * g.u + 10, p.near, r=16)
    c.rect(g.cx - bw / 2 - 20 * g.u, g.floor - 256 * g.u, bw + 40 * g.u, 30 * g.u, p.mid, r=12)
    c.rect(g.cx - 60 * g.u, g.floor - 320 * g.u, 120 * g.u, 70 * g.u, p.mid, r=12)
    sy = top + (0.07 if g.portrait else 0.1) * g.H
    sway = 3.0 * math.sin(TWO_PI * 0.15 * t + seed)
    c.rect(g.cx - 14 * g.u, sy, 28 * g.u, 250 * g.u, p.near, r=14)
    c.rect(g.cx - 90 * g.u, sy + 236 * g.u, 180 * g.u, 26 * g.u, p.near, r=13)
    c.circle(g.cx, sy, 26 * g.u, p.near)
    with c.tf(rot=sway, px=g.cx, py=sy):
        c.rect(g.cx - 210 * g.u, sy - 13 * g.u, 420 * g.u, 26 * g.u, p.near, r=13)
    for s in (-1, 1):
        ex = g.cx + s * 196 * g.u * math.cos(math.radians(sway))
        ey = sy + s * 196 * g.u * math.sin(math.radians(sway))
        c.rect(ex - 8 * g.u, ey, 16 * g.u, 130 * g.u, p.near, r=8)
        with c.clip_rect(ex - 110 * g.u, ey + 130 * g.u, 220 * g.u, 50 * g.u):
            c.ellipse(ex, ey + 130 * g.u, 96 * g.u, 38 * g.u, p.near)
    for sx_ in (0.12 * g.W, 0.88 * g.W):
        c.rect(sx_ - 40 * g.u, 0.3 * g.H, 80 * g.u, 34 * g.u, p.near, r=14)
        c.rect(sx_ - 12 * g.u, 0.3 * g.H + 34 * g.u, 24 * g.u, 60 * g.u, p.near, r=12)
        _light(c, sx_, 0.3 * g.H - 20, 0.26 * g.W, p.light, 0.12 * L)


@backdrop('map', 'atlas', 'world', theme='history')
def _map(c, g, p, t, seed, kw):
    """Landkarte: Rasterlinien (far, 14 px, alle 180 px), drei Landmassen (mid) mit Küstensaum (far), gestrichelte Route
    (glow), drei Pins (accent2) – der Hauptpin sendet alle 2.6 s einen Ring, Kompassrose oben rechts."""
    L = _L(p, kw)
    step = 180 * g.u
    x = g.x0
    while x < g.x1:
        c.rect(x - 7 * g.u, g.y0, 14 * g.u, g.h, p.far, alpha=0.55)
        x += step
    y = g.y0
    while y < g.y1:
        c.rect(g.x0, y - 7 * g.u, g.w, 14 * g.u, p.far, alpha=0.55)
        y += step
    R = _rand(seed + 29, 40)
    if g.portrait:
        lands = [(0.28, 0.5, 0.26), (0.82, 0.18, 0.15), (0.78, 0.8, 0.2)]
        pins = [(0.18 * g.W, 0.3 * g.H), (0.56 * g.W, 0.24 * g.H), (0.86 * g.W, 0.5 * g.H)]
        comp = (0.86 * g.W, 0.1 * g.H)
    else:
        lands = [(0.22, 0.55, 0.2), (0.62, 0.15, 0.14), (0.86, 0.75, 0.18)]
        pins = [(0.22 * g.W, 0.32 * g.H), (0.5 * g.W, 0.22 * g.H), (0.84 * g.W, 0.74 * g.H)]
        comp = (0.93 * g.W, 0.14 * g.H)
    for i, (ax, ay, ar) in enumerate(lands):
        cx_, cy_, r = ax * g.W, ay * g.H, ar * g.W
        pts = []
        for k in range(10):
            a = TWO_PI * k / 10
            rr = r * (0.7 + 0.5 * R[(i * 10 + k) % 40][0])
            pts.append((cx_ + rr * math.cos(a), cy_ + rr * 0.8 * math.sin(a)))
        c.smooth_poly([(cx_ + (px - cx_) * 1.09, cy_ + (py - cy_) * 1.09) for px, py in pts], p.far)
        c.smooth_poly(pts, p.mid)
    route = smooth_path(pins, 0.5, closed=False)
    paint_path = skia.Path(route)
    c.path(paint_path, p.light, alpha=0.3 * L, stroke=14 * g.u)
    for i, (px, py) in enumerate(pins):
        if i == 0:
            u = ((t + seed * 0.2) % 2.6) / 2.6
            c.ring(px, py, (30 + 120 * u) * g.u, 14 * g.u, p.accent2, 0.5 * (1 - u))
        c.path(P_union(P_circle(px, py - 30 * g.u, 26 * g.u), rounded_poly_path([(px - 22 * g.u, py - 24 * g.u), (px + 22 * g.u, py - 24 * g.u), (px, py + 12 * g.u)], 6)), p.accent2, 0.9)
        c.circle(px, py - 30 * g.u, 9 * g.u, p.mid)
    cx_, cy_ = comp
    c.ring(cx_, cy_, 50 * g.u, 14 * g.u, p.far)
    for k in range(4):
        with c.tf(rot=k * 90, px=cx_, py=cy_):
            c.path(rounded_poly_path([(cx_, cy_ - 76 * g.u), (cx_ + 16 * g.u, cy_ - 30 * g.u), (cx_ - 16 * g.u, cy_ - 30 * g.u)], 4), p.mid)


@backdrop('archive', 'records', 'files', theme='crime')
def _archive(c, g, p, t, seed, kw):
    """Aktenarchiv: Regalreihen über die ganze Höhe mit Aktenordnern (Etikettfeld) und Kartons in drei Stufen, eine
    Rollleiter rechts, ein warmer Lichtschein wandert langsam über die Regale (24-s-Periode), 14 Staubteilchen."""
    L = _L(p, kw)
    R = _rand(seed + 31, 240)
    row = 260 * g.u
    n_rows = int((g.floor - g.y0) / row) + 1
    for i in range(n_rows):
        by = g.floor - i * row
        x = g.x0 + 10
        k = 0
        while x < g.x1:
            r = R[(i * 37 + k) % 240]
            col = p.far if r[0] < 0.5 else (p.mid if r[0] < 0.86 else p.near)
            if r[1] < 0.6:
                w = (56 + 30 * r[2]) * g.u
                h = (170 + 40 * r[3]) * g.u
                c.rect(x, by - 22 * g.u - h, w, h, col, r=8)
                c.rect(x + 8 * g.u, by - 22 * g.u - h + 24 * g.u, w - 16 * g.u, 40 * g.u, p.deep if col != p.far else p.near, r=5, alpha=0.5)
                x += w + 5 * g.u
            else:
                w = (120 + 60 * r[2]) * g.u
                h = (110 + 30 * r[3]) * g.u
                c.rect(x, by - 22 * g.u - h, w, h, col, r=10)
                c.rect(x + w * 0.3, by - 22 * g.u - h + 24 * g.u, w * 0.4, 16 * g.u, p.deep, r=8, alpha=0.5)
                x += w + 14 * g.u
            if r[4] > 0.7:
                x += (40 + 120 * r[5]) * g.u
            k += 1
        c.rect(g.x0, by - 22 * g.u, g.w, 22 * g.u, p.mid, r=6)
    _floor(c, g, p)
    lx = (0.88 if g.portrait else 0.92) * g.W
    with c.tf(rot=-7, px=lx, py=g.floor):
        for s in (-1, 1):
            c.rect(lx + s * 60 * g.u - 10 * g.u, g.floor - 0.62 * g.H, 20 * g.u, 0.62 * g.H, p.near, r=10)
        y = g.floor - 60 * g.u
        while y > g.floor - 0.6 * g.H:
            c.rect(lx - 60 * g.u, y - 7 * g.u, 120 * g.u, 14 * g.u, p.near, r=7)
            y -= 80 * g.u
    sx = g.cx + 0.3 * g.W * math.sin(TWO_PI * t / 24.0 + seed)
    _light(c, sx, 0.5 * g.H, 0.45 * g.W, p.light, 0.1 * L)
    _dust(c, g, p, t, seed, kw, n=14, alpha=0.3 * L)


@backdrop('stage', 'theatre', 'theater', theme='curious')
def _stage(c, g, p, t, seed, kw):
    """Bühne: Vorhänge links und rechts mit Falten (near/mid, runder Saum), Lambrequin oben mit Bogensaum, dunkler
    Bühnenboden mit sieben Rampenlichtern (glow, atmen 0.3 Hz versetzt), Spot von oben, der langsam schwenkt (0.06 Hz)."""
    L = _L(p, kw)
    _floor(c, g, p)
    ang = 4.0 * math.sin(TWO_PI * 0.06 * t + seed)
    src = g.y0 - 100
    with c.tf(rot=ang, px=g.cx, py=src):
        _cone(c, g.cx, src, g.floor + 60, 80 * g.u, 0.6 * g.W, p.light, 0.14 * L)
    _light(c, g.cx + math.tan(math.radians(ang)) * (g.floor - src), g.floor + 10, 0.34 * g.W, p.light, 0.2 * L, squash=0.26)
    cw = (0.24 if g.portrait else 0.18) * g.W
    fold = 70 * g.u
    for side in (0, 1):
        x = g.x0 if side == 0 else g.W - cw
        end = cw if side == 0 else g.x1
        k = 0
        while x < end:
            col = p.near if k % 2 == 0 else p.mid
            c.rrect_mixed(x, g.y0, fold, g.floor + 40 * g.u - g.y0, (0, 0, fold / 2, fold / 2), col)
            x += fold
            k += 1
    vh = 0.13 * g.H
    scal = P_rrect(g.x0, g.y0, g.w, vh + OVER, 0)
    x = g.x0 + 50 * g.u
    while x < g.x1:
        scal.addCircle(x, vh + OVER - OVER, 52 * g.u)
        x += 104 * g.u
    c.path(scal, p.near)
    c.rect(g.x0, vh + 40 * g.u, g.w, 24 * g.u, p.mid, r=8)
    n = 7
    for i in range(n):
        x = g.W * (i + 0.5) / n
        br = 0.5 + 0.5 * math.sin(TWO_PI * 0.3 * t + i * 0.9)
        c.circle(x, g.floor + 22 * g.u, 12 * g.u, p.light, (0.6 + 0.3 * br) * L)
        _light(c, x, g.floor + 14 * g.u, 140 * g.u, p.light, (0.08 + 0.05 * br) * L, squash=0.5)


@backdrop('road', 'street', theme='heist')
def _road(c, g, p, t, seed, kw):
    """Straße bei Nacht: ferne Skyline (far), Bordstein (mid), Fahrbahn (deep) mit Mittelstreifen (far), Laterne mit
    Lichtkegel (alpha 0.16) und Schein, der sanft atmet (0.25 Hz), Verkehrsschild, Mond, eine Wolke zieht."""
    L = _L(p, kw)
    mx, my = g.sky
    _sun(c, g, p, mx, my, 60 * g.u, 0.9, 0.16, math.sin(TWO_PI * 0.05 * t))
    cx_ = g.x0 + ((0.3 * g.W + 14 * t) % (g.w + 400)) - 200
    c.path(P_cloud(cx_, 0.12 * g.H, 150 * g.u), p.far)
    _skyline(c, g, p.far, g.floor - 40 * g.u, 0.12 * g.H, 0.3 * g.H, 110 * g.u, 220 * g.u, seed + 41, gap=12)
    c.rect(g.x0, g.floor - 40 * g.u, g.w, 40 * g.u, p.mid)
    _floor(c, g, p)
    y = g.floor + (0.08 * g.H if g.portrait else 0.1 * g.H)
    x = g.x0 + (seed * 37) % 190
    while x < g.x1:
        c.rect(x, y - 8 * g.u, 110 * g.u, 16 * g.u, p.far, r=8)
        x += 200 * g.u
    sx_ = (0.05 if g.portrait else 0.3) * g.W
    c.rect(sx_ - 10 * g.u, g.floor - 300 * g.u, 20 * g.u, 260 * g.u, p.mid, r=10)
    c.rect(sx_ - 60 * g.u, g.floor - 380 * g.u, 120 * g.u, 120 * g.u, p.mid, r=24)
    lx = (0.76 if g.portrait else 0.68) * g.W
    ph = 0.4 * g.H
    breath = 0.9 + 0.1 * math.sin(TWO_PI * 0.25 * t + seed)
    c.rect(lx - 13 * g.u, g.floor - 40 * g.u - ph, 26 * g.u, ph, p.near, r=13 * g.u)
    arm_dir = -1 if lx > g.cx else 1
    ax = lx + arm_dir * 150 * g.u
    c.rect(min(lx, ax), g.floor - 40 * g.u - ph - 11 * g.u, 150 * g.u, 22 * g.u, p.near, r=11)
    c.rect(ax - 50 * g.u, g.floor - 40 * g.u - ph - 30 * g.u, 100 * g.u, 44 * g.u, p.near, r=22)
    c.circle(ax, g.floor - 40 * g.u - ph + 10 * g.u, 16 * g.u, p.light, 0.9 * L * breath)
    _cone(c, ax, g.floor - 40 * g.u - ph + 10 * g.u, g.floor + 120 * g.u, 90 * g.u, 0.5 * g.W, p.light, 0.16 * L * breath)
    _light(c, ax, g.floor + 60 * g.u, 0.3 * g.W, p.light, 0.18 * L * breath, squash=0.3)


@backdrop('sky_day', 'sky', 'day', theme='animal')
def _sky_day(c, g, p, t, seed, kw):
    """Taghimmel: heller Verlauf zum Horizont (bg1 -> foam-Mischung), Sonne mit atmendem Hof, drei Wolkenschichten (foam,
    alpha gestaffelt), die unterschiedlich schnell ziehen, zwei Hügelzüge am Boden."""
    L = _L(p, kw)
    _base(c, g, p, p.bg1, CO.hexs(CO.mix(p.bg1, p.foam, 0.28)))
    sx, sy = g.sky
    _sun(c, g, p, sx, sy, 90 * g.u, 0.9, 0.26, math.sin(TWO_PI * 0.05 * t))
    R = _rand(seed + 43, 30)
    for li, (n, spd, alpha, smin, smax, ymin, ymax) in enumerate(((5, 8.0, 0.16, 70, 110, 0.05, 0.4), (4, 14.0, 0.22, 110, 160, 0.08, 0.45), (3, 22.0, 0.3, 150, 220, 0.12, 0.5))):
        for i in range(n):
            r = R[(li * 6 + i) % 30]
            span = g.w + 600 * g.u
            x = g.x0 - 300 * g.u + ((r[0] * span + spd * t) % span)
            y = (ymin + (ymax - ymin) * r[1]) * g.H
            c.path(P_cloud(x, y, (smin + (smax - smin) * r[2]) * g.u), p.foam, alpha)
    _hills(c, g, g.floor - 0.03 * g.H, 0.04 * g.H, 0.9 * g.W, p.mid, seed + 1)
    _hills(c, g, g.floor + 0.04 * g.H, 0.03 * g.H, 0.6 * g.W, p.near, seed + 2, phase=1.9)


@backdrop('storm', 'rain', 'thunder', theme='heist')
def _storm(c, g, p, t, seed, kw):
    """Gewitter: aufgehellter Himmel (bg1/bg2-Mischung) über dunklem Grund, schwere Wolken (deep) ziehen, 40 Regenfäden
    (ink_soft), ein Baum biegt sich im Wind (0.3 Hz), alle 7 s ein Blitz (0.18 s) mit weichem Aufhellen."""
    L = _L(p, kw)
    _base(c, g, p, CO.hexs(CO.mix(p.bg2, p.soft, 0.08)), p.bg0)
    R = _rand(seed + 47, 20)
    _hills(c, g, g.floor - 0.06 * g.H, 0.04 * g.H, 0.9 * g.W, p.deep, seed + 1)
    tx = (0.84 if g.portrait else 0.88) * g.W
    bend = 4.0 * (0.5 + 0.5 * math.sin(TWO_PI * 0.3 * t + seed)) + 2.0 * math.sin(TWO_PI * 0.13 * t)
    with c.tf(rot=-bend, px=tx, py=g.floor):
        _tree(c, tx, g.floor - 0.02 * g.H, 0.3 * g.H, p.deep, t, seed + 9)
    _floor(c, g, p, color=p.bg0)
    for i in range(6):
        r = R[i]
        span = g.w + 600 * g.u
        x = g.x0 - 300 * g.u + ((r[0] * span + (10 + 10 * r[1]) * t) % span)
        y = (0.02 + 0.14 * r[2]) * g.H
        c.path(P_cloud(x, y, (220 + 140 * r[3]) * g.u), p.deep)
    period = 7.0
    u = ((t + seed * 0.3) % period) / 0.18
    if u < 1.0:
        bx = 0.3 * g.W if g.portrait else 0.35 * g.W
        pts = [(bx, 0.1 * g.H), (bx - 40 * g.u, 0.22 * g.H), (bx + 30 * g.u, 0.3 * g.H), (bx - 30 * g.u, 0.42 * g.H), (bx + 20 * g.u, 0.52 * g.H)]
        c.fill(p.light, 0.1 * (1 - u) * L)
        c.polyline(pts, p.light, 16 * g.u, 0.9 * (1 - u * u) * L, join='round')
        c.polyline(pts, p.light, 60 * g.u, 0.25 * (1 - u) * L, blur=24, blend='add')
    _dust(c, g, p, t, seed, kw, n=40, alpha=0.4, kind='rain', color=p.soft, speed=1.0, size=1.6)


@backdrop('dungeon', 'prison', theme='crime')
def _dungeon(c, g, p, t, seed, kw):
    """Kerker: Steinwand aus versetzten Quadern (far/mid), Bogenfenster mit Gitter und fahlem Lichtfächer, Wandfackel mit
    Flamme (Blob, glow/candle) und flackerndem Schein (2 Hz, weich), Ketten, Bodenplatten, 10 Staubteilchen."""
    L = _L(p, kw)
    R = _rand(seed + 53, 400)
    bw, bh, gap = 190 * g.u, 84 * g.u, 12 * g.u
    y = g.y0
    row = 0
    while y < g.floor:
        x = g.x0 - (bw / 2 if row % 2 else 0)
        k = 0
        while x < g.x1:
            r = R[(row * 29 + k) % 400]
            if r[0] > 0.08:
                c.rect(x, y, bw, bh, p.mid if r[1] > 0.72 else p.far, r=12)
            x += bw + gap
            k += 1
        y += bh + gap
        row += 1
    _floor(c, g, p)
    x = g.x0
    while x < g.x1:
        c.rect(x, g.floor + 10, 220 * g.u, 60 * g.u, p.far, r=10, alpha=0.5)
        x += 236 * g.u
    wx, wy = (0.7 * g.W, 0.27 * g.H) if g.portrait else (0.72 * g.W, 0.26 * g.H)
    ww, wh = 190 * g.u, 280 * g.u
    c.path(P_arch(wx - ww / 2 - 20 * g.u, wy - wh / 2 - 20 * g.u, ww + 40 * g.u, wh + 40 * g.u), p.near)
    c.path(P_arch(wx - ww / 2, wy - wh / 2, ww, wh), p.bg0)
    for k in range(3):
        c.rect(wx - 8 * g.u + (k - 1) * 56 * g.u, wy - wh / 2 + 10, 16 * g.u, wh - 20, p.mid, r=8)
    _cone(c, wx, wy + wh / 2, g.floor + 40, ww, 2.2 * ww, p.foam, 0.05 * L, blur=30, tail=0.0, skew=-200 * g.u)
    fx_, fy_ = (0.52 * g.W, 0.33 * g.H) if g.portrait else (0.5 * g.W, 0.36 * g.H)
    flick = 0.5 + 0.5 * math.sin(TWO_PI * 2.0 * t + seed) * 0.6 + 0.4 * math.sin(TWO_PI * 1.3 * t)
    c.rect(fx_ - 12 * g.u, fy_, 24 * g.u, 120 * g.u, p.near, r=12)
    c.rect(fx_ - 30 * g.u, fy_ + 50 * g.u, 60 * g.u, 20 * g.u, p.near, r=10)
    c.rect(fx_ - 22 * g.u, fy_ - 10 * g.u, 44 * g.u, 30 * g.u, p.mid, r=10)
    _light(c, fx_, fy_ - 40 * g.u, 0.42 * g.W, p.light, (0.13 + 0.04 * flick) * L)
    c.blob(fx_, fy_ - 40 * g.u, 32 * g.u, p.light, n=6, wob=0.2, seed=seed + 1, t=t, speed=1.1, alpha=0.95 * L)
    c.blob(fx_, fy_ - 28 * g.u, 16 * g.u, p.candle, n=6, wob=0.2, seed=seed + 3, t=t, speed=1.3, alpha=0.95 * L)
    for cxk in (0.06 * g.W, 0.94 * g.W):
        yy = 0.18 * g.H
        for k in range(6):
            if k % 2 == 0:
                c.rect(cxk - 12 * g.u, yy, 24 * g.u, 44 * g.u, p.near, r=12)
            else:
                c.rect(cxk - 8 * g.u, yy - 6 * g.u, 16 * g.u, 50 * g.u, p.mid, r=8)
            yy += 40 * g.u
    _dust(c, g, p, t, seed, kw, n=10, alpha=0.25 * L)


@backdrop('kitchen', 'cook', theme='food')
def _kitchen(c, g, p, t, seed, kw):
    """Küche: Fliesenspiegel (far), Hängeleiste mit Pfanne, Kelle und Schneebesen (near/mid, wiegen 0.15 Hz), Arbeitsplatte
    mit Schranktüren, Topf mit Deckel, aus dem Dampf aufsteigt (3-s-Schleife), Pendellampe mit weichem Licht."""
    L = _L(p, kw)
    dado = 0.5 * g.H if g.portrait else 0.48 * g.H
    _tiles(c, g, p.far, 96 * g.u, 8 * g.u, 0.16 * g.H, dado, alpha=0.8)
    c.rect(g.x0, dado, g.w, 24 * g.u, p.mid, r=6)
    _floor(c, g, p)
    top = g.floor - 190 * g.u
    c.rect(g.x0, top, g.w, 190 * g.u + 10, p.mid)
    c.rect(g.x0, top - 28 * g.u, g.w, 28 * g.u, p.near, r=8)
    x = g.x0 + 20 * g.u
    while x < g.x1:
        c.rect(x, top + 30 * g.u, 200 * g.u, 140 * g.u, p.far, r=12)
        c.rect(x + 86 * g.u, top + 50 * g.u, 28 * g.u, 28 * g.u, p.mid, r=8)
        x += 224 * g.u
    px = (0.56 if g.portrait else 0.58) * g.W
    py = top - 28 * g.u
    c.rect(px - 120 * g.u, py - 150 * g.u, 240 * g.u, 150 * g.u, p.near, r=24)
    c.rect(px - 150 * g.u, py - 120 * g.u, 36 * g.u, 22 * g.u, p.near, r=10)
    c.rect(px + 114 * g.u, py - 120 * g.u, 36 * g.u, 22 * g.u, p.near, r=10)
    c.rect(px - 130 * g.u, py - 176 * g.u, 260 * g.u, 30 * g.u, p.mid, r=14)
    c.circle(px, py - 186 * g.u, 14 * g.u, p.mid)
    for k in range(3):
        u = ((t / 3.0 + k * 0.33 + seed * 0.1) % 1.0)
        sy = py - 190 * g.u - u * 260 * g.u
        sx = px + (k - 1) * 40 * g.u + 24 * g.u * math.sin(TWO_PI * (u * 0.8 + k))
        c.circle(sx, sy, (22 + 30 * u) * g.u, p.foam, 0.16 * (1 - u) * L, blur=18 * g.u)
    rail_y = 0.19 * g.H
    rx0, rx1 = (0.1 * g.W, 0.6 * g.W) if g.portrait else (0.3 * g.W, 0.72 * g.W)
    c.rect(rx0, rail_y - 10 * g.u, rx1 - rx0, 20 * g.u, p.near, r=10)
    sway = 2.0 * math.sin(TWO_PI * 0.15 * t + seed)
    hooks = [(0.2, 'pan'), (0.5, 'ladle'), (0.8, 'whisk')]
    for i, (a, kind) in enumerate(hooks):
        hx = rx0 + a * (rx1 - rx0)
        with c.tf(rot=sway * (1 if i % 2 == 0 else -1), px=hx, py=rail_y):
            if kind == 'pan':
                c.rect(hx - 9 * g.u, rail_y, 18 * g.u, 120 * g.u, p.mid, r=9)
                c.circle(hx, rail_y + 170 * g.u, 60 * g.u, p.near)
            elif kind == 'ladle':
                c.rect(hx - 8 * g.u, rail_y, 16 * g.u, 150 * g.u, p.mid, r=8)
                with c.clip_rect(hx - 50 * g.u, rail_y + 150 * g.u, 100 * g.u, 40 * g.u):
                    c.ellipse(hx, rail_y + 150 * g.u, 44 * g.u, 36 * g.u, p.near)
            else:
                c.rect(hx - 8 * g.u, rail_y, 16 * g.u, 90 * g.u, p.mid, r=8)
                c.ellipse(hx, rail_y + 150 * g.u, 34 * g.u, 64 * g.u, p.near)
    lx = 0.78 * g.W if g.portrait else 0.86 * g.W
    c.rect(lx - 7 * g.u, g.y0, 14 * g.u, 0.1 * g.H + OVER, p.near, r=7)
    c.path(rounded_poly_path([(lx - 30 * g.u, 0.1 * g.H), (lx + 30 * g.u, 0.1 * g.H), (lx + 90 * g.u, 0.1 * g.H + 60 * g.u), (lx - 90 * g.u, 0.1 * g.H + 60 * g.u)], 10), p.near)
    c.circle(lx, 0.1 * g.H + 62 * g.u, 18 * g.u, p.light, 0.9 * L)
    _light(c, lx, 0.1 * g.H + 90 * g.u, 0.36 * g.W, p.light, 0.12 * L)


@backdrop('bank_hall', 'bank', theme='heist')
def _bank_hall(c, g, p, t, seed, kw):
    """Schalterhalle: Säulen mit Kapitell (far), hohe Bogenfenster (mid) mit heller Scheibe und Lichtfächern, die atmen
    (0.04 Hz versetzt), Schaltertresen (near) mit Ablage, Wanduhr mit laufendem Zeiger, Bodenfliesen, 12 Staubteilchen."""
    L = _L(p, kw)
    bay = (0.32 if g.portrait else 0.22) * g.W
    nb = int(g.w / bay) + 2
    wtop = 0.12 * g.H
    wh = (0.3 if g.portrait else 0.36) * g.H
    ww = 0.5 * bay
    for j in range(nb):
        x = g.x0 + j * bay + bay / 2
        wx = x - ww / 2
        c.path(P_arch(wx, wtop, ww, wh), p.mid)
        c.path(P_arch(wx + 18 * g.u, wtop + 18 * g.u, ww - 36 * g.u, wh - 36 * g.u), p.pane)
        c.rect(wx, wtop + wh * 0.5, ww, 16 * g.u, p.mid, r=6)
        c.rect(x - 8 * g.u, wtop, 16 * g.u, wh, p.mid, r=6)
        pulse = 0.5 + 0.5 * math.sin(TWO_PI * 0.04 * t + j * 1.4 + seed)
        _cone(c, x, wtop + wh, g.floor + 60, ww, 1.5 * ww, p.light, (0.03 + 0.04 * pulse) * L, blur=30, tail=0.0, skew=-0.3 * bay)
    for j in range(nb):
        x = g.x0 + j * bay
        c.rect(x - 45 * g.u, g.y0, 90 * g.u, g.floor - g.y0 + 10, p.far)
        c.rect(x - 64 * g.u, wtop - 60 * g.u, 128 * g.u, 40 * g.u, p.far, r=10)
        c.rect(x - 64 * g.u, g.floor - 40 * g.u, 128 * g.u, 40 * g.u, p.far, r=10)
    _floor(c, g, p)
    x = g.x0
    k = 0
    while x < g.x1:
        c.rect(x, g.floor + 12, 150 * g.u, 50 * g.u, p.far, r=8, alpha=0.5 if k % 2 == 0 else 0.25)
        x += 158 * g.u
        k += 1
    cw = 0.7 * g.W if g.portrait else 0.5 * g.W
    ccx = g.cx if g.portrait else 0.62 * g.W
    c.rect(ccx - cw / 2, g.floor - 170 * g.u, cw, 170 * g.u + 10, p.near, r=16)
    c.rect(ccx - cw / 2 - 16 * g.u, g.floor - 194 * g.u, cw + 32 * g.u, 28 * g.u, p.mid, r=12)
    x = ccx - cw / 2 + 40 * g.u
    while x < ccx + cw / 2 - 80 * g.u:
        c.rect(x, g.floor - 140 * g.u, 90 * g.u, 90 * g.u, p.mid, r=10)
        x += 150 * g.u
    kx, ky = g.cx, 0.07 * g.H
    c.circle(kx, ky, 56 * g.u, p.near)
    c.circle(kx, ky, 44 * g.u, p.far)
    with c.tf(rot=(t * 6.0) % 360, px=kx, py=ky):
        c.rect(kx - 7 * g.u, ky - 36 * g.u, 14 * g.u, 44 * g.u, p.near, r=7)
    with c.tf(rot=(t * 0.5 + seed * 30) % 360, px=kx, py=ky):
        c.rect(kx - 7 * g.u, ky - 24 * g.u, 14 * g.u, 32 * g.u, p.near, r=7)
    _dust(c, g, p, t, seed, kw, n=12, alpha=0.28 * L, area=(g.x0, wtop, g.w, g.floor - wtop))


# ================================================================ Bogen

def _guides(c, fmt, th):
    """Layout-Hilfen über einer Kulisse: Bühne, Odd (Bodenpunkt), Hero-Feld und Untertitel-Band (nur zur Prüfung)."""
    g = Geo(fmt)
    st = fmt.stage
    col = th.get('line', '#FFFFFF')
    c.rect(st.x, st.y, st.w, st.h, col, alpha=0.25, stroke=4, r=12)
    hx, hy = g.hero
    hs = 300 if fmt.portrait else 360
    c.rect_c(hx, hy, hs, hs, col, r=48, alpha=0.3, stroke=4)
    ox, oy = g.odd
    osz = 400 if fmt.portrait else 320
    c.rect_c(ox, oy - osz / 2, osz * 0.9, osz, col, r=48, alpha=0.3, stroke=4)
    cp = fmt.caption
    c.rect(cp.x, cp.y, cp.w, cp.h, col, alpha=0.25, stroke=4, r=28)


def sheet(out_path: str, scale: float = 0.3, cols: int = 6, t: float = 1.3, guides: bool = False, landscape: bool = True, mascot: bool = False) -> str:
    """Übersichtsbogen: alle Kulissen als Hochformat-Kacheln (verkleinert, beschriftet mit Name, Thema und Kurztext), darunter
    dieselben Kulissen im Querformat (kleiner), damit beide Kompositionen geprüft werden können. guides=True legt die
    Layout-Anker darüber, mascot=True stellt Odd und einen Hero-Platzhalter hinein (Prüfung der Ruhe unter Stickern)."""
    from .canvas import Frame
    from . import layout as LAY
    ns = names()
    pf, lf = LAY.get_format('portrait'), LAY.get_format('landscape')
    pad, label_h, top = 24, 70, 150
    tw, th_ = pf.W * scale, pf.H * scale
    rows = (len(ns) + cols - 1) // cols
    ls = scale * 0.64
    lw, lh = lf.W * ls, lf.H * ls
    lcols = max(1, int((cols * (tw + pad) - pad) // (lw + pad)))
    lrows = (len(ns) + lcols - 1) // lcols if landscape else 0
    W = int(cols * (tw + pad) + pad)
    H = int(top + rows * (th_ + label_h + pad) + (60 + lrows * (lh + label_h * 0.6 + pad) if landscape else 0) + pad)
    fr = Frame(W, H)
    c = fr.c
    base = TH.get('curious')
    c.gradient_bg('#14101F', '#0E0B16')
    c.text('KULISSEN · backdrops', 40, 72, F.font('display', 56, weight=800), base['ink'])
    c.text(f'{len(ns)} kulissen · hochformat 1080 x 1920 (x {scale:.2f}) · querformat 1920 x 1080 (x {ls:.2f}) · t = {t:.1f} s · silhouetten in bg2-stufen, licht additiv, korn 0.045',
           40, 112, F.font('mono', 20), base['ink_soft'])
    f_name, f_small = F.font('display', 26, weight=800), F.font('mono', 15)

    def tile(name, fmt, x, y, sc, tt):
        th = TH.get(SHEET_THEME.get(name, 'curious'))
        with c.clip_rect(x, y, fmt.W * sc, fmt.H * sc, r=18):
            with c.tf(x=x, y=y, sx=sc):
                draw(c, name, fmt, tt, th)
                if mascot:
                    _mascot_probe(c, fmt, th, tt)
                if guides:
                    _guides(c, fmt, th)
        return th

    for i, n in enumerate(ns):
        x = pad + (i % cols) * (tw + pad)
        y = top + (i // cols) * (th_ + label_h + pad)
        th = tile(n, pf, x, y, scale, t + i * 0.7)
        c.text(n, x + 4, y + th_ + 30, f_name, th['ink'])
        c.text(SHEET_THEME.get(n, 'curious'), x + tw - 4, y + th_ + 30, f_small, th['accent'], 'right', 'middle')
        c.text(_fit_text(c, DOC.get(n, ''), f_small, tw - 8), x + 4, y + th_ + 56, f_small, base['ink_soft'])
    if landscape:
        y0 = top + rows * (th_ + label_h + pad) + 20
        c.text('QUERFORMAT 1920 x 1080', 40, y0 + 10, F.font('mono', 20), base['ink_soft'], 'left', 'middle')
        for i, n in enumerate(ns):
            x = pad + (i % lcols) * (lw + pad)
            y = y0 + 40 + (i // lcols) * (lh + label_h * 0.6 + pad)
            th = tile(n, lf, x, y, ls, t + i * 0.7)
            c.text(n, x + 4, y + lh + 24, F.font('display', 20, weight=800), th['ink'])
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    fr.save_png(out_path)
    return out_path


def _fit_text(c, s, f, max_w):
    """Kürzt s mit Auslassungspunkten, bis es in max_w passt."""
    s = s.replace('\n', ' ')
    while s and c.text_width(s, f) > max_w:
        s = s[:-2].rstrip() + '…'
    return s


def _mascot_probe(c, fmt, th, t):
    """Odd und ein Hero-Platzhalter (Sticker) an den Layout-Ankern, nur für den Prüfbogen."""
    try:
        from . import mascot as M
    except Exception:
        return
    g = Geo(fmt)
    hx, hy = g.hero
    hs = 300 if fmt.portrait else 360
    c.sticker(lambda cc: cc.rect_c(hx, hy, hs * 0.8, hs * 0.8, th['accent'], r=48), rim=10)
    ox, oy = g.odd
    M.draw(c, ox, oy, 400 if fmt.portrait else 320, t, pose='idle', costume=M.costume_for(th.get('name', 'curious')), theme=th)
