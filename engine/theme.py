"""Farbthemen. VORLÄUFIG: wird mit den Werten aus STIL.md (Design-Jury) ersetzt.

Jedes Thema ist ein dict mit festen Schlüsseln, damit alle Module dieselben Namen benutzen:
bg0/bg1 (Verlauf oben/unten), bg2 (Fläche), ink (Schrift), ink_soft, accent, accent2, glow, card, card_ink,
danger, ok, line, caption_bg, caption_ink, caption_hi, mascot_main, mascot_dark, mascot_light.
"""
from __future__ import annotations
import os

KEYS = ['bg0', 'bg1', 'bg2', 'ink', 'ink_soft', 'accent', 'accent2', 'glow', 'card', 'card_ink', 'danger', 'ok', 'line',
        'caption_bg', 'caption_ink', 'caption_hi', 'mascot_main', 'mascot_dark', 'mascot_light']

BASE = {
    'bg0': '#141A2E', 'bg1': '#2A1E3F', 'bg2': '#3A2F5A', 'ink': '#FFF7EC', 'ink_soft': '#C9C2D6',
    'accent': '#FFC14A', 'accent2': '#5FF2C2', 'glow': '#FFD98A', 'card': '#FFC14A', 'card_ink': '#1A1020',
    'danger': '#FF5B3A', 'ok': '#5FF2C2', 'line': '#FFFFFF', 'caption_bg': '#0B0A14', 'caption_ink': '#FFFFFF', 'caption_hi': '#FFC14A',
    'mascot_main': '#8C7A6B', 'mascot_dark': '#2B2330', 'mascot_light': '#F2E8DA',
}

THEMES = {
    'curious': dict(BASE),
    'heist': {**BASE, 'bg0': '#0E1424', 'bg1': '#1F1A3A', 'bg2': '#2E2A55', 'accent': '#FFC14A', 'accent2': '#FF5B3A', 'glow': '#FFD98A'},
    'cave': {**BASE, 'bg0': '#0B0F14', 'bg1': '#1E2A2F', 'bg2': '#2E3F45', 'accent': '#FFB347', 'accent2': '#5FD3F2', 'glow': '#FFC98A'},
    'animal': {**BASE, 'bg0': '#10281F', 'bg1': '#1F4A33', 'bg2': '#2E6B49', 'accent': '#FFD166', 'accent2': '#FF8FA3', 'glow': '#FFE8A3'},
    'history': {**BASE, 'bg0': '#2A1A12', 'bg1': '#4A2E1E', 'bg2': '#6B4630', 'accent': '#F2C14E', 'accent2': '#8FD3F4', 'glow': '#FFE1A3'},
    'space': {**BASE, 'bg0': '#05070F', 'bg1': '#10163A', 'bg2': '#1E2A66', 'accent': '#9BE8FF', 'accent2': '#FFC14A', 'glow': '#CFF4FF'},
    'ocean': {**BASE, 'bg0': '#031A24', 'bg1': '#073B4C', 'bg2': '#0E5A6F', 'accent': '#5FF2C2', 'accent2': '#FFC14A', 'glow': '#A8FFE6'},
    'medical': {**BASE, 'bg0': '#15121F', 'bg1': '#2C1F3A', 'bg2': '#44305A', 'accent': '#FF6B8B', 'accent2': '#8EF0D2', 'glow': '#FFB3C2'},
    'crime': {**BASE, 'bg0': '#120D0D', 'bg1': '#2A1414', 'bg2': '#3F1E1E', 'accent': '#FF5B3A', 'accent2': '#FFC14A', 'glow': '#FF9A7A'},
}


class Theme(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e


def get(name: str = 'curious') -> Theme:
    d = THEMES.get(name) or THEMES['curious']
    t = Theme(BASE)
    t.update(d)
    t['name'] = name if name in THEMES else 'curious'
    return t


def names() -> list:
    return sorted(THEMES)


def sheet(out_path: str) -> str:
    from .canvas import Frame
    from . import fonts as F
    names_ = names()
    cols, cell, rows = 3, 360, (len(names_) + 2) // 3
    fr = Frame(cols * cell, rows * cell)
    c = fr.c
    c.fill('#111111')
    for i, n in enumerate(names_):
        th = get(n)
        x0, y0 = (i % cols) * cell, (i // cols) * cell
        c.rect(x0 + 10, y0 + 10, cell - 20, cell - 20, shader=c.linear(x0, y0, x0, y0 + cell, [th['bg0'], th['bg1']]), r=24)
        c.text(n, x0 + 30, y0 + 50, F.font('display', 34, weight=800), th['ink'])
        sw = ['accent', 'accent2', 'glow', 'card', 'danger', 'ok', 'bg2', 'ink_soft']
        for j, k in enumerate(sw):
            c.rect(x0 + 30 + (j % 4) * 76, y0 + 80 + (j // 4) * 76, 64, 64, th[k], r=14)
        c.rect(x0 + 30, y0 + 250, 300, 60, th['caption_bg'], r=16, alpha=0.75)
        c.text('caption word', x0 + 50, y0 + 280, F.font('caption', 30, weight=700), th['caption_ink'], 'left', 'middle')
        c.text('hi', x0 + 260, y0 + 280, F.font('caption', 30, weight=700), th['caption_hi'], 'left', 'middle')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fr.save_png(out_path)
    return out_path
