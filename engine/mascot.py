"""Odd, die Elster: parametrisches Maskottchen des Odd Cabinet (STIL.md Abschnitt 2, design/mascot.json).

Die Figur besteht aus 24 Primitiven (plus zwei Glanzpunkten und bis zu fünf Kostümteilen) und wird komplett aus
Kreisen, Ellipsen, abgerundeten Rechtecken und glatten Pfaden gezeichnet. Einheit ist die Körperhöhe ``size``:
(x, y) ist der Bodenmittelpunkt, der Scheitel liegt bei y - size. Lokale Koordinaten: u nach rechts, v nach oben
negativ (Boden v = 0, Scheitel v = -1.0). 3/4-Ansicht nach rechts, ``flip=True`` spiegelt.

Alles ist eine reine Funktion der Zeit ``t``: Atmen, Blinzeln, Schwanzwedeln und die Pose-Schleifen (Hüpfen in
``cheer``, Beine in ``run``, Fingertippen in ``think``) kommen deterministisch aus ``t`` und ``seed``; es gibt keinen
Zustand zwischen Bildern.

Sticker-Technik (STIL.md 1.2): die Figur wird in drei Durchgängen gezeichnet — Schatten (dy 8, sigma 16, alpha 0.20,
als Union in einem Layer), weißer Rand 14 px (``c.override``), Farbe. ``mode`` wählt den Durchgang, damit Szenen und
Album-Fächer die Figur auch als Silhouette oder nur als Rand zeichnen können.

Winkelkonventionen (Grad): Schwanz positiv = oben (Freude), negativ = unten (Trauer). Flügel 0 = hängt herab,
negativ = nach vorn (zum Schnabel), positiv = nach hinten/oben. Kopfneigung positiv = Schnabel hoch.
Körperneigung positiv = nach vorn gebeugt.
"""
from __future__ import annotations
import contextlib
import math
import os
import skia
from . import anim as A
from . import color as CO
from . import fonts as F
from . import fx
from . import theme as TH
from .canvas import rounded_poly_path, smooth_path

NAME = 'Odd'
LABEL = 'ODD · Pica pica · Exhibit No. 0'

POSES = ['idle', 'point', 'think', 'shock', 'laugh', 'sneak', 'peek', 'bow', 'cheer', 'facepalm', 'wink', 'fly', 'run', 'hide']
EXPRS = ['neutral', 'smile', 'smirk', 'surprised', 'worried', 'angry', 'sleepy', 'sly']
COSTUMES = ['default', 'thief', 'miner', 'explorer', 'astronaut', 'historian', 'diver', 'doctor', 'detective', 'chef']

# Thema -> Kostüm (STIL.md 2.4); im Skript überschreibbar ("mascot": {"costume": "chef"})
THEME_COSTUME = {
    'curious': 'default', 'heist': 'thief', 'cave': 'miner', 'animal': 'explorer', 'space': 'astronaut',
    'history': 'historian', 'ocean': 'diver', 'medical': 'doctor', 'crime': 'detective', 'food': 'chef',
}
COSTUME_THEME = {v: k for k, v in THEME_COSTUME.items()}

SIZE_DEFAULT = 400.0                 # Standardgröße Hochformat
RIM_PX = 14.0                        # Sticker-Rand bei size 400 (STIL.md 1.2)
RIM_MIN = 4.0
SHADOW = (8.0, 16.0, 0.20)           # dy, sigma, alpha des Sticker-Schattens
FLOOR_SHADOW_ALPHA = 0.25
DETAIL_MIN = 140.0                   # darunter ohne Glanzpunkt und Wange
DEFAULT_HEAD_TURN = 0.0              # 0 = 3/4-Ansicht (ein Auge sichtbar), 1 = frontal (beide Augen)

# Anker für Kostüme und Szenen (lokale Einheiten, Kopfteile vor der Kopfneigung)
ANCHORS = {'hat': (0.14, -1.00), 'face': (0.24, -0.80), 'neck': (0.08, -0.56), 'back': (-0.20, -0.50), 'beak_tip': (0.56, -0.77)}
WING_PIVOT = (-0.06, -0.58)
WING_BACK_PIVOT = (-0.04, -0.60)
WING_LEN = 0.42
WING_REST = 5.0                      # Ruhewinkel des nahen Flügels (hängt knapp hinter dem Bauch)
TAIL_PIVOT = (-0.25, -0.44)
TAIL_LEN = 0.36
HEAD_C = (0.14, -0.76)
NECK = (0.08, -0.56)

# Drei-Hebel-Mimik (STIL.md 2.2): Lider, Brauen, Schnabel; Schwanz als vierte Nadel
EXPRESSIONS = {
    'neutral':   dict(lid_top=0.0, lid_bottom=0.0, brow_l=0, brow_r=0, beak_open=0, beak_top_rot=0, pupil=1.0, eye_scale=1.0, cheek=0.0, tail=-30),
    'smile':     dict(lid_top=0.0, lid_bottom=0.15, brow_l=8, brow_r=8, beak_open=4, beak_top_rot=-6, pupil=1.1, eye_scale=1.0, cheek=0.3, tail=-10),
    'smirk':     dict(lid_top=0.35, lid_bottom=0.0, brow_l=18, brow_r=-4, beak_open=6, beak_top_rot=-4, pupil=1.0, eye_scale=1.0, cheek=0.2, tail=-15),
    'surprised': dict(lid_top=0.0, lid_bottom=0.0, brow_l=25, brow_r=25, beak_open=30, beak_top_rot=0, pupil=0.8, eye_scale=1.15, cheek=0.0, tail=20),
    'worried':   dict(lid_top=0.2, lid_bottom=0.0, brow_l=20, brow_r=-12, beak_open=8, beak_top_rot=0, pupil=1.0, eye_scale=1.0, look=(0.2, -0.5), cheek=0.0, tail=-40),
    'angry':     dict(lid_top=0.4, lid_bottom=0.0, brow_l=-25, brow_r=-25, beak_open=0, beak_top_rot=0, pupil=0.9, eye_scale=1.0, cheek=0.0, tail=10),
    'sleepy':    dict(lid_top=0.65, lid_bottom=0.1, brow_l=0, brow_r=0, beak_open=2, beak_top_rot=0, pupil=1.1, eye_scale=1.0, cheek=0.0, tail=-40),
    'sly':       dict(lid_top=0.5, lid_bottom=0.0, brow_l=-10, brow_r=-10, beak_open=6, beak_top_rot=-4, pupil=1.0, eye_scale=1.0, look=(0.8, 0.0), cheek=0.2, tail=0),
}

# Standard-Ausdruck je Pose (gilt, wenn expr=None; die Pose darf einzelne Hebel anpassen)
POSE_EXPR = {
    'idle': 'neutral', 'point': 'smile', 'think': 'neutral', 'shock': 'surprised', 'laugh': 'smile', 'sneak': 'sly',
    'peek': 'surprised', 'bow': 'sleepy', 'cheer': 'smile', 'facepalm': 'sleepy', 'wink': 'smirk', 'fly': 'neutral',
    'run': 'neutral', 'hide': 'neutral',
}

# Tropfenform des Flügels: (entlang, quer) in Einheiten; Flügel hängt bei Winkel 0 nach unten
WING_PTS = [(-0.05, 0.0), (0.035, -0.115), (0.19, -0.105), (0.42, 0.0), (0.19, 0.105), (0.035, 0.115)]


# ---------------------------------------------------------------------------------------------------------------
# Zeitfunktionen
# ---------------------------------------------------------------------------------------------------------------

def _hash(seed, i) -> float:
    """Deterministische Pseudozufallszahl 0..1 aus seed und Index."""
    x = math.sin(float(seed) * 12.9898 + float(i) * 78.233 + 1.37) * 43758.5453
    return x - math.floor(x)


def blink(t, seed=0, double=False, close=0.12, open_=0.09) -> float:
    """Lidschluss 0..1 zur Zeit t: Blinzeln alle 2.5 + 2.5·hash(seed, i) Sekunden, Schließen 120 ms, Öffnen 90 ms;
    ``double`` setzt 260 ms nach jedem Blinzeln ein zweites (think / worried). Reine Funktion von t."""
    if t < 0:
        return 0.0
    b, i, last = 0.0, 0, -10.0
    while i < 100000:
        b += 2.5 + 2.5 * _hash(seed, i)
        if b > t:
            break
        last = b
        i += 1
    dur = close + open_
    best = 0.0
    for b0 in ((last, last + 0.26) if double else (last,)):
        p = t - b0
        if 0.0 <= p < dur:
            v = A.in_out_sine(p / close) if p < close else 1.0 - A.in_out_sine((p - close) / open_)
            best = max(best, v)
    return best


def _breathe(t, hz=0.4, amp=0.015, seed=0) -> float:
    """Atmen: Skalierung 1 ± amp bei hz Hertz, Phase aus seed."""
    return 1.0 + amp * math.sin(2 * math.pi * hz * t + seed * 0.7)


def _wing_tip(pivot, angle, length=WING_LEN):
    a = math.radians(angle)
    return (pivot[0] - length * math.sin(a), pivot[1] + length * math.cos(a))


# ---------------------------------------------------------------------------------------------------------------
# Pose -> Parametersatz (reine Funktion von t)
# ---------------------------------------------------------------------------------------------------------------

def _base_state() -> dict:
    return dict(
        body_tilt=0.0, body_sy=1.0, body_dy=0.0, body_jitter=0.0, lift=0.0,
        head_tilt=0.0, head_turn=DEFAULT_HEAD_TURN, head_dy=0.0,
        wing=WING_REST, wing_back=None, tail=None, tail_wag=0.0,
        leg_len=1.0, leg_swing=(0.0, 0.0), leg_lift=(0.0, 0.0), foot_shift=(0.0, 0.0), feet_tuck=0.0,
        shake=(0.0, 0.0), crest=0.0, visible=None, hide_v=None, wing_front=False,
        breathe_hz=0.4, breathe_amp=0.015, cam=0.0,
        lid_top=0.0, lid_bottom=0.0, lid_near=None, brow_l=0.0, brow_r=0.0, beak_open=0.0, beak_top_rot=0.0,
        pupil=1.0, eye_scale=1.0, cheek=0.0, look=(0.0, 0.0), sheen=None, hat_in_hand=False, blink=True, double_blink=False,
    )


def _pose_params(pose, t, t0, seed) -> tuple:
    """Pose-abhängige Parameter als (P, face): P = Körper, face = Mimik-Anpassungen der Pose (nur bei expr=None)."""
    P = _base_state()
    f = {}
    u = t - t0
    if pose == 'idle':
        P['head_tilt'] = 6.0 + A.wobble(t, 0.3, 1.5, seed)
        P['tail_wag'] = 6.0 * A.osc(t, 0.5, seed)
        f['pupil'] = 1.2
        ph = (t / 1.8) % 3.0                      # jede dritte 1.8-s-Phase zur Kamera
        P['cam'] = A.smoothstep((ph - 2.0) / 0.2) * (1.0 - A.smoothstep((ph - 2.75) / 0.2))
    elif pose == 'point':
        sp = A.spring(u + 0.02, 0.0, 400.0, 12.0)
        P['wing'] = WING_REST - (70.0 + WING_REST) * sp + 2.0 * A.osc(t, 0.5, seed)
        P['body_tilt'] = 6.0
        P['head_tilt'] = 4.0
        P['foot_shift'] = (0.0, 0.03)
        f.update(brow_l=15, brow_r=8)
    elif pose == 'think':
        P['wing'] = -92.0 + 3.0 * abs(math.sin(2 * math.pi * 1.5 * t))      # Flügelspitze tippt unter dem Schnabel
        P['head_tilt'] = -8.0
        P['tail'] = -30.0 + 8.0 * math.tanh(5.0 * math.sin(2 * math.pi * 1.0 * t))
        P['double_blink'] = True
        f.update(brow_l=-12, brow_r=18, lid_top=0.45, beak_open=0, beak_top_rot=0, pupil=1.0, cheek=0.0, look=(0.4, -0.5))
    elif pose == 'shock':
        kf = A.Keyframes([(0.0, 1.0), (0.06, 0.85), (0.18, 1.18), (0.34, 1.0)], 'out_back')
        P['body_sy'] = kf.at(u) if u >= 0 else 1.0
        P['shake'] = A.shake(t, t0, 0.2, 8.0, seed=seed)
        P['crest'] = A.pop(t, t0, 0.2, 1.2) if u >= 0 else 0.0
        P['wing'] = 150.0 + 3.0 * A.osc(t, 7.0)
        P['wing_back'] = 122.0 - 3.0 * A.osc(t, 7.0)
        P['head_turn'] = 1.0
        P['head_tilt'] = 4.0
        P['tail'] = 30.0
        f.update(beak_open=35, pupil=0.7, eye_scale=1.15, brow_l=25, brow_r=25, lid_top=0.0, lid_bottom=0.0, cheek=0.0)
    elif pose == 'laugh':
        P['wing'] = -90.0 + 3.0 * A.osc(t, 8.0)
        P['body_jitter'] = 2.0 * A.osc(t, 8.0)
        P['body_dy'] = -0.02 * abs(math.sin(2 * math.pi * 4.0 * t))
        P['head_tilt'] = 8.0
        P['head_turn'] = 1.0
        P['tail'] = 20.0
        f.update(lid_bottom=0.4, beak_open=10.0 + 4.0 * abs(A.osc(t, 8.0)), beak_top_rot=-6, cheek=0.4, brow_l=10, brow_r=10, pupil=1.1)
    elif pose == 'sneak':
        step = 2 * math.pi * 1.6 * t
        P['body_tilt'] = 10.0
        P['head_tilt'] = -6.0
        P['leg_len'] = 1.2
        P['body_dy'] = -0.03 * abs(math.sin(step))
        P['leg_lift'] = (0.05 * max(0.0, math.sin(step)), 0.05 * max(0.0, -math.sin(step)))
        P['leg_swing'] = (14.0 * math.sin(step), -14.0 * math.sin(step))
        P['wing'] = -20.0
        P['tail'] = -40.0
        f.update(lid_top=0.5, look=(0.9, 0.0), beak_open=0, brow_l=-6, brow_r=-6, pupil=1.0, cheek=0.0)
    elif pose == 'peek':
        P['visible'] = {'head', 'wing'}
        P['wing'] = 150.0 + 4.0 * A.osc(t, 0.6)
        P['head_turn'] = 1.0
        P['head_tilt'] = 8.0 + A.wobble(t, 0.3, 2.0, seed)
        P['breathe_amp'] = 0.0
        f.update(pupil=1.4, brow_l=20, brow_r=20, beak_open=4, beak_top_rot=-4, lid_top=0.0, look=(0.0, 0.0), cheek=0.2)
    elif pose == 'bow':
        P['wing'] = -52.0
        P['head_tilt'] = -15.0
        P['tail'] = -45.0
        P['breathe_hz'] = 0.25
        P['hat_in_hand'] = True
        P['sheen'] = 0.4
        f.update(lid_top=0.6, lid_bottom=0.0, brow_l=4, brow_r=4, beak_open=0, beak_top_rot=0, pupil=1.0, cheek=0.0, look=(0.1, 0.4))
    elif pose == 'cheer':
        hop = abs(math.sin(2 * math.pi * 2.0 * t))
        P['body_dy'] = -0.05 * hop
        P['body_sy'] = 0.95 + 0.09 * hop
        P['wing'] = 158.0 + 10.0 * A.osc(t, 2.0)
        P['wing_back'] = 128.0 - 10.0 * A.osc(t, 2.0)
        P['feet_tuck'] = 0.5 * hop
        P['head_turn'] = 1.0
        P['head_tilt'] = 6.0
        P['tail'] = 30.0
        f.update(beak_open=12, beak_top_rot=-6, lid_bottom=0.15, brow_l=12, brow_r=12, cheek=0.3, pupil=1.1)
    elif pose == 'facepalm':
        P['wing'] = -124.0 + 1.5 * A.osc(t, 0.4)
        P['wing_front'] = True
        P['head_tilt'] = -10.0
        P['tail'] = -35.0
        f.update(lid_top=0.6, brow_l=-8, brow_r=12, beak_open=2, beak_top_rot=0, pupil=1.0, cheek=0.0, look=(0.0, 0.5))
    elif pose == 'wink':
        ph = u % 2.6
        P['lid_near'] = 1.0 if 0.0 <= ph < 0.3 else None
        P['head_tilt'] = 8.0
        P['head_turn'] = 1.0
        P['wing'] = -62.0 + 3.0 * A.osc(t, 0.8)
        P['tail'] = -5.0
        f.update(lid_top=0.2, brow_l=18, brow_r=-4, beak_open=6, beak_top_rot=-6, pupil=1.0, cheek=0.3)
    elif pose == 'fly':
        flap = math.sin(2 * math.pi * 6.0 * t)
        P['wing'] = 95.0 + 55.0 * flap
        P['wing_back'] = 80.0 - 55.0 * flap
        P['body_tilt'] = 12.0
        P['body_dy'] = -0.10 + 0.012 * flap
        P['leg_len'] = 0.6
        P['leg_swing'] = (38.0, 38.0)
        P['feet_tuck'] = 1.0
        P['tail'] = 12.0
        P['breathe_amp'] = 0.0
        f.update(beak_open=4, brow_l=6, brow_r=6, pupil=1.0, lid_top=0.1)
    elif pose == 'run':
        ph = 2 * math.pi * 4.0 * t
        P['wing'] = 40.0 + 12.0 * math.sin(ph)
        P['wing_back'] = 36.0 - 12.0 * math.sin(ph)
        P['body_tilt'] = 12.0
        P['body_dy'] = -0.02 * abs(math.sin(ph))
        P['leg_swing'] = (32.0 * math.sin(ph), -32.0 * math.sin(ph))
        P['leg_lift'] = (0.05 * max(0.0, -math.cos(ph)), 0.05 * max(0.0, math.cos(ph)))
        P['tail'] = 15.0
        P['breathe_amp'] = 0.0
        f.update(beak_open=6, brow_l=6, brow_r=6, pupil=1.0, lid_top=0.05)
    elif pose == 'hide':
        P['visible'] = {'head', 'tail'}
        P['hide_v'] = -0.71
        P['head_turn'] = 1.0
        P['tail'] = -30.0 + 4.0 * A.osc(t, 0.5, seed)
        f.update(pupil=1.3, brow_l=14, brow_r=14, lid_top=0.0, look=(0.0, -0.1))
    return P, f


def state(pose='idle', expr=None, t=0.0, look=(0.0, 0.0), seed=0, t0=0.0, respect=False, **kw) -> dict:
    """Vollständiger Parametersatz der Figur zur Zeit t (Pose-Schleife, Ausdruck, Blinzeln, Atmen).
    expr=None nimmt den Standard-Ausdruck der Pose samt ihrer Anpassungen; ein expliziter Ausdruck gewinnt über die
    Mimik der Pose. ``kw`` überschreibt einzelne Schlüssel (z. B. head_turn=1, tail=20, lid_top=0.3). Reine Funktion von t."""
    if pose not in POSES:
        pose = 'idle'
    P, pose_face = _pose_params(pose, float(t), float(t0), seed)
    explicit = expr in EXPRESSIONS
    name = expr if explicit else POSE_EXPR.get(pose, 'neutral')
    face = dict(EXPRESSIONS[name])
    if not explicit:
        face.update(pose_face)
    for k, v in face.items():
        if k != 'tail':
            P[k] = v
    if P['tail'] is None or explicit and pose in ('idle', 'point', 'wink'):
        P['tail'] = float(face['tail']) + P['tail_wag']
    if look is not None and (look[0] != 0.0 or look[1] != 0.0):
        P['look'] = (float(look[0]), float(look[1]))
    cam = P['cam']
    if cam > 0:                                   # Blick zur Kamera: Pupillen mittig, zweites Auge einblenden
        lx, ly = P['look']
        P['look'] = (lx * (1 - cam), ly * (1 - cam))
        P['head_turn'] = P['head_turn'] + (1.0 - P['head_turn']) * cam
    if respect:
        P['sheen'] = 0.4 if P['sheen'] is None else P['sheen']
        P['cheek'] = 0.0
    for k, v in kw.items():
        if k in P:
            P[k] = v
    P['pose'] = pose
    P['expr'] = name
    if P['blink']:
        P['lid_top'] = max(float(P['lid_top']), blink(float(t), seed, P['double_blink']))
    P['breathe'] = _breathe(float(t), P['breathe_hz'], P['breathe_amp'], seed)
    P['lift'] = 0.19 * (float(P['leg_len']) - 1.0)
    return P


# ---------------------------------------------------------------------------------------------------------------
# Geometrie-Helfer: lokale Einheiten -> Pixel
# ---------------------------------------------------------------------------------------------------------------

class _G:
    """Zeichnet in lokalen Einheiten (u, v) auf ein Canvas in Pixeln: Bodenmitte (x0, y0), Maßstab S = size.
    mode 'color' zeichnet normal; 'rim' / 'shadow' / 'silhouette' (flat) lassen Transparenzen und Glow weg."""

    def __init__(self, c, x0, y0, S, mode='color'):
        self.c, self.x0, self.y0, self.S = c, float(x0), float(y0), float(S)
        self.mode = mode
        self.flat = mode != 'color'

    def P(self, u, v):
        return (self.x0 + u * self.S, self.y0 + v * self.S)

    def circle(self, u, v, r, col, **kw):
        x, y = self.P(u, v)
        self.c.circle(x, y, r * self.S, col, **kw)

    def ellipse(self, u, v, rx, ry, col, rot=0.0, **kw):
        x, y = self.P(u, v)
        self.c.ellipse(x, y, rx * self.S, ry * self.S, col, rot=rot, **kw)

    def rrect(self, u, v, w, h, r, col, rot=0.0, **kw):
        x, y = self.P(u, v)
        self.c.rect_c(x, y, w * self.S, h * self.S, col, r=r * self.S, rot=rot, **kw)

    def line(self, u0, v0, u1, v1, w, col, **kw):
        x0, y0 = self.P(u0, v0)
        x1, y1 = self.P(u1, v1)
        self.c.line(x0, y0, x1, y1, col, w * self.S, **kw)

    def polyline(self, pts, w, col, **kw):
        self.c.polyline([self.P(u, v) for u, v in pts], col, w * self.S, **kw)

    def curve(self, pts, w, col, tension=0.6, **kw):
        self.c.smooth_poly([self.P(u, v) for u, v in pts], col, stroke=w * self.S, tension=tension, closed=False, **kw)

    def path(self, path, col, **kw):
        self.c.path(path, col, **kw)

    def rpoly(self, pts, r, col, **kw):
        self.c.path(self.rpoly_path(pts, r), col, **kw)

    def rpoly_path(self, pts, r) -> skia.Path:
        return rounded_poly_path([self.P(u, v) for u, v in pts], r * self.S)

    def tri(self, u, v, size, col, rot=0.0, r=0.015, **kw):
        """Abgerundetes gleichschenkliges Dreieck (Spitze oben) um (u, v)."""
        h = size * 0.9
        pts = [(u, v - h * 0.6), (u + size * 0.5, v + h * 0.4), (u - size * 0.5, v + h * 0.4)]
        with self.tf(rot=rot, pivot=(u, v)):
            self.rpoly(pts, r, col, **kw)

    def hexagon(self, u, v, r, col, rot=30.0, **kw):
        x, y = self.P(u, v)
        self.c.regular(x, y, r * self.S, 6, col, rot=rot, **kw)

    def arc(self, u, v, r, a0, a1, w, col, **kw):
        x, y = self.P(u, v)
        self.c.arc(x, y, r * self.S, a0, a1, col, width=w * self.S, **kw)

    def tf(self, rot=0.0, pivot=(0.0, 0.0), sx=1.0, sy=None, du=0.0, dv=0.0):
        px, py = self.P(*pivot)
        return self.c.tf(x=du * self.S, y=dv * self.S, rot=rot, sx=sx, sy=sy, px=px, py=py)

    def circle_path(self, u, v, r) -> skia.Path:
        p = skia.Path()
        x, y = self.P(u, v)
        p.addCircle(x, y, r * self.S)
        return p

    def ellipse_path(self, u, v, rx, ry, rot=0.0) -> skia.Path:
        p = skia.Path()
        x, y = self.P(u, v)
        p.addOval(skia.Rect.MakeLTRB(x - rx * self.S, y - ry * self.S, x + rx * self.S, y + ry * self.S))
        if rot:
            p.transform(skia.Matrix.RotateDeg(float(rot), skia.Point(x, y)))
        return p

    def rect_path(self, u, v, w, h) -> skia.Path:
        p = skia.Path()
        x, y = self.P(u, v)
        p.addRect(skia.Rect.MakeXYWH(x, y, w * self.S, h * self.S))
        return p

    def smooth_pts_path(self, pts) -> skia.Path:
        return smooth_path([self.P(u, v) for u, v in pts], 0.5, True)

    def clip(self, path):
        return self.c.clip_path(path)


# ---------------------------------------------------------------------------------------------------------------
# Die Figur
# ---------------------------------------------------------------------------------------------------------------

def _draw_wing(g, pivot, angle, col, band_col, sheen_col, sheen_alpha, detail, scale=1.0):
    """Flügel (Tropfen) mit Elfenbein-Band und Elsterblau-Schimmer, beides auf die Flügelform geclippt."""
    pts = [(pivot[0] + q * scale, pivot[1] + a * scale) for a, q in WING_PTS]
    with g.tf(rot=angle, pivot=pivot):
        path = g.smooth_pts_path(pts)
        g.path(path, col)
        with g.clip(path):
            g.rrect(pivot[0] + 0.01 * scale, pivot[1] + 0.15 * scale, 0.15 * scale, 0.065 * scale, 0.0325 * scale, band_col)
            if detail:
                g.ellipse(pivot[0] - 0.03 * scale, pivot[1] + 0.28 * scale, 0.045 * scale, 0.07 * scale, sheen_col, alpha=sheen_alpha)


def _draw_leg(g, side, P, col, w=0.026):
    """Bein (Rundlinie) mit Λ-Fuß (drei Zehen angedeutet); side -1 = hinten, +1 = vorn.
    Die Füße bleiben am Boden, der Körper hebt sich mit leg_len; leg_lift / leg_swing für Schritte."""
    i = 0 if side < 0 else 1
    hip = (0.09 * side, -0.19 - P['lift'])
    tuck = float(P['feet_tuck'])
    ankle = (0.10 * side + P['foot_shift'][i], -0.03 - P['leg_lift'][i])
    if tuck > 0:
        ankle = (ankle[0], hip[1] + (ankle[1] - hip[1]) * (1.0 - 0.45 * tuck))
    with g.tf(rot=P['leg_swing'][i], pivot=hip):
        g.line(hip[0], hip[1], ankle[0], ankle[1], w, col)
        toe = 0.03 * (1.0 - tuck)
        g.polyline([(ankle[0] - 0.06, ankle[1] + toe), (ankle[0], ankle[1]), (ankle[0] + 0.06, ankle[1] + toe)], w, col)


def _eye(g, eu, ev, r, P, th, detail, lid_near=None, alpha=1.0):
    """Auge: Weiß, Pupille mit Glanzpunkt, Ober- und Unterlid in Kopffarbe innerhalb des Augenclips."""
    if alpha <= 0.01:
        return
    main, dark, white = th['mascot_main'], th['mascot_dark'], th['line']
    k = r / 0.07
    pr = 0.033 * float(P['pupil']) * k
    g.circle(eu, ev, r, white, alpha=alpha)
    with g.clip(g.circle_path(eu, ev, r)):
        lx, ly = P['look']
        pu, pv = eu + lx * 0.042 * k, ev + ly * 0.042 * k
        g.circle(pu, pv, pr, dark, alpha=alpha)
        if detail and not g.flat:
            g.circle(pu - pr * 0.36, pv - pr * 0.36, 0.011 * k, white, alpha=alpha)
        lt = float(P['lid_top']) if lid_near is None else max(float(P['lid_top']), float(lid_near))
        lb = float(P['lid_bottom'])
        if lt > 0.001:
            g.rrect(eu, ev - r + lt * r, 2 * r + 0.02, 2 * r, 0.0, main, alpha=alpha)
        if lb > 0.001:
            g.rrect(eu, ev + 2 * r - lb * r, 2 * r + 0.02, 2 * r, 0.0, main, alpha=alpha)


def _brow(g, eu, ev, angle, col, alpha=0.9):
    """Elfenbein-Braue 0.12 x 0.03, 0.11 über dem Auge; positiv = zum Schnabel hin angehoben."""
    g.rrect(eu, ev - 0.11, 0.12, 0.03, 0.015, col, rot=-angle, alpha=alpha)


def _figure(g, P, th, costume, t, detail=True):
    """Zeichnet alle Teile in Zeichenreihenfolge (STIL.md 2.1) in lokalen Einheiten um den Bodenpunkt (0, 0)."""
    main, dark, light = th['mascot_main'], th['mascot_dark'], th['mascot_light']
    sheen, beak = th['mascot_sheen'], th['mascot_beak']
    vis = P['visible']
    flat = g.flat

    def on(part):
        return vis is None or part in vis

    hi_col = CO.lighten(main, 0.10)
    hi_alpha = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(2 * math.pi * 1.3 * t))
    sheen_alpha = P['sheen'] if P['sheen'] is not None else 0.6 + 0.4 * (0.5 + 0.5 * math.sin(2 * math.pi * 1.3 * t + 1.0))
    if P['expr'] == 'surprised':
        sheen_alpha = 1.0
    if flat:
        sheen_alpha = 1.0
    parts = _costume_parts(costume, th, t)
    hip = (0.0, -0.19 - P['lift'])

    def body_group():
        return g.tf(rot=P['body_tilt'] + P['body_jitter'], pivot=hip, dv=P['body_dy'] - P['lift'])

    with body_group():
        if on('tail'):                                      # 1-2 Schwanz mit Spitze
            with g.tf(rot=P['tail'], pivot=TAIL_PIVOT):
                g.rrect(TAIL_PIVOT[0] - TAIL_LEN / 2, TAIL_PIVOT[1], TAIL_LEN, 0.10, 0.05, main)
                g.ellipse(TAIL_PIVOT[0] - TAIL_LEN + 0.04, TAIL_PIVOT[1], 0.065, 0.05, sheen, alpha=sheen_alpha)
        if on('wing') and P['wing_back'] is not None:       # 3 Flügel fern
            _draw_wing(g, WING_BACK_PIVOT, P['wing_back'], dark, CO.mix(light, dark, 0.35), sheen, sheen_alpha * 0.8, detail, 0.95)
    if on('legs'):                                          # 4-7 Beine, Füße (bleiben am Boden)
        with g.tf(dv=P['body_dy'] if P['feet_tuck'] > 0 else 0.0):
            _draw_leg(g, -1, P, beak)
            _draw_leg(g, +1, P, beak)
    with body_group():
        if on('body'):                                      # 8 Körper, 9 Bauch, 10 Kragen, Glanzpunkt
            body_path = g.ellipse_path(0.0, -0.42, 0.31, 0.25, -10.0)
            g.path(body_path, main)
            with g.clip(body_path):
                g.ellipse(0.06, -0.36, 0.20, 0.17, light)
                ca = g.circle_path(0.10, -0.58, 0.17)
                cb = g.circle_path(0.16, -0.63, 0.17)
                g.path(skia.Op(ca, cb, skia.PathOp.kDifference_PathOp), light)
                if detail and not flat:
                    g.ellipse(-0.20, -0.56, 0.055, 0.032, hi_col, rot=-30.0, alpha=hi_alpha)
            for fn in parts.get('back', []):
                fn(g, P)
        if on('wing') and not P['wing_front']:              # 11-13 Flügel nah mit Band und Schimmer
            _draw_wing(g, WING_PIVOT, P['wing'], main, light, sheen, sheen_alpha, detail)
        if on('head'):                                      # 14-24 Kopf
            _head(g, P, th, parts, t, detail, hi_col, hi_alpha)
        if on('wing') and P['wing_front']:                  # Flügel vor dem Gesicht (facepalm): dunklerer Ton hebt ihn vom Kopf ab
            _draw_wing(g, WING_PIVOT, P['wing'], dark if not flat else main, light, sheen, sheen_alpha, detail)
        if on('wing'):                                      # Kostüm an der Flügelspitze (Lupe, Löffel, Hut in bow)
            hand = _wing_tip(WING_PIVOT, P['wing'])
            ang = P['wing']
            for fn in parts.get('hand', []):
                fn(g, P, hand, ang)
            if P['hat_in_hand'] and parts.get('removable'):
                for fn in parts.get('hat', []):
                    with g.tf(rot=ang + 165.0, pivot=hand):
                        with g.tf(du=hand[0] - ANCHORS['hat'][0], dv=hand[1] - ANCHORS['hat'][1] + 0.05):
                            fn(g, P)


def _head(g, P, th, parts, t, detail, hi_col, hi_alpha):
    """Kopfgruppe: Kreis, Glanz, Kostüm im Gesicht, Wange, Schnabel, Augen, Lider, Brauen, Scheitelfedern, Hut."""
    main, dark, light = th['mascot_main'], th['mascot_dark'], th['mascot_light']
    beak = th['mascot_beak']
    danger = th.get('danger', '#F0634A')
    turn = max(0.0, min(1.0, float(P['head_turn'])))
    hdy = float(P['head_dy'])
    hc = (HEAD_C[0], HEAD_C[1] + hdy)
    hide_v = P['hide_v']
    with g.tf(rot=-float(P['head_tilt']), pivot=NECK):
        with (g.clip(g.rect_path(-1.5, -2.0, 3.0, 2.0 + hide_v)) if hide_v is not None else contextlib.nullcontext()):
            g.circle(hc[0], hc[1], 0.24, main)
            if detail and not g.flat:
                g.ellipse(hc[0] - 0.11, hc[1] - 0.13, 0.058, 0.034, hi_col, rot=-35.0, alpha=hi_alpha)
            for fn in parts.get('face', []):
                fn(g, P)
            cheek = float(P['cheek'])
            if detail and cheek > 0.01 and not g.flat:
                g.ellipse(0.27 - 0.05 * turn, -0.69 + hdy, 0.045, 0.025, danger, alpha=min(0.4, cheek))
            # 16-18 Schnabel (Pivot folgt head_turn)
            bp = (0.35 - 0.06 * turn, -0.77 + hdy)
            bo = float(P['beak_open'])
            lower = [(bp[0], bp[1]), (bp[0] + 0.19, bp[1] + 0.02), (bp[0], bp[1] + 0.06)]
            with g.tf(rot=bo, pivot=bp):
                g.rpoly(lower, 0.015, dark)
                if bo > 20 and not g.flat:
                    with g.clip(g.rpoly_path(lower, 0.015)):
                        g.circle(bp[0] + 0.055, bp[1] + 0.055, 0.035, danger)
            with g.tf(rot=float(P['beak_top_rot']), pivot=bp):
                g.rpoly([(bp[0], bp[1] - 0.052), (bp[0] + 0.21, bp[1]), (bp[0], bp[1] + 0.025)], 0.02, beak)
            # 19-22 Augen (fern dann nah)
            es = float(P['eye_scale'])
            near = (0.24 - 0.05 * turn, -0.80 + hdy)
            far = (0.05, -0.80 + hdy)
            _eye(g, far[0], far[1], 0.06 * es, P, th, detail, None, alpha=turn)
            _eye(g, near[0], near[1], 0.07 * es, P, th, detail, P['lid_near'])
            # 23 Brauen
            _brow(g, near[0], near[1], float(P['brow_l']), light, 0.9)
            if turn > 0.01:
                _brow(g, far[0], far[1], float(P['brow_r']), light, 0.9 * turn)
            # 24 Scheitelfedern (shock)
            cr = float(P['crest'])
            if cr > 0.01:
                for du, rot in ((-0.075, -22.0), (0.0, 0.0), (0.075, 22.0)):
                    with g.tf(sx=cr, pivot=(hc[0] + du, hc[1] - 0.22)):
                        g.tri(hc[0] + du * 1.1, hc[1] - 0.265, 0.07, main, rot=rot)
            if not (P['hat_in_hand'] and parts.get('removable')):
                for fn in parts.get('hat', []):
                    fn(g, P)
            for fn in parts.get('front', []):
                fn(g, P)


# ---------------------------------------------------------------------------------------------------------------
# Kostüme (<= 5 Primitive, an den Ankern hat / face / neck / hand / back)
# ---------------------------------------------------------------------------------------------------------------

def _tool_rot(wing_angle) -> float:
    """Drehung eines Werkzeugs in der Flügelspitze: entlang des Flügels; hängt der Flügel, wird es schräg nach vorn oben gehalten."""
    bump = A.smoothstep((wing_angle + 40.0) / 40.0) * (1.0 - A.smoothstep((wing_angle - 20.0) / 40.0))
    return wing_angle + 90.0 - 125.0 * bump


def _costume_parts(costume, th, t) -> dict:
    """Zeichenfunktionen je Gruppe: 'back' (auf dem Körper, unter dem Flügel), 'face' (unter den Augen),
    'hat' (auf dem Kopf), 'front' (über dem Gesicht), 'hand' (an der Flügelspitze; fn(g, P, hand, angle))."""
    accent, accent2 = th.get('accent', '#F2B544'), th.get('accent2', '#5FD9B8')
    glow = th.get('glow') or accent
    ink, light, line = th.get('card_ink', '#171A28'), th['mascot_light'], th['line']
    wood, steel, paper = th.get('wood', '#8E6F52'), th.get('steel', '#9AA3B2'), th.get('paper', '#EAD9B8')
    hat = ANCHORS['hat']
    neck = ANCHORS['neck']
    parts = {}

    def turn_of(P):
        return max(0.0, min(1.0, float(P['head_turn'])))

    if costume == 'thief':
        def mask(g, P):                                   # Domino-Maske, Augen werden darüber gezeichnet
            tn = turn_of(P)
            u0 = 0.24 - 0.05 * tn
            g.rrect(u0 - 0.15, -0.80, 0.32, 0.055, 0.0275, accent2)         # Band um den Kopf
            g.ellipse(u0, -0.80, 0.09, 0.078, accent2)
            if tn > 0.01:
                g.ellipse(u0 - 0.17, -0.80, 0.078, 0.072, accent2, alpha=tn if not g.flat else 1.0)
        def loot(g, P):                                   # Beutel mit Edelstein am Schnabel
            tu, tv = 0.51 - 0.06 * turn_of(P), -0.76
            g.rrect(tu + 0.03, tv + 0.04, 0.06, 0.05, 0.015, wood)
            g.circle(tu + 0.03, tv + 0.14, 0.075, wood)
            g.hexagon(tu + 0.03, tv + 0.15, 0.032, accent)
        parts['face'] = [mask]
        parts['front'] = [loot]
    elif costume == 'miner':
        def helmet(g, P):
            with g.clip(g.rect_path(hat[0] - 0.3, hat[1] - 0.3, 0.6, 0.31)):
                g.circle(hat[0], hat[1] + 0.02, 0.21, accent)
            g.rrect(hat[0] + 0.02, hat[1] + 0.02, 0.44, 0.045, 0.022, accent)
            g.circle(hat[0] + 0.11, hat[1] - 0.09, 0.045, glow if not g.flat else accent)
        def cone(g, P):                                   # Lichtkegel folgt look (additiv, nur im Farbdurchgang)
            if g.flat:
                return
            look = P['look']
            ang = math.degrees(math.atan2(look[1] * 0.5 + 0.12, 1.0 + look[0] * 0.3))
            u, v = hat[0] + 0.11, hat[1] - 0.09
            with g.tf(rot=ang, pivot=(u, v)):
                g.rpoly([(u + 0.03, v), (u + 0.75, v - 0.16), (u + 0.75, v + 0.22)], 0.02, glow, alpha=0.25, blend='add')
        def coil(g, P):
            g.circle(-0.20, -0.50, 0.10, wood, stroke=0.045 * g.S)
        parts['hat'] = [helmet]
        parts['removable'] = True
        parts['front'] = [cone]
        parts['back'] = [coil]
    elif costume == 'explorer':
        def pith(g, P):
            with g.clip(g.rect_path(hat[0] - 0.3, hat[1] - 0.3, 0.6, 0.3 + 0.075)):
                g.ellipse(hat[0], hat[1] + 0.075, 0.25, 0.20, paper)
            g.rrect(hat[0] + 0.01, hat[1] + 0.075, 0.46, 0.045, 0.022, paper)
            g.rrect(hat[0], hat[1] + 0.035, 0.40, 0.04, 0.02, accent2)
        def binoc(g, P):
            u, v = neck[0] + 0.06, neck[1] + 0.12
            g.line(neck[0] - 0.08, neck[1] - 0.02, u, v - 0.02, 0.022, steel)
            g.rrect(u, v, 0.13, 0.04, 0.02, steel)
            g.circle(u - 0.045, v + 0.02, 0.045, steel)
            g.circle(u + 0.045, v + 0.02, 0.045, steel)
        parts['hat'] = [pith]
        parts['removable'] = True
        parts['back'] = [binoc]
    elif costume == 'astronaut':
        def dome(g, P):                                   # Glaskuppel: im Rand-/Schattenpass nur als Ring
            if g.flat:
                g.circle(HEAD_C[0], HEAD_C[1], 0.34, line, stroke=0.012 * g.S)
                return
            g.circle(HEAD_C[0], HEAD_C[1], 0.34, line, alpha=0.22)
            g.arc(HEAD_C[0], HEAD_C[1], 0.29, 200, 250, 0.022, line, alpha=0.35)
        def antenna(g, P):
            u, v = hat[0] - 0.02, hat[1] - 0.10
            g.line(u, v + 0.03, u, v - 0.10, 0.018, steel)
            on = (t % 1.0) < 0.5
            g.circle(u, v - 0.12, 0.024, accent2 if (on or g.flat) else steel)
        parts['front'] = [dome]
        parts['hat'] = [antenna]
    elif costume == 'historian':
        def topper(g, P):
            g.rrect(hat[0] + 0.01, hat[1] - 0.095, 0.26, 0.23, 0.03, ink)
            g.rrect(hat[0] + 0.01, hat[1] + 0.02, 0.40, 0.045, 0.022, ink)
            g.rrect(hat[0] + 0.01, hat[1] - 0.015, 0.26, 0.05, 0.0, accent)
        def monocle(g, P):
            eu, ev = (0.05, -0.80) if turn_of(P) > 0.5 else (0.24 - 0.05 * turn_of(P), -0.80)
            g.circle(eu, ev, 0.085, accent, stroke=0.02 * g.S)
            g.curve([(eu + 0.05, ev + 0.07), (eu + 0.10, ev + 0.17), (neck[0] + 0.04, neck[1] + 0.03)], 0.012, accent)
        parts['hat'] = [topper]
        parts['removable'] = True
        parts['front'] = [monocle]
    elif costume == 'diver':
        def goggles(g, P):                                # Augen bleiben sichtbar (werden darüber gezeichnet)
            tn = turn_of(P)
            cu = 0.24 - 0.13 * tn
            w = 0.30 + 0.12 * tn
            g.rrect(cu, -0.80, w, 0.17, 0.05, steel)
            if not g.flat:
                g.rrect(cu, -0.80, w - 0.05, 0.12, 0.035, accent2, alpha=0.3)
        def snorkel(g, P):
            u, v = hat[0] - 0.12, hat[1] + 0.12
            g.polyline([(u + 0.02, v + 0.22), (u - 0.09, v + 0.14), (u - 0.10, v - 0.12)], 0.03, accent)
            g.rrect(u - 0.10, v - 0.15, 0.05, 0.06, 0.02, accent)
        parts['face'] = [goggles]
        parts['hat'] = [snorkel]
    elif costume == 'doctor':
        def mirror(g, P):
            g.rrect(hat[0], hat[1] + 0.06, 0.44, 0.04, 0.02, steel)
            g.circle(hat[0] + 0.06, hat[1] + 0.06, 0.06, steel, stroke=0.024 * g.S)
        def stetho(g, P):
            g.curve([(neck[0] - 0.16, neck[1] + 0.00), (neck[0] - 0.04, neck[1] + 0.08), (neck[0] + 0.12, neck[1] + 0.04), (neck[0] + 0.16, neck[1] + 0.18)], 0.024, steel)
            g.circle(neck[0] + 0.17, neck[1] + 0.22, 0.05, steel)
        parts['hat'] = [mirror]
        parts['back'] = [stetho]
    elif costume == 'detective':
        def deerstalker(g, P):
            with g.clip(g.rect_path(hat[0] - 0.3, hat[1] - 0.3, 0.6, 0.32)):
                g.circle(hat[0], hat[1] + 0.03, 0.215, wood)
            g.rrect(hat[0] - 0.16, hat[1] + 0.025, 0.14, 0.05, 0.025, wood)
            g.rrect(hat[0] + 0.17, hat[1] + 0.025, 0.14, 0.05, 0.025, wood)
            g.rrect(hat[0], hat[1] - 0.03, 0.34, 0.04, 0.02, accent)
        def magnifier(g, P, hand, ang):
            with g.tf(rot=_tool_rot(ang), pivot=hand):
                g.line(hand[0] - 0.02, hand[1], hand[0] + 0.12, hand[1], 0.03, wood)
                g.circle(hand[0] + 0.22, hand[1], 0.10, steel, stroke=0.022 * g.S)
                if not g.flat:
                    g.circle(hand[0] + 0.22, hand[1], 0.09, line, alpha=0.15)
        parts['hat'] = [deerstalker]
        parts['removable'] = True
        parts['hand'] = [magnifier]
    elif costume == 'chef':
        def toque(g, P):
            g.rrect(hat[0] + 0.01, hat[1] - 0.06, 0.24, 0.18, 0.02, light)
            g.circle(hat[0] - 0.09, hat[1] - 0.14, 0.07, light)
            g.circle(hat[0] + 0.01, hat[1] - 0.18, 0.075, light)
            g.circle(hat[0] + 0.11, hat[1] - 0.14, 0.07, light)
        def spoon(g, P, hand, ang):
            with g.tf(rot=_tool_rot(ang), pivot=hand):
                g.line(hand[0] - 0.02, hand[1], hand[0] + 0.14, hand[1], 0.022, steel)
                g.ellipse(hand[0] + 0.18, hand[1], 0.05, 0.035, steel)
        parts['hat'] = [toque]
        parts['removable'] = True
        parts['hand'] = [spoon]
    return parts


# ---------------------------------------------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------------------------------------------

def rim_for(size: float, rim=None) -> float:
    """Sticker-Rand in Pixeln: 14 px bei size 400, proportional kleiner, nie unter 4 px."""
    if rim is not None:
        return float(rim)
    return max(RIM_MIN, RIM_PX * min(1.0, float(size) / SIZE_DEFAULT))


def costume_for(theme_name: str) -> str:
    """Kostüm zum Thema (STIL.md 2.4), unbekannt -> 'default'."""
    return THEME_COSTUME.get(theme_name, 'default')


def anchors(x, y, size, t=0.0, pose='idle', flip=False, seed=0, t0=0.0, expr=None, look=(0.0, 0.0), **kw) -> dict:
    """Pixelpositionen der Anker hat, face, neck, back, beak_tip, hand, top und floor zur Zeit t (ohne Pop/rot)."""
    P = state(pose, expr, t, look, seed, t0, **kw)
    S = float(size)
    sgn = -1.0 if flip else 1.0
    tilt = math.radians(P['body_tilt'] + P['body_jitter'])
    htilt = math.radians(-P['head_tilt'])
    hip = (0.0, -0.19 - P['lift'])
    dv = P['body_dy'] - P['lift']

    def body(u, v):
        du, dvv = u - hip[0], v - hip[1]
        cs, sn = math.cos(tilt), math.sin(tilt)
        return (hip[0] + du * cs - dvv * sn, hip[1] + du * sn + dvv * cs + dv)

    def head(u, v):
        du, dvv = u - NECK[0], v - NECK[1]
        cs, sn = math.cos(htilt), math.sin(htilt)
        return body(NECK[0] + du * cs - dvv * sn, NECK[1] + du * sn + dvv * cs)

    turn = max(0.0, min(1.0, float(P['head_turn'])))
    out = {}
    for k, (u, v) in ANCHORS.items():
        if k in ('hat', 'face', 'beak_tip'):
            uu = u - (0.06 * turn if k == 'beak_tip' else 0.05 * turn if k == 'face' else 0.0)
            pu, pv = head(uu, v + P['head_dy'])
        else:
            pu, pv = body(u, v)
        out[k] = (x + sgn * pu * S, y + pv * S)
    hu, hv = body(*_wing_tip(WING_PIVOT, P['wing']))
    out['hand'] = (x + sgn * hu * S, y + hv * S)
    tu, tv = head(0.14, -1.0)
    out['top'] = (x + sgn * tu * S, y + tv * S)
    out['floor'] = (float(x), float(y))
    return out


def draw(c, x, y, size, t=0.0, pose='idle', expr=None, costume='default', look=(0.0, 0.0), flip=False, theme=None,
         alpha=1.0, rot=0.0, k=1.0, mode='sticker', color=None, rim=None, shadow=True, seed=0, t0=0.0, **kw):
    """Zeichnet Odd mit Bodenmittelpunkt (x, y) und Körperhöhe size px zur Zeit t.

    pose: Name aus POSES (Zeitschleife über t; t0 = Beginn der Pose für Federn, Keyframes, Wink).
    expr: Name aus EXPRS oder None (Standard der Pose). costume: Name aus COSTUMES. look: Blick (-1..1, -1..1) im Bildraum.
    k: Einblendung: 0..1 wird als Pop gedeutet (out_back s 2.2, Drehung -6° -> 0°), Werte >= 1 sind die Skalierung selbst
    (so kann auch der Überschwinger von anim.pop durchgereicht werden). mode: 'sticker' (Schatten -> Rand -> Farbe),
    'color' (nur Farbe, z. B. innerhalb eines eigenen c.sticker-Wrappers), 'rim' (nur Rand), 'silhouette' (einfarbig in color).
    rim: Randbreite px (Standard 14 bei size 400, nie unter 4). shadow: Bodenschatten (fx.floor_shadow, alpha 0.25).
    Weitere kw überschreiben Zustandswerte (head_turn, tail, wing, lid_top, hide_v, visible, blink, ...)."""
    th = theme if theme is not None else TH.get('curious')
    if k <= 0.0:
        return
    if flip:
        look = (-float(look[0]), float(look[1]))
    P = state(pose, expr, t, look, seed, t0, respect=bool(th.get('respect_mode')), **kw)
    S = float(size)
    detail = S >= DETAIL_MIN
    if k < 1.0:
        sc, rot_pop = A.out_back(k, s=2.2), -6.0 * (1.0 - k)
    else:
        sc, rot_pop = float(k), 0.0
    sc *= P['breathe']
    sy = float(P['body_sy'])
    sx = 1.0 / math.sqrt(sy) if sy > 0 else 1.0
    shx, shy = P['shake']
    rim_px = rim_for(S, rim)

    def fig(cc, m):
        _figure(_G(cc, 0.0, 0.0, S, m), P, th, costume, t, detail)

    with (c.layer(alpha) if alpha < 1.0 else contextlib.nullcontext()):
        if shadow and P['visible'] is None and mode in ('sticker', 'color') and c._over is None:
            w = 0.72 * S * sc
            if pose == 'fly':
                fx.floor_shadow(c, x, y, w * 0.7, alpha=FLOOR_SHADOW_ALPHA * 0.5 * min(1.0, k))
            else:
                fx.floor_shadow(c, x, y, w * (1.0 + 0.15 * (1.0 - sy)), alpha=FLOOR_SHADOW_ALPHA * min(1.0, k * 2.0))
        with c.tf(x=x + shx, y=y + shy, rot=rot + rot_pop, sx=sc * (-1.0 if flip else 1.0), sy=sc, px=0.0, py=0.0):
            with c.tf(sx=sx, sy=sy, px=0.0, py=0.0):
                if mode == 'sticker':
                    dy, sigma, sa = SHADOW
                    with c.layer(sa):
                        with c.tf(x=0.0, y=dy / max(sc, 1e-3)):
                            with c.override(th.get('shadow', '#000000'), rim_px, sigma):
                                fig(c, 'shadow')
                    with c.override(th['line'], rim_px):
                        fig(c, 'rim')
                    fig(c, 'color')
                elif mode == 'rim':
                    with c.override(th['line'], rim_px):
                        fig(c, 'rim')
                elif mode == 'silhouette':
                    with c.override(color or th['ink'], 0.0):
                        fig(c, 'silhouette')
                else:
                    fig(c, 'color' if c._over is None else 'silhouette')


def draw_head(c, cx, cy, d, t=0.0, expr='smile', look=(0.0, 0.0), theme=None, costume='default', rim=None, head_turn=1.0,
              flip=False, alpha=1.0, mode='sticker', pose='idle', **kw):
    """Nur der Kopf (Wasserzeichen 44 px, Profilbild): Kopfmitte (cx, cy), Kopfdurchmesser d px."""
    S = d / 0.48
    for key, val in (('visible', {'head'}), ('head_turn', head_turn), ('breathe_amp', 0.0), ('head_tilt', 0.0),
                     ('body_tilt', 0.0), ('head_dy', 0.0), ('body_dy', 0.0), ('cam', 0.0)):
        kw.setdefault(key, val)
    x = cx - (-HEAD_C[0] if flip else HEAD_C[0]) * S
    y = cy - HEAD_C[1] * S
    draw(c, x, y, S, t=t, pose=pose, expr=expr, costume=costume, look=look, flip=flip, theme=theme, alpha=alpha,
         mode=mode, rim=rim if rim is not None else rim_for(S), shadow=False, **kw)


# ---------------------------------------------------------------------------------------------------------------
# Übersichtsbogen
# ---------------------------------------------------------------------------------------------------------------

def sheet(out_path: str, quick: bool = False) -> str:
    """Rendert den Bogen: Posen x Kostüme (beschriftet), eine Zeile mit allen Ausdrücken, Bewegungszeilen mit sechs
    Zeitpunkten (cheer, run), Größentest 420 / 240 / 140 / 120 / Kopf 44 px, Flip, Pop, Silhouette, Rand, und der
    120-px-Silhouettentest aller Posen. quick=True rendert einen kleinen Ausschnitt (Tests)."""
    from .canvas import Frame
    poses = POSES if not quick else ['idle', 'point', 'cheer']
    costumes = COSTUMES if not quick else ['default', 'thief']
    cw, chh, sz, lx, top = 270, 310, 190, 150, 150
    row_h, size_h, sil_h = 420, 520, 260
    W = lx + cw * len(costumes) + 40
    grid_h = chh * len(poses)
    H = top + grid_h + 40 + row_h * 3 + 40 + size_h + 40 + sil_h + 60
    fr = Frame(W, H)
    c = fr.c
    base = TH.get('curious')
    c.gradient_bg('#14101F', '#0E0B16')
    f_lab, f_small = F.font('mono', 20), F.font('mono', 16)
    c.text(LABEL, 40, 72, F.font('display', 56, weight=800), base['ink'])
    c.text('mascot sheet · posen x kostüme · ausdrücke · bewegung · größen · silhouetten', 40, 112, F.font('mono', 22), base['ink_soft'])

    def cell_bg(x0, y0, w, h, th):
        c.rect(x0, y0, w, h, shader=c.linear(x0, y0, x0, y0 + h, [th['bg0'], th['bg1']]), r=24)

    for j, co in enumerate(costumes):                       # Kopfzeile Kostüme
        th = TH.get(COSTUME_THEME.get(co, 'curious'))
        x0 = lx + j * cw
        c.text(co.upper(), x0 + cw / 2, top - 24, f_lab, th['accent'], 'center', 'middle')
        c.text(COSTUME_THEME.get(co, 'curious'), x0 + cw / 2, top - 4, f_small, base['ink_soft'], 'center', 'middle')
    for i, po in enumerate(poses):                          # Raster Posen x Kostüme
        y0 = top + i * chh
        c.text(po, lx - 24, y0 + chh / 2, F.font('display', 26, weight=700), base['ink'], 'right', 'middle')
        for j, co in enumerate(costumes):
            th = TH.get(COSTUME_THEME.get(co, 'curious'))
            x0 = lx + j * cw
            cell_bg(x0 + 6, y0 + 6, cw - 12, chh - 12, th)
            t = 0.35 + 0.17 * i + 0.11 * j
            cx = x0 + cw / 2 - 10
            if po == 'peek':
                with c.clip_rect(x0 + 6, y0 + 6, cw - 12, chh - 12, 24):
                    draw(c, cx + 10, y0 + chh + 0.55 * sz, sz, t, po, None, co, theme=th)
            elif po == 'hide':
                fy = y0 + chh - 40
                draw(c, cx, fy, sz, t, po, None, co, theme=th)
                c.rect_c(cx + 0.12 * sz, fy - 0.36 * sz, 0.78 * sz, 0.72 * sz, th['bg2'], r=18)
            else:
                lk = (0.5, 0.1) if po in ('idle', 'point') else (0.0, 0.0)
                draw(c, cx, y0 + chh - 44, sz, t, po, None, co, theme=th, look=lk, t0=t - 0.12 if po == 'wink' else 0.0)
    y = top + grid_h + 40
    c.text('AUSDRÜCKE (idle, head_turn 1, kostüm default)', 40, y + 18, f_lab, base['ink_soft'])
    ew = (W - 80) / len(EXPRS)
    for i, ex in enumerate(EXPRS):                          # Ausdrücke
        x0 = 40 + i * ew
        cell_bg(x0 + 4, y + 40, ew - 8, row_h - 60, base)
        draw(c, x0 + ew / 2 - 10, y + row_h - 60, 250, 1.3, 'idle', ex, 'default', theme=base, head_turn=1.0)
        c.text(ex, x0 + ew / 2, y + row_h - 34, f_lab, base['accent'], 'center', 'middle')
    y += row_h
    for po, th_name, times in (('cheer', 'heist', [0.0, 0.05, 0.10, 0.15, 0.20, 0.25]), ('run', 'crime', [0.0, 0.04, 0.08, 0.12, 0.16, 0.20])):
        th = TH.get(th_name)                                # Bewegung: 6 Zeitpunkte
        c.text(f'BEWEGUNG {po} · t = ' + ', '.join(f'{v:.2f}' for v in times) + ' s', 40, y + 18, f_lab, base['ink_soft'])
        mw = (W - 80) / 6
        for i, tt in enumerate(times):
            x0 = 40 + i * mw
            cell_bg(x0 + 4, y + 40, mw - 8, row_h - 60, th)
            draw(c, x0 + mw / 2 - 10, y + row_h - 70, 240, tt, po, None, THEME_COSTUME[th_name], theme=th)
            c.text(f't={tt:.2f}', x0 + mw / 2, y + row_h - 34, f_small, th['ink_soft'], 'center', 'middle')
        y += row_h
    th = base                                               # Größen und Modi
    c.text('GRÖSSEN 420 · 240 · 140 · 120 · kopf 44 (wasserzeichen) · flip · pop k 0.5 · silhouette · rim', 40, y + 18, f_lab, base['ink_soft'])
    cell_bg(40, y + 40, W - 80, size_h - 40, th)
    by = y + size_h - 30
    xx = 60 + 300
    draw(c, xx, by, 420, 0.9, 'idle', None, 'default', theme=th, look=(0.5, 0.1))
    for s, dx in ((240, 420), (140, 250), (120, 160)):
        xx += dx
        draw(c, xx, by, s, 0.9, 'idle', None, 'default', theme=th, look=(0.5, 0.1))
    xx += 140
    draw_head(c, xx, by - 40, 44, 0.9, 'smile', theme=th)
    c.text('44', xx, by, f_small, th['ink_soft'], 'center', 'middle')
    xx += 160
    draw(c, xx, by, 240, 0.9, 'point', None, 'thief', theme=TH.get('heist'), flip=True, look=(-0.6, 0.0))
    xx += 260
    draw(c, xx, by, 240, 0.9, 'idle', None, 'default', theme=th, k=0.5)
    xx += 230
    draw(c, xx, by, 240, 0.9, 'point', None, 'default', theme=th, mode='silhouette', color=th['ink'])
    xx += 250
    draw(c, xx, by, 240, 0.9, 'point', None, 'default', theme=th, mode='rim')
    y += size_h + 40
    c.text('SILHOUETTEN-TEST 120 px (jede Pose: Kopf, Schnabel, Schwanz, Flügel erkennbar?)', 40, y + 18, f_lab, base['ink_soft'])
    sw = (W - 80) / len(poses)
    for i, po in enumerate(poses):                          # Silhouettentest
        x0 = 40 + i * sw
        c.rect(x0 + 3, y + 40, sw - 6, sil_h - 50, th['bg1'], r=18)
        if po == 'peek':
            with c.clip_rect(x0 + 3, y + 40, sw - 6, sil_h - 50, 18):
                draw(c, x0 + sw / 2 + 8, y + sil_h - 30 + 0.50 * 120, 120, 0.5, po, None, 'default', theme=th, mode='silhouette', color=th['ink'], shadow=False)
        else:
            draw(c, x0 + sw / 2, y + sil_h - 30, 120, 0.5, po, None, 'default', theme=th, mode='silhouette', color=th['ink'], shadow=False)
        c.text(po, x0 + sw / 2, y + sil_h - 16, f_small, th['ink_soft'], 'center', 'middle')
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    fr.save_png(out_path)
    return out_path
