"""Prüfungen vor dem Rendern: Sicherheitszonen (TikTok-Oberfläche), Untertitel-Kontrast, Telefonansicht.

Module melden wichtige Flächen mit c.mark(x, y, w, h, label); run() hält sie gegen die Zonen des Formats.
"""
from __future__ import annotations
import math
import os
import numpy as np
from .canvas import Frame
from . import fonts as F
from .color import luminance


def _frame_marks(comp, t):
    fr = Frame(comp.fmt.W, comp.fmt.H)
    fr.c.marks = []
    fr.canvas.clear(0xFF000000)
    comp.draw(fr.c, t)
    arr = fr.to_array()
    return arr, fr.c.marks


def _overlap(a, b) -> float:
    """Anteil von a, der in b liegt."""
    x0, y0 = max(a['x'], b['x']), max(a['y'], b['y'])
    x1, y1 = min(a['x'] + a['w'], b['x'] + b['w']), min(a['y'] + a['h'], b['y'] + b['h'])
    if x1 <= x0 or y1 <= y0 or a['w'] <= 0 or a['h'] <= 0:
        return 0.0
    return (x1 - x0) * (y1 - y0) / (a['w'] * a['h'])


def default_times(comp) -> list:
    """Je Szene: kurz nach dem Übergang, Mitte, kurz vor dem Ende."""
    ts = []
    for sc in comp.scenes:
        ts += [sc.t0 + min(1.0, sc.dur * 0.3), sc.t0 + sc.dur * 0.5, max(sc.t0, sc.t1 - 0.4)]
    return sorted(set(round(t, 2) for t in ts if 0 <= t < comp.duration))


def run(project_dir: str, times: list = None, root: str = None) -> dict:
    from . import compose
    comp = compose.load(project_dir, root)
    fmt = comp.fmt
    times = [comp.tl.at(t) if isinstance(t, str) else float(t) for t in times] if times else default_times(comp)
    zones = []
    zones.append(('top', {'x': 0, 'y': 0, 'w': fmt.W, 'h': fmt.safe_top}))
    zones.append(('bottom', {'x': 0, 'y': fmt.H - fmt.safe_bottom, 'w': fmt.W, 'h': fmt.safe_bottom}))
    zones.append(('left', {'x': 0, 'y': 0, 'w': fmt.safe_left, 'h': fmt.H}))
    zones.append(('right', {'x': fmt.W - fmt.safe_right, 'y': 0, 'w': fmt.safe_right, 'h': fmt.H}))
    if fmt.buttons:
        zones.append(('buttons', {'x': fmt.buttons.x, 'y': fmt.buttons.y, 'w': fmt.buttons.w, 'h': fmt.buttons.h}))
    problems, caption_report = [], []
    for t in times:
        arr, marks = _frame_marks(comp, t)
        for m in marks:
            for zname, z in zones:
                ov = _overlap(m, z)
                lim = 0.02 if m['kind'] == 'text' else 0.25
                if ov > lim:
                    problems.append({'t': round(t, 2), 'label': m['label'], 'kind': m['kind'], 'zone': zname, 'overlap': round(ov, 2)})
        # Untertitel-Kontrast: Helligkeit hinter dem Untertitel-Band
        cap = fmt.caption
        band = arr[int(cap.y):int(cap.y1), int(cap.x):int(cap.x1), :3].astype(np.float32) / 255.0
        if band.size:
            lum = (0.2126 * band[..., 0] + 0.7152 * band[..., 1] + 0.0722 * band[..., 2])
            caption_report.append({'t': round(t, 2), 'mean': round(float(lum.mean()), 3), 'p90': round(float(np.percentile(lum, 90)), 3)})
    ok = not problems
    return {'ok': ok, 'times': [round(t, 2) for t in times], 'problems': problems, 'caption_band': caption_report,
            'hint': '' if ok else 'Elemente liegen in Sicherheitszonen: Position/Größe in der Szene ändern.'}


def phone(project_dir: str, times: list, root: str = None, out_dir: str = None) -> list:
    """Bild so, wie das TikTok-Telefon es zeigt: Suchleiste, Knöpfe rechts, Kanalname und Caption unten."""
    from . import compose
    from PIL import Image
    comp = compose.load(project_dir, root)
    fmt = comp.fmt
    out_dir = out_dir or os.path.join(project_dir, 'check')
    os.makedirs(out_dir, exist_ok=True)
    outs = []
    for t in times:
        tt = comp.tl.at(t) if isinstance(t, str) else float(t)
        fr = Frame(fmt.W, fmt.H)
        fr.canvas.clear(0xFF000000)
        comp.draw(fr.c, tt)
        c = fr.c
        if fmt.portrait:
            _tiktok_ui(c, fmt, comp)
        else:
            _youtube_ui(c, fmt, comp)
        p = os.path.join(out_dir, f'phone_{tt:06.2f}.png')
        Image.fromarray(fr.to_rgb()).resize((fmt.W // 2, fmt.H // 2), Image.LANCZOS).save(p)
        outs.append(p)
    return outs


def _tiktok_ui(c, fmt, comp):
    W, H = fmt.W, fmt.H
    white = '#FFFFFF'
    # Statusleiste und Kopfzeile
    c.rect(0, 0, W, 120, '#000000', alpha=0.35)
    c.text('9:41', 60, 62, F.font('body', 36, weight=700), white, 'left', 'middle', alpha=0.9)
    hdr = F.font('body', 38, weight=600)
    c.text('Following', W / 2 - 120, 170, hdr, white, 'center', 'middle', alpha=0.6)
    c.text('For You', W / 2 + 120, 170, F.font('body', 38, weight=800), white, 'center', 'middle')
    c.rect(W / 2 + 90, 198, 60, 5, white)
    c.circle(W - 70, 170, 20, white, stroke=4)
    c.line(W - 56, 184, W - 40, 200, white, 4)
    # Suchleiste (wenn aus Profil/Suche geöffnet)
    c.rect(40, 215, W - 80, 64, '#FFFFFF', r=32, alpha=0.18)
    c.text('Search', 80, 247, F.font('body', 30), white, 'left', 'middle', alpha=0.7)
    # Knöpfe rechts
    x = W - 95
    c.circle(x, 1000, 52, '#DDDDDD'); c.circle(x, 1000, 52, white, stroke=4); c.circle(x, 1050, 18, '#FF2D55'); c.text('+', x, 1050, F.font('body', 30, weight=800), white, 'center', 'middle')
    for i, (lab, sym) in enumerate([('142.3K', '♥'), ('1,208', '●'), ('3,452', '★'), ('Share', '➦')]):
        yy = 1130 + i * 125
        c.circle(x, yy, 36, white, alpha=0.95)
        c.text(lab, x, yy + 62, F.font('body', 26, weight=600), white, 'center', 'middle')
    c.circle(x, 1660, 44, '#222222'); c.circle(x, 1660, 44, white, stroke=4); c.circle(x, 1660, 14, white)
    # Kanalname, Caption, Musik
    name = (comp.cfg.get('brand', {}).get('handle') or '@channel')
    c.text(name, 50, 1595, F.font('body', 36, weight=700), white, 'left', 'middle')
    cap = comp.script.get('caption', '') or ''
    lines = F.wrap(cap, 'body', 30, 760)[:2]
    c.text_lines(lines, 50, 1625, F.font('body', 30), white, 'left', 1.2)
    c.text('♪  original sound', 50, 1730, F.font('body', 28), white, 'left', 'middle', alpha=0.9)
    # Navigationsleiste unten
    c.rect(0, H - 110, W, 110, '#000000', alpha=0.85)
    for i, lab in enumerate(['Home', 'Friends', '', 'Inbox', 'Profile']):
        xx = W * (i + 0.5) / 5
        if lab:
            c.text(lab, xx, H - 40, F.font('body', 24), white, 'center', 'middle', alpha=0.8 if i else 1.0)
        else:
            c.rect(xx - 50, H - 90, 100, 48, white, r=10)
    # Zonen zur Orientierung (dünn)
    c.rect(fmt.buttons.x, fmt.buttons.y, fmt.buttons.w, fmt.buttons.h, '#FF0000', stroke=2, alpha=0.5)
    c.rect(0, fmt.safe_top, W, 1, '#FF0000', alpha=0.6)
    c.rect(0, H - fmt.safe_bottom, W, 1, '#FF0000', alpha=0.6)


def _youtube_ui(c, fmt, comp):
    W, H = fmt.W, fmt.H
    c.rect(0, H - 8, W * 0.37, 8, '#FF0000')
    c.rect(0, H - 8, W, 8, '#FFFFFF', alpha=0.3)
    c.rect(0, H - 100, W, 92, '#000000', alpha=0.3)
    c.text('▶   ▶▶   🔊  0:27 / 9:48', 40, H - 54, F.font('body', 30), '#FFFFFF', 'left', 'middle')
