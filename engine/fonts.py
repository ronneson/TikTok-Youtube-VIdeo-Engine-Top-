"""Schriften: lädt die Google Fonts aus assets/fonts und liefert skia.Font-Objekte mit Variationsachsen.

Logische Namen (siehe FAMILIES) halten die Gestaltung an einer Stelle: display, number, body, caption, mono, serif, hand.
"""
from __future__ import annotations
import os
import skia
from . import ROOT

FONT_DIR = os.path.join(ROOT, 'assets', 'fonts')

# Datei je logischer Rolle. Die Designentscheidung steht in STIL.md; hier nur die Zuordnung.
FAMILIES = {
    'display': 'BricolageGrotesque[opsz,wdth,wght].ttf',
    'number': 'Unbounded[wght].ttf',
    'body': 'Outfit[wght].ttf',
    'caption': 'Outfit[wght].ttf',
    'mono': 'DMMono-Medium.ttf',
    'mono_light': 'DMMono-Regular.ttf',
    'serif': 'InstrumentSerif-Regular.ttf',
    'serif_italic': 'InstrumentSerif-Italic.ttf',
    'hand': 'Caveat[wght].ttf',
    'impact': 'Anton-Regular.ttf',
    'bebas': 'BebasNeue-Regular.ttf',
    'syne': 'Syne[wght].ttf',
    'inter': 'Inter[opsz,wght].ttf',
    'manrope': 'Manrope[wght].ttf',
    'nunito': 'Nunito[wght].ttf',
    'space': 'SpaceGrotesk[wght].ttf',
    'fraunces': 'Fraunces[SOFT,WONK,opsz,wght].ttf',
    'playfair': 'PlayfairDisplay[wght].ttf',
    'archivo': 'ArchivoBlack-Regular.ttf',
    'jetbrains': 'JetBrainsMono[wght].ttf',
}

_TYPEFACES: dict = {}
_FONTS: dict = {}


def _tag(s: str) -> int:
    return (ord(s[0]) << 24) | (ord(s[1]) << 16) | (ord(s[2]) << 8) | ord(s[3])


def set_family(role: str, filename: str):
    """Rolle auf eine andere Datei legen (z. B. aus config/engine.json)."""
    FAMILIES[role] = filename
    for k in [k for k in _TYPEFACES if k[0] == role]:
        _TYPEFACES.pop(k)
    for k in [k for k in _FONTS if k[0] == role]:
        _FONTS.pop(k)


def typeface(role: str, weight=None, opsz=None, wdth=None, soft=None) -> skia.Typeface:
    key = (role, weight, opsz, wdth, soft)
    tf = _TYPEFACES.get(key)
    if tf is not None:
        return tf
    fn = FAMILIES.get(role, role)
    path = fn if os.path.isabs(fn) else os.path.join(FONT_DIR, fn)
    base = _TYPEFACES.get((role, None, None, None, None))
    if base is None:
        base = skia.Typeface.MakeFromFile(path)
        if base is None:
            raise FileNotFoundError(f"Schrift nicht gefunden: {path}")
        _TYPEFACES[(role, None, None, None, None)] = base
    coords = []
    axes = {}
    try:
        for ax in base.getVariationDesignParameters():
            axes[ax.tag] = (ax.min, ax.max)
    except Exception:
        axes = {}
    def add(tagname, value):
        t = _tag(tagname)
        if value is not None and t in axes:
            lo, hi = axes[t]
            coords.append(skia.FontArguments.VariationPosition.Coordinate(t, float(max(lo, min(hi, value)))))
    add('wght', weight)
    add('opsz', opsz)
    add('wdth', wdth)
    add('SOFT', soft)
    if coords:
        # Die Coordinates müssen bis nach makeClone am Leben bleiben (skia hält nur einen Zeiger darauf).
        cs = skia.FontArguments.VariationPosition.Coordinates(coords)
        pos = skia.FontArguments.VariationPosition(cs)
        fa = skia.FontArguments()
        fa.setVariationDesignPosition(pos)
        tf = base.makeClone(fa)
        del cs, pos, fa
    else:
        tf = base
    _TYPEFACES[key] = tf
    return tf


def font(role: str = 'body', size: float = 40, weight=None, opsz=None, wdth=None, soft=None) -> skia.Font:
    """Liefert ein gecachtes skia.Font. opsz folgt der Größe, wenn nicht angegeben."""
    if opsz is None:
        opsz = size
    key = (role, round(size, 2), weight, opsz, wdth, soft)
    f = _FONTS.get(key)
    if f is not None:
        return f
    f = skia.Font(typeface(role, weight, opsz, wdth, soft), float(size))
    f.setEdging(skia.Font.Edging.kSubpixelAntiAlias)
    f.setSubpixel(True)
    f.setHinting(skia.FontHinting.kNone)
    _FONTS[key] = f
    return f


def measure(text: str, f: skia.Font) -> float:
    return f.measureText(text)


def metrics(f: skia.Font):
    """(ascent (negativ), descent, cap_height, x_height)"""
    m = f.getMetrics()
    cap = m.fCapHeight if m.fCapHeight else -m.fAscent * 0.7
    xh = m.fXHeight if m.fXHeight else -m.fAscent * 0.5
    return (m.fAscent, m.fDescent, cap, xh)


def fit_size(text: str, role: str, max_width: float, size: float, min_size: float = 12, **kw) -> float:
    """Größte Größe <= size, mit der text in max_width passt."""
    s = size
    while s > min_size:
        if measure(text, font(role, s, **kw)) <= max_width:
            return s
        s *= 0.94
    return min_size


def wrap(text: str, role: str, size: float, max_width: float, **kw) -> list:
    """Bricht text in Zeilen, die in max_width passen."""
    f = font(role, size, **kw)
    words = text.split()
    lines, cur = [], ''
    for w in words:
        trial = (cur + ' ' + w).strip()
        if measure(trial, f) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def available() -> list:
    return sorted(os.listdir(FONT_DIR)) if os.path.isdir(FONT_DIR) else []
