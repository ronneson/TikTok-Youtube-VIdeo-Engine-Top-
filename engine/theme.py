"""Farbthemen aus design/palette.json (Design-Jury, STIL.md Abschnitt 3).

Jedes Thema ist ein dict mit festen Schlüsseln. Konstanten (ink, line, card, caption_*, mascot_*, Naturfarben)
sind in allen Themen gleich; je Thema wechseln bg0/bg1/bg2, accent, accent2, glow, danger, ok, bed, costume.
theme.respect(th) liefert die gedämpfte Variante für Todesfälle (STIL.md 1.8).
"""
from __future__ import annotations
import json
import os
from . import ROOT
from . import color as CO

PALETTE_PATH = os.path.join(ROOT, 'design', 'palette.json')

CONSTANTS = {
    'ink': '#F7F1E6', 'ink_soft': '#C9C2D6', 'line': '#FFFFFF', 'card': '#F2B544', 'card_hi': '#F7C96B', 'card_ink': '#171A28',
    'caption_bg': '#171A28', 'caption_ink': '#F7F1E6', 'caption_hi': '#F2B544',
    'mascot_main': '#1F2233', 'mascot_dark': '#12141F', 'mascot_light': '#F7F1E6', 'mascot_sheen': '#2F9AA6', 'mascot_beak': '#3A3F4F',
    'wood': '#8E6F52', 'steel': '#9AA3B2', 'skin': '#E8C9A8', 'paper': '#EAD9B8', 'chalk': '#E9E4DA', 'foam': '#DDF3F5', 'water': '#5FD3F2',
    'candle': '#FFD8A0', 'stamp': '#F0634A', 'shadow': '#000000', 'gold_old': '#E2B55C', 'plum': '#5B3F8F',
}

# Fallback, falls design/palette.json fehlt (identisch mit der Jury-Palette)
_FALLBACK_THEMES = {
    'curious': {'bg0': '#1E1838', 'bg1': '#2E2250', 'bg2': '#41336C', 'accent': '#F2B544', 'accent2': '#5FD9B8', 'glow': '#FFD98A', 'danger': '#F0634A', 'ok': '#5FD9B8', 'bed': 'cabinet_swing', 'costume': 'default'},
    'heist': {'bg0': '#0F1A2C', 'bg1': '#1A2740', 'bg2': '#27385A', 'accent': '#F2B544', 'accent2': '#E8485C', 'glow': '#FFE08A', 'danger': '#E8485C', 'ok': '#58E0C2', 'bed': 'heist_tiptoe', 'costume': 'thief'},
    'cave': {'bg0': '#121420', 'bg1': '#232838', 'bg2': '#3B4254', 'accent': '#F2B544', 'accent2': '#6FAE8F', 'glow': '#FFD27A', 'danger': '#F0634A', 'ok': '#6FAE8F', 'bed': 'cave_drip', 'costume': 'miner'},
    'animal': {'bg0': '#163A2C', 'bg1': '#1F5A3F', 'bg2': '#2F7A52', 'accent': '#F7A233', 'accent2': '#3FB7B0', 'glow': '#FFD98A', 'danger': '#F0634A', 'ok': '#7CCB6B', 'bed': 'safari_bounce', 'costume': 'explorer'},
    'space': {'bg0': '#0B0D2A', 'bg1': '#1B1D5A', 'bg2': '#2E2F80', 'accent': '#FFD66B', 'accent2': '#E86BB0', 'glow': '#CFF4FF', 'danger': '#FF6B6B', 'ok': '#7FE3D2', 'bed': 'orbit_glow', 'costume': 'astronaut'},
    'history': {'bg0': '#3A271C', 'bg1': '#5A3C2A', 'bg2': '#7A5A42', 'accent': '#E2B55C', 'accent2': '#B8402E', 'glow': '#FFE1A3', 'danger': '#B8402E', 'ok': '#8FBF8F', 'bed': 'parlour_waltz', 'costume': 'historian'},
    'ocean': {'bg0': '#0A2638', 'bg1': '#0F4A66', 'bg2': '#1C6F8C', 'accent': '#F0634A', 'accent2': '#5FD9B8', 'glow': '#A8FFE6', 'danger': '#F0634A', 'ok': '#4FB38A', 'bed': 'orbit_glow', 'costume': 'diver'},
    'medical': {'bg0': '#16343A', 'bg1': '#1F4A50', 'bg2': '#2C6168', 'accent': '#F08CA8', 'accent2': '#E9C45A', 'glow': '#CFF8EE', 'danger': '#F0634A', 'ok': '#8EF0D2', 'bed': 'cabinet_swing_pulse', 'costume': 'doctor'},
    'crime': {'bg0': '#2A1430', 'bg1': '#3D1E3F', 'bg2': '#55305A', 'accent': '#F2B544', 'accent2': '#F0634A', 'glow': '#FFD98A', 'danger': '#F0634A', 'ok': '#5FD9B8', 'bed': 'cabinet_swing', 'costume': 'detective'},
    'food': {'bg0': '#1E1838', 'bg1': '#2E2250', 'bg2': '#41336C', 'accent': '#F7A233', 'accent2': '#5FD9B8', 'glow': '#FFD98A', 'danger': '#F0634A', 'ok': '#5FD9B8', 'bed': 'safari_bounce', 'costume': 'chef'},
}

KEYS = ['bg0', 'bg1', 'bg2', 'accent', 'accent2', 'glow', 'danger', 'ok'] + list(CONSTANTS)


def _load() -> tuple:
    consts = dict(CONSTANTS)
    themes = {k: dict(v) for k, v in _FALLBACK_THEMES.items()}
    if os.path.exists(PALETTE_PATH):
        try:
            with open(PALETTE_PATH, encoding='utf-8') as fh:
                p = json.load(fh)
            consts.update({k: v for k, v in p.get('constants', {}).items() if isinstance(v, str)})
            for name, t in p.get('themes', {}).items():
                base = themes.get(name, {})
                d = dict(base)
                d.update({k: v for k, v in t.items() if isinstance(v, str)})
                if isinstance(t.get('respect'), dict):
                    d['_respect'] = t['respect']
                themes[name] = d
        except Exception:
            pass
    return consts, themes


_CONSTS, THEMES = _load()


class Theme(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e


def get(name: str = 'curious') -> Theme:
    """Thema nach Name; unbekannt -> 'curious'. Alle Schlüssel aus KEYS sind garantiert vorhanden."""
    d = THEMES.get(name) or THEMES['curious']
    t = Theme(_CONSTS)
    t.update({k: v for k, v in d.items() if not k.startswith('_')})
    t['name'] = name if name in THEMES else 'curious'
    t['respect_mode'] = False
    t['_respect'] = d.get('_respect', {})
    return t


def respect(th: Theme) -> Theme:
    """Respekt-Variante (STIL.md 1.8): Hintergründe entsättigt, Akzente Elfenbein, Glow aus, Kerzenlicht."""
    r = Theme(th)
    spec = th.get('_respect') or {}
    for k in ('bg0', 'bg1', 'bg2'):
        r[k] = spec.get(k) or CO.hexs(CO.saturate(th[k], 0.7))
    r['accent'] = spec.get('accent') or th['ink']
    r['accent2'] = spec.get('accent2') or th['ink_soft']
    r['glow'] = None
    r['light_island'] = spec.get('light_island') or th['candle']
    r['respect_mode'] = True
    return r


def names() -> list:
    return sorted(THEMES)


def bed(name: str) -> str:
    return get(name).get('bed', 'cabinet_swing')


def costume(name: str) -> str:
    return get(name).get('costume', 'default')


def pairs(th: Theme) -> list:
    """Die vier Pflicht-Kontrastpaare mit Messwert (STIL.md 3.3)."""
    out = []
    for a, b in (('ink', 'bg0'), ('accent', 'bg0'), ('card_ink', 'card'), ('caption_ink', 'caption_bg')):
        out.append((a, b, round(CO.contrast(th[a], th[b]), 1)))
    return out


def sheet(out_path: str) -> str:
    """Farbbogen: je Thema Verlauf, Farbfelder, die vier Kontrastpaare mit Messwert, Untertitel-Probe."""
    from .canvas import Frame
    from . import fonts as F
    ns = names()
    cols, cw, ch = 2, 760, 420
    rows = (len(ns) + cols - 1) // cols
    fr = Frame(cols * cw, rows * ch)
    c = fr.c
    c.fill('#0D0D12')
    for i, n in enumerate(ns):
        th = get(n)
        x0, y0 = (i % cols) * cw, (i // cols) * ch
        c.rect(x0 + 12, y0 + 12, cw - 24, ch - 24, shader=c.linear(x0, y0, x0, y0 + ch, [th['bg0'], th['bg1']]), r=28)
        c.text(n.upper(), x0 + 36, y0 + 58, F.font('display', 40, weight=800), th['ink'])
        c.text(f"bett {th.get('bed')} · kostüm {th.get('costume')}", x0 + 36, y0 + 92, F.font('mono', 20), th['ink_soft'])
        sw = [('bg2', th['bg2']), ('accent', th['accent']), ('accent2', th['accent2']), ('glow', th['glow']), ('danger', th['danger']), ('ok', th['ok']), ('card', th['card']), ('card_hi', th['card_hi'])]
        for j, (k, col) in enumerate(sw):
            xx, yy = x0 + 36 + j * 86, y0 + 116
            c.rect(xx, yy, 72, 72, col, r=16)
            c.text(k, xx + 36, yy + 92, F.font('mono', 15), th['ink_soft'], 'center', 'middle')
        for j, (a, b, v) in enumerate(pairs(th)):
            xx, yy = x0 + 36 + j * 172, y0 + 232
            c.rect(xx, yy, 156, 64, th[b], r=14)
            c.text('Aa 12', xx + 12, yy + 32, F.font('display', 26, weight=800), th[a], 'left', 'middle')
            col = th['ok'] if v >= 4.5 else th['danger']
            c.text(f'{v}:1', xx + 144, yy + 32, F.font('mono', 18), col, 'right', 'middle')
            c.text(f'{a}/{b}', xx + 78, yy + 80, F.font('mono', 14), th['ink_soft'], 'center', 'middle')
        r = respect(th)
        for j, k in enumerate(('bg0', 'bg1', 'bg2', 'accent')):
            c.rect(x0 + 36 + j * 60, y0 + 336, 50, 40, r[k], r=10)
        c.text('respekt', x0 + 36 + 250, y0 + 356, F.font('mono', 16), th['ink_soft'], 'left', 'middle')
        c.rect(x0 + 420, y0 + 330, 300, 56, th['caption_bg'], r=18, alpha=0.92)
        c.text('caption', x0 + 440, y0 + 358, F.font('caption', 28, weight=700), th['caption_ink'], 'left', 'middle')
        c.text('word', x0 + 560, y0 + 358, F.font('caption', 28, weight=700), th['caption_hi'], 'left', 'middle')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fr.save_png(out_path)
    return out_path
