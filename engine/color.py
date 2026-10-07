"""Farben: Hex-Strings, Tupel und skia-Farben ineinander umrechnen, mischen, aufhellen."""
from __future__ import annotations
import colorsys
import skia

ColorLike = "str | tuple | list | skia.Color4f"


def parse(c, alpha: float = 1.0) -> tuple:
    """Gibt (r, g, b, a) als Floats 0..1 zurück. Akzeptiert '#RGB', '#RRGGBB', '#RRGGBBAA', Tupel, Color4f."""
    if isinstance(c, skia.Color4f):
        return (c.fR, c.fG, c.fB, c.fA * alpha)
    if isinstance(c, str):
        s = c.strip().lstrip('#')
        if len(s) == 3:
            s = ''.join(ch * 2 for ch in s)
        if len(s) == 6:
            r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
            a = 255
        elif len(s) == 8:
            r, g, b, a = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16)
        else:
            raise ValueError(f"unbekannte Farbe: {c!r}")
        return (r / 255.0, g / 255.0, b / 255.0, a / 255.0 * alpha)
    if isinstance(c, (tuple, list)):
        if len(c) == 3:
            r, g, b = c
            a = 1.0
        else:
            r, g, b, a = c[:4]
        if max(r, g, b) > 1.0:
            r, g, b = r / 255.0, g / 255.0, b / 255.0
        return (float(r), float(g), float(b), float(a) * alpha)
    raise TypeError(f"keine Farbe: {c!r}")


def c4f(c, alpha: float = 1.0) -> skia.Color4f:
    r, g, b, a = parse(c, alpha)
    return skia.Color4f(r, g, b, max(0.0, min(1.0, a)))


def hexs(c) -> str:
    r, g, b, a = parse(c)
    return '#%02X%02X%02X' % (round(r * 255), round(g * 255), round(b * 255))


def mix(a, b, t: float):
    """Lineare Mischung zweier Farben, t=0 -> a, t=1 -> b."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba, aa = parse(a)
    rb, gb, bb, ab = parse(b)
    return (ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t, aa + (ab - aa) * t)


def with_alpha(c, alpha: float):
    r, g, b, _ = parse(c)
    return (r, g, b, alpha)


def lighten(c, amount: float):
    """amount 0..1 Richtung Weiß."""
    return mix(c, (1, 1, 1, parse(c)[3]), amount)


def darken(c, amount: float):
    return mix(c, (0, 0, 0, parse(c)[3]), amount)


def hsl(c):
    r, g, b, a = parse(c)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return (h, s, l, a)


def from_hsl(h: float, s: float, l: float, a: float = 1.0):
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0, min(1, l)), max(0, min(1, s)))
    return (r, g, b, a)


def shift_hue(c, dh: float):
    h, s, l, a = hsl(c)
    return from_hsl(h + dh, s, l, a)


def saturate(c, factor: float):
    h, s, l, a = hsl(c)
    return from_hsl(h, s * factor, l, a)


def luminance(c) -> float:
    r, g, b, _ = parse(c)
    def lin(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a, b) -> float:
    """WCAG-Kontrastverhältnis."""
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def text_on(bg, light='#FFFFFF', dark='#101010'):
    """Wählt helle oder dunkle Schrift für einen Hintergrund."""
    return light if contrast(bg, light) >= contrast(bg, dark) else dark
