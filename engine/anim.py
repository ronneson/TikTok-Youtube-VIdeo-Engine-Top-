"""Zeit und Bewegung: Easing-Kurven, Tweens, Federn, Keyframes. Alles reine Funktionen der Zeit."""
from __future__ import annotations
import math


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def clamp01(v):
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def lerp(a, b, t):
    return a + (b - a) * t


def remap(v, a0, a1, b0=0.0, b1=1.0, ease=None):
    """v aus [a0,a1] nach [b0,b1], geklemmt, optional mit Easing."""
    if a1 == a0:
        t = 1.0 if v >= a1 else 0.0
    else:
        t = clamp01((v - a0) / (a1 - a0))
    if ease:
        t = EASE[ease](t) if isinstance(ease, str) else ease(t)
    return b0 + (b1 - b0) * t


def smoothstep(t):
    t = clamp01(t)
    return t * t * (3 - 2 * t)


def smootherstep(t):
    t = clamp01(t)
    return t * t * t * (t * (t * 6 - 15) + 10)


# --- Easing (Eingabe 0..1, Ausgabe meist 0..1, back/elastic dürfen überschwingen) ---

def linear(t): return clamp01(t)
def in_quad(t): t = clamp01(t); return t * t
def out_quad(t): t = clamp01(t); return 1 - (1 - t) * (1 - t)
def in_out_quad(t): t = clamp01(t); return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2
def in_cubic(t): t = clamp01(t); return t ** 3
def out_cubic(t): t = clamp01(t); return 1 - (1 - t) ** 3
def in_out_cubic(t): t = clamp01(t); return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
def in_quart(t): t = clamp01(t); return t ** 4
def out_quart(t): t = clamp01(t); return 1 - (1 - t) ** 4
def in_out_quart(t): t = clamp01(t); return 8 * t ** 4 if t < 0.5 else 1 - (-2 * t + 2) ** 4 / 2
def out_quint(t): t = clamp01(t); return 1 - (1 - t) ** 5
def in_expo(t): t = clamp01(t); return 0.0 if t == 0 else 2 ** (10 * t - 10)
def out_expo(t): t = clamp01(t); return 1.0 if t == 1 else 1 - 2 ** (-10 * t)
def in_out_expo(t):
    t = clamp01(t)
    if t == 0: return 0.0
    if t == 1: return 1.0
    return 2 ** (20 * t - 10) / 2 if t < 0.5 else (2 - 2 ** (-20 * t + 10)) / 2
def in_sine(t): t = clamp01(t); return 1 - math.cos(t * math.pi / 2)
def out_sine(t): t = clamp01(t); return math.sin(t * math.pi / 2)
def in_out_sine(t): t = clamp01(t); return -(math.cos(math.pi * t) - 1) / 2
def out_back(t, s=1.70158):
    t = clamp01(t); c3 = s + 1
    return 1 + c3 * (t - 1) ** 3 + s * (t - 1) ** 2
def in_back(t, s=1.70158):
    t = clamp01(t); c3 = s + 1
    return c3 * t ** 3 - s * t * t
def in_out_back(t, s=1.70158):
    t = clamp01(t); c2 = s * 1.525
    return ((2 * t) ** 2 * ((c2 + 1) * 2 * t - c2)) / 2 if t < 0.5 else ((2 * t - 2) ** 2 * ((c2 + 1) * (t * 2 - 2) + c2) + 2) / 2
def out_elastic(t, period=0.3):
    t = clamp01(t)
    if t == 0 or t == 1: return t
    c4 = (2 * math.pi) / period
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * c4) + 1
def out_bounce(t):
    t = clamp01(t); n1, d1 = 7.5625, 2.75
    if t < 1 / d1: return n1 * t * t
    if t < 2 / d1: t -= 1.5 / d1; return n1 * t * t + 0.75
    if t < 2.5 / d1: t -= 2.25 / d1; return n1 * t * t + 0.9375
    t -= 2.625 / d1; return n1 * t * t + 0.984375
def in_bounce(t): return 1 - out_bounce(1 - clamp01(t))
def out_circ(t): t = clamp01(t); return math.sqrt(1 - (t - 1) ** 2)
def in_circ(t): t = clamp01(t); return 1 - math.sqrt(1 - t * t)


EASE = {
    'linear': linear, 'in_quad': in_quad, 'out_quad': out_quad, 'in_out_quad': in_out_quad,
    'in_cubic': in_cubic, 'out_cubic': out_cubic, 'in_out_cubic': in_out_cubic,
    'in_quart': in_quart, 'out_quart': out_quart, 'in_out_quart': in_out_quart, 'out_quint': out_quint,
    'in_expo': in_expo, 'out_expo': out_expo, 'in_out_expo': in_out_expo,
    'in_sine': in_sine, 'out_sine': out_sine, 'in_out_sine': in_out_sine,
    'out_back': out_back, 'in_back': in_back, 'in_out_back': in_out_back,
    'out_elastic': out_elastic, 'out_bounce': out_bounce, 'in_bounce': in_bounce,
    'out_circ': out_circ, 'in_circ': in_circ, 'smooth': smoothstep, 'smoother': smootherstep,
}


def ease(name_or_fn, t):
    if callable(name_or_fn):
        return name_or_fn(t)
    return EASE[name_or_fn](t)


def tween(t, t0, dur, easing='out_cubic'):
    """0 vor t0, 1 nach t0+dur, dazwischen mit Easing."""
    if dur <= 0:
        return 1.0 if t >= t0 else 0.0
    return ease(easing, (t - t0) / dur)


def appear(t, t_in, t_out=None, d_in=0.35, d_out=0.3, ease_in='out_cubic', ease_out='in_cubic'):
    """Alpha-Kurve: blendet bei t_in ein, bei t_out aus. t_out=None -> bleibt."""
    a = tween(t, t_in, d_in, ease_in)
    if t_out is not None:
        a *= 1.0 - tween(t, t_out - d_out, d_out, ease_out)
    return a


def pop(t, t0, dur=0.45, overshoot=1.12):
    """Skalierung für ein Aufploppen: 0 -> overshoot -> 1."""
    if t < t0:
        return 0.0
    u = clamp01((t - t0) / dur)
    return out_back(u, s=(overshoot - 1) * 10)


def spring(t, t0, stiffness=140.0, damping=12.0, mass=1.0):
    """Gedämpfte Feder von 0 nach 1 ab t0 (physikalisch), für organische Überschwinger."""
    if t <= t0:
        return 0.0
    x = t - t0
    w0 = math.sqrt(stiffness / mass)
    zeta = damping / (2 * math.sqrt(stiffness * mass))
    if zeta < 1:
        wd = w0 * math.sqrt(1 - zeta * zeta)
        return 1 - math.exp(-zeta * w0 * x) * (math.cos(wd * x) + (zeta * w0 / wd) * math.sin(wd * x))
    return 1 - math.exp(-w0 * x) * (1 + w0 * x)


def osc(t, freq=1.0, phase=0.0, lo=-1.0, hi=1.0):
    """Sinus-Schwingung zwischen lo und hi."""
    s = math.sin(2 * math.pi * freq * t + phase)
    return lo + (hi - lo) * (s * 0.5 + 0.5)


def wobble(t, freq=0.7, amp=1.0, seed=0):
    """Weiche, unregelmäßige Bewegung (Summe dreier Sinus)."""
    p = seed * 1.7
    return amp * (0.5 * math.sin(2 * math.pi * freq * t + p) + 0.3 * math.sin(2 * math.pi * freq * 2.13 * t + p * 2.1) + 0.2 * math.sin(2 * math.pi * freq * 0.47 * t + p * 0.7))


def pulse(t, period=1.0, width=0.5):
    """Weicher Puls 0..1 mit Periode."""
    u = (t / period) % 1.0
    return smoothstep(u / width) * (1 - smoothstep((u - width) / (1 - width))) if 0 < width < 1 else 0.0


def breathe(t, period=3.0, amp=0.02):
    return 1.0 + amp * math.sin(2 * math.pi * t / period)


def stagger(i, n, t, t0, delay=0.08, dur=0.4, easing='out_cubic'):
    """Element i von n erscheint um i*delay versetzt."""
    return tween(t, t0 + i * delay, dur, easing)


def typewriter(t, t0, text, cps=28.0):
    """Zeigt text zeichenweise ab t0 mit cps Zeichen pro Sekunde."""
    if t < t0:
        return ''
    n = int((t - t0) * cps)
    return text[:n]


def count_value(t, t0, dur, start, end, easing='out_cubic'):
    """Zählt von start nach end über dur Sekunden."""
    return lerp(start, end, tween(t, t0, dur, easing))


def shake(t, t0, dur=0.3, amp=8.0, freq=28.0, seed=0.0):
    """Abklingendes Zittern (dx, dy) ab t0."""
    if t < t0 or t > t0 + dur:
        return (0.0, 0.0)
    u = (t - t0) / dur
    env = (1 - u) ** 2 * amp
    return (env * math.sin(2 * math.pi * freq * (t - t0) + seed), env * math.cos(2 * math.pi * freq * 1.3 * (t - t0) + seed * 2))


class Keyframes:
    """Stützstellen [(t, wert), ...]; wert darf Zahl oder Tupel sein. Easing zwischen den Stützstellen."""

    def __init__(self, keys, easing='in_out_cubic'):
        self.keys = sorted(keys, key=lambda k: k[0])
        self.easing = easing

    def at(self, t):
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1]
        if t >= ks[-1][0]:
            return ks[-1][1]
        for i in range(len(ks) - 1):
            t0, v0 = ks[i]
            t1, v1 = ks[i + 1]
            if t0 <= t <= t1:
                u = ease(self.easing, (t - t0) / (t1 - t0)) if t1 > t0 else 1.0
                if isinstance(v0, (tuple, list)):
                    return tuple(a + (b - a) * u for a, b in zip(v0, v1))
                return v0 + (v1 - v0) * u
        return ks[-1][1]


def hold_then(t, t_switch, before, after):
    return before if t < t_switch else after
