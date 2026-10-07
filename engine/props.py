"""Piktogramm-Repertoire („Peel & Pop“, STIL.md Abschnitt 7): flache Sticker aus Kreisen, Ellipsen, Rechtecken und Pfaden.

Jedes Piktogramm ist eine Funktion fn(c, p, s, t, kw), die um den Ursprung (0, 0) zeichnet; s = größte Ausdehnung in px,
p = Palette des Themas (nur Themenfarben, keine eigenen HEX-Werte), t = Zeit für genau eine Eigenbewegung (schweben,
wippen, funkeln, drehen, tropfen). Zwei-Ton-Flat über tone(): Grundfarbe, harte Schattenfläche (-12 %) rechts unten,
Glanzpunkt (+10 %) oben links, der bei 1.3 Hz funkelt. Keine Linien innen, keine Verläufe.

draw() legt Verschiebung, Drehung, Pop-Skalierung (k) und die Sticker-Technik darum: Schatten (dy 8, sigma 16, alpha 0.20)
-> weißer Rand (10 px) -> Farbe. mode='color' zeichnet nur die Farbe, 'rim' nur den Rand, 'silhouette' alles in einer Farbe.
Unbekannte Namen zeichnen eine neutrale Fragezeichen-Karte, nie einen Fehler.
"""
from __future__ import annotations
import math
import os
import skia
from . import anim as A
from . import fonts as F
from . import theme as TH
from . import color as CO
from .canvas import rounded_poly_path, smooth_path

PROPS: dict = {}        # name -> fn(c, p, s, t, kw)
HULLS: dict = {}        # name -> (w, h) relativ zu s (Hüllform für Marks und Sichtprüfung)
ALIASES: dict = {}      # alias -> name

RIM = 10.0              # Sticker-Rand der Piktogramme (STIL.md 1.2)
SHADOW = (8.0, 16.0, 0.20)
TWO_PI = 2 * math.pi


def prop(name, *aliases, hull=(1.0, 1.0)):
    """Registriert eine Zeichenfunktion unter name (und Aliasnamen) mit relativer Hüllform (w, h)."""
    def deco(fn):
        PROPS[name] = fn
        HULLS[name] = hull
        for a in aliases:
            PROPS[a] = fn
            HULLS[a] = hull
            ALIASES[a] = name
        return fn
    return deco


class Pal:
    """Kurznamen der Themenfarben für die Piktogramme (alle aus theme.get, siehe STIL.md 3)."""

    def __init__(self, th):
        g = th.get
        self.accent = g('accent', '#F2B544')
        self.accent2 = g('accent2', '#5FD9B8')
        self.glow = g('glow') or g('ink', '#F7F1E6')
        self.ink = g('ink', '#F7F1E6')          # Elfenbein
        self.soft = g('ink_soft', '#C9C2D6')
        self.dark = g('card_ink', '#171A28')    # Tinte
        self.bg2 = g('bg2', '#41336C')
        self.white = g('line', '#FFFFFF')       # nur Rand, Augenweiß, Glanz
        self.danger = g('danger', '#F0634A')
        self.ok = g('ok', '#5FD9B8')
        self.wood = g('wood', '#8E6F52')
        self.steel = g('steel', '#9AA3B2')
        self.skin = g('skin', '#E8C9A8')
        self.paper = g('paper', '#EAD9B8')
        self.chalk = g('chalk', '#E9E4DA')
        self.foam = g('foam', '#DDF3F5')
        self.water = g('water', '#5FD3F2')
        self.candle = g('candle', '#FFD8A0')
        self.gold = g('gold_old', '#E2B55C')    # Altgold für Münzen/Barren, nie Wunder-Gold
        self.rock = CO.hexs(CO.mix(self.steel, self.bg2, 0.55))
        self.steel_dark = CO.hexs(CO.darken(self.steel, 0.3))
        self.wood_dark = CO.hexs(CO.darken(self.wood, 0.25))
        self.respect = bool(g('respect_mode'))


# ---------------------------------------------------------------- Pfade

def P_circle(x, y, r):
    p = skia.Path(); p.addCircle(float(x), float(y), float(max(0.0, r))); return p


def P_oval(x, y, rx, ry):
    p = skia.Path(); p.addOval(skia.Rect.MakeLTRB(x - rx, y - ry, x + rx, y + ry)); return p


def P_rrect(x, y, w, h, r=0.0):
    """Abgerundetes Rechteck um den Mittelpunkt (x, y)."""
    p = skia.Path()
    rect = skia.Rect.MakeXYWH(x - w / 2, y - h / 2, w, h)
    if r > 0:
        p.addRoundRect(rect, float(r), float(r))
    else:
        p.addRect(rect)
    return p


def P_rrect4(x, y, w, h, radii):
    """Rechteck mit Rundung je Ecke (tl, tr, br, bl)."""
    rr = skia.RRect()
    tl, tr, br, bl = radii
    rr.setRectRadii(skia.Rect.MakeXYWH(x - w / 2, y - h / 2, w, h), [(tl, tl), (tr, tr), (br, br), (bl, bl)])
    p = skia.Path(); p.addRRect(rr); return p


def P_poly(pts, r=0.0):
    """Polygon, optional mit abgerundeten Ecken."""
    if r > 0:
        return rounded_poly_path(pts, r)
    p = skia.Path()
    p.moveTo(float(pts[0][0]), float(pts[0][1]))
    for x, y in pts[1:]:
        p.lineTo(float(x), float(y))
    p.close()
    return p


def P_smooth(pts, tension=0.5, closed=True):
    return smooth_path(pts, tension, closed)


def P_pie(x, y, r, a0, a1):
    p = skia.Path()
    p.moveTo(x, y)
    p.arcTo(skia.Rect.MakeLTRB(x - r, y - r, x + r, y + r), float(a0), float(a1 - a0), False)
    p.close()
    return p


def P_union(*paths):
    out = paths[0]
    for q in paths[1:]:
        r = skia.Op(out, q, skia.PathOp.kUnion_PathOp)
        out = r if r is not None else out
    return out


def P_diff(a, b):
    r = skia.Op(a, b, skia.PathOp.kDifference_PathOp)
    return r if r is not None else a


def P_inter(a, b):
    r = skia.Op(a, b, skia.PathOp.kIntersect_PathOp)
    return r if r is not None else a


def P_rot(path, deg, px=0.0, py=0.0):
    q = skia.Path(path)
    m = skia.Matrix()
    m.setRotate(float(deg), float(px), float(py))
    q.transform(m)
    return q


def P_move(path, dx, dy):
    q = skia.Path(path); q.offset(float(dx), float(dy)); return q


def P_heart(x, y, w):
    """Herz aus zwei Kreisen und einer abgerundeten Spitze, Breite w."""
    r = w * 0.26
    top = P_union(P_circle(x - r, y - w * 0.14, r), P_circle(x + r, y - w * 0.14, r))
    tip = P_poly([(x - w * 0.5, y - w * 0.12), (x + w * 0.5, y - w * 0.12), (x, y + w * 0.46)], w * 0.06)
    return P_union(top, tip)


def P_drop(x, y, w, h):
    """Tropfen: Kreis unten, abgerundete Spitze oben; Mittelpunkt (x, y), Breite w, Höhe h."""
    r = w / 2
    cy = y + h / 2 - r
    body = P_circle(x, cy, r)
    tip = P_poly([(x, y - h / 2), (x + r * 0.98, cy - r * 0.2), (x - r * 0.98, cy - r * 0.2)], w * 0.10)
    return P_union(body, tip)


def P_star(x, y, r_out, r_in, n=5, rot=-90.0, r_corner=0.0):
    pts = []
    for i in range(n * 2):
        rr = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180.0 / n)
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    return P_poly(pts, r_corner)


# ---------------------------------------------------------------- Zwei-Ton-Flat

def plain(c) -> bool:
    """True im Farbpass; False im Rand-, Schatten- oder Silhouettenpass (dort nur Grundformen zeichnen)."""
    return c._over is None


def tone(c, path, color, s, t, shade=True, shine=True, ph=0.0, alpha=1.0, shine_at=None):
    """Fläche in Zwei-Ton-Flat (STIL.md 1.2): Grundfarbe, Schattenfläche -12 % um 6 % von s nach rechts unten (geclippt),
    Glanzpunkt-Ellipse 12 % x 7 % von s oben links in +10 %, Alpha 0.6..1.0 funkelnd bei 1.3 Hz. Im Rand-/Schattenpass nur die Fläche."""
    c.path(path, color, alpha)
    if not plain(c) or s < 64:
        return
    b = path.getBounds()
    m = min(b.width(), b.height())
    if shade and m >= 0.12 * s:
        off = min(0.06 * s, m * 0.3)
        with c.clip_path(path):
            c.path(P_move(path, off, off), CO.darken(color, 0.12), alpha)
    if shine and m >= 0.26 * s:
        if shine_at is None:
            ex, ey = b.left() + b.width() * 0.30, b.top() + b.height() * 0.26
        else:
            ex, ey = shine_at
        a = alpha * (0.8 + 0.2 * math.sin(TWO_PI * 1.3 * t + ph))
        with c.clip_path(path):
            c.ellipse(ex, ey, 0.06 * s, 0.035 * s, CO.lighten(color, 0.10), a, rot=-22)


def flat(c, path, color, alpha=1.0):
    """Fläche ohne Zwei-Ton (Details, Löcher, Innenflächen)."""
    c.path(path, color, alpha)


def stroke(c, pts, color, width, closed=False, alpha=1.0):
    """Dicke Rundlinie durch Punkte (mindestens 14 px bei Hero-Größe: width >= 0.05 s)."""
    c.polyline(pts, color, width, alpha, closed=closed)


def curve(c, pts, color, width, closed=False, alpha=1.0, tension=0.5):
    """Weiche dicke Linie durch Punkte."""
    c.path(smooth_path(pts, tension, closed), color, alpha, stroke=width)


def add_glow(c, x, y, r, color, alpha=0.3, sigma=None):
    """Additiver Lichtfleck, nur im Farbpass (Lampen, Flammen, Edelsteine)."""
    if plain(c) and alpha > 0:
        c.glow(x, y, r, color, alpha, sigma)


# ---------------------------------------------------------------- Bewegungen (je Prop genau eine)

def hover(t, ph=0.0, amp=4.0, f=0.5):
    """Schweben: y-Versatz in px bei 0.5 Hz."""
    return amp * math.sin(TWO_PI * f * t + ph)


def rock(t, ph=0.0, amp=3.0, f=0.3):
    """Wippen: Winkel in Grad bei 0.3 Hz."""
    return amp * math.sin(TWO_PI * f * t + ph)


def twinkle(t, ph=0.0, f=1.3):
    """Funkeln 0.6..1.0 bei 1.3 Hz."""
    return 0.8 + 0.2 * math.sin(TWO_PI * f * t + ph)


def breathe(t, ph=0.0, amp=0.015, f=0.4):
    return 1.0 + amp * math.sin(TWO_PI * f * t + ph)


def _phase(name: str, seed) -> float:
    h = sum((i + 1) * ord(ch) for i, ch in enumerate(name)) % 97
    return 1.7 * float(seed or 0) + h * 0.37


# ---------------------------------------------------------------- Text in Props

def label_font(role, size):
    return F.font(role, size)


# ---------------------------------------------------------------- Öffentliche API

def names() -> list:
    """Alle Piktogrammnamen (ohne Aliasnamen), alphabetisch."""
    return sorted(n for n in PROPS if n not in ALIASES)


def has(name) -> bool:
    return name in PROPS


def hull(name, size) -> tuple:
    """Hüllform (w, h) in px für Schatten-/Markenzwecke."""
    w, h = HULLS.get(name, (1.0, 1.0))
    return (w * size, h * size)


def draw(c, name, x, y, size, t=0.0, theme=None, alpha=1.0, rot=0.0, k=1.0, mode='sticker', rim=RIM, shadow=True, color=None, seed=0, **kw):
    """Zeichnet Piktogramm name mit Mittelpunkt (x, y) und größter Ausdehnung size px.

    t treibt die Eigenbewegung; theme = theme.get(...) (None -> curious); alpha < 1 zeichnet den ganzen Sticker in einer Ebene;
    rot in Grad; k = Pop-Skalierung 0..1 (0 = unsichtbar). mode: 'sticker' (Schatten -> Rand -> Farbe), 'color' (nur Farbe),
    'rim' (nur Rand), 'silhouette' (eine Farbe: color oder ink). rim = Randbreite px, shadow False schaltet den Schatten ab.
    Weitere Schlüssel (text, level, dir, ...) gehen an das Piktogramm. Unbekannte Namen -> Fragezeichen-Karte."""
    if k <= 0.001 or alpha <= 0.0 or size <= 0:
        return
    th = theme if theme is not None else TH.get('curious')
    fn = PROPS.get(name) or _placeholder
    p = Pal(th)
    s = float(size)
    kw = dict(kw)
    kw.setdefault('ph', _phase(name, seed))
    kw.setdefault('seed', seed)

    def body(cc):
        fn(cc, p, s, t, kw)

    def run(cc):
        with cc.tf(x=x, y=y, rot=rot, sx=k, px=0.0, py=0.0):
            hw, hh = hull(name, s)
            cc.mark(-hw / 2, -hh / 2, hw, hh, name, 'sticker')
            if mode == 'silhouette':
                cc.silhouette(body, color or th['ink'])
            elif mode == 'rim':
                with cc.override(th['line'], rim):
                    body(cc)
            elif mode == 'color':
                body(cc)
            else:
                if shadow:
                    dy, sigma, a = SHADOW
                    with cc.tf(y=dy):
                        with cc.override(th.get('shadow', '#000000'), rim, sigma, a):
                            body(cc)
                if rim and rim > 0:
                    with cc.override(th['line'], rim):
                        body(cc)
                body(cc)

    if alpha < 1.0:
        with c.layer(alpha):
            run(c)
    else:
        run(c)


def sheet(out_path: str, theme: str = 'curious', cols: int = 8, size: float = 150, cell=(320, 250), t: float = 0.4) -> str:
    """Übersichtsbogen: jedes Piktogramm als Sticker (size px) und daneben als 120-px-Silhouette (Silhouettentest STIL.md 1.2),
    beschriftet in DM Mono; Lichtrichtung oben links. Rückgabe: Pfad der PNG."""
    from .canvas import Frame
    th = TH.get(theme)
    ns = names()
    cw, ch = cell
    rows = (len(ns) + cols - 1) // cols
    W, H = cols * cw, rows * ch + 90
    fr = Frame(W, H)
    c = fr.c
    c.gradient_bg(th['bg0'], th['bg1'])
    c.text(f"PROPS · {theme.upper()} · {len(ns)} PIKTOGRAMME · STICKER {int(size)} PX + SILHOUETTE 120 PX", 36, 52, F.font('mono', 22), th['ink'], 'left', 'middle', spacing=2)
    fm = F.font('mono', 17)
    for i, n in enumerate(ns):
        x0, y0 = (i % cols) * cw, 90 + (i // cols) * ch
        c.rect(x0 + 8, y0 + 8, cw - 16, ch - 16, th['bg2'], r=24, alpha=0.35)
        hw = max(1.0, HULLS.get(n, (1.0, 1.0))[0])
        draw(c, n, x0 + 104, y0 + 108, size / hw, t + i * 0.37, th, seed=i)
        draw(c, n, x0 + 248, y0 + 108, 120 / hw, t, th, mode='silhouette', color=th['ink'], seed=i)
        c.text(n, x0 + cw / 2, y0 + ch - 30, fm, th['ink_soft'], 'center', 'middle')
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    fr.save_png(out_path)
    return out_path


# ---------------------------------------------------------------- Platzhalter

def _placeholder(c, p, s, t, kw):
    """Neutrale Fragezeichen-Karte für unbekannte Namen (ink_soft, Tinte), wippt leicht."""
    with c.tf(rot=rock(t, kw['ph'])):
        tone(c, P_rrect(0, 0, 0.72 * s, 0.92 * s, 0.08 * s), p.soft, s, t, ph=kw['ph'])
        flat(c, P_poly([(0.36 * s, -0.46 * s), (0.36 * s, -0.24 * s), (0.14 * s, -0.46 * s)]), CO.darken(p.soft, 0.18))
        c.text('?', 0, 0.02 * s, F.font('display', 0.56 * s), p.dark, 'center', 'middle')


# ================================================================ Geld und Beute

@prop('money', hull=(0.96, 0.62))
def _money(c, p, s, t, kw):
    """Geldbündel: zwei Scheine (ok) mit Banderole (Elfenbein) und Siegelkreis; wippt."""
    with c.tf(rot=rock(t, kw['ph'], 3)):
        flat(c, P_rrect(0.05 * s, 0.07 * s, 0.86 * s, 0.46 * s, 0.07 * s), CO.darken(p.ok, 0.22))
        tone(c, P_rrect(0, 0, 0.86 * s, 0.46 * s, 0.07 * s), p.ok, s, t, ph=kw['ph'])
        flat(c, P_rrect(0, 0, 0.26 * s, 0.46 * s), p.ink)
        flat(c, P_circle(0, 0, 0.08 * s), CO.darken(p.ok, 0.12))
        flat(c, P_circle(-0.32 * s, 0, 0.05 * s), CO.darken(p.ok, 0.18))
        flat(c, P_circle(0.32 * s, 0, 0.05 * s), CO.darken(p.ok, 0.18))


@prop('money_bag', hull=(0.78, 0.96))
def _money_bag(c, p, s, t, kw):
    """Beutel (wood) mit Zugband (accent) und Edelstein-Sticker (accent2) statt Dollarzeichen; schwebt."""
    with c.tf(y=hover(t, kw['ph'])):
        body = P_union(P_circle(0, 0.14 * s, 0.36 * s), P_poly([(-0.2 * s, -0.16 * s), (0.2 * s, -0.16 * s), (0.3 * s, 0.1 * s), (-0.3 * s, 0.1 * s)], 0.05 * s))
        tone(c, body, p.wood, s, t, ph=kw['ph'])
        flat(c, P_rrect(0, -0.2 * s, 0.34 * s, 0.1 * s, 0.05 * s), p.accent)
        neck = P_poly([(-0.17 * s, -0.42 * s), (0.17 * s, -0.42 * s), (0.11 * s, -0.22 * s), (-0.11 * s, -0.22 * s)], 0.04 * s)
        tone(c, neck, p.wood, s, t, shine=False, shade=False)
        gem = P_poly([(-0.13 * s, 0.1 * s), (0.13 * s, 0.1 * s), (0.19 * s, 0.2 * s), (0, 0.36 * s), (-0.19 * s, 0.2 * s)], 0.02 * s)
        flat(c, gem, p.accent2)
        if plain(c):
            flat(c, P_poly([(-0.13 * s, 0.1 * s), (0.13 * s, 0.1 * s), (0, 0.2 * s)]), CO.lighten(p.accent2, 0.2), twinkle(t, kw['ph']))


@prop('coin', hull=(0.86, 0.86))
def _coin(c, p, s, t, kw):
    """Münze in Altgold mit Prägering und Stern; dreht sich (Scale-X 0.55..1), die dunkle Kante wird sichtbar."""
    cs = math.cos(TWO_PI * 0.35 * t + kw['ph'])
    ax = 0.55 + 0.45 * abs(cs)
    edge = 0.14 * s * (1 - ax) / 0.45 * (1 if cs >= 0 else -1)
    if abs(edge) > 1:
        with c.tf(x=edge, sx=ax):
            flat(c, P_circle(0, 0, 0.42 * s), CO.darken(p.gold, 0.3))
    with c.tf(sx=ax):
        tone(c, P_circle(0, 0, 0.42 * s), p.gold, s, t, ph=kw['ph'])
        flat(c, P_circle(0, 0, 0.3 * s), CO.darken(p.gold, 0.12))
        flat(c, P_star(0, 0, 0.17 * s, 0.085 * s, 5, -90, 0.015 * s), p.gold)


@prop('gold_bar', hull=(0.96, 0.6))
def _gold_bar(c, p, s, t, kw):
    """Goldbarren (Altgold): Trapez-Front, helle Deckfläche, Prägefeld; schwebt."""
    with c.tf(y=hover(t, kw['ph'])):
        front = P_poly([(-0.46 * s, 0.27 * s), (0.46 * s, 0.27 * s), (0.36 * s, -0.08 * s), (-0.36 * s, -0.08 * s)], 0.03 * s)
        tone(c, front, p.gold, s, t, ph=kw['ph'], shine=False)
        top = P_poly([(-0.36 * s, -0.08 * s), (0.36 * s, -0.08 * s), (0.26 * s, -0.27 * s), (-0.26 * s, -0.27 * s)], 0.03 * s)
        tone(c, top, CO.lighten(p.gold, 0.14), s, t, ph=kw['ph'], shade=False)
        flat(c, P_rrect(0, 0.1 * s, 0.34 * s, 0.14 * s, 0.03 * s), CO.darken(p.gold, 0.14))


@prop('diamond', 'gem', hull=(0.9, 0.86))
def _diamond(c, p, s, t, kw):
    """Edelstein aus Polygon (accent2): Krone, Rundiste, Facetten; funkelt (Glanzstern 1.3 Hz)."""
    w, top, mid, bot = 0.45 * s, -0.36 * s, -0.12 * s, 0.44 * s
    outer = P_poly([(-w * 0.6, top), (w * 0.6, top), (w, mid), (0, bot), (-w, mid)], 0.03 * s)
    tone(c, outer, p.accent2, s, t, ph=kw['ph'], shine=False)
    if plain(c):
        flat(c, P_poly([(-w * 0.6, top), (w * 0.6, top), (w * 0.3, mid), (-w * 0.3, mid)]), CO.lighten(p.accent2, 0.28))
        flat(c, P_poly([(w * 0.6, top), (w, mid), (w * 0.3, mid)]), CO.lighten(p.accent2, 0.12))
        flat(c, P_poly([(-w * 0.6, top), (-w, mid), (-w * 0.3, mid)]), CO.lighten(p.accent2, 0.12))
        flat(c, P_poly([(-w * 0.3, mid), (w * 0.3, mid), (0, bot)]), CO.darken(p.accent2, 0.1))
        a = twinkle(t, kw['ph'])
        sp = P_star(-0.2 * s, -0.3 * s, 0.1 * s * a, 0.03 * s, 4, -90)
        flat(c, sp, p.white, a)
        add_glow(c, 0, 0, 0.5 * s, p.glow, 0.12)


@prop('safe', hull=(0.82, 0.9))
def _safe(c, p, s, t, kw):
    """Tresor: Korpus (steel), Türfeld, Zahlenrad (accent) und Griff; das Rad dreht langsam."""
    tone(c, P_rrect(0, 0, 0.78 * s, 0.86 * s, 0.08 * s), p.steel, s, t, ph=kw['ph'], shine=False)
    flat(c, P_rrect(0, 0, 0.6 * s, 0.68 * s, 0.06 * s), CO.darken(p.steel, 0.2))
    flat(c, P_circle(-0.08 * s, 0, 0.19 * s), p.dark)
    with c.tf(rot=40 * t + kw['ph'] * 10, px=-0.08 * s, py=0):
        flat(c, P_circle(-0.08 * s, 0, 0.14 * s), p.accent)
        flat(c, P_rrect(-0.08 * s, -0.08 * s, 0.05 * s, 0.09 * s, 0.02 * s), p.dark)
    flat(c, P_rrect(0.2 * s, 0, 0.06 * s, 0.3 * s, 0.03 * s), p.dark)
    flat(c, P_rrect(-0.28 * s, 0.47 * s, 0.1 * s, 0.08 * s, 0.03 * s), p.steel_dark)
    flat(c, P_rrect(0.28 * s, 0.47 * s, 0.1 * s, 0.08 * s, 0.03 * s), p.steel_dark)


@prop('vault_door', hull=(0.94, 0.94))
def _vault_door(c, p, s, t, kw):
    """Tresortür: Stahlscheibe mit Bolzenkranz und vierspeichigem Rad (accent); das Rad dreht (öffnen per kw['open'] 0..1)."""
    open_k = float(kw.get('open', 0.0))
    with c.tf(sx=max(0.08, 1 - 0.92 * open_k), px=-0.47 * s, py=0):
        tone(c, P_circle(0, 0, 0.47 * s), p.steel, s, t, ph=kw['ph'], shine=False)
        flat(c, P_circle(0, 0, 0.36 * s), CO.darken(p.steel, 0.22))
        for i in range(8):
            a = math.radians(i * 45 + 22.5)
            flat(c, P_circle(0.415 * s * math.cos(a), 0.415 * s * math.sin(a), 0.035 * s), p.steel_dark)
        with c.tf(rot=30 * t + kw['ph'] * 10):
            for i in range(4):
                flat(c, P_rot(P_rrect(0.15 * s, 0, 0.3 * s, 0.07 * s, 0.035 * s), i * 90), p.accent)
            c.ring(0, 0, 0.27 * s, 0.07 * s, p.accent)
        flat(c, P_circle(0, 0, 0.08 * s), p.accent)


@prop('key', hull=(0.96, 0.4))
def _key(c, p, s, t, kw):
    """Schlüssel (Altgold): Ring mit Loch, Bart mit zwei Zähnen; wippt um die Mitte."""
    with c.tf(rot=rock(t, kw['ph'], 6)):
        head = P_diff(P_circle(-0.3 * s, 0, 0.18 * s), P_circle(-0.3 * s, 0, 0.07 * s))
        tone(c, head, p.gold, s, t, ph=kw['ph'], shine=False)
        shaft = P_union(P_rrect(0.1 * s, 0, 0.6 * s, 0.1 * s, 0.05 * s), P_rrect(0.3 * s, 0.08 * s, 0.07 * s, 0.18 * s, 0.025 * s), P_rrect(0.42 * s, 0.07 * s, 0.07 * s, 0.16 * s, 0.025 * s))
        tone(c, shaft, p.gold, s, t, shine=False)


@prop('lock', hull=(0.7, 0.9))
def _lock(c, p, s, t, kw):
    """Vorhängeschloss: Bügel (steel), Körper (accent), Schlüsselloch (Tinte); der Bügel hebt sich leicht an."""
    lift = 0.03 * s * (0.5 + 0.5 * math.sin(TWO_PI * 0.5 * t + kw['ph']))
    c.arc(0, -0.18 * s - lift, 0.2 * s, 180, 360, p.steel, 0.09 * s)
    c.line(-0.2 * s, -0.18 * s - lift, -0.2 * s, -0.02 * s, p.steel, 0.09 * s)
    c.line(0.2 * s, -0.18 * s - lift, 0.2 * s, 0.0, p.steel, 0.09 * s)
    tone(c, P_rrect(0, 0.17 * s, 0.6 * s, 0.52 * s, 0.09 * s), p.accent, s, t, ph=kw['ph'])
    flat(c, P_union(P_circle(0, 0.11 * s, 0.07 * s), P_rrect(0, 0.23 * s, 0.07 * s, 0.18 * s, 0.03 * s)), p.dark)


@prop('mask', 'mask_domino', hull=(0.96, 0.5))
def _mask(c, p, s, t, kw):
    """Domino-Maske (Tinte): zwei verschmolzene Ovale mit Augenschlitzen (Sticker-Weiß); neigt sich."""
    with c.tf(rot=rock(t, kw['ph'], 4)):
        body = P_union(P_oval(-0.22 * s, 0, 0.27 * s, 0.22 * s), P_oval(0.22 * s, 0, 0.27 * s, 0.22 * s), P_rrect(0, 0.02 * s, 0.5 * s, 0.2 * s, 0.06 * s))
        tone(c, body, p.dark, s, t, ph=kw['ph'], shine=False)
        flat(c, P_oval(-0.2 * s, -0.01 * s, 0.13 * s, 0.085 * s), p.white)
        flat(c, P_oval(0.2 * s, -0.01 * s, 0.13 * s, 0.085 * s), p.white)
        if plain(c):
            flat(c, P_oval(-0.22 * s, -0.12 * s, 0.12 * s, 0.04 * s), CO.lighten(p.dark, 0.18))


@prop('crowbar', hull=(0.96, 0.6))
def _crowbar(c, p, s, t, kw):
    """Brecheisen (steel): Schaft mit Haken, der sich über das Ende zurückbiegt, flaches Keilende; wippt wie beim Hebeln."""
    with c.tf(rot=-24 + rock(t, kw['ph'], 5, 0.4)):
        w = 0.09 * s
        c.line(-0.4 * s, 0, 0.28 * s, 0, p.steel, w)
        c.arc(0.28 * s, -0.14 * s, 0.14 * s, 90, -130, p.steel, w)
        flat(c, P_poly([(-0.5 * s, -0.09 * s), (-0.5 * s, 0.09 * s), (-0.36 * s, 0.05 * s), (-0.36 * s, -0.05 * s)], 0.02 * s), p.steel)
        if plain(c):
            c.line(-0.3 * s, -0.02 * s, 0.1 * s, -0.02 * s, CO.lighten(p.steel, 0.22), 0.03 * s, twinkle(t, kw['ph']))


@prop('barrel', hull=(0.74, 0.94))
def _barrel(c, p, s, t, kw):
    """Fass (wood) mit zwei Reifen (steel) und Füllstandsfenster: kw['level'] 0..1, kw['liquid'] = 'syrup' (accent) | 'water'; Flüssigkeit wogt."""
    level = float(kw.get('level', 0.65))
    liquid = p.water if kw.get('liquid') == 'water' else p.accent
    body = P_union(P_rrect(0, 0, 0.6 * s, 0.9 * s, 0.14 * s), P_oval(0, 0, 0.36 * s, 0.42 * s))
    tone(c, body, p.wood, s, t, ph=kw['ph'], shine=False)
    win = P_rrect(0, 0.02 * s, 0.32 * s, 0.5 * s, 0.06 * s)
    flat(c, win, p.paper)
    if plain(c) and level > 0:
        with c.clip_path(win):
            y_top = 0.27 * s - 0.5 * s * min(1.0, level)
            pts = [(-0.2 * s, 0.4 * s), (-0.2 * s, y_top)]
            for i in range(5):
                xx = -0.2 * s + i * 0.1 * s
                pts.append((xx, y_top + 0.015 * s * math.sin(TWO_PI * 0.6 * t + i * 1.6 + kw['ph'])))
            pts += [(0.2 * s, y_top), (0.2 * s, 0.4 * s)]
            c.smooth_poly(pts, liquid, tension=0.4)
    flat(c, P_rrect(0, -0.26 * s, 0.68 * s, 0.08 * s, 0.03 * s), p.steel)
    flat(c, P_rrect(0, 0.26 * s, 0.68 * s, 0.08 * s, 0.03 * s), p.steel)


@prop('syrup_bottle', hull=(0.5, 0.96))
def _syrup_bottle(c, p, s, t, kw):
    """Sirupflasche: Bernstein-Korpus (accent), Hals, Deckel (wood), Papier-Etikett mit Blatt (danger); schwebt."""
    with c.tf(y=hover(t, kw['ph'])):
        body = P_union(P_rrect(0, 0.14 * s, 0.46 * s, 0.64 * s, 0.1 * s), P_rrect(0, -0.24 * s, 0.18 * s, 0.26 * s, 0.05 * s))
        tone(c, body, p.accent, s, t, ph=kw['ph'])
        flat(c, P_rrect(0, -0.4 * s, 0.22 * s, 0.14 * s, 0.04 * s), p.wood)
        flat(c, P_rrect(0, 0.16 * s, 0.34 * s, 0.34 * s, 0.05 * s), p.paper)
        leaf = P_union(P_star(0, 0.13 * s, 0.14 * s, 0.085 * s, 5, -90, 0.02 * s), P_rrect(0, 0.26 * s, 0.03 * s, 0.1 * s, 0.015 * s))
        flat(c, leaf, p.danger)


@prop('water_drop', hull=(0.52, 0.9))
def _water_drop(c, p, s, t, kw):
    """Wassertropfen (water): fällt in einer Schleife und staucht beim Aufsetzen (Squash, Volumenregel)."""
    u = ((t * 0.9 + kw['ph'] / TWO_PI) % 1.0)
    if u < 0.72:
        y = -0.18 * s + 0.36 * s * A.in_quad(u / 0.72)
        sy, sx = 1.0, 1.0
    else:
        v = (u - 0.72) / 0.28
        sy = 1 - 0.14 * math.sin(math.pi * v)
        sx = 1 / math.sqrt(sy)
        y = 0.18 * s
    with c.tf(y=y, sx=sx, sy=sy, px=0, py=0.3 * s):
        tone(c, P_drop(0, 0, 0.42 * s, 0.6 * s), p.water, s, t, ph=kw['ph'], shine_at=(-0.1 * s, 0.1 * s))


@prop('cheese', hull=(0.96, 0.7))
def _cheese(c, p, s, t, kw):
    """Käsekeil (accent) mit Löchern (dunkler); wippt."""
    with c.tf(rot=rock(t, kw['ph'])):
        wedge = P_poly([(-0.46 * s, 0.3 * s), (0.46 * s, 0.3 * s), (0.46 * s, -0.06 * s), (-0.1 * s, -0.34 * s)], 0.05 * s)
        tone(c, wedge, p.accent, s, t, ph=kw['ph'], shine=False)
        flat(c, P_poly([(-0.46 * s, 0.3 * s), (0.46 * s, 0.3 * s), (0.46 * s, 0.14 * s), (-0.46 * s, 0.14 * s)], 0.03 * s), CO.darken(p.accent, 0.12))
        for (x, y, r) in ((0.2, 0.0, 0.07), (-0.05, 0.14, 0.05), (0.3, -0.14, 0.04)):
            flat(c, P_circle(x * s, y * s, r * s), CO.darken(p.accent, 0.3))


@prop('cheese_wheel', hull=(0.92, 0.92))
def _cheese_wheel(c, p, s, t, kw):
    """Käselaib (accent) mit herausgeschnittenem Keil (bleibt leer, auch als Silhouette), Rinde und Löchern; wippt."""
    with c.tf(rot=rock(t, kw['ph'])):
        cut = P_pie(0, 0, 0.6 * s, -82, -10)
        disc = P_diff(P_circle(0, 0, 0.45 * s), cut)
        tone(c, disc, p.accent, s, t, ph=kw['ph'], shine=False)
        with c.clip_path(disc):
            flat(c, P_diff(P_circle(0, 0, 0.45 * s), P_circle(0, 0, 0.39 * s)), CO.darken(p.accent, 0.16))
            flat(c, P_diff(P_pie(0, 0, 0.5 * s, -90, -2), P_pie(0, 0, 0.5 * s, -85, -7)), CO.lighten(p.accent, 0.16))
            for (x, y, r) in ((-0.2, -0.08, 0.07), (0.04, 0.2, 0.06), (-0.22, 0.22, 0.045), (0.26, 0.14, 0.04), (-0.05, -0.26, 0.04)):
                flat(c, P_circle(x * s, y * s, r * s), CO.darken(p.accent, 0.3))


# ================================================================ Orte, Gebäude, Kunst

@prop('painting', hull=(0.96, 0.8))
def _painting(c, p, s, t, kw):
    """Gemälde: Rahmen (wood) mit Leinwand (paper), darauf Hügel (ok) und Sonne (accent); schwebt."""
    with c.tf(y=hover(t, kw['ph'])):
        tone(c, P_rrect(0, 0, 0.92 * s, 0.76 * s, 0.05 * s), p.wood, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(0, 0, 0.74 * s, 0.58 * s, 0.02 * s), p.paper)
        with c.clip_path(P_rrect(0, 0, 0.74 * s, 0.58 * s, 0.02 * s)):
            flat(c, P_circle(0.14 * s, -0.1 * s, 0.1 * s), p.accent)
            flat(c, P_oval(-0.12 * s, 0.3 * s, 0.4 * s, 0.26 * s), CO.darken(p.ok, 0.15))
            flat(c, P_oval(0.22 * s, 0.34 * s, 0.36 * s, 0.22 * s), p.ok)


@prop('frame', hull=(0.9, 0.96))
def _frame(c, p, s, t, kw):
    """Leerer Bilderrahmen (wood) mit dunkler Wand (bg2) dahinter; pendelt leicht um die Aufhängung."""
    with c.tf(rot=rock(t, kw['ph'], 2.5), px=0, py=-0.5 * s):
        outer = P_rrect(0, 0, 0.8 * s, 0.92 * s, 0.05 * s)
        tone(c, outer, p.wood, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(0, 0, 0.6 * s, 0.72 * s, 0.02 * s), p.bg2)
        flat(c, P_rrect(0, -0.46 * s, 0.14 * s, 0.1 * s, 0.03 * s), p.wood_dark)
        for (x, y) in ((-0.4, -0.46), (0.4, -0.46), (-0.4, 0.46), (0.4, 0.46)):
            flat(c, P_circle(x * s, y * s, 0.06 * s), p.wood_dark)


@prop('museum', hull=(0.96, 0.84))
def _museum(c, p, s, t, kw):
    """Museum: Giebel, vier Säulen und Sockel (paper), Türflügel (accent); schwebt."""
    with c.tf(y=hover(t, kw['ph'])):
        tone(c, P_poly([(-0.48 * s, -0.12 * s), (0.48 * s, -0.12 * s), (0, -0.42 * s)], 0.04 * s), p.paper, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(0, -0.1 * s, 0.84 * s, 0.08 * s, 0.02 * s), CO.darken(p.paper, 0.14))
        for x in (-0.3, -0.1, 0.1, 0.3):
            flat(c, P_rrect(x * s, 0.13 * s, 0.1 * s, 0.36 * s, 0.02 * s), p.paper)
        flat(c, P_rrect(0, 0.36 * s, 0.9 * s, 0.1 * s, 0.03 * s), CO.darken(p.paper, 0.14))
        flat(c, P_rrect(0, 0.17 * s, 0.1 * s, 0.26 * s, 0.02 * s), p.accent)


@prop('bank', hull=(0.96, 0.84))
def _bank(c, p, s, t, kw):
    """Bank: Flachdach-Tempel (chalk) mit drei Säulen und Münze (Altgold) im Giebel; schwebt."""
    with c.tf(y=hover(t, kw['ph'], 4, 0.45)):
        tone(c, P_rrect(0, -0.28 * s, 0.92 * s, 0.22 * s, 0.05 * s), p.chalk, s, t, ph=kw['ph'], shine=False)
        flat(c, P_circle(0, -0.28 * s, 0.08 * s), p.gold)
        for x in (-0.3, 0.0, 0.3):
            flat(c, P_rrect(x * s, 0.08 * s, 0.14 * s, 0.42 * s, 0.03 * s), p.chalk)
        flat(c, P_rrect(0, 0.36 * s, 0.96 * s, 0.1 * s, 0.03 * s), CO.darken(p.chalk, 0.14))


@prop('building', hull=(0.64, 0.98))
def _building(c, p, s, t, kw):
    """Hochhaus (bg2) mit Fensterraster (glow) und Antenne; ein Fenster wechselt langsam (<= 1 Hz)."""
    body = P_union(P_rrect(0, 0.06 * s, 0.56 * s, 0.84 * s, 0.04 * s), P_rrect(-0.1 * s, -0.4 * s, 0.26 * s, 0.1 * s, 0.03 * s))
    tone(c, body, p.bg2, s, t, ph=kw['ph'], shine=False)
    c.line(-0.1 * s, -0.44 * s, -0.1 * s, -0.5 * s, p.steel, 0.04 * s)
    on = int(t * 0.8 + kw['ph']) % 6
    i = 0
    for row in range(4):
        for col in range(3):
            x, y = (-0.17 + col * 0.17) * s, (-0.22 + row * 0.17) * s
            lit = (i * 7 + 3) % 6 != on
            flat(c, P_rrect(x, y, 0.1 * s, 0.1 * s, 0.015 * s), p.glow if lit else CO.darken(p.bg2, 0.25))
            i += 1
    flat(c, P_rrect(0, 0.4 * s, 0.14 * s, 0.14 * s, 0.02 * s), p.dark)


@prop('house', hull=(0.9, 0.9))
def _house(c, p, s, t, kw):
    """Haus: Wand (paper), Dach (danger), Tür und Fenster, Schornstein mit schwebender Rauchwolke."""
    tone(c, P_rrect(0, 0.14 * s, 0.6 * s, 0.56 * s, 0.03 * s), p.paper, s, t, ph=kw['ph'], shine=False)
    flat(c, P_rrect(0.2 * s, -0.28 * s, 0.1 * s, 0.2 * s, 0.02 * s), p.wood)
    tone(c, P_poly([(-0.46 * s, -0.1 * s), (0.46 * s, -0.1 * s), (0, -0.46 * s)], 0.04 * s), p.danger, s, t, shine=False)
    flat(c, P_rrect4(-0.14 * s, 0.26 * s, 0.14 * s, 0.3 * s, (0.07 * s, 0.07 * s, 0, 0)), p.wood)
    flat(c, P_rrect(0.14 * s, 0.1 * s, 0.14 * s, 0.14 * s, 0.02 * s), p.glow)
    if plain(c):
        u = (t * 0.4 + kw['ph']) % 1.0
        c.circle(0.2 * s + 0.04 * s * u, -0.42 * s - 0.12 * s * u, 0.05 * s * (1 + u), p.soft, 0.5 * (1 - u))


@prop('police', hull=(0.9, 0.74))
def _police(c, p, s, t, kw):
    """Polizeimütze: Deckel und Schirm (Tinte), Band (accent2) und Stern (Altgold); wippt."""
    with c.tf(rot=rock(t, kw['ph'])):
        top = P_union(P_oval(0, -0.1 * s, 0.42 * s, 0.26 * s), P_rrect(0, 0.08 * s, 0.76 * s, 0.26 * s, 0.06 * s))
        tone(c, top, p.dark, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(0, 0.08 * s, 0.76 * s, 0.14 * s, 0.04 * s), p.accent2)
        flat(c, P_rrect4(0.06 * s, 0.26 * s, 0.7 * s, 0.14 * s, (0.02 * s, 0.02 * s, 0.07 * s, 0.07 * s)), CO.lighten(p.dark, 0.12))
        flat(c, P_star(0, -0.08 * s, 0.11 * s, 0.05 * s, 5, -90, 0.012 * s), p.gold)


@prop('handcuffs', hull=(0.96, 0.5))
def _handcuffs(c, p, s, t, kw):
    """Handschellen (steel): zwei Ringe mit Gelenk und Kettenglied; die Ringe wackeln gegeneinander."""
    a = rock(t, kw['ph'], 5, 0.5)
    for sgn in (-1, 1):
        with c.tf(rot=sgn * a, px=sgn * 0.3 * s, py=0):
            c.ring(sgn * 0.3 * s, 0, 0.17 * s, 0.085 * s, p.steel)
            flat(c, P_rrect(sgn * 0.3 * s, 0.19 * s, 0.14 * s, 0.1 * s, 0.03 * s), p.steel_dark)
    c.ring(0, 0, 0.06 * s, 0.035 * s, p.steel_dark)
    c.line(-0.13 * s, 0, 0.13 * s, 0, p.steel_dark, 0.035 * s)


# ================================================================ Fahrzeuge

def _wheel(c, p, x, y, r, t, ph, speed=330):
    """Rad: Reifen (Tinte), Felge (steel), eine Speichenmarke außerhalb der Mitte zeigt die Drehung."""
    flat(c, P_circle(x, y, r), p.dark)
    flat(c, P_circle(x, y, r * 0.55), p.steel)
    with c.tf(rot=speed * t + ph * 20, px=x, py=y):
        flat(c, P_rrect(x, y, r * 0.9, r * 0.22, r * 0.1), CO.darken(p.steel, 0.3))
        flat(c, P_circle(x + r * 0.32, y, r * 0.14), p.dark)


@prop('car', 'getaway_car', hull=(0.98, 0.56))
def _car(c, p, s, t, kw):
    """Auto (Seitenansicht): Karosserie (accent2), Kabine, Fenster (foam), Räder drehen; kw['color'] überschreibt die Lackfarbe."""
    col = kw.get('paint', p.accent2)
    body = P_union(P_rrect(0, 0.06 * s, 0.94 * s, 0.26 * s, 0.08 * s), P_poly([(-0.32 * s, -0.06 * s), (0.3 * s, -0.06 * s), (0.2 * s, -0.26 * s), (-0.18 * s, -0.26 * s)], 0.05 * s))
    tone(c, body, col, s, t, ph=kw['ph'], shine_at=(-0.2 * s, -0.05 * s))
    flat(c, P_poly([(-0.26 * s, -0.08 * s), (-0.02 * s, -0.08 * s), (-0.02 * s, -0.22 * s), (-0.15 * s, -0.22 * s)], 0.02 * s), p.foam)
    flat(c, P_poly([(0.02 * s, -0.08 * s), (0.24 * s, -0.08 * s), (0.17 * s, -0.22 * s), (0.02 * s, -0.22 * s)], 0.02 * s), p.foam)
    flat(c, P_rrect(0.44 * s, 0.02 * s, 0.06 * s, 0.06 * s, 0.02 * s), p.glow)
    _wheel(c, p, -0.28 * s, 0.2 * s, 0.11 * s, t, kw['ph'])
    _wheel(c, p, 0.28 * s, 0.2 * s, 0.11 * s, t, kw['ph'])


@prop('motorcycle', hull=(0.98, 0.6))
def _motorcycle(c, p, s, t, kw):
    """Motorrad: zwei große Räder, Rahmen und Tank (danger), Sattel, Lenker; Räder drehen."""
    _wheel(c, p, -0.3 * s, 0.14 * s, 0.17 * s, t, kw['ph'], 300)
    _wheel(c, p, 0.3 * s, 0.14 * s, 0.17 * s, t, kw['ph'] + 1, 300)
    c.polyline([(-0.3 * s, 0.14 * s), (-0.06 * s, -0.08 * s), (0.18 * s, -0.06 * s), (0.3 * s, 0.14 * s)], p.steel, 0.06 * s)
    c.line(-0.06 * s, -0.08 * s, 0.02 * s, 0.12 * s, p.steel, 0.06 * s)
    tone(c, P_oval(0.06 * s, -0.12 * s, 0.17 * s, 0.1 * s), p.danger, s, t, ph=kw['ph'])
    flat(c, P_rrect(-0.16 * s, -0.17 * s, 0.22 * s, 0.07 * s, 0.035 * s), p.dark)
    c.line(0.22 * s, -0.12 * s, 0.3 * s, -0.28 * s, p.steel, 0.05 * s)
    c.line(0.24 * s, -0.28 * s, 0.36 * s, -0.28 * s, p.dark, 0.05 * s)


@prop('helicopter', hull=(0.98, 0.72))
def _helicopter(c, p, s, t, kw):
    """Hubschrauber: Kabine (accent), Heck, Kufen (steel), Hauptrotor als flacher Balken (Tinte); schwebt, der Heckrotor dreht."""
    with c.tf(y=hover(t, kw['ph'], 4, 0.6)):
        flat(c, P_rrect(-0.12 * s, 0.1 * s, 0.3 * s, 0.05 * s, 0.02 * s), p.steel)
        c.line(-0.3 * s, 0.2 * s, 0.3 * s, 0.2 * s, p.steel, 0.04 * s)
        for x in (-0.14, 0.14):
            c.line(x * s, 0.06 * s, x * s, 0.2 * s, p.steel, 0.035 * s)
        tail = P_union(P_rrect(-0.26 * s, -0.04 * s, 0.34 * s, 0.08 * s, 0.04 * s), P_rrect(-0.42 * s, -0.11 * s, 0.06 * s, 0.16 * s, 0.03 * s))
        tone(c, tail, p.accent, s, t, shine=False, shade=False)
        tone(c, P_oval(0.08 * s, -0.02 * s, 0.3 * s, 0.17 * s), p.accent, s, t, ph=kw['ph'])
        flat(c, P_inter(P_oval(0.08 * s, -0.02 * s, 0.3 * s, 0.17 * s), P_rrect(0.26 * s, -0.06 * s, 0.26 * s, 0.14 * s, 0.05 * s)), p.foam)
        c.line(0.08 * s, -0.19 * s, 0.08 * s, -0.27 * s, p.dark, 0.04 * s)
        flat(c, P_rrect(0.08 * s, -0.29 * s, 0.9 * s, 0.05 * s, 0.025 * s), p.dark)
        flat(c, P_circle(0.08 * s, -0.29 * s, 0.045 * s), p.steel_dark)
        with c.tf(rot=720 * t + kw['ph'] * 30, px=-0.42 * s, py=-0.11 * s):
            flat(c, P_rrect(-0.42 * s, -0.11 * s, 0.03 * s, 0.18 * s, 0.015 * s), p.dark)


@prop('truck', hull=(0.98, 0.6))
def _truck(c, p, s, t, kw):
    """Lkw: Fahrerhaus (accent2) mit Fenster, Kofferaufbau (paper), Räder drehen."""
    tone(c, P_rrect(-0.12 * s, -0.04 * s, 0.7 * s, 0.4 * s, 0.05 * s), p.paper, s, t, ph=kw['ph'], shine=False)
    cab = P_union(P_rrect(0.34 * s, 0.06 * s, 0.26 * s, 0.2 * s, 0.04 * s), P_rrect4(0.31 * s, -0.08 * s, 0.2 * s, 0.14 * s, (0.04 * s, 0.1 * s, 0, 0)))
    tone(c, cab, p.accent2, s, t, shine=False)
    flat(c, P_rrect4(0.31 * s, -0.08 * s, 0.14 * s, 0.1 * s, (0.02 * s, 0.07 * s, 0.01 * s, 0.01 * s)), p.foam)
    flat(c, P_rrect(0, 0.17 * s, 0.98 * s, 0.05 * s, 0.02 * s), p.steel_dark)
    _wheel(c, p, -0.3 * s, 0.22 * s, 0.1 * s, t, kw['ph'])
    _wheel(c, p, -0.08 * s, 0.22 * s, 0.1 * s, t, kw['ph'])
    _wheel(c, p, 0.34 * s, 0.22 * s, 0.1 * s, t, kw['ph'])


# ================================================================ Karte, Zeit

@prop('map', hull=(0.96, 0.74))
def _map(c, p, s, t, kw):
    """Faltkarte: drei Paneele (paper), gestrichelte Route (danger) und Zielpunkt; schwebt."""
    with c.tf(y=hover(t, kw['ph'])):
        pan = P_union(P_poly([(-0.48 * s, -0.3 * s), (-0.16 * s, -0.36 * s), (-0.16 * s, 0.3 * s), (-0.48 * s, 0.36 * s)], 0.03 * s),
                      P_poly([(-0.16 * s, -0.36 * s), (0.16 * s, -0.3 * s), (0.16 * s, 0.36 * s), (-0.16 * s, 0.3 * s)], 0.03 * s),
                      P_poly([(0.16 * s, -0.3 * s), (0.48 * s, -0.36 * s), (0.48 * s, 0.3 * s), (0.16 * s, 0.36 * s)], 0.03 * s))
        tone(c, pan, p.paper, s, t, ph=kw['ph'], shine=False)
        flat(c, P_poly([(-0.16 * s, -0.36 * s), (0.16 * s, -0.3 * s), (0.16 * s, 0.36 * s), (-0.16 * s, 0.3 * s)], 0.03 * s), CO.darken(p.paper, 0.1))
        if plain(c):
            c.path(smooth_path([(-0.36 * s, 0.2 * s), (-0.14 * s, 0.0), (0.06 * s, 0.12 * s), (0.26 * s, -0.12 * s)], 0.5, False), p.danger, stroke=0.035 * s)
        flat(c, P_circle(0.28 * s, -0.14 * s, 0.07 * s), p.danger)
        flat(c, P_circle(0.28 * s, -0.14 * s, 0.03 * s), p.paper)


@prop('pin', 'map_pin', hull=(0.6, 0.9))
def _pin(c, p, s, t, kw):
    """Ortsmarke (danger): Kreis mit Spitze und hellem Kern; hüpft."""
    u = (t * 0.9 + kw['ph'] / TWO_PI) % 1.0
    y = -0.12 * s * abs(math.sin(math.pi * u))
    with c.tf(y=y):
        body = P_union(P_circle(0, -0.12 * s, 0.3 * s), P_poly([(-0.2 * s, 0.1 * s), (0.2 * s, 0.1 * s), (0, 0.45 * s)], 0.03 * s))
        tone(c, body, p.danger, s, t, ph=kw['ph'])
        flat(c, P_circle(0, -0.12 * s, 0.12 * s), p.ink)


@prop('clock', hull=(0.9, 0.9))
def _clock(c, p, s, t, kw):
    """Uhr: Gehäuse (Tinte), Zifferblatt (chalk), vier Marken, Zeiger drehen (Minute 1 U/6 s, Stunde 1 U/72 s)."""
    tone(c, P_circle(0, 0, 0.45 * s), p.dark, s, t, ph=kw['ph'], shine=False)
    flat(c, P_circle(0, 0, 0.37 * s), p.chalk)
    for i in range(4):
        with c.tf(rot=i * 90):
            flat(c, P_rrect(0, -0.3 * s, 0.04 * s, 0.07 * s, 0.015 * s), p.dark)
    with c.tf(rot=(t * 5 + kw['ph'] * 30) % 360):
        c.line(0, 0, 0, -0.18 * s, p.dark, 0.05 * s)
    with c.tf(rot=(t * 60 + kw['ph'] * 60) % 360):
        c.line(0, 0, 0, -0.28 * s, p.danger, 0.04 * s)
    flat(c, P_circle(0, 0, 0.04 * s), p.dark)


@prop('calendar', hull=(0.86, 0.9))
def _calendar(c, p, s, t, kw):
    """Kalenderblatt: Kopfband (danger) mit zwei Ringen, Blatt (paper) mit Zahl (Unbounded, kw['text']); schwebt.
    kw['flip'] 0..1 blättert das Blatt (Scale-Y 1 -> 0 -> 1, vom Skript auf den Ton page_flip gelegt)."""
    text = str(kw.get('text', '31'))
    u = float(kw.get('flip', 0.0))
    with c.tf(y=hover(t, kw['ph'])):
        tone(c, P_rrect(0, 0.04 * s, 0.8 * s, 0.82 * s, 0.07 * s), p.paper, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect4(0, -0.27 * s, 0.8 * s, 0.2 * s, (0.07 * s, 0.07 * s, 0, 0)), p.danger)
        for x in (-0.2, 0.2):
            flat(c, P_rrect(x * s, -0.36 * s, 0.06 * s, 0.16 * s, 0.03 * s), p.steel)
        sy = abs(math.cos(math.pi * u)) if 0 < u < 1 else 1.0
        with c.tf(sy=max(0.02, sy), sx=1.0, px=0, py=-0.17 * s):
            c.text(text, 0, 0.1 * s, F.font('number', 0.36 * s), p.dark, 'center', 'middle')


@prop('hourglass', hull=(0.6, 0.92))
def _hourglass(c, p, s, t, kw):
    """Sanduhr: Holzrahmen, Glas (foam), Sand (accent) rinnt in einer 6-s-Schleife von oben nach unten."""
    u = ((t / 6.0 + kw['ph'] / TWO_PI) % 1.0)
    glass = P_union(P_poly([(-0.26 * s, -0.36 * s), (0.26 * s, -0.36 * s), (0.04 * s, 0), (-0.04 * s, 0)], 0.04 * s),
                    P_poly([(-0.04 * s, 0), (0.04 * s, 0), (0.26 * s, 0.36 * s), (-0.26 * s, 0.36 * s)], 0.04 * s))
    tone(c, glass, p.foam, s, t, ph=kw['ph'], shine=False)
    if plain(c):
        with c.clip_path(glass):
            top_h = 0.3 * s * (1 - u)
            flat(c, P_rrect(0, -0.03 * s - top_h / 2, 0.6 * s, top_h, 0), p.accent)
            bot_h = 0.3 * s * u
            flat(c, P_poly([(-0.3 * s, 0.34 * s), (0.3 * s, 0.34 * s), (0.3 * s, 0.34 * s - bot_h * 0.4), (0, 0.34 * s - bot_h), (-0.3 * s, 0.34 * s - bot_h * 0.4)]), p.accent)
            if 0.02 < u < 0.98:
                c.line(0, -0.02 * s, 0, 0.3 * s, p.accent, 0.03 * s)
    for y in (-0.42, 0.42):
        flat(c, P_rrect(0, y * s, 0.56 * s, 0.09 * s, 0.03 * s), p.wood)
    for x in (-0.26, 0.26):
        c.line(x * s, -0.4 * s, x * s, 0.4 * s, p.wood, 0.035 * s)


# ================================================================ Höhle, Natur, Himmel

@prop('skull', 'skull_friendly', hull=(0.8, 0.9))
def _skull(c, p, s, t, kw):
    """Freundlicher Totenkopf (chalk): runder Schädel, Kiefer, runde Augen und Nase (Tinte), zwei Zähne; wackelt."""
    with c.tf(rot=rock(t, kw['ph'], 4)):
        head = P_union(P_circle(0, -0.08 * s, 0.37 * s), P_rrect(0, 0.26 * s, 0.4 * s, 0.3 * s, 0.08 * s))
        tone(c, head, p.chalk, s, t, ph=kw['ph'])
        flat(c, P_circle(-0.14 * s, -0.1 * s, 0.1 * s), p.dark)
        flat(c, P_circle(0.14 * s, -0.1 * s, 0.1 * s), p.dark)
        flat(c, P_poly([(-0.06 * s, 0.12 * s), (0.06 * s, 0.12 * s), (0, 0.02 * s)], 0.015 * s), p.dark)
        flat(c, P_rrect(0, 0.26 * s, 0.26 * s, 0.05 * s, 0.02 * s), p.dark)
        for x in (-0.1, 0.0, 0.1):
            flat(c, P_rrect(x * s, 0.31 * s, 0.05 * s, 0.1 * s, 0.015 * s), p.dark)


@prop('bone', hull=(0.96, 0.4))
def _bone(c, p, s, t, kw):
    """Knochen (chalk): Schaft mit je zwei Kugeln an den Enden; wippt."""
    with c.tf(rot=rock(t, kw['ph'], 8) - 20):
        bone = P_union(P_rrect(0, 0, 0.7 * s, 0.14 * s, 0.07 * s),
                       P_circle(-0.36 * s, -0.08 * s, 0.1 * s), P_circle(-0.36 * s, 0.08 * s, 0.1 * s),
                       P_circle(0.36 * s, -0.08 * s, 0.1 * s), P_circle(0.36 * s, 0.08 * s, 0.1 * s))
        tone(c, bone, p.chalk, s, t, ph=kw['ph'], shine=False)


@prop('cave', hull=(0.98, 0.84))
def _cave(c, p, s, t, kw):
    """Höhleneingang: Felsbuckel (rock) mit dunkler Öffnung (Tinte) und Stalaktiten; ein Tropfen fällt."""
    mound = P_union(P_oval(0, 0.1 * s, 0.49 * s, 0.4 * s), P_rrect(0, 0.3 * s, 0.98 * s, 0.24 * s, 0.06 * s))
    tone(c, mound, p.rock, s, t, ph=kw['ph'], shine=False)
    hole = P_union(P_oval(0, 0.16 * s, 0.26 * s, 0.26 * s), P_rrect(0, 0.3 * s, 0.52 * s, 0.24 * s, 0.03 * s))
    flat(c, hole, p.dark)
    with c.clip_path(hole):
        for (x, h) in ((-0.14, 0.12), (0.0, 0.18), (0.14, 0.1)):
            flat(c, P_poly([((x - 0.06) * s, -0.12 * s), ((x + 0.06) * s, -0.12 * s), (x * s, (-0.1 + h) * s)], 0.012 * s), p.rock)
        if plain(c):
            u = (t * 0.8 + kw['ph']) % 1.0
            c.circle(0, (0.1 + 0.3 * A.in_quad(u)) * s, 0.025 * s, p.water, 1 - u * 0.5)


@prop('rock', hull=(0.9, 0.76))
def _rock(c, p, s, t, kw):
    """Felsbrocken (rock): abgerundetes Vieleck mit heller Facette; wackelt."""
    with c.tf(rot=rock(t, kw['ph'], 3)):
        pts = [(-0.44 * s, 0.2 * s), (-0.3 * s, -0.22 * s), (0.05 * s, -0.37 * s), (0.42 * s, -0.12 * s), (0.44 * s, 0.26 * s), (0.1 * s, 0.38 * s), (-0.3 * s, 0.36 * s)]
        tone(c, P_poly(pts, 0.06 * s), p.rock, s, t, ph=kw['ph'], shine=False)
        if plain(c):
            flat(c, P_poly([(-0.3 * s, -0.22 * s), (0.05 * s, -0.37 * s), (0.1 * s, -0.08 * s), (-0.16 * s, 0.0)], 0.04 * s), CO.lighten(p.rock, 0.14))


@prop('lantern', hull=(0.56, 0.96))
def _lantern(c, p, s, t, kw):
    """Laterne: Kappe und Fuß (steel), Glas (candle) mit Flamme (accent); pendelt am Henkel, das Licht flackert sanft."""
    fl = 0.85 + 0.15 * math.sin(TWO_PI * 2.3 * t + kw['ph']) * math.sin(TWO_PI * 1.1 * t)
    with c.tf(rot=rock(t, kw['ph'], 3, 0.4), px=0, py=-0.42 * s):
        c.arc(0, -0.32 * s, 0.1 * s, 180, 360, p.steel, 0.04 * s)
        flat(c, P_rrect(0, -0.3 * s, 0.4 * s, 0.1 * s, 0.03 * s), p.steel)
        tone(c, P_rrect(0, 0.0, 0.3 * s, 0.56 * s, 0.05 * s), p.candle, s, t, ph=kw['ph'], shine=False)
        flat(c, P_drop(0, 0.04 * s, 0.14 * s, 0.24 * s), p.accent)
        flat(c, P_rrect(0, 0.34 * s, 0.46 * s, 0.1 * s, 0.03 * s), p.steel)
        flat(c, P_rrect(0, 0.42 * s, 0.3 * s, 0.08 * s, 0.03 * s), p.steel_dark)
        add_glow(c, 0, 0.02 * s, 0.4 * s, p.glow, 0.3 * fl)


@prop('rope', hull=(0.9, 0.86))
def _rope(c, p, s, t, kw):
    """Seilrolle (skin/wood-Mix): drei gestapelte Windungen mit losem Ende; wiegt sich."""
    col = CO.hexs(CO.mix(p.skin, p.wood, 0.45))
    with c.tf(rot=rock(t, kw['ph'], 3)):
        for i, y in enumerate((0.18, 0.0, -0.18)):
            ring = P_diff(P_oval(0, y * s, 0.4 * s, 0.2 * s), P_oval(0, y * s, 0.2 * s, 0.08 * s))
            tone(c, ring, col if i != 1 else CO.darken(col, 0.08), s, t, shine=False, shade=(i == 2))
        c.path(smooth_path([(0.3 * s, 0.26 * s), (0.44 * s, 0.34 * s), (0.38 * s, 0.44 * s)], 0.5, False), col, stroke=0.07 * s)


@prop('bat', hull=(0.98, 0.6))
def _bat(c, p, s, t, kw):
    """Fledermaus (Tinte): Körper, Ohren, gezackte Flügel, Augen (glow); Flügel schlagen bei 4 Hz."""
    flap = 18 * math.sin(TWO_PI * 4 * t + kw['ph'])
    for sgn in (-1, 1):
        with c.tf(rot=sgn * flap, px=sgn * 0.08 * s, py=0):
            wing = P_smooth([(sgn * 0.08 * s, -0.08 * s), (sgn * 0.3 * s, -0.24 * s), (sgn * 0.48 * s, -0.12 * s), (sgn * 0.4 * s, 0.08 * s), (sgn * 0.3 * s, 0.0), (sgn * 0.2 * s, 0.1 * s), (sgn * 0.1 * s, 0.04 * s)], 0.35)
            tone(c, wing, p.dark, s, t, shine=False, shade=False)
    body = P_union(P_oval(0, 0.02 * s, 0.14 * s, 0.2 * s), P_circle(0, -0.14 * s, 0.13 * s),
                   P_poly([(-0.13 * s, -0.16 * s), (-0.03 * s, -0.16 * s), (-0.11 * s, -0.34 * s)], 0.01 * s),
                   P_poly([(0.03 * s, -0.16 * s), (0.13 * s, -0.16 * s), (0.11 * s, -0.34 * s)], 0.01 * s))
    tone(c, body, p.dark, s, t, ph=kw['ph'], shine=False)
    flat(c, P_circle(-0.05 * s, -0.15 * s, 0.03 * s), p.glow)
    flat(c, P_circle(0.05 * s, -0.15 * s, 0.03 * s), p.glow)


@prop('fish', hull=(0.98, 0.6))
def _fish(c, p, s, t, kw):
    """Fisch (accent2): Rumpf, Schwanzflosse wedelt, Rückenflosse, Auge (Sticker-Weiß) mit Pupille."""
    wag = 14 * math.sin(TWO_PI * 2 * t + kw['ph'])
    with c.tf(rot=wag, px=0.24 * s, py=0):
        tail = P_poly([(0.24 * s, 0), (0.48 * s, -0.22 * s), (0.48 * s, 0.22 * s)], 0.04 * s)
        tone(c, tail, CO.darken(p.accent2, 0.1), s, t, shine=False, shade=False)
    body = P_oval(-0.08 * s, 0, 0.38 * s, 0.22 * s)
    tone(c, body, p.accent2, s, t, ph=kw['ph'])
    flat(c, P_poly([(-0.2 * s, -0.18 * s), (0.08 * s, -0.18 * s), (-0.02 * s, -0.34 * s)], 0.03 * s), CO.darken(p.accent2, 0.1))
    flat(c, P_oval(0.0, 0.06 * s, 0.1 * s, 0.06 * s), CO.darken(p.accent2, 0.14))
    flat(c, P_circle(-0.3 * s, -0.05 * s, 0.06 * s), p.white)
    flat(c, P_circle(-0.31 * s, -0.05 * s, 0.03 * s), p.dark)


@prop('octopus', hull=(0.9, 0.9))
def _octopus(c, p, s, t, kw):
    """Oktopus (danger): Kuppelkopf, sechs Tentakel als dicke Kurven, die wogen, Augen (Sticker-Weiß)."""
    col = p.danger
    for i in range(6):
        x = (-0.3 + i * 0.12) * s
        w = math.sin(TWO_PI * 0.8 * t + kw['ph'] + i * 0.9)
        pts = [(x, 0.06 * s), (x + 0.03 * s * w, 0.22 * s), (x + 0.08 * s * w, 0.34 * s), (x + 0.02 * s * w + (0.06 * s if i % 2 else -0.06 * s), 0.42 * s)]
        c.path(smooth_path(pts, 0.5, False), CO.darken(col, 0.1) if i % 2 else col, stroke=0.08 * s)
    head = P_union(P_circle(0, -0.08 * s, 0.32 * s), P_rrect(0, 0.08 * s, 0.64 * s, 0.14 * s, 0.07 * s))
    tone(c, head, col, s, t, ph=kw['ph'])
    for x in (-0.11, 0.11):
        flat(c, P_circle(x * s, -0.04 * s, 0.07 * s), p.white)
        flat(c, P_circle(x * s + 0.01 * s, -0.03 * s, 0.035 * s), p.dark)


@prop('bird', hull=(0.96, 0.7))
def _bird(c, p, s, t, kw):
    """Vogel (accent2): Körper, Kopf, Schnabel (accent), Schwanz, Flügel (Tropfen) schlägt bei 3 Hz; keine Elster."""
    col = p.accent2
    tone(c, P_oval(-0.02 * s, 0.06 * s, 0.32 * s, 0.2 * s), col, s, t, ph=kw['ph'])
    flat(c, P_poly([(-0.3 * s, 0.0), (-0.48 * s, -0.14 * s), (-0.46 * s, 0.1 * s)], 0.03 * s), CO.darken(col, 0.12))
    tone(c, P_circle(0.22 * s, -0.14 * s, 0.17 * s), col, s, t, shine=False)
    flat(c, P_poly([(0.36 * s, -0.16 * s), (0.5 * s, -0.1 * s), (0.36 * s, -0.06 * s)], 0.015 * s), p.accent)
    flat(c, P_circle(0.26 * s, -0.18 * s, 0.05 * s), p.white)
    flat(c, P_circle(0.27 * s, -0.18 * s, 0.025 * s), p.dark)
    flap = 25 * math.sin(TWO_PI * 3 * t + kw['ph'])
    with c.tf(rot=flap, px=0.0, py=0.0):
        wing = P_smooth([(0.02 * s, -0.02 * s), (-0.12 * s, -0.22 * s), (-0.3 * s, -0.1 * s), (-0.14 * s, 0.08 * s)], 0.4)
        tone(c, wing, CO.darken(col, 0.14), s, t, shine=False, shade=False)
    c.line(-0.04 * s, 0.26 * s, -0.06 * s, 0.36 * s, p.accent, 0.035 * s)
    c.line(0.08 * s, 0.26 * s, 0.08 * s, 0.36 * s, p.accent, 0.035 * s)


@prop('cat', hull=(0.9, 0.84))
def _cat(c, p, s, t, kw):
    """Katzenkopf (steel-grau): runder Kopf, spitze Ohren mit Innenohr (skin), Augen, Nase, Schnurrhaare; ein Ohr zuckt."""
    col = p.steel
    tw = 10 * max(0.0, math.sin(TWO_PI * 0.7 * t + kw['ph'])) ** 8
    with c.tf(rot=-tw, px=-0.22 * s, py=-0.2 * s):
        flat(c, P_poly([(-0.4 * s, -0.08 * s), (-0.34 * s, -0.46 * s), (-0.06 * s, -0.26 * s)], 0.03 * s), col)
        flat(c, P_poly([(-0.33 * s, -0.14 * s), (-0.3 * s, -0.36 * s), (-0.14 * s, -0.25 * s)], 0.02 * s), p.skin)
    flat(c, P_poly([(0.4 * s, -0.08 * s), (0.34 * s, -0.46 * s), (0.06 * s, -0.26 * s)], 0.03 * s), col)
    flat(c, P_poly([(0.33 * s, -0.14 * s), (0.3 * s, -0.36 * s), (0.14 * s, -0.25 * s)], 0.02 * s), p.skin)
    tone(c, P_oval(0, 0.02 * s, 0.4 * s, 0.34 * s), col, s, t, ph=kw['ph'])
    for x in (-0.15, 0.15):
        flat(c, P_oval(x * s, -0.04 * s, 0.07 * s, 0.075 * s), p.ok)
        flat(c, P_oval(x * s, -0.04 * s, 0.025 * s, 0.065 * s), p.dark)
    flat(c, P_poly([(-0.05 * s, 0.1 * s), (0.05 * s, 0.1 * s), (0, 0.16 * s)], 0.012 * s), p.danger)
    for sgn in (-1, 1):
        c.line(sgn * 0.14 * s, 0.14 * s, sgn * 0.44 * s, 0.1 * s, p.ink, 0.025 * s)
        c.line(sgn * 0.14 * s, 0.2 * s, sgn * 0.44 * s, 0.24 * s, p.ink, 0.025 * s)


@prop('dog', hull=(0.9, 0.86))
def _dog(c, p, s, t, kw):
    """Hundekopf (wood-braun): Schlappohren (wackeln), Schnauze (skin), Nase (Tinte), Zunge (danger)."""
    col = p.wood
    wag = 6 * math.sin(TWO_PI * 1.2 * t + kw['ph'])
    for sgn in (-1, 1):
        with c.tf(rot=sgn * wag, px=sgn * 0.3 * s, py=-0.2 * s):
            tone(c, P_oval(sgn * 0.36 * s, 0.0, 0.12 * s, 0.3 * s), CO.darken(col, 0.18), s, t, shine=False, shade=False)
    tone(c, P_oval(0, -0.04 * s, 0.34 * s, 0.34 * s), col, s, t, ph=kw['ph'])
    flat(c, P_oval(0, 0.14 * s, 0.2 * s, 0.14 * s), p.skin)
    flat(c, P_oval(0, 0.06 * s, 0.07 * s, 0.05 * s), p.dark)
    flat(c, P_rrect(0.0, 0.27 * s, 0.09 * s, 0.1 * s, 0.04 * s), p.danger)
    for x in (-0.14, 0.14):
        flat(c, P_circle(x * s, -0.12 * s, 0.05 * s), p.dark)
        flat(c, P_circle(x * s - 0.015 * s, -0.135 * s, 0.016 * s), p.white)


@prop('rat', hull=(0.98, 0.66))
def _rat(c, p, s, t, kw):
    """Ratte (steel-grau): Rumpf, Kopf mit großen runden Ohren (skin innen), Nase (danger), Schwanz schlängelt."""
    col = p.steel
    w = math.sin(TWO_PI * 1.5 * t + kw['ph'])
    c.path(smooth_path([(-0.26 * s, 0.1 * s), (-0.38 * s, 0.16 * s + 0.04 * s * w), (-0.46 * s, 0.02 * s - 0.04 * s * w), (-0.5 * s, -0.08 * s)], 0.5, False), p.skin, stroke=0.05 * s)
    tone(c, P_oval(-0.08 * s, 0.1 * s, 0.32 * s, 0.2 * s), col, s, t, ph=kw['ph'])
    for x, r in ((0.12, 0.11), (0.3, 0.09)):
        flat(c, P_circle(x * s, -0.2 * s, r * s), col)
        flat(c, P_circle(x * s, -0.2 * s, r * 0.6 * s), p.skin)
    tone(c, P_poly([(0.02 * s, -0.08 * s), (0.5 * s, 0.1 * s), (0.08 * s, 0.26 * s)], 0.08 * s), col, s, t, shine=False)
    flat(c, P_circle(0.48 * s, 0.1 * s, 0.045 * s), p.danger)
    flat(c, P_circle(0.24 * s, 0.02 * s, 0.035 * s), p.dark)


@prop('snake', hull=(0.98, 0.6))
def _snake(c, p, s, t, kw):
    """Schlange (ok): S-förmiger Körper als dicke Kurve, Kopf, Auge, Zunge (danger); der Körper wellt sich."""
    pts = []
    for i in range(7):
        x = (-0.44 + i * 0.12) * s
        y = 0.14 * s * math.sin(i * 1.1 + TWO_PI * 0.8 * t + kw['ph']) + 0.06 * s
        pts.append((x, y))
    c.path(smooth_path(pts, 0.5, False), p.ok, stroke=0.12 * s)
    if plain(c):
        c.path(smooth_path(pts, 0.5, False), CO.darken(p.ok, 0.12), stroke=0.04 * s)
    hx, hy = pts[-1]
    tone(c, P_oval(hx + 0.04 * s, hy - 0.02 * s, 0.14 * s, 0.1 * s), p.ok, s, t, ph=kw['ph'], shine=False)
    flat(c, P_circle(hx + 0.07 * s, hy - 0.05 * s, 0.025 * s), p.dark)
    c.line(hx + 0.17 * s, hy, hx + 0.26 * s, hy - 0.02 * s, p.danger, 0.02 * s)


@prop('bug', hull=(0.8, 0.9))
def _bug(c, p, s, t, kw):
    """Käfer (danger): Rumpf mit Flügelnaht und Punkten (Tinte), Kopf, sechs Beine, Fühler wippen."""
    for i, y in enumerate((-0.08, 0.06, 0.2)):
        for sgn in (-1, 1):
            c.line(sgn * 0.2 * s, y * s, sgn * 0.36 * s, (y + 0.1 - i * 0.02) * s, p.dark, 0.035 * s)
    tone(c, P_oval(0, 0.06 * s, 0.26 * s, 0.33 * s), p.danger, s, t, ph=kw['ph'])
    c.line(0, -0.2 * s, 0, 0.38 * s, p.dark, 0.025 * s)
    for (x, y, r) in ((-0.12, -0.02, 0.05), (0.12, 0.06, 0.05), (-0.1, 0.22, 0.04), (0.1, 0.26, 0.035)):
        flat(c, P_circle(x * s, y * s, r * s), p.dark)
    flat(c, P_circle(0, -0.3 * s, 0.12 * s), p.dark)
    a = 8 * math.sin(TWO_PI * 1.5 * t + kw['ph'])
    for sgn in (-1, 1):
        with c.tf(rot=sgn * a, px=sgn * 0.06 * s, py=-0.38 * s):
            c.line(sgn * 0.06 * s, -0.38 * s, sgn * 0.18 * s, -0.48 * s, p.dark, 0.03 * s)
            flat(c, P_circle(sgn * 0.18 * s, -0.48 * s, 0.03 * s), p.dark)


@prop('tree', hull=(0.8, 0.98))
def _tree(c, p, s, t, kw):
    """Baum: Stamm (wood), drei gestapelte Kronenkreise (ok); wiegt sich um den Fuß."""
    with c.tf(rot=rock(t, kw['ph'], 2), px=0, py=0.48 * s):
        flat(c, P_rrect(0, 0.34 * s, 0.14 * s, 0.3 * s, 0.04 * s), p.wood)
        crown = P_union(P_circle(0, -0.22 * s, 0.26 * s), P_circle(-0.18 * s, 0.02 * s, 0.22 * s), P_circle(0.18 * s, 0.02 * s, 0.22 * s), P_circle(0, 0.1 * s, 0.2 * s))
        tone(c, crown, p.ok, s, t, ph=kw['ph'])


@prop('mountain', hull=(0.98, 0.76))
def _mountain(c, p, s, t, kw):
    """Gebirge: zwei abgerundete Dreiecke (rock, bg2) mit Schneekappen (chalk); eine kleine Wolke zieht vorbei."""
    back = P_poly([(-0.1 * s, 0.38 * s), (0.5 * s, 0.38 * s), (0.2 * s, -0.22 * s)], 0.05 * s)
    tone(c, back, CO.lighten(p.rock, 0.1), s, t, shine=False, shade=False)
    flat(c, P_inter(back, P_poly([(0.06 * s, -0.02 * s), (0.34 * s, -0.02 * s), (0.2 * s, -0.3 * s)])), p.chalk)
    front = P_poly([(-0.5 * s, 0.38 * s), (0.18 * s, 0.38 * s), (-0.16 * s, -0.38 * s)], 0.05 * s)
    tone(c, front, p.rock, s, t, ph=kw['ph'], shine=False)
    flat(c, P_inter(front, P_poly([(-0.34 * s, -0.1 * s), (0.02 * s, -0.1 * s), (-0.16 * s, -0.46 * s)])), p.chalk)
    if plain(c):
        cx = -0.2 * s + 0.06 * s * math.sin(TWO_PI * 0.2 * t + kw['ph'])
        cl = P_union(P_circle(cx, -0.02 * s, 0.06 * s), P_circle(cx + 0.08 * s, 0.0, 0.05 * s), P_circle(cx - 0.07 * s, 0.01 * s, 0.045 * s))
        flat(c, cl, p.ink, 0.9)


@prop('wave', hull=(0.98, 0.7))
def _wave(c, p, s, t, kw):
    """Welle (water): Kamm mit Schaumkrone (foam), rollt seitlich hin und her."""
    with c.tf(x=0.04 * s * math.sin(TWO_PI * 0.5 * t + kw['ph'])):
        body = P_smooth([(-0.48 * s, 0.34 * s), (-0.4 * s, 0.0), (-0.1 * s, -0.3 * s), (0.26 * s, -0.34 * s), (0.4 * s, -0.16 * s), (0.28 * s, -0.08 * s), (0.14 * s, -0.16 * s), (0.2 * s, 0.02 * s), (0.48 * s, 0.14 * s), (0.48 * s, 0.34 * s)], 0.45)
        tone(c, body, p.water, s, t, ph=kw['ph'], shine=False)
        foam = P_union(P_circle(0.3 * s, -0.26 * s, 0.1 * s), P_circle(0.14 * s, -0.3 * s, 0.08 * s), P_circle(0.4 * s, -0.16 * s, 0.07 * s))
        flat(c, foam, p.foam)
        flat(c, P_rrect(0, 0.28 * s, 0.96 * s, 0.12 * s, 0.05 * s), CO.darken(p.water, 0.15))


@prop('cloud', hull=(0.98, 0.6))
def _cloud(c, p, s, t, kw):
    """Wolke (chalk): vier verschmolzene Kreise auf flachem Boden; schwebt."""
    with c.tf(y=hover(t, kw['ph'], 5)):
        cl = P_union(P_circle(-0.22 * s, 0.06 * s, 0.18 * s), P_circle(0.0, -0.08 * s, 0.24 * s), P_circle(0.24 * s, 0.06 * s, 0.17 * s), P_rrect(0.0, 0.14 * s, 0.76 * s, 0.2 * s, 0.1 * s))
        tone(c, cl, p.chalk, s, t, ph=kw['ph'])


@prop('sun', hull=(0.98, 0.98))
def _sun(c, p, s, t, kw):
    """Sonne (accent): Scheibe mit acht abgerundeten Strahlen; die Strahlen drehen langsam."""
    with c.tf(rot=12 * t + kw['ph'] * 10):
        for i in range(8):
            with c.tf(rot=i * 45):
                flat(c, P_rrect(0, -0.38 * s, 0.09 * s, 0.2 * s, 0.045 * s), p.accent)
    tone(c, P_circle(0, 0, 0.26 * s), p.accent, s, t, ph=kw['ph'])
    add_glow(c, 0, 0, 0.5 * s, p.glow, 0.18)


@prop('moon', hull=(0.9, 0.9))
def _moon(c, p, s, t, kw):
    """Mondsichel (chalk) mit zwei Kratern und zwei funkelnden Sternen (glow)."""
    moon = P_diff(P_circle(0, 0, 0.4 * s), P_circle(0.16 * s, -0.08 * s, 0.32 * s))
    tone(c, moon, p.chalk, s, t, ph=kw['ph'], shine=False)
    flat(c, P_circle(-0.2 * s, -0.1 * s, 0.05 * s), CO.darken(p.chalk, 0.12))
    flat(c, P_circle(-0.12 * s, 0.18 * s, 0.035 * s), CO.darken(p.chalk, 0.12))
    for i, (x, y) in enumerate(((0.28, -0.3), (0.34, 0.12))):
        a = twinkle(t, kw['ph'] + i * 2)
        flat(c, P_star(x * s, y * s, 0.08 * s * a, 0.03 * s, 4, -90), p.glow, a)


@prop('star', hull=(0.96, 0.92))
def _star(c, p, s, t, kw):
    """Stern (glow/accent): fünfzackig mit abgerundeten Spitzen; atmet und funkelt."""
    k = 1 + 0.05 * math.sin(TWO_PI * 1.3 * t + kw['ph'])
    with c.tf(sx=k):
        tone(c, P_star(0, 0.03 * s, 0.46 * s, 0.22 * s, 5, -90, 0.03 * s), p.accent, s, t, ph=kw['ph'], shine=False)
        if plain(c):
            flat(c, P_star(0, 0.03 * s, 0.26 * s, 0.12 * s, 5, -90, 0.02 * s), CO.lighten(p.accent, 0.18))


@prop('planet', 'planet_ring', hull=(0.98, 0.7))
def _planet(c, p, s, t, kw):
    """Ringplanet (accent2) mit Band und geneigtem Ring (steel/soft), der hinten und vorn liegt; schwebt."""
    with c.tf(y=hover(t, kw['ph'])):
        ring_back = P_inter(P_diff(P_oval(0, 0, 0.48 * s, 0.14 * s), P_oval(0, 0, 0.36 * s, 0.08 * s)), P_rrect(0, -0.25 * s, 1.2 * s, 0.5 * s))
        ring_front = P_inter(P_diff(P_oval(0, 0, 0.48 * s, 0.14 * s), P_oval(0, 0, 0.36 * s, 0.08 * s)), P_rrect(0, 0.25 * s, 1.2 * s, 0.5 * s))
        with c.tf(rot=-18):
            flat(c, ring_back, p.soft)
        tone(c, P_circle(0, 0, 0.27 * s), p.accent2, s, t, ph=kw['ph'])
        with c.clip_path(P_circle(0, 0, 0.27 * s)):
            flat(c, P_rrect(0, 0.08 * s, 0.6 * s, 0.07 * s, 0.03 * s), CO.darken(p.accent2, 0.14))
            flat(c, P_rrect(0, -0.1 * s, 0.6 * s, 0.04 * s, 0.02 * s), CO.darken(p.accent2, 0.14))
        with c.tf(rot=-18):
            flat(c, ring_front, p.soft)


@prop('rocket', hull=(0.6, 0.98))
def _rocket(c, p, s, t, kw):
    """Rakete: Rumpf (chalk), Spitze und Finnen (danger), Bullauge (water), Flamme (accent) flackert."""
    with c.tf(y=hover(t, kw['ph'], 3, 0.6)):
        if plain(c):
            fl = 1 + 0.25 * math.sin(TWO_PI * 7 * t + kw['ph'])
            flat(c, P_drop(0, 0.4 * s, 0.16 * s, 0.26 * s * fl), p.accent)
            flat(c, P_drop(0, 0.37 * s, 0.08 * s, 0.14 * s * fl), p.glow)
        for sgn in (-1, 1):
            flat(c, P_poly([(sgn * 0.14 * s, 0.1 * s), (sgn * 0.3 * s, 0.32 * s), (sgn * 0.14 * s, 0.3 * s)], 0.03 * s), p.danger)
        body = P_union(P_rrect(0, 0.04 * s, 0.28 * s, 0.56 * s, 0.1 * s), P_poly([(-0.14 * s, -0.16 * s), (0.14 * s, -0.16 * s), (0, -0.48 * s)], 0.04 * s))
        tone(c, body, p.chalk, s, t, ph=kw['ph'])
        flat(c, P_poly([(-0.14 * s, -0.16 * s), (0.14 * s, -0.16 * s), (0, -0.48 * s)], 0.04 * s), p.danger)
        flat(c, P_circle(0, -0.02 * s, 0.07 * s), p.steel)
        flat(c, P_circle(0, -0.02 * s, 0.045 * s), p.water)


# ================================================================ Forschung, Medizin

@prop('telescope', hull=(0.98, 0.9))
def _telescope(c, p, s, t, kw):
    """Fernrohr (steel) auf Dreibein (wood); das Rohr wippt leicht, als suche es den Himmel ab."""
    for dx in (-0.2, 0.0, 0.2):
        c.line(0, 0.1 * s, dx * s, 0.46 * s, p.wood, 0.04 * s)
    with c.tf(rot=-30 + rock(t, kw['ph'], 3), px=0, py=0.06 * s):
        tube = P_union(P_rrect(0, 0.06 * s, 0.7 * s, 0.16 * s, 0.05 * s), P_rrect(0.32 * s, 0.06 * s, 0.14 * s, 0.22 * s, 0.04 * s), P_rrect(-0.38 * s, 0.06 * s, 0.1 * s, 0.1 * s, 0.03 * s))
        tone(c, tube, p.steel, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(0.12 * s, 0.06 * s, 0.1 * s, 0.17 * s, 0.03 * s), p.accent)
        flat(c, P_rrect(0.39 * s, 0.06 * s, 0.03 * s, 0.18 * s, 0.01 * s), p.water)
    flat(c, P_circle(0, 0.1 * s, 0.05 * s), p.wood_dark)


@prop('microscope', hull=(0.8, 0.98))
def _microscope(c, p, s, t, kw):
    """Mikroskop: Fuß und Arm (steel), Tubus (Tinte), Objekttisch, Linse (water); der Grobtrieb-Knopf dreht."""
    flat(c, P_rrect(0, 0.42 * s, 0.6 * s, 0.1 * s, 0.04 * s), p.steel_dark)
    c.path(smooth_path([(0.1 * s, 0.38 * s), (0.3 * s, 0.1 * s), (0.2 * s, -0.22 * s), (0.0, -0.3 * s)], 0.5, False), p.steel, stroke=0.1 * s)
    flat(c, P_rrect(-0.1 * s, 0.1 * s, 0.4 * s, 0.06 * s, 0.02 * s), p.steel)
    with c.tf(rot=-14, px=-0.06 * s, py=-0.18 * s):
        tone(c, P_rrect(-0.06 * s, -0.16 * s, 0.14 * s, 0.5 * s, 0.04 * s), p.dark, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(-0.06 * s, -0.42 * s, 0.2 * s, 0.07 * s, 0.03 * s), p.dark)
        flat(c, P_rrect(-0.06 * s, 0.1 * s, 0.1 * s, 0.06 * s, 0.02 * s), p.steel)
    flat(c, P_circle(-0.1 * s, 0.2 * s, 0.05 * s), p.water)
    with c.tf(rot=60 * t + kw['ph'] * 20, px=0.26 * s, py=0.06 * s):
        flat(c, P_circle(0.26 * s, 0.06 * s, 0.07 * s), p.accent)
        flat(c, P_rrect(0.26 * s, 0.02 * s, 0.02 * s, 0.05 * s, 0.01 * s), p.dark)


@prop('syringe', hull=(0.98, 0.5))
def _syringe(c, p, s, t, kw):
    """Spritze: Zylinder (foam) mit Wirkstoff (accent2), Kolben (steel) bewegt sich, Nadel (steel)."""
    u = 0.5 + 0.5 * math.sin(TWO_PI * 0.4 * t + kw['ph'])
    with c.tf(rot=-30):
        c.line(0.3 * s, 0, 0.5 * s, 0, p.steel, 0.03 * s)
        flat(c, P_rrect(0.3 * s, 0, 0.06 * s, 0.14 * s, 0.02 * s), p.steel)
        c.line(-0.5 * s + 0.16 * s * u, 0, -0.2 * s + 0.16 * s * u, 0, p.steel, 0.05 * s)
        flat(c, P_rrect(-0.5 * s + 0.16 * s * u, 0, 0.05 * s, 0.22 * s, 0.02 * s), p.steel)
        tone(c, P_rrect(0.02 * s, 0, 0.5 * s, 0.18 * s, 0.04 * s), p.foam, s, t, ph=kw['ph'], shine=False)
        with c.clip_path(P_rrect(0.02 * s, 0, 0.5 * s, 0.18 * s, 0.04 * s)):
            flat(c, P_rrect(0.02 * s + 0.1 * s * u, 0, 0.42 * s - 0.2 * s * u, 0.18 * s), p.accent2)
            flat(c, P_rrect(-0.2 * s + 0.16 * s * u, 0, 0.04 * s, 0.2 * s), p.steel_dark)
        flat(c, P_rrect(-0.22 * s, 0, 0.05 * s, 0.3 * s, 0.02 * s), p.steel)


@prop('pill', hull=(0.9, 0.5))
def _pill(c, p, s, t, kw):
    """Kapsel: zwei Hälften (accent, chalk); wippt."""
    with c.tf(rot=-30 + rock(t, kw['ph'], 8)):
        cap = P_rrect(0, 0, 0.8 * s, 0.34 * s, 0.17 * s)
        tone(c, cap, p.chalk, s, t, ph=kw['ph'])
        with c.clip_path(cap):
            flat(c, P_rrect(-0.2 * s, 0, 0.4 * s, 0.4 * s), p.accent)


@prop('heart', 'heart_anatomy', hull=(0.9, 0.84))
def _heart(c, p, s, t, kw):
    """Herz (danger): klassische Form, pulsiert bei 1 Hz (Scale 1..1.06)."""
    u = (t * 1.0 + kw['ph'] / TWO_PI) % 1.0
    k = 1 + 0.06 * max(0.0, math.sin(math.pi * min(1.0, u / 0.35)))
    with c.tf(sx=k):
        tone(c, P_heart(0, -0.02 * s, 0.86 * s), p.danger, s, t, ph=kw['ph'])


@prop('brain', hull=(0.92, 0.76))
def _brain(c, p, s, t, kw):
    """Gehirn (skin-rosa): Großhirn als breites Oval, Kleinhirn-Buckel unten rechts, Stamm; Windungen als dicke Bögen; pulsiert sanft."""
    col = CO.hexs(CO.mix(p.skin, p.danger, 0.3))
    with c.tf(sx=breathe(t, kw['ph'], 0.02, 0.8)):
        big = P_union(P_oval(-0.04 * s, -0.06 * s, 0.42 * s, 0.3 * s), P_circle(-0.2 * s, 0.1 * s, 0.2 * s))
        small = P_circle(0.24 * s, 0.18 * s, 0.14 * s)
        stem = P_rrect(0.1 * s, 0.3 * s, 0.1 * s, 0.14 * s, 0.03 * s)
        tone(c, P_union(big, small, stem), col, s, t, ph=kw['ph'])
        flat(c, small, CO.darken(col, 0.1))
        d = CO.darken(col, 0.2)
        c.arc(-0.22 * s, -0.08 * s, 0.1 * s, 120, 330, d, 0.035 * s)
        c.arc(0.02 * s, -0.12 * s, 0.1 * s, 160, 360, d, 0.035 * s)
        c.arc(0.2 * s, -0.04 * s, 0.09 * s, 220, 400, d, 0.035 * s)
        c.arc(-0.1 * s, 0.1 * s, 0.08 * s, 0, 180, d, 0.035 * s)
        c.arc(0.24 * s, 0.18 * s, 0.07 * s, 20, 200, d, 0.03 * s)


@prop('bomb', hull=(0.84, 0.9))
def _bomb(c, p, s, t, kw):
    """Bombe (Tinte) mit Zünder (steel), Lunte (wood) und Funke (accent), der flackert."""
    c.path(smooth_path([(0.14 * s, -0.3 * s), (0.22 * s, -0.42 * s), (0.34 * s, -0.4 * s)], 0.5, False), p.wood, stroke=0.035 * s)
    flat(c, P_rrect(0.1 * s, -0.26 * s, 0.14 * s, 0.1 * s, 0.03 * s), p.steel)
    tone(c, P_circle(-0.02 * s, 0.08 * s, 0.36 * s), p.dark, s, t, ph=kw['ph'], shine_at=(-0.14 * s, -0.08 * s))
    if plain(c):
        a = 0.7 + 0.3 * math.sin(TWO_PI * 2.7 * t + kw['ph'])
        flat(c, P_star(0.36 * s, -0.4 * s, 0.1 * s * a, 0.04 * s, 4, 20 * t), p.accent, a)
        add_glow(c, 0.36 * s, -0.4 * s, 0.14 * s, p.glow, 0.3 * a)


@prop('fire', hull=(0.7, 0.96))
def _fire(c, p, s, t, kw):
    """Flamme (accent) mit Kern (glow): Blob-Form flackert bei 7 Hz, Glow additiv."""
    f = 1 + 0.05 * math.sin(TWO_PI * 7 * t + kw['ph'])
    outer = P_smooth([(0, -0.46 * s * f), (0.14 * s, -0.2 * s), (0.3 * s, 0.0), (0.3 * s, 0.26 * s), (0.1 * s, 0.46 * s), (-0.12 * s, 0.46 * s), (-0.32 * s, 0.26 * s), (-0.26 * s, 0.02 * s), (-0.1 * s, -0.14 * s)], 0.45)
    tone(c, outer, p.accent, s, t, ph=kw['ph'], shine=False)
    inner = P_smooth([(0.02 * s, -0.06 * s * f), (0.14 * s, 0.14 * s), (0.12 * s, 0.34 * s), (-0.02 * s, 0.42 * s), (-0.16 * s, 0.32 * s), (-0.12 * s, 0.12 * s)], 0.45)
    flat(c, inner, p.glow)
    add_glow(c, 0, 0.1 * s, 0.5 * s, p.glow, 0.25)


@prop('lightning', hull=(0.6, 0.98))
def _lightning(c, p, s, t, kw):
    """Blitz (accent) mit 4-px-Ecken; pulsiert weich in Helligkeit und Glow (1.5 Hz, kein Stroboskop)."""
    bolt = P_poly([(0.1 * s, -0.48 * s), (-0.26 * s, 0.06 * s), (-0.02 * s, 0.06 * s), (-0.14 * s, 0.48 * s), (0.28 * s, -0.1 * s), (0.04 * s, -0.1 * s)], 4)
    tone(c, bolt, p.accent, s, t, ph=kw['ph'], shine=False)
    if plain(c):
        a = 0.5 + 0.5 * math.sin(TWO_PI * 1.5 * t + kw['ph'])
        flat(c, bolt, p.glow, 0.7 * a)
        add_glow(c, 0, 0, 0.4 * s, p.glow, 0.3 * a)


# ================================================================ Zeichen und Pfeile

@prop('question', hull=(0.72, 0.92))
def _question(c, p, s, t, kw):
    """Fragezeichen-Sticker (accent): abgerundete Karte, '?' in Tinte (Bricolage); wippt."""
    with c.tf(rot=rock(t, kw['ph'], 4)):
        tone(c, P_rrect(0, 0, 0.7 * s, 0.9 * s, 0.1 * s), p.accent, s, t, ph=kw['ph'])
        c.text('?', 0, 0.02 * s, F.font('display', 0.62 * s), p.dark, 'center', 'middle')


@prop('exclamation', 'exclaim', hull=(0.6, 0.92))
def _exclamation(c, p, s, t, kw):
    """Ausrufezeichen-Sticker (danger): '!' in Tinte; stretcht kurz nach oben (Scale-Y Puls)."""
    u = (t * 0.7 + kw['ph'] / TWO_PI) % 1.0
    sy = 1 + 0.08 * max(0.0, math.sin(math.pi * min(1.0, u / 0.25)))
    with c.tf(sx=1 / math.sqrt(sy), sy=sy, px=0, py=0.45 * s):
        tone(c, P_rrect(0, 0, 0.56 * s, 0.9 * s, 0.1 * s), p.danger, s, t, ph=kw['ph'])
        c.text('!', 0, 0.02 * s, F.font('display', 0.66 * s), p.dark, 'center', 'middle')


def _arrow(c, p, s, t, kw, deg):
    """Fetter Richtungspfeil (accent), pulsiert in Pfeilrichtung."""
    u = (t * 0.9 + kw['ph'] / TWO_PI) % 1.0
    d = 0.05 * s * math.sin(math.pi * u) ** 2
    with c.tf(rot=deg):
        with c.tf(x=d):
            head = P_poly([(0.06 * s, -0.42 * s), (0.48 * s, 0), (0.06 * s, 0.42 * s)], 0.05 * s)
            shaft = P_rrect(-0.2 * s, 0, 0.56 * s, 0.36 * s, 0.06 * s)
            tone(c, P_union(head, shaft), p.accent, s, t, ph=kw['ph'], shine=False)


@prop('arrow_up', hull=(0.9, 0.96))
def _arrow_up(c, p, s, t, kw):
    """Pfeil nach oben."""
    _arrow(c, p, s, t, kw, -90)


@prop('arrow_down', hull=(0.9, 0.96))
def _arrow_down(c, p, s, t, kw):
    """Pfeil nach unten."""
    _arrow(c, p, s, t, kw, 90)


@prop('arrow_right', hull=(0.96, 0.9))
def _arrow_right(c, p, s, t, kw):
    """Pfeil nach rechts."""
    _arrow(c, p, s, t, kw, 0)


@prop('arrow_left', hull=(0.96, 0.9))
def _arrow_left(c, p, s, t, kw):
    """Pfeil nach links."""
    _arrow(c, p, s, t, kw, 180)


@prop('arrow', hull=(0.96, 0.96))
def _arrow_any(c, p, s, t, kw):
    """Pfeil mit kw['dir'] = 'up' | 'down' | 'left' | 'right' (Standard: up)."""
    _arrow(c, p, s, t, kw, {'up': -90, 'down': 90, 'left': 180, 'right': 0}.get(kw.get('dir', 'up'), -90))


# ================================================================ Auszeichnungen

@prop('trophy', hull=(0.8, 0.96))
def _trophy(c, p, s, t, kw):
    """Pokal (Altgold): Kelch mit Henkeln, Stiel und Sockel (wood); funkelt."""
    for sgn in (-1, 1):
        c.arc(sgn * 0.28 * s, -0.14 * s, 0.13 * s, -90, 90 if sgn > 0 else -270, p.gold, 0.05 * s)
    cup = P_union(P_rrect4(0, -0.14 * s, 0.5 * s, 0.5 * s, (0.04 * s, 0.04 * s, 0.24 * s, 0.24 * s)), P_rrect(0, -0.37 * s, 0.56 * s, 0.08 * s, 0.03 * s))
    tone(c, cup, p.gold, s, t, ph=kw['ph'])
    flat(c, P_rrect(0, 0.2 * s, 0.1 * s, 0.16 * s, 0.03 * s), p.gold)
    flat(c, P_rrect(0, 0.33 * s, 0.4 * s, 0.1 * s, 0.03 * s), p.wood)
    flat(c, P_rrect(0, 0.42 * s, 0.5 * s, 0.08 * s, 0.03 * s), p.wood_dark)
    if plain(c):
        a = twinkle(t, kw['ph'])
        flat(c, P_star(-0.14 * s, -0.3 * s, 0.07 * s * a, 0.025 * s, 4, -90), p.white, a)


@prop('medal', hull=(0.6, 0.98))
def _medal(c, p, s, t, kw):
    """Medaille: zwei Bandstreifen (danger, accent2) und Scheibe (Altgold) mit Stern; pendelt."""
    with c.tf(rot=rock(t, kw['ph'], 5, 0.4), px=0, py=-0.48 * s):
        flat(c, P_poly([(-0.14 * s, -0.48 * s), (0.02 * s, -0.48 * s), (0.08 * s, 0.1 * s), (-0.08 * s, 0.1 * s)], 0.02 * s), p.danger)
        flat(c, P_poly([(-0.02 * s, -0.48 * s), (0.14 * s, -0.48 * s), (0.08 * s, 0.1 * s), (-0.08 * s, 0.1 * s)], 0.02 * s), p.accent2)
        tone(c, P_circle(0, 0.22 * s, 0.26 * s), p.gold, s, t, ph=kw['ph'])
        flat(c, P_circle(0, 0.22 * s, 0.19 * s), CO.darken(p.gold, 0.12))
        flat(c, P_star(0, 0.23 * s, 0.13 * s, 0.06 * s, 5, -90, 0.012 * s), p.gold)


@prop('crown', hull=(0.98, 0.8))
def _crown(c, p, s, t, kw):
    """Krone (Altgold): drei Zacken mit Kugeln, Reif mit Edelsteinen (accent2, danger); wippt."""
    with c.tf(rot=rock(t, kw['ph'])):
        body = P_poly([(-0.46 * s, -0.3 * s), (-0.2 * s, -0.02 * s), (0, -0.4 * s), (0.2 * s, -0.02 * s), (0.46 * s, -0.3 * s), (0.4 * s, 0.3 * s), (-0.4 * s, 0.3 * s)], 0.04 * s)
        tone(c, P_union(body, P_rrect(0, 0.26 * s, 0.84 * s, 0.14 * s, 0.05 * s)), p.gold, s, t, ph=kw['ph'], shine=False)
        for (x, y) in ((-0.46, -0.3), (0, -0.4), (0.46, -0.3)):
            flat(c, P_circle(x * s, y * s, 0.055 * s), p.gold)
        flat(c, P_rrect(0, 0.26 * s, 0.84 * s, 0.14 * s, 0.05 * s), CO.darken(p.gold, 0.12))
        flat(c, P_circle(0, 0.26 * s, 0.05 * s), p.danger)
        flat(c, P_circle(-0.24 * s, 0.26 * s, 0.04 * s), p.accent2)
        flat(c, P_circle(0.24 * s, 0.26 * s, 0.04 * s), p.accent2)


# ================================================================ Papier, Medien

@prop('book', hull=(0.84, 0.94))
def _book(c, p, s, t, kw):
    """Buch: Einband (accent2) mit Rücken, Seitenblock (paper), Titelfeld; schwebt."""
    with c.tf(y=hover(t, kw['ph'])):
        flat(c, P_rrect(0.04 * s, 0.02 * s, 0.7 * s, 0.86 * s, 0.03 * s), p.paper)
        cover = P_rrect4(-0.02 * s, -0.02 * s, 0.74 * s, 0.86 * s, (0.03 * s, 0.07 * s, 0.07 * s, 0.03 * s))
        tone(c, cover, p.accent2, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(-0.33 * s, -0.02 * s, 0.1 * s, 0.86 * s, 0.03 * s), CO.darken(p.accent2, 0.2))
        flat(c, P_rrect(0.06 * s, -0.12 * s, 0.4 * s, 0.14 * s, 0.03 * s), p.paper)


@prop('scroll', hull=(0.9, 0.9))
def _scroll(c, p, s, t, kw):
    """Schriftrolle (paper) mit zwei Holzstäben und Textzeilen (Tinte); schwebt. kw['text'] optional als Zitatzeile."""
    with c.tf(y=hover(t, kw['ph'])):
        tone(c, P_rrect(0, 0, 0.56 * s, 0.8 * s, 0.03 * s), p.paper, s, t, ph=kw['ph'], shine=False)
        for y in (-0.42, 0.42):
            flat(c, P_rrect(0, y * s, 0.8 * s, 0.1 * s, 0.05 * s), CO.darken(p.paper, 0.2))
            flat(c, P_rrect(0, y * s, 0.9 * s, 0.06 * s, 0.03 * s), p.wood)
        text = kw.get('text')
        if text:
            c.text_fit(str(text), 0, 0.0, 'serif_italic', 0.14 * s, 0.48 * s, p.dark, 'center', 'middle')
        else:
            for i, w in enumerate((0.36, 0.3, 0.34, 0.2)):
                flat(c, P_rrect(-0.2 * s + w * s / 2, (-0.2 + i * 0.13) * s, w * s, 0.04 * s, 0.02 * s), CO.darken(p.paper, 0.35))


@prop('letter', hull=(0.96, 0.7))
def _letter(c, p, s, t, kw):
    """Briefumschlag (paper) mit Lasche und Siegel (danger); schwebt."""
    with c.tf(y=hover(t, kw['ph'])):
        tone(c, P_rrect(0, 0, 0.92 * s, 0.64 * s, 0.05 * s), p.paper, s, t, ph=kw['ph'], shine=False)
        flat(c, P_poly([(-0.46 * s, -0.32 * s), (0.46 * s, -0.32 * s), (0, 0.06 * s)], 0.04 * s), CO.darken(p.paper, 0.14))
        flat(c, P_circle(0, 0.04 * s, 0.09 * s), p.danger)


@prop('phone', hull=(0.5, 0.96))
def _phone(c, p, s, t, kw):
    """Smartphone (Tinte) mit Bildschirm (foam), Kamera-Punkt; klingelt (kurze Wackler alle 2 s)."""
    u = (t * 0.5 + kw['ph'] / TWO_PI) % 1.0
    a = 5 * math.sin(TWO_PI * 6 * t) if u < 0.3 else 0.0
    with c.tf(rot=a):
        tone(c, P_rrect(0, 0, 0.48 * s, 0.92 * s, 0.09 * s), p.dark, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(0, 0.0, 0.4 * s, 0.76 * s, 0.05 * s), p.foam)
        flat(c, P_rrect(0, -0.34 * s, 0.14 * s, 0.03 * s, 0.015 * s), p.dark)
        flat(c, P_rrect(0, 0.42 * s, 0.16 * s, 0.03 * s, 0.015 * s), p.steel)
        flat(c, P_circle(0, -0.12 * s, 0.1 * s), p.accent2)
        flat(c, P_rrect(0, 0.1 * s, 0.26 * s, 0.05 * s, 0.025 * s), p.soft)
        flat(c, P_rrect(0, 0.2 * s, 0.18 * s, 0.05 * s, 0.025 * s), p.soft)


@prop('camera', hull=(0.96, 0.74))
def _camera(c, p, s, t, kw):
    """Kamera (Tinte): Gehäuse, Objektiv (steel + water), Auslöser; schwebt, der Blitz leuchtet alle 2 s auf."""
    with c.tf(y=hover(t, kw['ph'])):
        flat(c, P_rrect(-0.26 * s, -0.3 * s, 0.22 * s, 0.1 * s, 0.03 * s), p.dark)
        flat(c, P_rrect(0.3 * s, -0.3 * s, 0.1 * s, 0.08 * s, 0.03 * s), p.accent)
        tone(c, P_rrect(0, 0.04 * s, 0.92 * s, 0.6 * s, 0.09 * s), p.dark, s, t, ph=kw['ph'], shine=False)
        flat(c, P_circle(0, 0.04 * s, 0.22 * s), p.steel)
        flat(c, P_circle(0, 0.04 * s, 0.16 * s), p.water)
        flat(c, P_circle(0, 0.04 * s, 0.07 * s), p.dark)
        flat(c, P_rrect(0.32 * s, -0.08 * s, 0.1 * s, 0.1 * s, 0.03 * s), p.steel)
        if plain(c):
            u = (t * 0.5 + kw['ph'] / TWO_PI) % 1.0
            fl = max(0.0, 1 - u / 0.12) if u < 0.12 else 0.0
            c.circle(0.32 * s, -0.08 * s, 0.2 * s, p.glow, 0.6 * fl, blur=0.1 * s, blend='add')


@prop('tv', hull=(0.96, 0.9))
def _tv(c, p, s, t, kw):
    """Röhrenfernseher (wood) mit Bildschirm (foam) und Knöpfen; die Antenne wackelt."""
    with c.tf(rot=rock(t, kw['ph'], 4, 0.5), px=0, py=-0.3 * s):
        c.line(0, -0.3 * s, -0.22 * s, -0.5 * s, p.steel, 0.035 * s)
        c.line(0, -0.3 * s, 0.22 * s, -0.5 * s, p.steel, 0.035 * s)
        flat(c, P_circle(-0.22 * s, -0.5 * s, 0.035 * s), p.steel)
        flat(c, P_circle(0.22 * s, -0.5 * s, 0.035 * s), p.steel)
    tone(c, P_rrect(0, 0.06 * s, 0.92 * s, 0.68 * s, 0.09 * s), p.wood, s, t, ph=kw['ph'], shine=False)
    flat(c, P_rrect(-0.1 * s, 0.06 * s, 0.56 * s, 0.5 * s, 0.07 * s), p.foam)
    flat(c, P_circle(0.3 * s, -0.08 * s, 0.05 * s), p.dark)
    flat(c, P_circle(0.3 * s, 0.08 * s, 0.05 * s), p.dark)
    flat(c, P_rrect(0.3 * s, 0.24 * s, 0.1 * s, 0.05 * s, 0.02 * s), p.dark)
    for x in (-0.3, 0.3):
        flat(c, P_rrect(x * s, 0.44 * s, 0.1 * s, 0.1 * s, 0.03 * s), p.wood_dark)


@prop('newspaper', hull=(0.9, 0.9))
def _newspaper(c, p, s, t, kw):
    """Zeitung (paper): Kopfzeile kw['text'] (Standard 'EXTRA', Bricolage), Balkentext und Bildfeld (Tinte); wippt."""
    text = str(kw.get('text', 'EXTRA'))
    with c.tf(rot=-6 + rock(t, kw['ph'])):
        flat(c, P_rrect(0.04 * s, 0.04 * s, 0.84 * s, 0.84 * s, 0.03 * s), CO.darken(p.paper, 0.12))
        tone(c, P_rrect(0, 0, 0.84 * s, 0.84 * s, 0.03 * s), p.paper, s, t, ph=kw['ph'], shine=False)
        c.text_fit(text, 0, -0.26 * s, 'display', 0.24 * s, 0.7 * s, p.dark, 'center', 'middle')
        flat(c, P_rrect(-0.18 * s, 0.12 * s, 0.36 * s, 0.3 * s, 0.02 * s), p.dark)
        for i, w in enumerate((0.3, 0.3, 0.22, 0.3)):
            flat(c, P_rrect(0.06 * s + w * s / 2, (-0.02 + i * 0.1) * s, w * s, 0.04 * s, 0.02 * s), CO.darken(p.paper, 0.35))


@prop('magnifier', hull=(0.96, 0.96))
def _magnifier(c, p, s, t, kw):
    """Lupe: Ring (steel), Linse (foam) mit Glanzbogen, Griff (wood); schwenkt suchend."""
    with c.tf(rot=rock(t, kw['ph'], 6, 0.35)):
        c.line(0.2 * s, 0.2 * s, 0.42 * s, 0.42 * s, p.wood, 0.12 * s)
        flat(c, P_circle(-0.08 * s, -0.08 * s, 0.33 * s), p.steel)
        flat(c, P_circle(-0.08 * s, -0.08 * s, 0.26 * s), p.foam)
        if plain(c):
            c.arc(-0.08 * s, -0.08 * s, 0.19 * s, 200, 260, p.white, 0.035 * s, 0.9)


@prop('footprints', hull=(0.72, 0.96))
def _footprints(c, p, s, t, kw):
    """Fußspuren (chalk): zwei Sohlen mit Zehen; die jüngere Spur leuchtet abwechselnd heller (Gehrhythmus)."""
    u = (t * 0.8 + kw['ph'] / TWO_PI) % 1.0
    for i, (x, y) in enumerate(((-0.18, 0.18), (0.18, -0.18))):
        fresh = (u < 0.5) == (i == 0)
        col = p.chalk if fresh else CO.darken(p.chalk, 0.22)
        foot = P_union(P_oval(x * s, y * s + 0.02 * s, 0.11 * s, 0.17 * s), P_oval(x * s - 0.01 * s, y * s + 0.2 * s, 0.09 * s, 0.07 * s))
        tone(c, foot, col, s, t, shine=False)
        for (dx, r) in ((-0.11, 0.03), (-0.04, 0.035), (0.04, 0.035), (0.11, 0.03)):
            flat(c, P_circle(x * s + dx * s, y * s - 0.21 * s + abs(dx) * s * 0.3, r * s), col)


@prop('sandwich', hull=(0.96, 0.84))
def _sandwich(c, p, s, t, kw):
    """Angebissenes Sandwich: Brötchen (paper/wood) oben als Kuppel, Salat (ok), Tomate (danger), Käse (accent), Boden; Biss oben rechts; wippt.
    kw['chip'] legt einen DNA-Chip-Sticker (accent2) auf das Brot."""
    bread = CO.hexs(CO.mix(p.paper, p.wood, 0.3))
    bite = P_circle(0.36 * s, -0.24 * s, 0.19 * s)
    with c.tf(rot=rock(t, kw['ph'])):
        tone(c, P_diff(P_rrect4(0, 0.3 * s, 0.86 * s, 0.22 * s, (0.03 * s, 0.03 * s, 0.1 * s, 0.1 * s)), bite), bread, s, t, shine=False, shade=False)
        flat(c, P_diff(P_rrect(0, 0.14 * s, 0.9 * s, 0.1 * s, 0.03 * s), bite), p.accent)
        flat(c, P_diff(P_rrect(0, 0.04 * s, 0.86 * s, 0.12 * s, 0.06 * s), bite), p.danger)
        leaf = P_smooth([(-0.46 * s, -0.06 * s), (-0.3 * s, -0.12 * s), (-0.14 * s, -0.05 * s), (0.02 * s, -0.12 * s), (0.18 * s, -0.05 * s), (0.34 * s, -0.12 * s), (0.46 * s, -0.06 * s), (0.46 * s, 0.02 * s), (-0.46 * s, 0.02 * s)], 0.4)
        flat(c, P_diff(leaf, bite), p.ok)
        top = P_rrect4(0, -0.24 * s, 0.86 * s, 0.4 * s, (0.22 * s, 0.22 * s, 0.04 * s, 0.04 * s))
        tone(c, P_diff(top, bite), bread, s, t, ph=kw['ph'], shine=False)
        if plain(c):
            for (x, y) in ((-0.24 * s, -0.3 * s), (-0.06 * s, -0.36 * s), (0.1 * s, -0.32 * s)):
                flat(c, P_oval(x, y, 0.03 * s, 0.018 * s), CO.lighten(bread, 0.3))
        if kw.get('chip'):
            flat(c, P_rrect(-0.22 * s, -0.18 * s, 0.16 * s, 0.11 * s, 0.02 * s), p.accent2)
            flat(c, P_rrect(-0.22 * s, -0.18 * s, 0.08 * s, 0.05 * s, 0.01 * s), p.dark)


@prop('tunnel', hull=(0.96, 0.84))
def _tunnel(c, p, s, t, kw):
    """Tunnel: Felsbogen (rock) mit dunkler Röhre (Tinte) und Schienen (steel), die in die Tiefe laufen; Schwellen wandern."""
    arch = P_union(P_circle(0, -0.02 * s, 0.4 * s), P_rrect(0, 0.2 * s, 0.8 * s, 0.44 * s, 0.03 * s))
    tone(c, P_union(arch, P_rrect(0, 0.36 * s, 0.96 * s, 0.14 * s, 0.05 * s)), p.rock, s, t, ph=kw['ph'], shine=False)
    hole = P_union(P_circle(0, -0.02 * s, 0.28 * s), P_rrect(0, 0.16 * s, 0.56 * s, 0.36 * s, 0.02 * s))
    flat(c, hole, p.dark)
    if plain(c):
        with c.clip_path(hole):
            u = (t * 0.6 + kw['ph'] / TWO_PI) % 1.0
            for i in range(4):
                v = ((i + u) / 4.0)
                y = 0.0 + 0.36 * s * v ** 1.6
                w = 0.1 * s + 0.4 * s * v
                flat(c, P_rrect(0, y, w, 0.03 * s + 0.02 * s * v, 0.01 * s), p.steel_dark, 0.5 + 0.5 * v)
            c.line(-0.04 * s, 0.0, -0.22 * s, 0.4 * s, p.steel, 0.025 * s)
            c.line(0.04 * s, 0.0, 0.22 * s, 0.4 * s, p.steel, 0.025 * s)


@prop('drill', hull=(0.98, 0.7))
def _drill(c, p, s, t, kw):
    """Bohrmaschine: Gehäuse (danger) mit Griff, Bohrer (steel) mit wanderndem Rillenmuster (dreht)."""
    body = P_union(P_rrect(-0.1 * s, -0.08 * s, 0.6 * s, 0.26 * s, 0.08 * s), P_poly([(-0.26 * s, 0.0), (-0.06 * s, 0.0), (-0.1 * s, 0.34 * s), (-0.3 * s, 0.34 * s)], 0.04 * s))
    tone(c, body, p.danger, s, t, ph=kw['ph'])
    flat(c, P_rrect(-0.18 * s, 0.14 * s, 0.08 * s, 0.1 * s, 0.03 * s), p.dark)
    flat(c, P_rrect(0.26 * s, -0.08 * s, 0.12 * s, 0.16 * s, 0.03 * s), p.steel_dark)
    bit = P_rrect(0.4 * s, -0.08 * s, 0.26 * s, 0.09 * s, 0.03 * s)
    flat(c, bit, p.steel)
    if plain(c):
        with c.clip_path(bit):
            off = (t * 0.073 * s) % (0.06 * s)
            for i in range(6):
                x = 0.28 * s + i * 0.06 * s + off
                with c.tf(rot=-30, px=x, py=-0.08 * s):
                    flat(c, P_rrect(x, -0.08 * s, 0.02 * s, 0.14 * s), p.steel_dark)


@prop('ladder', hull=(0.6, 0.98))
def _ladder(c, p, s, t, kw):
    """Leiter (wood): zwei Holme, fünf Sprossen; kippt leicht um den Fuß."""
    with c.tf(rot=8 + rock(t, kw['ph'], 3, 0.25), px=0, py=0.48 * s):
        for x in (-0.2, 0.2):
            flat(c, P_rrect(x * s, 0, 0.09 * s, 0.96 * s, 0.04 * s), p.wood)
        for i in range(5):
            flat(c, P_rrect(0, (-0.36 + i * 0.18) * s, 0.4 * s, 0.07 * s, 0.03 * s), CO.darken(p.wood, 0.15))


@prop('suitcase', hull=(0.96, 0.8))
def _suitcase(c, p, s, t, kw):
    """Koffer (wood): Korpus mit Griff, Band und zwei Schlössern (Altgold); schwebt."""
    with c.tf(y=hover(t, kw['ph'])):
        c.arc(0, -0.26 * s, 0.16 * s, 180, 360, p.wood_dark, 0.06 * s)
        tone(c, P_rrect(0, 0.06 * s, 0.92 * s, 0.62 * s, 0.09 * s), p.wood, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(0, -0.12 * s, 0.92 * s, 0.1 * s, 0.02 * s), CO.darken(p.wood, 0.18))
        for x in (-0.28, 0.28):
            flat(c, P_rrect(x * s, -0.1 * s, 0.1 * s, 0.1 * s, 0.025 * s), p.gold)


@prop('globe', hull=(0.88, 0.98))
def _globe(c, p, s, t, kw):
    """Globus: Kugel (water) mit Kontinenten (ok), die um die Achse wandern, Bügel und Fuß (steel)."""
    c.arc(0, -0.04 * s, 0.42 * s, -10, 100, p.steel, 0.05 * s)
    flat(c, P_rrect(0, 0.46 * s, 0.4 * s, 0.07 * s, 0.03 * s), p.steel)
    c.line(0.2 * s, 0.38 * s, 0, 0.46 * s, p.steel, 0.05 * s)
    ball = P_circle(0, -0.04 * s, 0.36 * s)
    tone(c, ball, p.water, s, t, ph=kw['ph'])
    if plain(c):
        with c.clip_path(ball):
            off = (t * 0.12 * s) % (1.44 * s)
            for k in (-1.44 * s, 0.0):
                x0 = off + k
                flat(c, P_smooth([(x0 - 0.2 * s, -0.3 * s), (x0 + 0.02 * s, -0.26 * s), (x0 + 0.06 * s, -0.08 * s), (x0 - 0.1 * s, 0.02 * s), (x0 - 0.24 * s, -0.1 * s)], 0.4), p.ok)
                flat(c, P_smooth([(x0 + 0.3 * s, -0.14 * s), (x0 + 0.52 * s, -0.1 * s), (x0 + 0.46 * s, 0.18 * s), (x0 + 0.28 * s, 0.26 * s), (x0 + 0.2 * s, 0.06 * s)], 0.4), p.ok)
                flat(c, P_smooth([(x0 + 0.76 * s, -0.3 * s), (x0 + 1.0 * s, -0.22 * s), (x0 + 0.94 * s, 0.0), (x0 + 0.7 * s, -0.06 * s)], 0.4), p.ok)


# ================================================================ Sticker-Text, Sprechblasen, Stempel (STIL.md 5.4, 7)

def fit_font(c, text, role, size, max_w, spacing=0.0):
    """Schrift der Rolle, notfalls verkleinert, bis text in max_w passt (ohne Mindestgröße: Props sind Dekoration)."""
    sz = size
    for _ in range(12):
        f = F.font(role, sz)
        if c.text_width(text, f, spacing) <= max_w:
            return f
        sz *= 0.92
    return F.font(role, sz)


def _plate_text(c, p, s, t, kw, text, fill, ink, role='display', size_k=0.3, rot=0.0, pad=0.28, max_w=1.5):
    """Textplakette: Füllung, Text in Tinte; Breite folgt dem Text (höchstens max_w * s, Text wird eingepasst)."""
    f = fit_font(c, text, role, size_k * s, (max_w - pad) * s)
    w = c.text_width(text, f) + pad * s
    h = size_k * s * 1.7
    with c.tf(rot=rot):
        tone(c, P_rrect(0, 0, w, h, 0.09 * s), fill, s, t, ph=kw['ph'], shine=False)
        c.text(text, 0, 0.0, f, ink, 'center', 'middle')
    return w, h


@prop('speech_bubble', hull=(1.1, 0.7))
def _speech_bubble(c, p, s, t, kw):
    """Sprechblase (Elfenbein) mit Schwanzpfeil unten links; kw['text'] (Standard 'Odd.') in Unbounded, Tinte; wippt."""
    text = str(kw.get('text', 'Odd.'))
    f = fit_font(c, text, 'number', 0.3 * s, 1.2 * s)
    w = c.text_width(text, f) + 0.34 * s
    h = 0.56 * s
    with c.tf(rot=rock(t, kw['ph'], 2.5), px=0, py=0.45 * s):
        body = P_union(P_rrect(0, -0.06 * s, w, h, 0.14 * s), P_poly([(-w * 0.3, 0.16 * s), (-w * 0.08, 0.16 * s), (-w * 0.32, 0.44 * s)], 0.03 * s))
        tone(c, body, p.ink, s, t, ph=kw['ph'], shine=False, shade=False)
        c.text(text, 0, -0.06 * s, f, p.dark, 'center', 'middle')


@prop('thought_bubble', hull=(1.1, 0.8))
def _thought_bubble(c, p, s, t, kw):
    """Gedankenblase (Elfenbein): Wolkenform mit zwei kleinen Kreisen; kw['text'] in Bricolage, Tinte; schwebt."""
    text = str(kw.get('text', '?'))
    f = fit_font(c, text, 'display', 0.26 * s, 1.1 * s)
    w = max(0.7 * s, c.text_width(text, f) + 0.4 * s)
    with c.tf(y=hover(t, kw['ph'])):
        cloud = P_union(P_rrect(0, -0.1 * s, w, 0.46 * s, 0.2 * s), P_circle(-w * 0.3, -0.26 * s, 0.14 * s), P_circle(0, -0.3 * s, 0.17 * s), P_circle(w * 0.3, -0.26 * s, 0.14 * s))
        tone(c, cloud, p.ink, s, t, ph=kw['ph'], shine=False, shade=False)
        flat(c, P_circle(-w * 0.3, 0.22 * s, 0.07 * s), p.ink)
        flat(c, P_circle(-w * 0.38, 0.36 * s, 0.04 * s), p.ink)
        c.text(text, 0, -0.1 * s, f, p.dark, 'center', 'middle')


@prop('stamp', hull=(1.4, 0.5))
def _stamp(c, p, s, t, kw):
    """Gummistempel (STIL.md 5.4): Koralle-Rahmen 6 px, Text Bricolage 800 Versalien in Koralle, -8°, Multiply-Korn 0.08.
    kw['text'] (Standard 'VERIFIED ODD'); der Einschlag (Scale 1.6 -> 1.0) kommt aus k, hier nur ein leichtes Atmen."""
    text = str(kw.get('text', 'VERIFIED ODD')).upper()
    f = fit_font(c, text, 'display', 0.3 * s, 1.2 * s)
    w = c.text_width(text, f) + 0.3 * s
    h = 0.5 * s
    with c.tf(rot=-8, sx=breathe(t, kw['ph'], 0.01)):
        frame = P_diff(P_rrect(0, 0, w, h, 0.11 * s), P_rrect(0, 0, w - 0.08 * s, h - 0.08 * s, 0.08 * s))
        flat(c, frame, p.danger)
        c.text(text, 0, 0.0, f, p.danger, 'center', 'middle')
        if plain(c):
            with c.clip_path(P_rrect(0, 0, w, h, 0.11 * s)):
                c.grain(0.08, seed=4, blend='multiply')


@prop('flip_card', hull=(1.0, 0.68))
def _flip_card(c, p, s, t, kw):
    """Karteikarte (Elfenbein, 3:2) mit Text DM Mono in Tinte: kw['front'] / kw['back']; kw['flip'] 0..1 klappt per Scale-X
    (1 -> 0 -> 1) auf die Rückseite, die den Stempeltext trägt (Koralle)."""
    front, back = str(kw.get('front', 'APPROVED')), str(kw.get('back', 'FAKE'))
    u = float(kw.get('flip', 0.0))
    sx = abs(math.cos(math.pi * u))
    show_back = u > 0.5
    with c.tf(y=hover(t, kw['ph']), sx=max(0.02, sx), px=0, py=0):
        tone(c, P_rrect(0, 0, 0.96 * s, 0.64 * s, 0.08 * s), p.ink, s, t, ph=kw['ph'], shine=False, shade=False)
        for i in range(3):
            flat(c, P_rrect(0, (-0.12 + i * 0.14) * s, 0.76 * s, 0.015 * s), p.soft)
        flat(c, P_rrect(0, -0.26 * s, 0.96 * s, 0.05 * s), p.danger if show_back else p.accent2)
        if show_back:
            f = F.font('display', 0.22 * s)
            w = c.text_width(back, f) + 0.2 * s
            with c.tf(rot=-8):
                flat(c, P_diff(P_rrect(0, 0.02 * s, w, 0.34 * s, 0.07 * s), P_rrect(0, 0.02 * s, w - 0.06 * s, 0.28 * s, 0.05 * s)), p.danger)
                c.text(back, 0, 0.02 * s, f, p.danger, 'center', 'middle')
        else:
            c.text_fit(front, 0, 0.02 * s, 'mono', 0.16 * s, 0.8 * s, p.dark, 'center', 'middle')


@prop('keyword', hull=(1.4, 0.5))
def _keyword(c, p, s, t, kw):
    """Schlagwort-Sticker: kw['text'] Versalien in Bricolage 800 auf accent-Plakette, Tinte; leicht gedreht (-4..4°), atmet."""
    text = str(kw.get('text', 'ODD')).upper()
    rot = float(kw.get('tilt', -3))
    with c.tf(sx=breathe(t, kw['ph'], 0.01)):
        _plate_text(c, p, s, t, kw, text, p.accent, p.dark, 'display', 0.3, rot)


@prop('stat_chip', hull=(1.2, 0.6))
def _stat_chip(c, p, s, t, kw):
    """Stat-Plakette (Elfenbein): Wert kw['value'] in Unbounded, Label kw['label'] in DM Mono Versalien; kw['k'] 0..1 zählt den Wert hoch."""
    label = str(kw.get('label', 'TONS')).upper()
    val = kw.get('value', 22)
    kk = float(kw.get('k', 1.0))
    if isinstance(val, (int, float)):
        shown = f"{val * kk:,.0f}" if float(val).is_integer() else f"{val * kk:.1f}"
    else:
        shown = str(val)
    fv, fl = F.font('number', 0.3 * s), F.font('mono', 0.11 * s)
    w = max(0.8 * s, max(c.text_width(shown, fv), c.text_width(label, fl, 2)) + 0.3 * s)
    with c.tf(sx=breathe(t, kw['ph'], 0.01)):
        tone(c, P_rrect(0, 0, w, 0.6 * s, 0.14 * s), p.ink, s, t, ph=kw['ph'], shine=False, shade=False)
        c.text(shown, 0, -0.06 * s, fv, p.dark, 'center', 'middle')
        c.text(label, 0, 0.17 * s, fl, p.dark, 'center', 'middle', alpha=0.7, spacing=2)


@prop('country_chip', hull=(0.9, 0.9))
def _country_chip(c, p, s, t, kw):
    """Länder-Chip: Kreis (bg2) mit 2–3-Buchstaben-Kürzel kw['code'] in DM Mono (Elfenbein); keine Flaggen; wippt."""
    code = str(kw.get('code', 'UK')).upper()[:3]
    with c.tf(rot=rock(t, kw['ph'])):
        tone(c, P_circle(0, 0, 0.44 * s), p.bg2, s, t, ph=kw['ph'], shine=False)
        flat(c, P_circle(0, 0, 0.36 * s), CO.lighten(p.bg2, 0.08))
        c.text(code, 0, 0.0, F.font('mono', 0.3 * s), p.ink, 'center', 'middle', spacing=2)


# ================================================================ Respekt (STIL.md 1.8)

@prop('ghost_halo', hull=(0.9, 0.6))
def _ghost_halo(c, p, s, t, kw):
    """Heiligenschein (Elfenbein/candle): flacher Ring mit weichem Glow; schwebt langsam."""
    col = p.candle
    with c.tf(y=hover(t, kw['ph'], 4, 0.3)):
        ring = P_diff(P_oval(0, 0, 0.45 * s, 0.16 * s), P_oval(0, 0, 0.33 * s, 0.08 * s))
        tone(c, ring, col, s, t, ph=kw['ph'], shine=False)
        add_glow(c, 0, 0, 0.5 * s, col, 0.2)


@prop('candle', hull=(0.5, 0.98))
def _candle(c, p, s, t, kw):
    """Gedenkkerze: Wachs (chalk) mit Tropfen, Docht, Flamme (candle/accent) flackert sanft, Glow."""
    fl = 1 + 0.08 * math.sin(TWO_PI * 3 * t + kw['ph']) * math.sin(TWO_PI * 1.3 * t)
    flat(c, P_rrect(0, 0.46 * s, 0.4 * s, 0.07 * s, 0.03 * s), p.wood)
    body = P_union(P_rrect(0, 0.14 * s, 0.26 * s, 0.6 * s, 0.04 * s), P_rrect(0.1 * s, -0.06 * s, 0.07 * s, 0.2 * s, 0.035 * s))
    tone(c, body, p.chalk, s, t, ph=kw['ph'], shine=False)
    c.line(0, -0.16 * s, 0, -0.24 * s, p.dark, 0.025 * s)
    with c.tf(sx=1.0, sy=fl, px=0, py=-0.22 * s):
        flat(c, P_drop(0, -0.34 * s, 0.14 * s, 0.26 * s), p.candle)
        flat(c, P_drop(0, -0.3 * s, 0.07 * s, 0.13 * s), p.accent)
    add_glow(c, 0, -0.32 * s, 0.4 * s, p.candle, 0.25 * fl)


@prop('closed_label', hull=(1.3, 0.6))
def _closed_label(c, p, s, t, kw):
    """„EXHIBIT CLOSED“-Schild (Tinte, Elfenbein-Text DM Mono) an zwei Kettengliedern; pendelt sehr langsam."""
    text = str(kw.get('text', 'EXHIBIT CLOSED')).upper()
    with c.tf(rot=rock(t, kw['ph'], 1.5, 0.25), px=0, py=-0.3 * s):
        for x in (-0.3, 0.3):
            c.line(x * s, -0.3 * s, x * s, -0.12 * s, p.steel, 0.035 * s)
        f = fit_font(c, text, 'mono', 0.14 * s, 1.1 * s, 1)
        w = c.text_width(text, f, 1) + 0.24 * s
        tone(c, P_rrect(0, 0.06 * s, w, 0.36 * s, 0.06 * s), p.dark, s, t, ph=kw['ph'], shine=False, shade=False)
        flat(c, P_diff(P_rrect(0, 0.06 * s, w - 0.06 * s, 0.3 * s, 0.04 * s), P_rrect(0, 0.06 * s, w - 0.1 * s, 0.26 * s, 0.03 * s)), p.ink, 0.6)
        c.text(text, 0, 0.06 * s, f, p.ink, 'center', 'middle', spacing=1)


# ================================================================ Heist-Ergänzungen

@prop('bridge', hull=(0.98, 0.6))
def _bridge(c, p, s, t, kw):
    """Brücke (rock/steel): Fahrbahn mit drei Bögen und zwei Pfeilern; kw['segments'] 0..3 lässt Segmente von rechts fehlen; schwebt."""
    seg = int(kw.get('segments', 3))
    with c.tf(y=hover(t, kw['ph'], 3)):
        deck = P_rrect(0, -0.16 * s, 0.98 * s, 0.1 * s, 0.03 * s)
        if seg < 3:
            deck = P_inter(deck, P_rrect(-0.49 * s + 0.49 * s * seg / 3, 0, 0.98 * s * seg / 3, 1.0 * s))
        tone(c, deck, p.steel, s, t, ph=kw['ph'], shine=False)
        wall = P_rrect(0, 0.12 * s, 0.98 * s, 0.46 * s, 0.03 * s)
        for i, x in enumerate((-0.32, 0.0, 0.32)):
            wall = P_diff(wall, P_union(P_circle(x * s, 0.14 * s, 0.12 * s), P_rrect(x * s, 0.26 * s, 0.24 * s, 0.24 * s)))
        if seg < 3:
            wall = P_inter(wall, P_rrect(-0.49 * s + 0.49 * s * seg / 3, 0, 0.98 * s * seg / 3, 1.0 * s))
        tone(c, wall, p.rock, s, t, shine=False)
        for x in (-0.16, 0.16):
            if x < -0.49 + 0.98 * seg / 3:
                flat(c, P_rrect(x * s, -0.1 * s, 0.07 * s, 0.14 * s, 0.02 * s), p.steel_dark)


@prop('wheelbarrow', hull=(0.98, 0.7))
def _wheelbarrow(c, p, s, t, kw):
    """Schubkarre: Mulde (steel), Rad dreht, Griffe und Stütze (wood)."""
    c.line(-0.2 * s, 0.1 * s, -0.48 * s, -0.06 * s, p.wood, 0.05 * s)
    c.line(-0.14 * s, 0.14 * s, -0.16 * s, 0.34 * s, p.wood, 0.05 * s)
    tub = P_poly([(-0.3 * s, -0.16 * s), (0.34 * s, -0.16 * s), (0.26 * s, 0.14 * s), (-0.18 * s, 0.14 * s)], 0.04 * s)
    tone(c, tub, p.steel, s, t, ph=kw['ph'], shine=False)
    flat(c, P_rrect(0.02 * s, -0.16 * s, 0.68 * s, 0.06 * s, 0.03 * s), CO.darken(p.steel, 0.2))
    _wheel(c, p, 0.3 * s, 0.26 * s, 0.11 * s, t, kw['ph'])


# ================================================================ Höhle

@prop('helmet_lamp', hull=(0.96, 0.7))
def _helmet_lamp(c, p, s, t, kw):
    """Grubenhelm (accent) mit Krempe und Lampe; der Lichtkegel (glow, additiv) schwenkt leicht."""
    tone(c, P_union(P_pie(0, 0.08 * s, 0.36 * s, 180, 360), P_rrect(0, 0.1 * s, 0.86 * s, 0.1 * s, 0.05 * s)), p.accent, s, t, ph=kw['ph'], shine=False)
    flat(c, P_rrect(0, -0.1 * s, 0.14 * s, 0.14 * s, 0.03 * s), p.steel)
    flat(c, P_circle(0, -0.1 * s, 0.05 * s), p.glow)
    if plain(c):
        a = rock(t, kw['ph'], 8, 0.3)
        with c.tf(rot=a, px=0, py=-0.1 * s):
            c.poly([(0, -0.1 * s), (0.5 * s, -0.5 * s), (0.5 * s, 0.3 * s)], p.glow, 0.25, blend='add')


@prop('flashlight', hull=(0.98, 0.6))
def _flashlight(c, p, s, t, kw):
    """Taschenlampe (steel) mit Lichtkegel (glow alpha 0.25, additiv); der Kegel schwenkt."""
    with c.tf(rot=rock(t, kw['ph'], 4, 0.3)):
        tone(c, P_union(P_rrect(-0.2 * s, 0, 0.46 * s, 0.18 * s, 0.06 * s), P_poly([(0.0, -0.14 * s), (0.14 * s, -0.16 * s), (0.14 * s, 0.16 * s), (0.0, 0.14 * s)], 0.02 * s)), p.steel, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(-0.3 * s, 0, 0.06 * s, 0.14 * s, 0.02 * s), p.dark)
        flat(c, P_rrect(0.14 * s, 0, 0.04 * s, 0.3 * s, 0.015 * s), p.glow)
        if plain(c):
            c.poly([(0.16 * s, -0.15 * s), (0.5 * s, -0.3 * s), (0.5 * s, 0.3 * s), (0.16 * s, 0.15 * s)], p.glow, 0.25, blend='add')


@prop('stalactite_set', hull=(0.98, 0.7))
def _stalactite_set(c, p, s, t, kw):
    """Stalaktiten (rock): Deckenband mit vier abgerundeten Zapfen (4-px-Spitzen); an einem fällt ein Tropfen (water)."""
    tone(c, P_rrect(0, -0.3 * s, 0.98 * s, 0.1 * s, 0.03 * s), p.rock, s, t, ph=kw['ph'], shine=False)
    for (x, h, w) in ((-0.34, 0.3, 0.14), (-0.1, 0.5, 0.18), (0.16, 0.36, 0.14), (0.38, 0.22, 0.1)):
        flat(c, P_poly([((x - w / 2) * s, -0.28 * s), ((x + w / 2) * s, -0.28 * s), (x * s, (-0.28 + h) * s)], 4), p.rock)
    if plain(c):
        u = (t * 0.7 + kw['ph']) % 1.0
        c.circle(-0.1 * s, (0.24 + 0.26 * A.in_quad(u)) * s, 0.03 * s, p.water, 1 - u * 0.6)


@prop('narrow_passage', hull=(0.98, 0.98))
def _narrow_passage(c, p, s, t, kw):
    """Enge Felsspalte: zwei zerklüftete Felswände (rock) mit Spalt kw['gap'] (0..1, Standard 0.25); die Wände atmen minimal."""
    gap = float(kw.get('gap', 0.25)) * 0.5 * s
    for sgn in (-1, 1):
        with c.tf(x=sgn * 0.01 * s * math.sin(TWO_PI * 0.3 * t + kw['ph'])):
            e = [(-0.49, 0.24), (-0.4, 0.06), (-0.3, -0.06), (-0.18, 0.06), (-0.12, 0.22), (0.0, 0.3), (0.06, 0.18), (0.2, 0.1), (0.3, 0.14), (0.42, 0.06), (0.49, 0.12)]
            pts = [(sgn * 0.49 * s, -0.49 * s)] + [(sgn * (gap + 0.12 * s + yy * s * (0.5 if sgn > 0 else 0.5)), xx * s) for xx, yy in e] + [(sgn * 0.49 * s, 0.49 * s)]
            tone(c, P_poly(pts, 0.03 * s), p.rock if sgn < 0 else CO.darken(p.rock, 0.1), s, t, ph=kw['ph'], shine=False)
            if plain(c):
                flat(c, P_poly([(sgn * 0.49 * s, -0.49 * s), (sgn * 0.49 * s, 0.49 * s), (sgn * 0.36 * s, 0.49 * s), (sgn * 0.34 * s, -0.49 * s)]), CO.darken(p.rock, 0.12) if sgn < 0 else CO.darken(p.rock, 0.22))


# ================================================================ Tiere (Baukasten-Teile)

@prop('paw', hull=(0.84, 0.86))
def _paw(c, p, s, t, kw):
    """Pfotenabdruck (Tinte/soft): Ballen und vier Zehen; hüpft."""
    u = (t * 0.8 + kw['ph'] / TWO_PI) % 1.0
    with c.tf(y=-0.06 * s * abs(math.sin(math.pi * u))):
        paw = P_union(P_oval(0, 0.16 * s, 0.26 * s, 0.22 * s), P_circle(-0.3 * s, -0.08 * s, 0.1 * s), P_circle(-0.11 * s, -0.26 * s, 0.11 * s), P_circle(0.11 * s, -0.26 * s, 0.11 * s), P_circle(0.3 * s, -0.08 * s, 0.1 * s))
        tone(c, paw, p.soft, s, t, ph=kw['ph'], shine=False)


@prop('feather', hull=(0.6, 0.98))
def _feather(c, p, s, t, kw):
    """Feder (accent2) mit Kiel (paper) und Kerben; schaukelt beim Fallen."""
    with c.tf(rot=rock(t, kw['ph'], 10, 0.35)):
        plume = P_smooth([(0, -0.48 * s), (0.2 * s, -0.2 * s), (0.16 * s, 0.2 * s), (0, 0.36 * s), (-0.16 * s, 0.2 * s), (-0.2 * s, -0.2 * s)], 0.45)
        notch = P_union(P_poly([(0.2 * s, -0.02 * s), (0.04 * s, 0.04 * s), (0.22 * s, 0.12 * s)]), P_poly([(-0.2 * s, 0.1 * s), (-0.04 * s, 0.16 * s), (-0.2 * s, 0.24 * s)]))
        tone(c, P_diff(plume, notch), p.accent2, s, t, ph=kw['ph'], shine=False)
        c.line(0, -0.3 * s, 0, 0.49 * s, p.paper, 0.03 * s)


@prop('egg', hull=(0.7, 0.9))
def _egg(c, p, s, t, kw):
    """Ei (chalk) mit Sprenkeln; schaukelt sanft um den Fuß, als wolle es schlüpfen."""
    with c.tf(rot=rock(t, kw['ph'], 5, 0.6), px=0, py=0.4 * s):
        egg = P_union(P_circle(0, 0.1 * s, 0.33 * s), P_poly([(-0.3 * s, 0.0), (0.3 * s, 0.0), (0, -0.46 * s)], 0.14 * s))
        tone(c, egg, p.chalk, s, t, ph=kw['ph'])
        for (x, y) in ((-0.1, -0.1), (0.12, 0.0), (-0.02, 0.2)):
            flat(c, P_oval(x * s, y * s, 0.04 * s, 0.03 * s), CO.darken(p.chalk, 0.14))


# ================================================================ Weltraum

@prop('satellite', hull=(0.98, 0.8))
def _satellite(c, p, s, t, kw):
    """Satellit: Korpus (steel), zwei Solarflügel (water) mit Raster, Schüssel; dreht langsam um die Mitte."""
    with c.tf(rot=rock(t, kw['ph'], 10, 0.15)):
        for sgn in (-1, 1):
            c.line(sgn * 0.14 * s, 0, sgn * 0.26 * s, 0, p.steel, 0.04 * s)
            panel = P_rrect(sgn * 0.36 * s, 0, 0.22 * s, 0.34 * s, 0.03 * s)
            tone(c, panel, p.water, s, t, shine=False, shade=False)
            flat(c, P_rrect(sgn * 0.36 * s, 0, 0.02 * s, 0.34 * s), CO.darken(p.water, 0.3))
            flat(c, P_rrect(sgn * 0.36 * s, 0, 0.22 * s, 0.02 * s), CO.darken(p.water, 0.3))
        tone(c, P_rrect(0, 0, 0.26 * s, 0.26 * s, 0.05 * s), p.steel, s, t, ph=kw['ph'])
        c.arc(0, -0.2 * s, 0.12 * s, 180, 360, p.ink, 0.04 * s)
        c.line(0, -0.13 * s, 0, -0.28 * s, p.steel_dark, 0.03 * s)


@prop('space_helmet', hull=(0.9, 0.9))
def _space_helmet(c, p, s, t, kw):
    """Raumhelm: Kugel (chalk) mit Visier (water) und Glanzbogen, Kragen (steel); schwebt."""
    with c.tf(y=hover(t, kw['ph'])):
        tone(c, P_circle(0, -0.04 * s, 0.4 * s), p.chalk, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(0, 0.36 * s, 0.5 * s, 0.14 * s, 0.05 * s), p.steel)
        flat(c, P_inter(P_circle(0, -0.04 * s, 0.32 * s), P_rrect(0.02 * s, 0.0, 0.7 * s, 0.44 * s, 0.14 * s)), p.water)
        if plain(c):
            c.arc(0, -0.04 * s, 0.24 * s, 190, 250, p.white, 0.035 * s, 0.9)


# ================================================================ Geschichte

@prop('sword_shield', hull=(0.98, 0.98))
def _sword_shield(c, p, s, t, kw):
    """Schild (danger mit Altgold-Kreuz) und gekreuztes Schwert (steel, Griff wood); wippt."""
    with c.tf(rot=rock(t, kw['ph'])):
        with c.tf(rot=40):
            c.line(0, -0.46 * s, 0, 0.16 * s, p.steel, 0.07 * s)
            c.line(-0.12 * s, 0.18 * s, 0.12 * s, 0.18 * s, p.gold, 0.05 * s)
            c.line(0, 0.2 * s, 0, 0.4 * s, p.wood, 0.06 * s)
        shield = P_union(P_rrect4(0, -0.12 * s, 0.6 * s, 0.44 * s, (0.08 * s, 0.08 * s, 0.02 * s, 0.02 * s)), P_poly([(-0.3 * s, 0.06 * s), (0.3 * s, 0.06 * s), (0, 0.44 * s)], 0.08 * s))
        tone(c, shield, p.danger, s, t, ph=kw['ph'])
        flat(c, P_rrect(0, 0.0, 0.08 * s, 0.4 * s, 0.03 * s), p.gold)
        flat(c, P_rrect(0, -0.08 * s, 0.34 * s, 0.08 * s, 0.03 * s), p.gold)


@prop('column', hull=(0.6, 0.98))
def _column(c, p, s, t, kw):
    """Antike Säule (paper): Kapitell, kannelierter Schaft, Basis; schwebt."""
    with c.tf(y=hover(t, kw['ph'])):
        tone(c, P_rrect(0, 0, 0.3 * s, 0.76 * s, 0.03 * s), p.paper, s, t, ph=kw['ph'], shine=False)
        for x in (-0.09, 0.0, 0.09):
            flat(c, P_rrect(x * s, 0, 0.03 * s, 0.68 * s, 0.015 * s), CO.darken(p.paper, 0.12))
        flat(c, P_rrect(0, -0.42 * s, 0.5 * s, 0.1 * s, 0.03 * s), CO.darken(p.paper, 0.08))
        flat(c, P_rrect(0, -0.34 * s, 0.38 * s, 0.06 * s, 0.02 * s), CO.darken(p.paper, 0.08))
        flat(c, P_rrect(0, 0.42 * s, 0.5 * s, 0.1 * s, 0.03 * s), CO.darken(p.paper, 0.08))


@prop('ship', hull=(0.98, 0.9))
def _ship(c, p, s, t, kw):
    """Segelschiff: Rumpf (wood), Mast, zwei Segel (chalk) und Wimpel (danger); schaukelt auf der Welle."""
    with c.tf(rot=rock(t, kw['ph'], 4, 0.35), px=0, py=0.3 * s):
        c.line(0.02 * s, 0.2 * s, 0.02 * s, -0.46 * s, p.wood_dark, 0.04 * s)
        flat(c, P_poly([(0.06 * s, -0.42 * s), (0.4 * s, 0.1 * s), (0.06 * s, 0.1 * s)], 0.03 * s), p.chalk)
        flat(c, P_poly([(-0.02 * s, -0.36 * s), (-0.3 * s, 0.1 * s), (-0.02 * s, 0.1 * s)], 0.03 * s), CO.darken(p.chalk, 0.08))
        flat(c, P_poly([(0.02 * s, -0.48 * s), (0.18 * s, -0.44 * s), (0.02 * s, -0.4 * s)], 0.01 * s), p.danger)
        hull_p = P_poly([(-0.46 * s, 0.14 * s), (0.46 * s, 0.14 * s), (0.34 * s, 0.4 * s), (-0.34 * s, 0.4 * s)], 0.06 * s)
        tone(c, hull_p, p.wood, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(0, 0.18 * s, 0.9 * s, 0.05 * s, 0.02 * s), p.wood_dark)


@prop('quill', hull=(0.8, 0.98))
def _quill(c, p, s, t, kw):
    """Schreibfeder (chalk) steckt im Tintenfass (Tinte, Altgold-Deckel); die Feder schreibt (kleines Pendeln)."""
    with c.tf(rot=18 + rock(t, kw['ph'], 4, 0.8), px=0.0, py=0.24 * s):
        plume = P_smooth([(0.02 * s, -0.5 * s), (0.2 * s, -0.3 * s), (0.16 * s, -0.02 * s), (0.02 * s, 0.2 * s), (-0.1 * s, 0.02 * s), (-0.12 * s, -0.26 * s)], 0.45)
        tone(c, plume, p.chalk, s, t, ph=kw['ph'], shine=False)
        c.line(0.02 * s, -0.4 * s, 0.0, 0.28 * s, CO.darken(p.chalk, 0.18), 0.025 * s)
        flat(c, P_poly([(-0.03 * s, 0.14 * s), (0.05 * s, 0.14 * s), (0.0, 0.3 * s)], 0.01 * s), p.gold)
    well = P_rrect4(0.0, 0.34 * s, 0.4 * s, 0.28 * s, (0.04 * s, 0.04 * s, 0.1 * s, 0.1 * s))
    tone(c, well, p.dark, s, t, shine=False)
    flat(c, P_rrect(0.0, 0.2 * s, 0.26 * s, 0.07 * s, 0.03 * s), p.gold)
    flat(c, P_rrect(0.0, 0.36 * s, 0.26 * s, 0.05 * s, 0.02 * s), p.gold)


# ================================================================ Ozean

@prop('submarine', hull=(0.98, 0.6))
def _submarine(c, p, s, t, kw):
    """U-Boot (accent): Rumpf, Turm, Periskop, Bullaugen (water), Schraube dreht."""
    with c.tf(y=hover(t, kw['ph'], 3, 0.4)):
        with c.tf(rot=400 * t, px=-0.46 * s, py=0.04 * s):
            flat(c, P_rrect(-0.46 * s, 0.04 * s, 0.05 * s, 0.22 * s, 0.025 * s), p.steel)
        tone(c, P_union(P_oval(0, 0.04 * s, 0.44 * s, 0.18 * s), P_rrect(0.06 * s, -0.18 * s, 0.2 * s, 0.14 * s, 0.04 * s)), p.accent, s, t, ph=kw['ph'])
        c.line(0.12 * s, -0.24 * s, 0.12 * s, -0.32 * s, p.steel, 0.035 * s)
        c.line(0.12 * s, -0.32 * s, 0.2 * s, -0.32 * s, p.steel, 0.035 * s)
        for x in (-0.18, 0.0, 0.18):
            flat(c, P_circle(x * s, 0.04 * s, 0.06 * s), p.steel)
            flat(c, P_circle(x * s, 0.04 * s, 0.04 * s), p.water)


@prop('anchor', hull=(0.8, 0.98))
def _anchor(c, p, s, t, kw):
    """Anker (steel): Ring, Schaft, Querstock, Bogen mit Flunken; pendelt."""
    with c.tf(rot=rock(t, kw['ph'], 5, 0.35), px=0, py=-0.4 * s):
        c.ring(0, -0.38 * s, 0.08 * s, 0.05 * s, p.steel)
        c.line(0, -0.3 * s, 0, 0.3 * s, p.steel, 0.07 * s)
        c.line(-0.22 * s, -0.16 * s, 0.22 * s, -0.16 * s, p.steel, 0.06 * s)
        c.arc(0, 0.08 * s, 0.36 * s, 20, 160, p.steel, 0.07 * s)
        for sgn in (-1, 1):
            flat(c, P_poly([(sgn * 0.34 * s, 0.2 * s), (sgn * 0.44 * s, 0.1 * s), (sgn * 0.3 * s, 0.1 * s)], 0.02 * s), p.steel)


@prop('bubbles', hull=(0.8, 0.98))
def _bubbles(c, p, s, t, kw):
    """Luftblasen (foam): drei Ringe mit Glanz, steigen in einer Schleife auf."""
    for i, (x, r, sp) in enumerate(((-0.2, 0.16, 0.5), (0.14, 0.11, 0.7), (0.26, 0.07, 0.9))):
        u = (t * 0.25 * sp + kw['ph'] / TWO_PI + i * 0.3) % 1.0
        y = 0.4 * s - 0.8 * s * u
        a = 1.0 if 0.05 < u < 0.9 else 0.0
        if a <= 0:
            continue
        xx = x * s + 0.03 * s * math.sin(TWO_PI * 1.5 * t + i)
        flat(c, P_diff(P_circle(xx, y, r * s), P_circle(xx, y, r * s * 0.68)), p.foam)
        flat(c, P_circle(xx - r * s * 0.4, y - r * s * 0.4, r * s * 0.18), p.white)


@prop('jellyfish', hull=(0.8, 0.98))
def _jellyfish(c, p, s, t, kw):
    """Qualle (accent2): Glocke mit Punkten, vier wogende Tentakel; pulsiert."""
    k = 1 + 0.05 * math.sin(TWO_PI * 0.8 * t + kw['ph'])
    for i, x in enumerate((-0.22, -0.08, 0.08, 0.22)):
        w = math.sin(TWO_PI * 0.8 * t + kw['ph'] + i)
        c.path(smooth_path([(x * s, 0.0), (x * s + 0.04 * s * w, 0.18 * s), (x * s - 0.04 * s * w, 0.34 * s), (x * s + 0.05 * s * w, 0.48 * s)], 0.5, False), CO.darken(p.accent2, 0.08), stroke=0.05 * s)
    with c.tf(sx=k, sy=1 / k, px=0, py=0):
        bell = P_union(P_pie(0, 0.0, 0.38 * s, 180, 360), P_rrect(0, 0.0, 0.76 * s, 0.1 * s, 0.05 * s))
        tone(c, bell, p.accent2, s, t, ph=kw['ph'])
        for (x, y, r) in ((-0.14, -0.18, 0.04), (0.08, -0.24, 0.035), (0.2, -0.1, 0.03)):
            flat(c, P_circle(x * s, y * s, r * s), CO.lighten(p.accent2, 0.3))


@prop('treasure_chest', hull=(0.9, 0.84))
def _treasure_chest(c, p, s, t, kw):
    """Schatztruhe (wood) mit Beschlägen (Altgold), offenem Deckel und funkelnden Münzen (gold)."""
    tone(c, P_rrect4(0, -0.22 * s, 0.84 * s, 0.26 * s, (0.13 * s, 0.13 * s, 0.02 * s, 0.02 * s)), p.wood_dark, s, t, shine=False)
    flat(c, P_rrect(0, -0.12 * s, 0.84 * s, 0.05 * s), p.gold)
    coins = P_union(P_circle(-0.2 * s, -0.04 * s, 0.1 * s), P_circle(0.0, -0.08 * s, 0.11 * s), P_circle(0.2 * s, -0.04 * s, 0.1 * s), P_circle(0.1 * s, 0.0, 0.1 * s))
    flat(c, coins, p.gold)
    tone(c, P_rrect(0, 0.2 * s, 0.84 * s, 0.4 * s, 0.05 * s), p.wood, s, t, ph=kw['ph'], shine=False)
    flat(c, P_rrect(0, 0.04 * s, 0.84 * s, 0.05 * s), p.gold)
    for x in (-0.36, 0.36):
        flat(c, P_rrect(x * s, 0.2 * s, 0.06 * s, 0.4 * s), p.gold)
    flat(c, P_rrect(0, 0.1 * s, 0.12 * s, 0.14 * s, 0.03 * s), p.gold)
    flat(c, P_circle(0, 0.1 * s, 0.025 * s), p.dark)
    if plain(c):
        for i, (x, y) in enumerate(((-0.14, -0.16), (0.16, -0.1))):
            a = max(0.0, math.sin(TWO_PI * 0.65 * t + kw['ph'] + i * math.pi))
            flat(c, P_star(x * s, y * s, 0.09 * s * a, 0.03 * s * a, 4, -90), p.white, a)


# ================================================================ Medizin

@prop('microbe', hull=(0.9, 0.9))
def _microbe(c, p, s, t, kw):
    """Mikrobe (ok): Blob mit Flecken und Augen (Sticker-Weiß), Fortsätze; dreht langsam."""
    with c.tf(rot=20 * t + kw['ph'] * 10):
        for i in range(8):
            a = math.radians(i * 45)
            c.line(0.24 * s * math.cos(a), 0.24 * s * math.sin(a), 0.42 * s * math.cos(a), 0.42 * s * math.sin(a), p.ok, 0.06 * s)
            flat(c, P_circle(0.42 * s * math.cos(a), 0.42 * s * math.sin(a), 0.04 * s), p.ok)
        tone(c, P_circle(0, 0, 0.3 * s), p.ok, s, t, ph=kw['ph'])
        flat(c, P_circle(0.1 * s, 0.1 * s, 0.07 * s), CO.darken(p.ok, 0.15))
        flat(c, P_circle(-0.14 * s, 0.08 * s, 0.04 * s), CO.darken(p.ok, 0.15))
    for x in (-0.08, 0.08):
        flat(c, P_circle(x * s, -0.06 * s, 0.06 * s), p.white)
        flat(c, P_circle(x * s + 0.01 * s, -0.05 * s, 0.03 * s), p.dark)


@prop('stethoscope', hull=(0.9, 0.98))
def _stethoscope(c, p, s, t, kw):
    """Stethoskop (steel): Ohrbügel, Schlauch (Tinte) in U-Form, Bruststück; die Membran wippt."""
    c.path(smooth_path([(-0.3 * s, -0.44 * s), (-0.3 * s, -0.1 * s), (-0.1 * s, 0.1 * s), (0.1 * s, 0.1 * s), (0.3 * s, -0.1 * s), (0.3 * s, -0.44 * s)], 0.5, False), p.dark, stroke=0.05 * s)
    c.path(smooth_path([(0, 0.1 * s), (0.04 * s, 0.24 * s), (0.16 * s, 0.34 * s)], 0.5, False), p.dark, stroke=0.05 * s)
    for x in (-0.3, 0.3):
        flat(c, P_rrect(x * s, -0.44 * s, 0.07 * s, 0.1 * s, 0.03 * s), p.steel)
    with c.tf(rot=rock(t, kw['ph'], 8, 0.5), px=0.16 * s, py=0.34 * s):
        tone(c, P_circle(0.2 * s, 0.38 * s, 0.12 * s), p.steel, s, t, ph=kw['ph'])
        flat(c, P_circle(0.2 * s, 0.38 * s, 0.07 * s), p.steel_dark)


@prop('tooth', hull=(0.8, 0.9))
def _tooth(c, p, s, t, kw):
    """Zahn (chalk): Krone mit zwei Wurzeln, Glanz; wippt."""
    with c.tf(rot=rock(t, kw['ph'], 4)):
        tooth = P_union(P_rrect(0, -0.12 * s, 0.68 * s, 0.56 * s, 0.26 * s), P_oval(-0.17 * s, 0.22 * s, 0.14 * s, 0.26 * s), P_oval(0.17 * s, 0.22 * s, 0.14 * s, 0.26 * s))
        tone(c, tooth, p.chalk, s, t, ph=kw['ph'])
        flat(c, P_oval(0, 0.04 * s, 0.08 * s, 0.1 * s), CO.darken(p.chalk, 0.1))


# ================================================================ Gericht

@prop('scales', hull=(0.98, 0.98))
def _scales(c, p, s, t, kw):
    """Waage (Altgold): Säule, Balken wippt, zwei Schalen (steel) an Schnüren."""
    flat(c, P_rrect(0, 0.42 * s, 0.4 * s, 0.08 * s, 0.03 * s), p.gold)
    c.line(0, 0.4 * s, 0, -0.3 * s, p.gold, 0.06 * s)
    a = rock(t, kw['ph'], 6, 0.3)
    with c.tf(rot=a, px=0, py=-0.3 * s):
        c.line(-0.42 * s, -0.3 * s, 0.42 * s, -0.3 * s, p.gold, 0.05 * s)
        for sgn in (-1, 1):
            x = sgn * 0.4 * s
            with c.tf(rot=-a, px=x, py=-0.3 * s):
                c.line(x, -0.3 * s, x - 0.1 * s, 0.0, p.steel, 0.02 * s)
                c.line(x, -0.3 * s, x + 0.1 * s, 0.0, p.steel, 0.02 * s)
                flat(c, P_pie(x, -0.02 * s, 0.14 * s, 0, 180), p.steel)
    flat(c, P_circle(0, -0.3 * s, 0.05 * s), p.gold)


@prop('gavel', hull=(0.98, 0.84))
def _gavel(c, p, s, t, kw):
    """Richterhammer (wood) mit Block; hämmert in einer weichen Schleife (0.8 Hz)."""
    a = -18 + 14 * math.cos(TWO_PI * 0.8 * t + kw['ph'])
    tone(c, P_rrect(0.2 * s, 0.38 * s, 0.5 * s, 0.1 * s, 0.03 * s), p.wood_dark, s, t, shine=False)
    with c.tf(rot=a, px=0.28 * s, py=0.14 * s):
        c.line(0.28 * s, 0.14 * s, -0.3 * s, 0.14 * s, p.wood, 0.07 * s)
        tone(c, P_rrect(0.24 * s, 0.04 * s, 0.22 * s, 0.4 * s, 0.06 * s), p.wood, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(0.24 * s, 0.04 * s, 0.24 * s, 0.06 * s, 0.02 * s), p.wood_dark)


@prop('file_folder', hull=(0.96, 0.8))
def _file_folder(c, p, s, t, kw):
    """Aktenmappe (accent) mit Reiter und Papieren (chalk), kw['text'] als Etikett (DM Mono, <= 8 Zeichen); schwebt."""
    text = str(kw.get('text', 'CASE 017')).upper()[:8]
    with c.tf(y=hover(t, kw['ph'])):
        flat(c, P_rrect4(-0.2 * s, -0.3 * s, 0.48 * s, 0.16 * s, (0.05 * s, 0.05 * s, 0, 0)), CO.darken(p.accent, 0.12))
        flat(c, P_rrect(0.04 * s, -0.1 * s, 0.76 * s, 0.4 * s, 0.03 * s), p.chalk)
        tone(c, P_rrect(0, 0.08 * s, 0.92 * s, 0.56 * s, 0.05 * s), p.accent, s, t, ph=kw['ph'], shine=False)
        flat(c, P_rrect(0, 0.04 * s, 0.56 * s, 0.1 * s, 0.03 * s), p.chalk)
        c.text(text, 0, 0.04 * s, fit_font(c, text, 'mono', 0.08 * s, 0.5 * s, 1), p.dark, 'center', 'middle', spacing=1)


# ================================================================ Essen

@prop('banana', hull=(0.98, 0.64))
def _banana(c, p, s, t, kw):
    """Banane (accent): dicker Bogen mit dunklerer Kante, Stiel (wood) und Spitze; wippt."""
    with c.tf(rot=rock(t, kw['ph'], 4)):
        c.arc(0, -0.14 * s, 0.4 * s, 25, 155, p.accent, 0.2 * s)
        if plain(c):
            c.arc(0, -0.14 * s, 0.46 * s, 30, 150, CO.darken(p.accent, 0.12), 0.06 * s)
        for ang, col in ((22, p.wood), (158, p.wood_dark)):
            flat(c, P_circle(0.4 * s * math.cos(math.radians(ang)), -0.14 * s + 0.4 * s * math.sin(math.radians(ang)), 0.06 * s), col)


@prop('bread', hull=(0.96, 0.7))
def _bread(c, p, s, t, kw):
    """Brotlaib (wood/paper-Mix) mit drei Einschnitten; wippt."""
    col = CO.hexs(CO.mix(p.paper, p.wood, 0.4))
    with c.tf(rot=rock(t, kw['ph'])):
        loaf = P_union(P_rrect4(0, 0.06 * s, 0.9 * s, 0.5 * s, (0.3 * s, 0.3 * s, 0.1 * s, 0.1 * s)))
        tone(c, loaf, col, s, t, ph=kw['ph'])
        for x in (-0.2, 0.0, 0.2):
            with c.tf(rot=-30, px=x * s, py=-0.1 * s):
                flat(c, P_rrect(x * s, -0.1 * s, 0.04 * s, 0.18 * s, 0.02 * s), CO.lighten(col, 0.25))


@prop('pizza', hull=(0.9, 0.96))
def _pizza(c, p, s, t, kw):
    """Pizzastück: Teigrand (wood/paper), Belag (accent) mit Salami (danger); wippt."""
    crust = CO.hexs(CO.mix(p.paper, p.wood, 0.4))
    with c.tf(rot=rock(t, kw['ph'])):
        slice_p = P_poly([(-0.4 * s, -0.42 * s), (0.4 * s, -0.42 * s), (0, 0.48 * s)], 0.05 * s)
        tone(c, slice_p, p.accent, s, t, ph=kw['ph'], shine=False)
        flat(c, P_inter(slice_p, P_rrect(0, -0.42 * s, 1.0 * s, 0.16 * s)), crust)
        for (x, y, r) in ((-0.12, -0.2, 0.07), (0.12, -0.14, 0.06), (0.0, 0.08, 0.06)):
            flat(c, P_circle(x * s, y * s, r * s), p.danger)
