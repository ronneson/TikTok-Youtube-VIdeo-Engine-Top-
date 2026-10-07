"""Untertitel Wort für Wort: Wortgruppen von 3–5 Wörtern, aktives Wort hervorgehoben, Plakette dahinter.

Stil über cfg['look']: caption_style = 'word' (aktives Wort farbig) | 'karaoke' (gesprochene Wörter farbig) | 'line',
caption_size (px, Hochformat), caption_max_words, caption_max_chars, caption_upper (Versalien).
"""
from __future__ import annotations
from . import anim as A
from . import fonts as F

_CHUNK_CACHE: dict = {}


def chunks(tl, max_words=4, max_chars=24) -> list:
    """Teilt jede Zeile in Wortgruppen. Rückgabe: [{'words': [Word], 't0', 't1', 'line'}]. Zeitfenster bis zur nächsten Gruppe."""
    key = (id(tl), max_words, max_chars)
    if key in _CHUNK_CACHE:
        return _CHUNK_CACHE[key]
    out = []
    for ln in tl.lines:
        cur = []
        for w in ln.words:
            trial = ' '.join(x.w for x in cur + [w])
            if cur and (len(cur) >= max_words or len(trial) > max_chars):
                out.append({'words': cur, 'line': ln.id})
                cur = []
            cur.append(w)
            if w.w.endswith(('.', '!', '?')) and len(cur) >= 2:
                out.append({'words': cur, 'line': ln.id})
                cur = []
        if cur:
            out.append({'words': cur, 'line': ln.id})
    for i, ch in enumerate(out):
        ch['t0'] = ch['words'][0].t0
        nxt = out[i + 1]['words'][0].t0 if i + 1 < len(out) else ch['words'][-1].t1 + 1.0
        ch['t1'] = min(nxt, ch['words'][-1].t1 + 0.6)
    _CHUNK_CACHE[key] = out
    return out


def current(tl, t, max_words=4, max_chars=24):
    for ch in chunks(tl, max_words, max_chars):
        if ch['t0'] - 0.08 <= t < ch['t1']:
            return ch
    return None


def draw(c, fmt, tl, t, theme, cfg=None):
    look = (cfg or {}).get('look', {})
    if not look.get('captions', True):
        return
    style = look.get('caption_style', 'word')
    upper = look.get('caption_upper', False)
    size = look.get('caption_size', 56) * fmt.scale
    ch = current(tl, t, look.get('caption_max_words', 4), look.get('caption_max_chars', 24))
    if not ch:
        return
    th = theme
    f = F.font('caption', size, weight=look.get('caption_weight', 800))
    words = ch['words']
    texts = [w.w.upper() if upper else w.w for w in words]
    gap = size * 0.28
    widths = [c.text_width(s, f) for s in texts]
    total = sum(widths) + gap * (len(words) - 1)
    max_w = fmt.caption.w
    lines = [list(range(len(words)))]
    if total > max_w and len(words) > 1:
        # auf zwei Zeilen verteilen
        acc, split = 0, len(words)
        for i, w in enumerate(widths):
            acc += w + gap
            if acc > total / 2:
                split = i + 1
                break
        lines = [list(range(split)), list(range(split, len(words)))]
    lh = size * 1.18
    cy = fmt.caption.cy
    pop = 0.96 + 0.04 * A.out_back(min(1.0, (t - ch['t0'] + 0.08) / 0.16))
    # Plakette
    plate_w = max(sum(widths[i] for i in ln) + gap * (len(ln) - 1) for ln in lines) + size * 0.9
    plate_h = lh * len(lines) + size * 0.45
    with c.tf(sx=pop, px=fmt.cx, py=cy):
        c.rect_c(fmt.cx, cy, plate_w, plate_h, th.get('caption_bg', '#000000'), r=size * 0.36, alpha=look.get('caption_plate_alpha', 0.68))
        c.mark(fmt.cx - plate_w / 2, cy - plate_h / 2, plate_w, plate_h, 'caption', 'text')
        y = cy - (len(lines) - 1) * lh / 2
        for ln in lines:
            w_line = sum(widths[i] for i in ln) + gap * (len(ln) - 1)
            x = fmt.cx - w_line / 2
            for i in ln:
                w = words[i]
                active = w.t0 - 0.02 <= t < w.t1 + 0.08 or (t >= w.t1 and i == ln[-1] and ln is lines[-1] and t < ch['t1'] and all(t >= x_.t1 for x_ in words))
                spoken = t >= w.t0 - 0.02
                if style == 'karaoke':
                    col = th.get('caption_hi', '#FFC14A') if spoken else th.get('caption_ink', '#FFFFFF')
                    a = 1.0 if spoken else 0.55
                elif style == 'line':
                    col, a = th.get('caption_ink', '#FFFFFF'), 1.0
                else:
                    col = th.get('caption_hi', '#FFC14A') if (w.t0 - 0.02 <= t < w.t1 + 0.08) else th.get('caption_ink', '#FFFFFF')
                    a = 1.0
                sc = 1.0
                if style == 'word' and w.t0 - 0.02 <= t < w.t1 + 0.08:
                    sc = 1.0 + 0.07 * A.out_back(min(1.0, (t - w.t0 + 0.02) / 0.14))
                with c.tf(sx=sc, px=x + widths[i] / 2, py=y):
                    c.text(texts[i], x + widths[i] / 2, y, f, col, 'center', 'middle', alpha=a)
                x += widths[i] + gap
            y += lh
