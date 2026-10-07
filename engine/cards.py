"""Nummernkarten und Tafeln („Peel & Pop“, STIL.md Abschnitte 5, 4.2 und 1.4).

Alles hier ist UI- oder Karten-Ebene und wird ausschließlich mit canvas.C gezeichnet: Sammelkarte 560 px in Zwei-Ton-Gold,
Badge 240 px, Choreografie des Nummernwechsels (Variante A „Elster-Lieferung“, B „Zählwerk“, „one“ für #1 mit Krone,
Strahlen und Funkeln), Eintragstitel in der Haltezeit mit Gleitflug in die Kopfzeile, Meta-Pille, Serienetikett,
Album-Leiste (Fächer statt Balken), Wasserzeichen, Hook-Headline, Schlagwort-Sticker, Stat-Plakette mit Zählwerk,
Stempel und Flip-Karte. Jede Karte und Tafel ist ein Sticker (Schatten -> weißer Rand -> Farbe über c.sticker bzw.
c.override) und meldet ihre Fläche mit c.mark(kind 'card' | 'text') an. Alle Funktionen sind reine Funktionen der Zeit t.

Zeitachse eines Nummernwechsels (relativ zu t0, STIL.md 5.2): Flug/Iris t0 … t0+0.33, Landung t0+0.33, Haltezeit bis
t0+1.25 (Titel ab t0+0.55 per Wort-Stagger), Schrumpfen in den Badge-Slot t0+1.25 … t0+1.67, Meta-Pille ab t0+1.70.
"""
from __future__ import annotations
import math
import os
import re
import skia
from . import anim as A
from . import fonts as F
from . import theme as TH
from . import color as CO
from . import fx

__all__ = ['number_card', 'card_flight', 'flight_pos', 'title_plate', 'stat_plate', 'meta_tag', 'series_label', 'progress',
           'watermark', 'hook_title', 'keyword', 'stamp', 'flip_card', 'metrics', 'sheet']

TWO_PI = 2 * math.pi
SHADOW = (8.0, 16.0, 0.20)          # ein Schatten für alles (STIL.md 1.1)
CARD_SHADOW = (8.0, 16.0, 0.22)     # Sammelkarte (STIL.md 5.1)
SLOT_SHADOW = (4.0, 8.0, 0.20)      # Album-Fächer (40 px): Schatten halbiert, sonst unlesbar
T_LAND, T_HOLD, T_SHRINK0, T_SHRINK1, T_META = 0.33, 0.55, 1.25, 1.67, 1.70
STAGGER = 0.045

# Mini-Piktogramm im Themenstreifen der Karte (Mode silhouette, Elfenbein); props entscheidet, ob es den Namen kennt
THEME_ICON = {'curious': 'gem', 'heist': 'money_bag', 'cave': 'lantern', 'animal': 'paw', 'space': 'rocket',
              'history': 'scroll', 'ocean': 'anchor', 'medical': 'pill', 'crime': 'gavel', 'food': 'cheese'}


# ---------------------------------------------------------------- Maße und Helfer

def metrics(fmt) -> dict:
    """Maße aller Karten und Tafeln je Format (STIL.md 1.4, 4.2, 5.1). Hochformat sind die Leitwerte, Querformat hat eigene."""
    st = fmt.stage
    if fmt.portrait:
        return dict(
            card=560.0, card_r=72.0, card_rim=12.0, card_margin=44.0, digit=420.0, digit_one=500.0, hash=48.0, word=28.0,
            strip=72.0, icon=44.0, card_c=(fmt.cx, 860.0), iris_r=96.0, crown=120.0,
            badge=240.0, badge_r=48.0, badge_rim=8.0, badge_margin=22.0, badge_digit=150.0, badge_hash=24.0,
            badge_c=(fmt.card.cx, fmt.card.cy),
            title=72.0, title_min=60.0, title_floor=48.0, title_top=1160.0, title_w=660.0, title_cx=fmt.cx, title_lead=1.1,
            head=52.0, head_min=40.0, head_floor=34.0, head2=36.0, head_w=560.0, head_x=fmt.title.x, head_y=fmt.title.y + 4,
            head_pad=(14.0, 24.0), head_r=24.0, head_lines=1,
            meta=26.0, meta_min=22.0, meta_h=48.0, meta_rim=6.0, meta_w=360.0, meta_right=fmt.title.x1, meta_cy=fmt.title.cy,
            meta_left=None,
            label=28.0, label_x=fmt.label.x, label_y=310.0,
            stat=96.0, stat_min=72.0, stat_label=28.0, stat_w=440.0, stat_h=150.0, stat_rim=10.0, stat_r=48.0,
            stat_c=(st.x + 0.76 * st.w, st.y + 0.14 * st.h),
            key=80.0, key_min=56.0, key_w=500.0, key_c=(st.x + 0.72 * st.w, st.y + 0.22 * st.h),
            hook=104.0, hook_min=88.0, hook_floor=72.0, hook_w=660.0, hook_cy=860.0, hook_lead=1.06,
            slot=40.0, slot_gap=12.0, slot_r=12.0, slot_digit=22.0, slot_rim=4.0, slot_row_max=6,
            wm_head=44.0, wm_text=24.0,
            stamp=64.0, stamp_rim=6.0, stamp_frame=6.0, stamp_r=24.0, stamp_w=420.0, stamp_h=110.0,
            flip_w=300.0, flip_h=200.0, flip_r=24.0, flip_text=30.0, text_rim=8.0, mono_min=26.0,
        )
    k = 0.78
    return dict(
        card=460.0, card_r=60.0, card_rim=10.0, card_margin=36.0, digit=340.0, digit_one=400.0, hash=38.0, word=22.0,
        strip=58.0, icon=36.0, card_c=(st.cx, 480.0), iris_r=78.0, crown=100.0,
        badge=200.0, badge_r=40.0, badge_rim=6.0, badge_margin=18.0, badge_digit=120.0, badge_hash=20.0,
        badge_c=(fmt.card.cx, fmt.card.cy),
        title=56.0, title_min=46.0, title_floor=40.0, title_top=480.0 + 230.0 + 20.0, title_w=900.0, title_cx=st.cx, title_lead=1.1,
        head=56.0, head_min=40.0, head_floor=32.0, head2=48.0, head_w=fmt.title.w - 48, head_x=fmt.title.x, head_y=fmt.title.y,
        head_pad=(12.0, 20.0), head_r=20.0, head_lines=2,
        meta=22.0, meta_min=18.0, meta_h=40.0, meta_rim=5.0, meta_w=300.0, meta_right=None, meta_cy=fmt.title.y1 - 22,
        meta_left=fmt.title.x,
        label=22.0, label_x=fmt.label.x, label_y=fmt.label.cy,
        stat=76.0, stat_min=56.0, stat_label=22.0, stat_w=360.0, stat_h=118.0, stat_rim=8.0, stat_r=38.0,
        stat_c=(st.x + 0.84 * st.w, st.y + 0.16 * st.h),
        key=62.0, key_min=44.0, key_w=400.0, key_c=(st.x + 0.84 * st.w, st.y + 0.30 * st.h),
        hook=81.0, hook_min=68.0, hook_floor=56.0, hook_w=1000.0, hook_cy=st.cy - 40, hook_lead=1.06,
        slot=32.0, slot_gap=20.0, slot_r=10.0, slot_digit=18.0, slot_rim=4.0, slot_row_max=12,
        wm_head=40.0, wm_text=20.0,
        stamp=50.0, stamp_rim=5.0, stamp_frame=5.0, stamp_r=20.0, stamp_w=330.0, stamp_h=86.0,
        flip_w=234.0, flip_h=156.0, flip_r=20.0, flip_text=24.0, text_rim=6.0, mono_min=22.0,
    )


def _th(theme):
    return theme if theme is not None else TH.get('curious')


def _respect(th) -> bool:
    return bool(th.get('respect_mode'))


def _plain(c) -> bool:
    """True im Farbpass; False im Rand-, Schatten- oder Silhouettenpass (dort nur Hüllformen zeichnen)."""
    return c._over is None


def _breathe(t, amp=0.01, f=0.4, ph=0.0) -> float:
    return 1.0 + amp * math.sin(TWO_PI * f * t + ph)


def _hash01(*vals) -> float:
    """Deterministische Zahl 0..1 aus beliebigen Werten (Phasen, Drehungen, Funkelpositionen)."""
    h = 0
    for v in vals:
        for ch in str(v):
            h = (h * 31 + ord(ch)) % 1000003
    return (h % 997) / 997.0


def _rrect(cx, cy, w, h, r) -> skia.Path:
    p = skia.Path()
    p.addRoundRect(skia.Rect.MakeXYWH(cx - w / 2, cy - h / 2, w, h), float(r), float(r))
    return p


def _dashed_rrect(c, cx, cy, w, h, r, color, alpha=1.0, width=3.0, dash=(6.0, 6.0)):
    """Gestrichelter Rand eines abgerundeten Rechtecks (leeres Album-Fach)."""
    p = c.paint(color, alpha, stroke=width)
    p.setPathEffect(skia.DashPathEffect.Make([float(d) for d in dash], 0.0))
    c.k.drawPath(_rrect(cx, cy, w, h, r), p)


def _mono_spacing(size) -> float:
    """Laufweite +0.14 em für DM Mono (STIL.md 4.1)."""
    return 0.14 * size


def _sizes(size, min_size, floor):
    """Größenstufen von size abwärts (x 0.94) bis min_size, dann weiter bis floor."""
    out, s = [], float(size)
    while True:
        out.append(s)
        if s <= floor + 1e-6:
            return out
        s = max(floor, s * 0.94)


def _lines_fit(text, role, size, min_size, max_w, max_lines, floor=None, prefer_fewer=True) -> tuple:
    """Bricht text in höchstens max_lines Zeilen. prefer_fewer: erst eine Zeile von size bis min_size, dann zwei Zeilen usw.
    (Titel), sonst die größte Größe mit <= max_lines Zeilen (Schlagworte). Passt es bei min_size nicht, geht es bis floor
    (lange Titel bleiben lesbar). Rückgabe (lines, size)."""
    floor = min_size if floor is None else floor
    sizes = _sizes(size, min_size, floor)

    def fits(s, n):
        lines = F.wrap(text, role, s, max_w)
        f = F.font(role, s)
        return lines if len(lines) <= n and all(F.measure(ln, f) <= max_w for ln in lines) else None

    order = [(n, s) for n in range(1, max_lines + 1) for s in sizes if s >= min_size - 1e-6] if prefer_fewer else []
    order += [(max_lines, s) for s in sizes]
    for n, s in order:
        lines = fits(s, n)
        if lines:
            return lines, s
    s = sizes[-1]
    lines = F.wrap(text, role, s, max_w)
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + [' '.join(lines[max_lines - 1:])]
    return lines, s


def _words_layout(c, lines, f, x, top, align, leading, spacing=0.0) -> list:
    """Wortpositionen eines Textblocks: [{'w', 'cx', 'cy', 'width', 'line'}]; Zeilenmitte (Versalhöhe) bei top + (i + 0.5) * lh."""
    lh = f.getSize() * leading
    space = c.text_width(' ', f, spacing)
    out = []
    for i, ln in enumerate(lines):
        ws = ln.split()
        widths = [c.text_width(w, f, spacing) for w in ws]
        total = sum(widths) + space * (len(ws) - 1)
        x0 = x - total / 2 if align == 'center' else x - total if align == 'right' else x
        cy = top + (i + 0.5) * lh
        xx = x0
        for w, wd in zip(ws, widths):
            out.append({'w': w, 'cx': xx + wd / 2, 'cy': cy, 'width': wd, 'line': i})
            xx += wd + space
    return out


def _block_width(c, lines, f, spacing=0.0) -> float:
    return max(c.text_width(ln, f, spacing) for ln in lines) if lines else 0.0


def _draw_words(c, words, f, colors, spacing=0.0, scales=None, rots=None, alpha=1.0):
    """Wörter einzeln setzen (Pop je Wort möglich); colors = Farbe oder Liste je Wort."""
    for i, w in enumerate(words):
        col = colors[i] if isinstance(colors, (list, tuple)) else colors
        k = scales[i] if scales else 1.0
        if k <= 0.001:
            continue
        rot = rots[i] if rots else 0.0
        if k != 1.0 or rot:
            with c.tf(rot=rot, sx=k, px=w['cx'], py=w['cy']):
                c.text(w['w'], w['cx'], w['cy'], f, col, 'center', 'middle', alpha, spacing)
        else:
            c.text(w['w'], w['cx'], w['cy'], f, col, 'center', 'middle', alpha, spacing)


def _pop_sticker(c, th, body, hull, t, t0, px, py, rim, shadow=SHADOW, dur=0.32, overshoot=1.17, k_out=1.0, breathe=0.0,
                 rot_in=-6.0, ph=0.0):
    """Sticker mit Pop-In (Scale 0 -> 1.08 -> 1, Drehung rot_in -> 0, 320 ms) um (px, py). Antizipation: der Schattenfleck der
    fertigen Form erscheint 60 ms vor der Form (STIL.md 1.5). body(c) zeichnet den Sticker, hull(c) seine Hüllform.
    k_out 1 -> 0 ist der Pop-Out (Scale -> 0, +15°). Rückgabe: Pop-Skalierung (0 = unsichtbar)."""
    if k_out <= 0.001 or t < t0 - 0.06:
        return 0.0
    k = A.pop(t, t0, dur, overshoot) if t >= t0 else 0.0
    if breathe and t >= t0 + dur:
        k *= _breathe(t, breathe, ph=ph)
    dy, sigma, sa = shadow
    a_sh = sa * A.clamp01((t - (t0 - 0.06)) / 0.06) * k_out
    rot = rot_in * (1.0 - min(1.0, k)) + 15.0 * (1.0 - k_out)
    with c.tf(x=0.0, y=dy):
        with c.override(th.get('shadow', '#000000'), rim, sigma, a_sh):
            hull(c)
    if k <= 0.001:
        return 0.0
    with c.tf(rot=rot, sx=k * k_out, px=px, py=py):
        with c.override(th['line'], rim):
            body(c)
        body(c)
    return k * k_out


def _out_scale(k_out) -> tuple:
    """Pop-Out (STIL.md 1.5): Scale 1 -> 0.9 -> 0 und +15° über k_out 1 -> 0 (Zeitverlauf in_cubic liefert der Aufrufer)."""
    k = A.clamp01(k_out)
    return k, 15.0 * (1.0 - k)


def _squash(t, t_land, amount=0.08) -> tuple:
    """Landen (STIL.md 1.5): 90 ms sy 1 -> 1 - amount, dann Feder zurück (stiffness 324, damping 19.8); sx = 1/sqrt(sy)."""
    if t < t_land:
        return 1.0, 1.0
    u = t - t_land
    if u < 0.09:
        sy = 1.0 - amount * A.out_quad(u / 0.09)
    else:
        sy = (1.0 - amount) + amount * A.spring(t, t_land + 0.09, 324.0, 19.8)
    sy = max(0.5, sy)
    return 1.0 / math.sqrt(sy), sy


def _sparkles(c, cx, cy, rx, ry, t, t0, th, n=12, seed=0, dur=1.6, rise=0.0, size=18.0):
    """n Funkel-Sterne in glow um eine Fläche (rx, ry): jeder lebt 0.5 s (Scale 0 -> 1 -> 0, Phase aus seed), rise = Aufstieg in px.
    Nur im Farbpass und nie im Respekt-Modus (glow aus)."""
    if not _plain(c) or not th.get('glow') or t < t0:
        return
    col = th['glow']
    for i in range(n):
        h1, h2, h3 = _hash01(seed, i, 'a'), _hash01(seed, i, 'b'), _hash01(seed, i, 'c')
        start = t0 + h1 * max(0.05, dur - 0.5)
        u = (t - start) / 0.5
        if u < 0 or u > 1:
            continue
        k = math.sin(math.pi * u)
        ang = h2 * TWO_PI
        px = cx + math.cos(ang) * rx * (0.85 + 0.35 * h3)
        py = cy + math.sin(ang) * ry * (0.85 + 0.35 * h3) - rise * u
        r = size * (0.7 + 0.6 * h3) * k
        if r < 1:
            continue
        c.glow(px, py, r * 2.2, col, 0.25 * k, sigma=r)
        c.star(px, py, r, r * 0.32, 4, col, alpha=0.95, rot=-90 + 20 * (h2 - 0.5))


# ---------------------------------------------------------------- Die Sammelkarte

def _card_params(M, kind='big', one=False):
    """Parametersatz der Karte: 'big' (Haltezeit, #1 x 1.15) oder 'badge' (gedockt). Alle Werte linear interpolierbar."""
    if kind == 'badge':
        return dict(size=M['badge'], r=M['badge_r'], rim=M['badge_rim'], margin=M['badge_margin'], digit=M['badge_digit'],
                    hash=M['badge_hash'], strip=0.0, word=M['word'], icon=M['icon'], band=0.0)
    s = 1.15 if one else 1.0
    return dict(size=M['card'] * s, r=M['card_r'] * s, rim=M['card_rim'], margin=M['card_margin'] * s,
                digit=(M['digit_one'] if one else M['digit']), hash=M['hash'], strip=M['strip'], word=M['word'], icon=M['icon'],
                band=(0.38 if one else 0.0))


def _lerp_params(a, b, u):
    return {k: a[k] + (b[k] - a[k]) * u for k in a}


def _card_face(c, th, P, rank, t, word='', icon=None, roll=None, flash=0.0):
    """Zeichnet die Karte um (0, 0): Gold-Körper, obere 46 % in card_hi (Kante 4° schräg), Glanzpunkt, '#', Ziffer (Unbounded 900),
    Themenstreifen in Tinte mit Wort + Mini-Piktogramm, Koralle-Eckband 'TOP' (#1). Im Rand-/Schattenpass nur der Körper.
    roll = (old_rank, old_dy, new_dy) lässt die Ziffern im Zählwerk rollen; flash 0..1 blitzt die Goldfläche."""
    s = P['size']
    h = s / 2.0
    body = _rrect(0, 0, s, s, P['r'])
    c.path(body, th['card'])
    if not _plain(c):
        return
    margin, strip = P['margin'], P['strip']
    with c.clip_path(body):
        yc = -h + 0.46 * s
        dy = h * math.tan(math.radians(4.0))
        c.poly([(-h - 8, -h - 8), (h + 8, -h - 8), (h + 8, yc - dy), (-h - 8, yc + dy)], th['card_hi'])
        a = 0.8 + 0.2 * math.sin(TWO_PI * 1.3 * t)
        c.ellipse(-h + 0.31 * s, -h + 0.11 * s, 0.06 * s, 0.035 * s, CO.lighten(th['card_hi'], 0.10), a, rot=-22)
        if P['band'] > 0.01:
            bw = P['band'] * s
            c.poly([(h - bw, -h - 2), (h + 2, -h - 2), (h + 2, -h + bw)], th['danger'])
            fb = F.font('mono', max(10.0, 24.0 * s / 560.0))
            with c.tf(rot=45.0, px=h - bw * 0.36, py=-h + bw * 0.36):
                c.text('TOP', h - bw * 0.36, -h + bw * 0.36, fb, th['ink'], 'center', 'middle', spacing=_mono_spacing(fb.getSize()))
        if strip > 1.0:
            c.rect(-h - 2, h - strip, s + 4, strip + 2, th['card_ink'])
            fw = F.font('mono', P['word'])
            sp = _mono_spacing(P['word'])
            ww = c.text_width(word, fw, sp)
            icon_px = P['icon'] if icon else 0.0
            gap = 16.0 if icon else 0.0
            total = ww + gap + icon_px
            x0 = -total / 2
            sy = h - strip / 2
            a_strip = A.clamp01((strip - 1.0) / 24.0)
            if icon:
                from . import props
                with c.layer(a_strip) if a_strip < 1 else _null():
                    props.draw(c, icon, x0 + icon_px / 2, sy, icon_px, t, th, mode='silhouette', color=th['ink'])
            c.text(word, x0 + icon_px + gap, sy, fw, th['ink'], 'left', 'middle', a_strip, sp)
        if flash > 0:
            c.rect(-h - 2, -h - 2, s + 4, s + 4, th['line'], alpha=0.25 * flash)
    fh = F.font('mono', P['hash'])
    c.text('#', -h + margin, -h + margin, fh, th['card_ink'], 'left', 'top')
    digit = str(rank)
    dsz = F.fit_size(digit, 'number', s - 2 * margin, P['digit'], P['digit'] * 0.45)
    fd = F.font('number', dsz)
    dyc = (margin + P['hash'] - strip) / 2.0
    if roll is None:
        c.text(digit, 0, dyc, fd, th['card_ink'], 'center', 'middle')
    else:
        old_rank, old_dy, new_dy = roll
        zone = skia.Path()
        zone.addRect(skia.Rect.MakeLTRB(-h, -h + margin + P['hash'] * 0.9, h, h - max(strip, margin * 0.5)))
        with c.clip_path(zone):
            c.text(str(old_rank), 0, dyc + old_dy, fd, th['card_ink'], 'center', 'middle')
            c.text(digit, 0, dyc + new_dy, fd, th['card_ink'], 'center', 'middle')


class _null:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


def _card_sticker(c, th, P, rank, cx, cy, t, word='', icon=None, rot=0.0, sx=1.0, sy=1.0, pivot=None, roll=None, flash=0.0,
                  shadow=CARD_SHADOW, label=None):
    """Karte als Sticker um (cx, cy): Schatten der Hüllform -> weißer Rand -> Farbe; Squash/Rotation um pivot (lokal)."""
    s = P['size']
    rim = P['rim']
    px, py = pivot if pivot else (0.0, 0.0)

    def hull(cc):
        cc.path(_rrect(0, 0, s, s, P['r']), th['card'])

    def body(cc):
        _card_face(cc, th, P, rank, t, word, icon, roll, flash)

    with c.tf(x=cx, y=cy, rot=rot, sx=sx, sy=sy, px=px, py=py):
        dy, sigma, sa = shadow
        with c.tf(x=0.0, y=dy):
            with c.override(th.get('shadow', '#000000'), rim, sigma, sa):
                hull(c)
        with c.override(th['line'], rim):
            hull(c)
        body(c)
        c.mark(-s / 2, -s / 2, s, s, label or f'card#{rank}', 'card')


def _card_word(th, word) -> str:
    return str(word if word else th.get('name', 'curious')).upper()


def _card_icon(th, icon=None):
    try:
        from . import props
    except Exception:
        return None
    name = icon or THEME_ICON.get(th.get('name', 'curious'), 'question')
    return name if props.has(name) else ('question' if props.has('question') else None)


def flight_pos(fmt, t, t0, variant='A') -> tuple:
    """Lage der fliegenden Karte (x, y, rot, scale) für t in [t0, t0 + 0.33), sonst None.
    Variante A: Odd bringt die Karte von oben rechts, hält sie am Schnabel (Oberkante Mitte, siehe beak_point) und lässt sie
    bei t0 + 0.22 über der Bildmitte los; sie fällt 100 px mit -18° -> 0° und landet bei t0 + 0.33.
    Variante 'one': Wurf aus Odds Position (Bühne 0.5 / 0.56) im Bogen in die Mitte, Scale 0.5 -> 1."""
    M = metrics(fmt)
    u = t - t0
    if u < 0 or u >= T_LAND:
        return None
    cx, cy = M['card_c']
    st = fmt.stage
    big = M['card'] * (1.15 if variant == 'one' else 1.0)
    if variant == 'one':
        v = u / T_LAND
        sx0, sy0 = st.x + 0.50 * st.w, st.y + 0.56 * st.h
        x = sx0 + (cx - sx0) * A.out_quad(v)
        y = sy0 + (cy - sy0) * v - 0.30 * st.h * 4 * v * (1 - v)
        return (x, y, -30.0 * (1.0 - A.out_quad(v)), 0.5 + 0.5 * A.out_quad(v))
    drop = 100.0
    x0, y0 = fmt.W + 0.35 * big, st.y + 0.10 * st.h
    rx, ry = cx, cy - drop
    if u < 0.22:
        v = A.out_quad(u / 0.22)
        return (x0 + (rx - x0) * v, y0 + (ry - y0) * v, -18.0, 0.72)
    v = (u - 0.22) / (T_LAND - 0.22)
    return (cx, ry + drop * A.in_quad(v), -18.0 * (1.0 - A.out_quad(v)), 0.72 + 0.28 * A.out_quad(v))


def beak_point(fmt, t, t0, variant='A') -> tuple:
    """Punkt, an dem Odds Schnabelspitze die Karte hält (Oberkante Mitte der gedrehten Karte); None, wenn keine Karte fliegt oder
    sie schon losgelassen ist (ab t0 + 0.22 in Variante A)."""
    pos = flight_pos(fmt, t, t0, variant)
    if pos is None or (variant != 'one' and t - t0 >= 0.22):
        return None
    M = metrics(fmt)
    x, y, rot, sc = pos
    half = M['card'] * (1.15 if variant == 'one' else 1.0) * sc / 2
    a = math.radians(rot)
    return (x + half * math.sin(a), y - half * math.cos(a))


def card_flight(c, fmt, rank, t, t0, theme, variant='A', word=None, icon=None):
    """Die Karte im Flug (t0 … t0 + 0.33): am Schnabel der Elster (Variante A) oder im Wurf (#1). scenes.py ruft sie nach dem
    Zeichnen von Odd, damit die Karte vor dem Schnabel liegt; number_card(..., flight=False) überlässt ihr dann diesen Abschnitt.
    Smear: zwischen t0 + 0.03 und t0 + 0.17 wird die Karte bis 1.3x entlang des Bewegungsvektors gestreckt."""
    th = _th(theme)
    M = metrics(fmt)
    pos = flight_pos(fmt, t, t0, variant)
    if pos is None:
        return
    x, y, rot, sc = pos
    one = variant == 'one'
    P = _card_params(M, 'big', one and rank == 1)
    P = dict(P)
    P['size'] *= sc
    P['r'] *= sc
    P['margin'] *= sc
    P['digit'] *= sc
    P['hash'] *= sc
    P['strip'] *= sc
    P['word'] *= sc
    P['icon'] *= sc
    P['rim'] = max(4.0, P['rim'] * max(0.7, sc))
    u = t - t0
    nxt = flight_pos(fmt, t + 1.0 / fmt.fps, t0, variant)
    smear = 0.0
    if 0.03 <= u <= 0.17 and nxt is not None and not one:
        smear = 0.3 * (1.0 - abs((u - 0.10) / 0.07))
    word = _card_word(th, word)
    icon = _card_icon(th, icon)
    if smear > 0.01 and nxt:
        ang = math.degrees(math.atan2(nxt[1] - y, nxt[0] - x))
        with c.tf(rot=ang, sx=1.0 + smear, px=x, py=y):
            with c.tf(rot=-ang, px=x, py=y):
                _card_sticker(c, th, P, rank, x, y, t, word, icon, rot=rot)
    else:
        _card_sticker(c, th, P, rank, x, y, t, word, icon, rot=rot)


def _iris_card(c, fmt, M, th, rank, t, t0, P, word, icon, total):
    """Variante B „Zählwerk“: Sticker-Iris (Radius 96, Rand 12) wächst ab t0 - 0.03 in 360 ms (out_back s 1.7) aus der Mitte;
    darin rollt die alte Ziffer nach oben hinaus und die neue von unten herein (260 ms, 6 % Überschwingen)."""
    cx, cy = M['card_c']
    s = P['size']
    u = A.clamp01((t - (t0 - 0.03)) / 0.36)
    m = A.out_back(u, 1.7) if u < 1.0 else 1.0
    mw = max(4.0, s * m)
    mr = min(M['iris_r'], mw / 2)
    v = A.clamp01((t - t0) / 0.26)
    e = A.out_back(v, 0.6)
    roll_h = s * 0.72
    old_rank = min(total, rank + 1)
    roll = (old_rank, -roll_h * e, roll_h * (1.0 - e))
    with c.clip_rect(cx - mw / 2 - P['rim'], cy - mw / 2 - P['rim'], mw + 2 * P['rim'], mw + 2 * P['rim'], r=mr + P['rim']):
        _card_sticker(c, th, P, rank, cx, cy, t, word, icon, roll=roll)
    if u < 1.0:
        c.rect_c(cx, cy, mw, mw, th['line'], r=mr, stroke=P['rim'])


def number_card(c, fmt, rank, t, t0, theme, total=5, k_out=1.0, variant=None, word=None, icon=None, flight=True, effects=True,
                seed=0):
    """Countdown-Karte mit der ganzen Choreografie ab t0 (STIL.md 5.1/5.2): Variante 'A' (Elster-Lieferung: Flug, Fall, Landung
    mit Squash und 24 Konfetti), 'B' (Zählwerk per Sticker-Iris, Goldblitz bei t0 + 0.33) oder 'one' (#1: Wurf, Krone 200 ms
    nach der Landung, Lichtstrahlen und 12 Funkeln in der Haltezeit; rank 1 wählt 'one' immer). Haltezeit t0 + 0.33 … 1.25 als
    große Karte in der Bildmitte, Schrumpfen in den Badge-Slot t0 + 1.25 … 1.67 (in_out_cubic), danach Badge mit Atmen 1 %.
    k_out 1 -> 0 ist der Pop-Out des Badges beim nächsten Wechsel. word/icon überschreiben Themenwort und Mini-Piktogramm;
    flight=False lässt den Flugabschnitt aus (scenes.py zeichnet ihn mit card_flight vor dem Schnabel); effects=False schaltet
    Konfetti, Strahlen und Funkeln ab (Respekt-Modus tut das automatisch)."""
    th = _th(theme)
    M = metrics(fmt)
    if k_out <= 0.001 or t < t0 - 0.03:
        return
    if rank == 1:
        variant = 'one'
    variant = variant or 'A'
    one = rank == 1
    respect = _respect(th)
    fxon = effects and not respect
    t_land, t_s0, t_s1 = t0 + T_LAND, t0 + T_SHRINK0, t0 + T_SHRINK1
    word = _card_word(th, word)
    icon = _card_icon(th, icon)
    Pbig = _card_params(M, 'big', one)
    Pbadge = _card_params(M, 'badge')
    cx, cy = M['card_c']
    bx, by = M['badge_c']

    if t < t_land:
        if variant == 'B':
            _iris_card(c, fmt, M, th, rank, t, t0, Pbig, word, icon, total)
        elif flight:
            card_flight(c, fmt, rank, t, t0, th, variant, word, icon)
        return

    if t < t_s0:
        u_ray = 1.0
        P = Pbig
        x, y = cx, cy
        sx, sy = _squash(t, t_land) if variant != 'B' else (1.0, 1.0)
        br = _breathe(t)
        flash = max(0.0, 1.0 - (t - t_land) / 0.10) if variant == 'B' else 0.0
        crown_k = A.pop(t, t_land + 0.20, 0.32, 1.22) if one else 0.0
    elif t < t_s1:
        u = A.in_out_cubic((t - t_s0) / (T_SHRINK1 - T_SHRINK0))
        u_ray = 1.0 - u
        P = _lerp_params(Pbig, Pbadge, u)
        x, y = cx + (bx - cx) * u, cy + (by - cy) * u
        sx, sy = 1.0, 1.0
        br = _breathe(t)
        flash = 0.0
        crown_k = A.clamp01(1.0 - 2.5 * u) if one else 0.0
    else:
        u_ray = 0.0
        P = Pbadge
        x, y = bx, by
        sx, sy = 1.0, 1.0
        br = _breathe(t)
        flash = 0.0
        crown_k = 0.0

    k, rot_out = _out_scale(k_out) if t >= t_s1 else (1.0, 0.0)
    if one and fxon and u_ray > 0.01 and th.get('glow'):
        st = fmt.stage
        with c.clip_rect(st.x, st.y, st.w, st.h):
            with c.layer(u_ray):
                fx.light_rays(c, x, y, t, th, n=9, length=0.62 * max(fmt.W, fmt.H), alpha=0.16, spread=16.0, speed=5.0)
    half = P['size'] / 2
    _card_sticker(c, th, P, rank, x, y, t, word, icon, rot=rot_out, sx=sx * br * k, sy=sy * br * k, pivot=(0.0, half), flash=flash)
    if one and crown_k > 0.001 and t >= t_land:
        from . import props
        props.draw(c, 'crown', x - 0.37 * P['size'], y - half - 0.01 * P['size'], M['crown'] * P['size'] / Pbig['size'], t, th, rot=-14.0, k=crown_k, seed=seed)
    if one and fxon and u_ray > 0.01:
        _sparkles(c, x, y, half * 1.05, half * 1.05, t, t_land + 0.1, th, n=12, seed=seed + rank, dur=0.9, size=16.0 * P['size'] / Pbig['size'])
    if fxon and variant != 'B' and t_land <= t < t_land + 1.4:
        # Konfetti aus den unteren Ecken der Landestelle (je Seite die Hälfte), nicht über der Ziffer
        n = 40 if one else 24
        hb = Pbig['size'] / 2
        fx.confetti_burst(c, cx - hb * 0.8, cy + hb, t, t_land, th, n=n // 2, seed=seed + rank * 3, dur=1.4, power=780)
        fx.confetti_burst(c, cx + hb * 0.8, cy + hb, t, t_land, th, n=n - n // 2, seed=seed + rank * 3 + 1, dur=1.4, power=780)


# ---------------------------------------------------------------- Titel: Haltezeit und Kopfzeile

def _title_layout(c, fmt, M, title) -> dict:
    """Zeilen und Größen des Titels: Haltezeit (72 px, fit bis 60, max. 2 Zeilen, zentriert) und Kopfzeile (52 px, fit bis 40,
    eine Zeile <= 560 px; zweizeilige Titel behalten ihre Zeilen in der Kopfzeile kleiner). Gleiche Zeilenbrüche in beiden
    Zuständen, damit der Gleitflug eine reine Transformation ist."""
    lines, hold = _lines_fit(title, 'display', M['title'], M['title_min'], M['title_w'], 2, M['title_floor'])
    if len(lines) == 1 or M['head_lines'] >= 2:
        if len(lines) == 1:
            head = F.fit_size(title, 'display', M['head_w'], M['head'], M['head_floor'])
        else:
            head = min(F.fit_size(ln, 'display', M['head_w'], M['head2'], M['head_floor'] * 0.85) for ln in lines)
    else:
        head = min(F.fit_size(ln, 'display', M['head_w'], M['head2'], M['head_floor'] * 0.85) for ln in lines)
    return {'lines': lines, 'hold': hold, 'head': head}


def _header_box(c, M, L, size=None) -> tuple:
    """Plakette der Kopfzeile (x, y, w, h) für die Zeilen bei Größe size (Standard: Kopfzeilengröße)."""
    size = L['head'] if size is None else size
    f = F.font('display', size)
    pv, ph = M['head_pad']
    lh = size * M['title_lead']
    w = _block_width(c, L['lines'], f) + 2 * ph
    h = lh * len(L['lines']) + 2 * pv
    return (M['head_x'], M['head_y'], w, h)


def title_plate(c, fmt, title, t, t0, theme, k_out=1.0, rank=None):
    """Eintragstitel: ab t0 + 0.55 als Sticker-Text (Elfenbein, Rand 8) unter der großen Karte, Wort für Wort mit 45 ms Versatz
    (Pop-In); t0 + 1.25 … 1.67 gleitet er in die Kopfzeile (72 -> 52 px, Rand verschwindet, Tinte-Plakette alpha 0.92 wächst
    dahinter); danach gedockte Kopfzeile. k_out 1 -> 0 = Pop-Out der Kopfzeile. rank=1 rückt den Titel unter die
    größere #1-Karte (644 px)."""
    th = _th(theme)
    M = metrics(fmt)
    if not title or k_out <= 0.001 or t < t0 + T_HOLD:
        return
    if rank == 1:
        M = dict(M)
        M['title_top'] = max(M['title_top'], M['card_c'][1] + M['card'] * 1.15 / 2 + 22)
    L = _title_layout(c, fmt, M, title)
    lines = L['lines']
    t_s0, t_s1 = t0 + T_SHRINK0, t0 + T_SHRINK1
    u = 0.0 if t < t_s0 else 1.0 if t >= t_s1 else A.in_out_cubic((t - t_s0) / (T_SHRINK1 - T_SHRINK0))
    size = L['hold'] + (L['head'] - L['hold']) * u
    f = F.font('display', size)
    lh = size * M['title_lead']
    pv, ph = M['head_pad']
    hx, hy, hw, hh = _header_box(c, M, L)
    # Zeilenursprünge: Haltezeit zentriert bei title_cx / title_top, Kopfzeile linksbündig in der Plakette
    words = []
    for i, ln in enumerate(lines):
        ws = ln.split()
        widths = [c.text_width(w, f) for w in ws]
        space = c.text_width(' ', f)
        total = sum(widths) + space * (len(ws) - 1)
        x_hold = M['title_cx'] - total / 2
        y_hold = M['title_top'] + (i + 0.5) * lh
        x_head = hx + ph
        y_head = hy + pv + (i + 0.5) * lh
        x0 = x_hold + (x_head - x_hold) * u
        cy = y_hold + (y_head - y_hold) * u
        xx = x0
        for w, wd in zip(ws, widths):
            words.append({'w': w, 'cx': xx + wd / 2, 'cy': cy, 'width': wd, 'line': i})
            xx += wd + space
    rim = M['text_rim'] * (1.0 - A.smoothstep((u - 0.25) / 0.5))
    plate_a = 0.92 * A.smoothstep((u - 0.45) / 0.45)
    k, rot_out = _out_scale(k_out) if u >= 1.0 else (1.0, 0.0)
    if k <= 0.001:
        return
    scales = [1.0] * len(words)
    rots = [0.0] * len(words)
    if u <= 0.0:
        for j in range(len(words)):
            kk = A.pop(t, t0 + T_HOLD + j * STAGGER, 0.32, 1.17)
            scales[j] = kk
            rots[j] = -6.0 * (1.0 - min(1.0, kk))
    # Blockmaße (für Plakette und Mark)
    bw = _block_width(c, lines, f)
    bh = lh * len(lines)
    bx = min(w['cx'] - w['width'] / 2 for w in words)
    by = words[0]['cy'] - lh / 2
    px, py = hx, hy + hh / 2
    with c.tf(rot=rot_out, sx=k, px=px, py=py):
        if plate_a > 0.001:
            pw = bw + 2 * ph
            phh = bh + 2 * pv
            pxx, pyy = bx - ph, by - pv
            dy, sigma, sa = SHADOW
            c.rect(pxx, pyy + dy, pw, phh, th.get('shadow', '#000000'), M['head_r'], sa * plate_a, blur=sigma)
            c.rect(pxx, pyy, pw, phh, th['caption_bg'], M['head_r'], plate_a)
        col = th['ink']

        def body(cc):
            _draw_words(cc, words, f, col, 0.0, scales, rots)

        if rim >= 1.0:
            c.sticker(body, rim=rim, rim_color=th['line'], shadow=SHADOW)
        else:
            body(c)
        c.mark(bx, by, bw, bh, 'title', 'text')


# ---------------------------------------------------------------- Stat-Plakette (Zählwerk, tabellarisch)

_NUM_RE = re.compile(r'\d[\d,\.]*\d|\d')


def split_value(value) -> tuple:
    """Zerlegt '$18M' in ('$', '18', 'M'): erste Ziffernfolge (mit , und .) ist die Zahl, Rest Präfix/Suffix."""
    s = str(value)
    m = _NUM_RE.search(s)
    if not m:
        return s, '', ''
    return s[:m.start()], m.group(0), s[m.end():]


def _format_like(v: float, pattern: str) -> str:
    """Formatiert v wie pattern ('300,000' -> Tausenderkomma, '1.5' -> eine Nachkommastelle)."""
    dec = len(pattern.split('.')[1]) if '.' in pattern else 0
    if ',' in pattern:
        return f'{v:,.{dec}f}'
    return f'{v:.{dec}f}'


def _tabular_widths(c, f) -> float:
    return max(c.text_width(d, f) for d in '0123456789')


def stat_plate(c, fmt, value, label, t, t0, theme, count=True, x=None, y=None, k_out=1.0, pair=False, seed=0):
    """Stat-Plakette (Elfenbein-Sticker, Rand 10, Radius 48, <= 440 x 150): Wert Unbounded 800 96 px (fit bis 72), Label DM Mono
    28 Versalien in Tinte alpha 0.7. Mit count zählt die Zahl 0.8 s (out_quart) hoch; Präfix/Suffix ('$', 'M', ' t') bleiben
    stehen, Ziffern laufen tabellarisch (feste Breite je Ziffer, rechtsbündig), die letzte Ziffer poppt 1.15 für 100 ms.
    Pop-In bei t0 mit Schatten-Antizipation. x/y überschreiben den Anker (Bühne 0.76 / 0.14); pair=True rückt sie auf
    0.10, wenn zugleich ein Schlagwort steht (STIL.md 1.4)."""
    th = _th(theme)
    M = metrics(fmt)
    if t < t0 - 0.06 or k_out <= 0.001:
        return
    cx = M['stat_c'][0] if x is None else x
    cy = (M['stat_c'][1] - (0.04 * fmt.stage.h if pair else 0.0)) if y is None else y
    pre, num, suf = split_value(value)
    label = str(label or '').upper()
    inner_w = M['stat_w'] - 2 * 36
    full = pre + num + suf
    vsz = F.fit_size(full, 'number', inner_w, M['stat'], M['stat_min'], weight=800)
    fl = F.font('mono', M['stat_label'])
    sp = _mono_spacing(M['stat_label'])
    # tabellarische Breite kann breiter sein als der proportionale Satz: Größe daran einpassen
    for _ in range(16):
        fv = F.font('number', vsz, weight=800)
        dw = _tabular_widths(c, fv)

        def adv(ch, fv=fv, dw=dw):
            return dw if ch.isdigit() else c.text_width(ch, fv)

        w_pre, w_num, w_suf = c.text_width(pre, fv), sum(adv(ch) for ch in num), c.text_width(suf, fv)
        w_val = w_pre + w_num + w_suf
        if w_val <= inner_w or vsz <= M['stat_min'] * 0.7:
            break
        vsz *= 0.94
    w_lab = c.text_width(label, fl, sp) if label else 0.0
    pw = min(M['stat_w'], max(w_val, w_lab) + 2 * 36)
    ph = M['stat_h'] if label else M['stat_h'] * 0.72
    target = float(num.replace(',', '')) if num else 0.0
    if count and num:
        v = A.count_value(t, t0, 0.8, 0.0, target, 'out_quart')
        shown = _format_like(v, num) if t < t0 + 0.8 else num
    else:
        shown = num
    u_last = A.clamp01((t - (t0 + 0.8)) / 0.10)
    last_k = (1.15 - 0.15 * A.out_quad(u_last)) if (count and num and t >= t0 + 0.8) else 1.0
    y_val = -ph * 0.12 if label else 0.0
    y_lab = ph * 0.28

    def hull(cc):
        cc.path(_rrect(cx, cy, pw, ph, M['stat_r']), th['ink'])

    def body(cc):
        cc.path(_rrect(cx, cy, pw, ph, M['stat_r']), th['ink'])
        if not _plain(cc):
            return
        x0 = cx - w_val / 2
        cc.text(pre, x0, cy + y_val, fv, th['card_ink'], 'left', 'middle')
        xr = x0 + w_pre + w_num
        for idx, ch in enumerate(reversed(shown)):
            a = adv(ch)
            xr -= a
            kk = last_k if idx == 0 else 1.0
            if kk != 1.0:
                with cc.tf(sx=kk, px=xr + a / 2, py=cy + y_val):
                    cc.text(ch, xr + a / 2, cy + y_val, fv, th['card_ink'], 'center', 'middle')
            else:
                cc.text(ch, xr + a / 2, cy + y_val, fv, th['card_ink'], 'center', 'middle')
        cc.text(suf, x0 + w_pre + w_num, cy + y_val, fv, th['card_ink'], 'left', 'middle')
        if label:
            cc.text(label, cx, cy + y_lab, fl, th['card_ink'], 'center', 'middle', 0.7, sp)

    k = _pop_sticker(c, th, body, hull, t, t0, cx, cy, M['stat_rim'], SHADOW, k_out=k_out, breathe=0.01, ph=_hash01(seed, 'stat'))
    if k > 0.001:
        c.mark(cx - pw / 2, cy - ph / 2, pw, ph, 'stat', 'text')


# ---------------------------------------------------------------- Meta-Pille, Serienetikett

def meta_tag(c, fmt, place, year, t, t0, theme, k_out=1.0):
    """Meta-Pille „ORT · JAHR“: DM Mono 26 (fit bis 22) Versalien auf bg2-Pille (Höhe 48, Rand 6), rechtsbündig an x 1010 in der
    Kopfzeile (Querformat: links unter dem Titel). Tippt sich ab t0 ein: 1 Zeichen je Frame, höchstens 12 Ticks; die Pille
    wächst mit dem Text."""
    th = _th(theme)
    M = metrics(fmt)
    if t < t0 or k_out <= 0.001:
        return
    parts = [str(place).upper().strip() if place else '', str(year).strip() if year not in (None, '') else '']
    text = ' · '.join(p for p in parts if p)
    if not text:
        return
    n = len(text)
    ticks = min(12, n)
    step = int((t - t0) * fmt.fps) + 1
    shown_n = n if step >= ticks else int(math.ceil(n * step / ticks))
    shown = text[:shown_n]
    pad = 18.0
    sz = F.fit_size(text, 'mono', M['meta_w'] - 2 * pad - _mono_spacing(M['meta']) * n, M['meta'], M['meta_min'])
    f = F.font('mono', sz)
    sp = _mono_spacing(sz)
    w_full = c.text_width(text, f, sp) + 2 * pad
    w_now = max(M['meta_h'], c.text_width(shown, f, sp) + 2 * pad)
    h = M['meta_h']
    cy = M['meta_cy']
    if M['meta_right'] is not None:
        x1 = M['meta_right']
        cx = x1 - w_now / 2
        px = x1
    else:
        x0 = M['meta_left']
        cx = x0 + w_now / 2
        px = x0
    k = A.pop(t, t0, 0.16, 1.10)
    ko, rot = _out_scale(k_out)
    with c.tf(rot=rot, sx=k * ko, px=px, py=cy):
        def body(cc):
            cc.path(_rrect(cx, cy, w_now, h, h / 2), th['bg2'])
            if _plain(cc):
                cc.text(shown, cx, cy, f, th['ink'], 'center', 'middle', 1.0, sp)
        c.sticker(body, rim=M['meta_rim'], rim_color=th['line'], shadow=SHADOW)
        c.mark(cx - w_now / 2, cy - h / 2, w_now, h, 'meta', 'text')


def series_label(c, fmt, text, theme, alpha=1.0, typed=1.0):
    """Serienetikett + Archivnummer (DM Mono 28, Versalien, Laufweite +0.14 em, Elfenbein alpha 0.8, x 70, y 310 Mitte, <= 22
    Zeichen). typed 0..1 zeigt den Anfang des Textes (Tipp-Effekt im Hook)."""
    th = _th(theme)
    M = metrics(fmt)
    if not text or alpha <= 0.001 or typed <= 0.0:
        return
    s = str(text).upper()
    n = max(0, min(len(s), int(math.ceil(len(s) * A.clamp01(typed)))))
    shown = s[:n]
    f = F.font('mono', M['label'])
    sp = _mono_spacing(M['label'])
    w = c.text_width(shown, f, sp)
    c.text(shown, M['label_x'], M['label_y'], f, th['ink'], 'left', 'middle', 0.8 * alpha, sp)
    c.mark(M['label_x'], M['label_y'] - M['label'] * 0.5, w, M['label'], 'label', 'text')


# ---------------------------------------------------------------- Album-Leiste

def _slot_positions(fmt, M, total) -> list:
    """Mittelpunkte der Fächer von #total (links) bis #1 (rechts); im Hochformat ab 7 Fächern zwei Reihen."""
    n = int(total)
    per_row = n if n <= M['slot_row_max'] else int(math.ceil(n / 2))
    slot, gap = M['slot'], M['slot_gap']
    x0, y0 = fmt.progress.x + 2, fmt.progress.y + 2
    pitch_y = slot + 8
    out = []
    for i in range(n):
        row, col = divmod(i, per_row)
        out.append((x0 + slot / 2 + col * (slot + gap), y0 + slot / 2 + row * pitch_y))
    return out


def _mini_badge(c, th, cx, cy, size, r, rank, digit_px, rim, fill, sx=1.0, sy=1.0, rot=0.0, shadow=SLOT_SHADOW, shine=0.0):
    """40-px-Mini-Sticker eines Fachs: Fläche (Gold / Elfenbein) mit Ziffer DM Mono 22 in Tinte, Rand 4, kleiner Schatten."""
    f = F.font('mono', digit_px)

    def body(cc):
        cc.path(_rrect(0, 0, size, size, r), fill)
        if _plain(cc):
            cc.text(str(rank), 0, 0, f, th['card_ink'], 'center', 'middle')
            if shine > 0.001:
                cc.circle(-size * 0.22, -size * 0.22, size * 0.10, th['line'], shine)

    with c.tf(x=cx, y=cy, rot=rot, sx=sx, sy=sy, px=0.0, py=size / 2):
        c.sticker(body, rim=rim, rim_color=th['line'], shadow=shadow)


def progress(c, fmt, rank, total, t, theme, t_fill=None, seed=0):
    """Album-Leiste (STIL.md 5.3) statt Balken: total Fächer 40 x 40 (Radius 12, gestrichelter Rand line alpha 0.35, Abstand 12)
    in fmt.progress, von links #total bis rechts #1. Fächer mit Nummer > rank sind gefüllt (Gold, Ziffer DM Mono 22 Tinte);
    das Fach für rank ist gefüllt, wenn t_fill None ist, sonst füllt es sich bei t_fill: 420 ms vorher fliegt der Badge als
    40-px-Mini-Sticker aus dem Badge-Slot hinauf (in_out_cubic), Landung mit 8 % Squash, Glanz; bei rank 1 leuchtet die
    Leiste 600 ms in glow und 12 Funkeln steigen auf („Album voll“). Das nächste leere Fach pulsiert (Rand-Alpha 0.35 -> 0.6,
    0.8 Hz). rank = total + 1 zeigt die leere Leiste (Hook). Respekt-Modus: Füllung Elfenbein, kein Funkeln, kein Glow.
    Konvention für scenes.py (STIL.md 5.2): im Eintrag r fliegt der alte Badge in sein Fach -> progress(rank=r+1,
    t_fill=t0+0.58); im Eintrag 1 füllt sich das letzte Fach aus der großen Karte -> progress(rank=1, t_fill=t0+0.58)."""
    th = _th(theme)
    M = metrics(fmt)
    total = int(total)
    if total <= 0:
        return
    respect = _respect(th)
    fill_col = th['ink'] if respect else th['card']
    pos = _slot_positions(fmt, M, total)
    slot, r = M['slot'], M['slot_r']
    pending = t_fill is not None and t < t_fill
    next_rank = rank if pending else rank - 1
    xs = [p[0] for p in pos]
    ys = [p[1] for p in pos]
    bar = (min(xs) - slot / 2 - 4, min(ys) - slot / 2 - 4, max(xs) - min(xs) + slot + 8, max(ys) - min(ys) + slot + 8)
    c.mark(*bar, 'progress', 'card')
    # „Album voll“: Glow 600 ms unter der Leiste
    if rank == 1 and t_fill is not None and not respect and th.get('glow') and t_fill <= t < t_fill + 0.6:
        g = 1.0 - (t - t_fill) / 0.6
        c.rect(bar[0] - 20, bar[1] - 20, bar[2] + 40, bar[3] + 40, th['glow'], r=30, alpha=0.5 * g, blur=30, blend='add')
    for i, (cx, cy) in enumerate(pos):
        rk = total - i
        filled = rk > rank or (rk == rank and not pending)
        if filled:
            sx = sy = 1.0
            shine = 0.0
            if rk == rank and t_fill is not None:
                sx, sy = _squash(t, t_fill, 0.08)
                shine = 0.0 if respect else max(0.0, 1.0 - (t - t_fill) / 0.35) * 0.9
            _mini_badge(c, th, cx, cy, slot, r, rk, M['slot_digit'], M['slot_rim'], fill_col, sx, sy, shine=shine)
        else:
            a = 0.35
            if rk == next_rank:
                a = 0.35 + 0.25 * (0.5 + 0.5 * math.sin(TWO_PI * 0.8 * t))
            _dashed_rrect(c, cx, cy, slot - 3, slot - 3, r - 1.5, th['line'], a, 3.0, (6.0, 6.0))
    # Flug des Mini-Stickers in sein Fach
    if pending and t >= t_fill - 0.42:
        i = total - rank
        if 0 <= i < len(pos):
            tx, ty = pos[i]
            bx, by = M['badge_c'] if rank != 1 else M['card_c']
            u = A.in_out_cubic((t - (t_fill - 0.42)) / 0.42)
            x = bx + (tx - bx) * u
            y = by + (ty - by) * u - 60.0 * math.sin(math.pi * u)
            _mini_badge(c, th, x, y, slot, r, rank, M['slot_digit'], M['slot_rim'], fill_col, rot=15.0 * (1.0 - u))
    if rank == 1 and t_fill is not None and not respect:
        _sparkles(c, bar[0] + bar[2] / 2, bar[1] + bar[3] / 2, bar[2] / 2, bar[3] / 2, t, t_fill, th, n=12, seed=seed + 11, dur=0.8,
                  rise=50.0, size=10.0)


# ---------------------------------------------------------------- Wasserzeichen

def watermark(c, fmt, cfg, theme, alpha=0.62, t=0.0):
    """Wasserzeichen oben rechts in fmt.watermark: Odd-Kopf 44 px (mascot.draw_head; engine.brand.draw_mark, falls vorhanden)
    über dem Handle in DM Mono 24 (cfg['brand']['handle'], sonst der Name), alles in einer Ebene mit alpha 0.62."""
    th = _th(theme)
    M = metrics(fmt)
    if alpha <= 0.001:
        return
    brand = (cfg or {}).get('brand', {}) if isinstance(cfg, dict) else {}
    name = str(brand.get('name') or 'ODD CABINET')
    text = str(brand.get('handle') or name)
    slot = fmt.watermark
    cx = slot.cx
    head_cy = slot.y + 25.0 * (M['wm_head'] / 44.0)
    text_y = slot.y + slot.h - 13.0
    f_sz = F.fit_size(text, 'mono', slot.w, M['wm_text'], 16)
    f = F.font('mono', f_sz)
    with c.layer(alpha):
        drawn = False
        try:
            from . import brand as _brand
            if hasattr(_brand, 'draw_mark'):
                _brand.draw_mark(c, cx, head_cy, M['wm_head'], t=t, theme=th)
                drawn = True
        except Exception:
            drawn = False
        if not drawn:
            try:
                from . import mascot
                mascot.draw_head(c, cx, head_cy, M['wm_head'], t=t, expr='smile', look=(0.3, 0.15), theme=th)
                drawn = True
            except Exception:
                drawn = False
        if not drawn:
            c.circle(cx, head_cy, M['wm_head'] / 2, th['card'], stroke=None)
        c.text(text, cx, text_y, f, th['ink'], 'center', 'middle')
    c.mark(slot.x, slot.y, slot.w, slot.h, 'watermark', 'card')


# ---------------------------------------------------------------- Hook-Headline

def _split_markup(text, keyword=None) -> tuple:
    """Wörter und Markierung: '*SOUND MADE UP.*' oder keyword='sound made up' -> Liste (wort, gold?)."""
    marked = set()
    words = []
    if '*' in str(text):
        on = False
        for tok in str(text).split():
            w = tok
            if w.startswith('*'):
                on = True
                w = w[1:]
            end = w.endswith('*')
            if end:
                w = w[:-1]
            words.append(w)
            if on:
                marked.add(len(words) - 1)
            if end:
                on = False
    else:
        words = str(text).split()
    if keyword and not marked:
        def clean(s):
            return re.sub(r'[^\w]', '', s).lower()
        kws = [clean(w) for w in str(keyword).split()]
        cw = [clean(w) for w in words]
        for i in range(len(cw) - len(kws) + 1):
            if cw[i:i + len(kws)] == kws:
                marked.update(range(i, i + len(kws)))
                break
    return words, marked


def hook_title(c, fmt, text, t, t0, theme, keyword=None, seed=0):
    """Hook-Headline (STIL.md 4.2): Bricolage 800 wdth 90, 104 px (fit bis 88), Zeilenhöhe 1.06, Laufweite -0.02 em, max. 3 Zeilen,
    zentriert um y 860; Sticker-Text Elfenbein mit Rand 8 und Schatten, das Schlüsselwort (keyword oder *markiert*) in Gold mit
    leisem Funkeln. Steht ab t0 ohne Pop-In; Mikro-Schweben ±3 px."""
    th = _th(theme)
    M = metrics(fmt)
    if not text or t < t0:
        return
    words, marked = _split_markup(text, keyword)
    plain_text = ' '.join(words)
    lines, size = _lines_fit(plain_text, 'display', M['hook'], M['hook_min'], M['hook_w'], 3, M['hook_floor'])
    f = F.font('display', size)
    sp = -0.02 * size
    lh = size * M['hook_lead']
    top = M['hook_cy'] - lh * len(lines) / 2 + 3.0 * math.sin(TWO_PI * 0.4 * (t - t0) + _hash01(seed))
    ws = _words_layout(c, lines, f, fmt.cx if fmt.portrait else fmt.stage.cx, top, 'center', M['hook_lead'], sp)
    gold = th['caption_hi']
    colors = [gold if i in marked else th['ink'] for i in range(len(ws))]
    if marked and th.get('glow') and not _respect(th):
        tw = 0.5 + 0.5 * math.sin(TWO_PI * 1.3 * (t - t0))
        for i in marked:
            if i < len(ws):
                w = ws[i]
                c.glow(w['cx'], w['cy'], max(w['width'], size) * 0.55, th['glow'], 0.06 + 0.08 * tw, sigma=size * 0.45)

    def body(cc):
        _draw_words(cc, ws, f, colors, sp)

    c.sticker(body, rim=M['text_rim'], rim_color=th['line'], shadow=SHADOW)
    bw = _block_width(c, lines, f, sp)
    c.mark(ws[0]['cx'] - bw / 2 if len(lines) == 1 else (fmt.cx if fmt.portrait else fmt.stage.cx) - bw / 2, top, bw, lh * len(lines), 'hook', 'text')


# ---------------------------------------------------------------- Schlagwort-Sticker

def keyword(c, fmt, text, t, t0, t1, theme, y=None, x=None, pair=False, seed=0):
    """Schlagwort-Sticker (STIL.md 4.2): Bricolage 800 wdth 90, 80 px (fit bis 56), 1–2 Zeilen <= 500 px, Versalien, Füllung
    accent, weißer Rand 8, Schatten; Drehung -4° … +4° (aus dem Text), Pop-In bei t0 (Antizipation), Pop-Out bis t1
    (Scale -> 0, +15°, 160 ms in_cubic). Anker Bühne 0.72 / 0.22; pair=True rückt auf 0.26, wenn zugleich eine Stat steht;
    y (und x) überschreiben."""
    th = _th(theme)
    M = metrics(fmt)
    if not text or t < t0 - 0.06 or (t1 is not None and t >= t1):
        return
    s = str(text).upper()
    lines, size = _lines_fit(s, 'display', M['key'], M['key_min'], M['key_w'], 1)
    if len(lines) > 1 or F.measure(lines[0], F.font('display', size)) > M['key_w']:
        lines, size = _lines_fit(s, 'display', M['key_min'], M['key_min'] * 0.8, M['key_w'], 2, M['key_min'] * 0.7)
    f = F.font('display', size)
    lh = size * 1.05
    cx = M['key_c'][0] if x is None else x
    cy = (M['key_c'][1] + (0.04 * fmt.stage.h if pair else 0.0)) if y is None else y
    top = cy - lh * len(lines) / 2
    ws = _words_layout(c, lines, f, cx, top, 'center', 1.05)
    tilt = -4.0 + 8.0 * _hash01(s, seed)
    k_out = 1.0
    if t1 is not None and t >= t1 - 0.16:
        k_out = 1.0 - A.in_cubic((t - (t1 - 0.16)) / 0.16)
    bw = _block_width(c, lines, f)
    bh = lh * len(lines)

    def hull(cc):
        with cc.tf(rot=tilt, px=cx, py=cy):
            _draw_words(cc, ws, f, th['accent'])

    def body(cc):
        with cc.tf(rot=tilt, px=cx, py=cy):
            _draw_words(cc, ws, f, th['accent'])

    k = _pop_sticker(c, th, body, hull, t, t0, cx, cy, M['text_rim'], SHADOW, k_out=k_out, breathe=0.012, ph=_hash01(s))
    if k > 0.001:
        c.mark(cx - bw / 2, top, bw, bh, 'keyword', 'text')


# ---------------------------------------------------------------- Stempel und Flip-Karte

def stamp(c, fmt, text, t, t0, theme, x, y, seed=0):
    """Gummistempel (STIL.md 5.4): Koralle-Rahmen 6 px, Radius 24, Text Bricolage 800 64 px Versalien in Koralle, weißer Rand 6,
    -8°, Multiply-Korn 0.08; Einschlag Scale 1.6 -> 1.0 in 120 ms (in_quart), danach 2 Frames Shake 4 px. Nie im Respekt-Modus.
    Liegt der Stempel in Höhe der Knopfleiste, rückt x so weit nach links, dass er sie nicht berührt."""
    th = _th(theme)
    M = metrics(fmt)
    if t < t0 or _respect(th):
        return
    s = str(text).upper()
    pad = 34.0
    sz = F.fit_size(s, 'display', M['stamp_w'] - 2 * pad, M['stamp'], M['stamp'] * 0.6)
    f = F.font('display', sz)
    w = min(M['stamp_w'], c.text_width(s, f) + 2 * pad)
    h = M['stamp_h']
    if fmt.buttons is not None and y + h > fmt.buttons.y:
        x = min(x, fmt.buttons.x - w / 2 - 16)
    u = A.clamp01((t - t0) / 0.12)
    sc = 1.6 - 0.6 * A.in_quart(u)
    shx, shy = A.shake(t, t0 + 0.12, 2.0 / fmt.fps + 0.001, 4.0, seed=seed)
    fr = M['stamp_frame']
    col = th['danger']

    def body(cc):
        with cc.tf(rot=-8.0):
            outer = _rrect(0, 0, w, h, M['stamp_r'])
            inner = _rrect(0, 0, w - 2 * fr, h - 2 * fr, M['stamp_r'] - fr)
            ring = skia.Op(outer, inner, skia.PathOp.kDifference_PathOp) or outer
            cc.path(ring, col)
            cc.text(s, 0, 0, f, col, 'center', 'middle')
            if _plain(cc):
                with cc.clip_path(outer):
                    cc.grain(0.08, seed=4, blend='multiply')

    with c.tf(x=x + shx, y=y + shy, sx=sc, px=0.0, py=0.0):
        c.sticker(body, rim=M['stamp_rim'], rim_color=th['line'], shadow=SHADOW)
        c.mark(-w / 2, -h / 2, w, h, 'stamp', 'text')


def flip_card(c, fmt, front, back, t, t0, theme, x, y, t_in=None, seed=0):
    """Flip-Karte (STIL.md 5.4): Elfenbein-Karteikarte 300 x 200, Radius 24, Text DM Mono 30 Tinte; Pop-In bei t_in (Standard
    t0 - 0.6), klappt ab t0 per Scale-X 1 -> 0 -> 1 (260 ms) auf die Rückseite mit dem Stempeltext in Koralle. Schwebt ±4 px."""
    th = _th(theme)
    M = metrics(fmt)
    t_in = t0 - 0.6 if t_in is None else t_in
    if t < t_in - 0.06:
        return
    w, h, r = M['flip_w'], M['flip_h'], M['flip_r']
    u = A.clamp01((t - t0) / 0.26)
    sx = max(0.03, abs(math.cos(math.pi * u)))
    show_back = u > 0.5
    hover = 4.0 * math.sin(TWO_PI * 0.5 * t + _hash01(seed, 'flip'))
    f = F.font('mono', M['flip_text'])
    sp = _mono_spacing(M['flip_text'])
    text = str(back if show_back else front).upper()

    def hull(cc):
        with cc.tf(sx=sx, px=x, py=y):
            cc.path(_rrect(x, y, w, h, r), th['ink'])

    def body(cc):
        with cc.tf(sx=sx, px=x, py=y):
            cc.path(_rrect(x, y, w, h, r), th['ink'])
            if not _plain(cc):
                return
            with cc.clip_path(_rrect(x, y, w, h, r)):
                cc.rect(x - w / 2, y - h / 2, w, h * 0.13, th['danger'] if show_back else th['accent2'])
            for i in range(3):
                cc.rect_c(x, y + h * (-0.02 + i * 0.2), w * 0.76, 4.0, th['ink_soft'], r=2, alpha=0.7)
            if show_back:
                fs = F.font('display', M['flip_text'] * 1.45)
                tw = cc.text_width(text, fs) + 36
                with cc.tf(rot=-8.0, px=x, py=y + h * 0.1):
                    outer = _rrect(x, y + h * 0.1, tw, M['flip_text'] * 2.2, 14)
                    inner = _rrect(x, y + h * 0.1, tw - 10, M['flip_text'] * 2.2 - 10, 10)
                    cc.path(skia.Op(outer, inner, skia.PathOp.kDifference_PathOp) or outer, th['danger'])
                    cc.text(text, x, y + h * 0.1, fs, th['danger'], 'center', 'middle')
            else:
                cc.text_fit(text, x, y + h * 0.1, 'mono', M['flip_text'], w * 0.8, th['card_ink'], 'center', 'middle', spacing=sp)

    with c.tf(y=hover):
        k = _pop_sticker(c, th, body, hull, t, t_in, x, y, M['text_rim'] + 2, SHADOW, overshoot=1.17, ph=_hash01(seed))
        if k > 0.001:
            c.mark(x - w / 2, y - h / 2, w, h, 'flip_card', 'card')


# ---------------------------------------------------------------- Übersichtsbogen

def _frame_bg(c, fmt, th, t=0.0):
    c.gradient_bg(th['bg0'], th['bg1'])
    if th.get('glow'):
        c.spotlight(fmt.cx, fmt.stage.cy, 520 if fmt.portrait else 600, th['glow'], 0.10)
    c.grain(0.045)


def _zones(c, fmt, th):
    """Sicherheitszonen als feine Linien (nur im Bogen): safe_top, safe_bottom, Knopfleiste."""
    col = th['danger']
    c.line(0, fmt.safe_top, fmt.W, fmt.safe_top, col, 2, 0.35, dash=[12, 10])
    c.line(0, fmt.H - fmt.safe_bottom, fmt.W, fmt.H - fmt.safe_bottom, col, 2, 0.35, dash=[12, 10])
    if fmt.buttons:
        b = fmt.buttons
        c.rect(b.x, b.y, b.w, b.h, col, r=8, alpha=0.25, stroke=2)


def _frame(fmt, th, draw, t=0.0, zones=True):
    """Rendert ein ganzes Bild des Formats (Hintergrund, draw(c), Vignette, Zonen) und liefert es als numpy-Array."""
    from .canvas import Frame
    fr = Frame(fmt.W, fmt.H)
    c = fr.c
    _frame_bg(c, fmt, th, t)
    draw(c)
    c.vignette(0.28)
    if zones:
        _zones(c, fmt, th)
    return fr.to_array().copy()


def sheet(out_path: str, quick: bool = False) -> str:
    """Übersichtsbogen library/sheets/cards.png: Hoch- und Querformat-Bilder der Choreografie (Hook, Flug, Landung, Zählwerk,
    Haltezeit mit Titel, Schrumpfen, #1 mit Krone, gedockter Eintrag mit Kopfzeile/Meta/Stat/Schlagwort/Stempel, Respekt-Modus,
    Top 10) sowie Einzelteile: Karten 5 … 1 und 10, Badges, Stat-Zählwerk, Meta-Tipp, Album-Zustände, Flip-Karte, Stempel.
    quick=True rendert nur wenige Bilder (Tests)."""
    from .canvas import Frame
    from . import layout
    cfg = {'brand': {'name': 'ODD CABINET', 'handle': '@oddcabinet'}}
    fp, fl = layout.get_format('portrait'), layout.get_format('landscape')
    th_h, th_c, th_s = TH.get('heist'), TH.get('curious'), TH.get('space')
    th_r = TH.respect(TH.get('history'))
    T0 = 2.0
    label = 'CURIOUS HEISTS · 017'

    def ui(c, fmt, th, rank, t, t_fill=None, total=5, label_typed=1.0):
        series_label(c, fmt, label, th, typed=label_typed)
        progress(c, fmt, rank, total, t, th, t_fill)
        watermark(c, fmt, cfg, th, t=t)

    frames_p = [
        ('hook · Headline, Etikett tippt', th_h, 0.9, lambda c, t: (hook_title(c, fp, 'Five real heists that *SOUND MADE UP.*', t, 0.0, th_h), ui(c, fp, th_h, 6, t, label_typed=A.clamp01((t - 0.4) / 0.5)))),
        ('#5 A · Flug t0+0.14 (Smear)', th_h, T0 + 0.14, lambda c, t: (number_card(c, fp, 5, t, T0, th_h, variant='A'), ui(c, fp, th_h, 6, t))),
        ('#5 A · Landung t0+0.38 (Squash, Konfetti)', th_h, T0 + 0.38, lambda c, t: (number_card(c, fp, 5, t, T0, th_h, variant='A'), ui(c, fp, th_h, 6, t))),
        ('#4 B · Zählwerk t0+0.12 (Iris, Mini-Flug)', th_h, T0 + 0.12, lambda c, t: (number_card(c, fp, 4, t, T0, th_h, variant='B'), ui(c, fp, th_h, 5, t, T0 + 0.58))),
        ('#3 · Haltezeit t0+0.95 (Titel-Stagger)', th_h, T0 + 0.95, lambda c, t: (number_card(c, fp, 3, t, T0, th_h, variant='A'), title_plate(c, fp, 'The Antwerp Sandwich', t, T0, th_h), ui(c, fp, th_h, 4, t, T0 + 0.58))),
        ('#2 · Schrumpfen t0+1.45 (Titel gleitet)', th_c, T0 + 1.45, lambda c, t: (number_card(c, fp, 2, t, T0, th_c, variant='B'), title_plate(c, fp, 'The Fake Cop of Tokyo', t, T0, th_c), ui(c, fp, th_c, 3, t, T0 + 0.58))),
        ('#1 · t0+1.0 · Krone, Strahlen, Album voll', th_h, T0 + 1.0, lambda c, t: (number_card(c, fp, 1, t, T0, th_h), title_plate(c, fp, 'The Maple Syrup Heist', t, T0, th_h, rank=1), ui(c, fp, th_h, 1, t, T0 + 0.58))),
        ('gedockt t0+3.1 · Kopf, Meta, Stat, Wort, Stempel', th_s, T0 + 3.1, lambda c, t: (number_card(c, fp, 3, t, T0, th_s, variant='A'), title_plate(c, fp, 'The Mona Lisa Walkout', t, T0, th_s), meta_tag(c, fp, 'Paris', 1911, t, T0 + T_META, th_s), stat_plate(c, fp, '$100M+', 'in diamonds', t, T0 + 2.4, th_s, pair=True), keyword(c, fp, 'Nobody noticed', t, T0 + 2.2, None, th_s, pair=True), stamp(c, fp, 'Never found', t, T0 + 2.9, th_s, 700, 960), ui(c, fp, th_s, 4, t))),
        ('langer Titel · Respekt-Modus · Flip', th_r, T0 + 4.0, lambda c, t: (number_card(c, fp, 2, t, T0, th_r, variant='B'), title_plate(c, fp, 'The Night the Whole Village Vanished', t, T0, th_r), meta_tag(c, fp, 'Roanoke', 1590, t, T0 + T_META, th_r), stat_plate(c, fp, '115 people', 'never found', t, T0 + 2.4, th_r), flip_card(c, fp, 'Approved', 'Fake', t, T0 + 3.4, th_r, 700, 960), ui(c, fp, th_r, 3, t))),
        ('Top 10 · #10 t0+0.9 · zwei Reihen', th_c, T0 + 0.9, lambda c, t: (number_card(c, fp, 10, t, T0, th_c, variant='A', total=10), title_plate(c, fp, 'The Great Cheese Robbery', t, T0, th_c), ui(c, fp, th_c, 11, t, total=10))),
    ]
    frames_l = [
        ('Querformat · Hook', th_h, 0.9, lambda c, t: (hook_title(c, fl, 'Five real heists that *SOUND MADE UP.*', t, 0.0, th_h), ui(c, fl, th_h, 6, t))),
        ('Querformat · #1 Haltezeit', th_h, T0 + 1.0, lambda c, t: (number_card(c, fl, 1, t, T0, th_h), title_plate(c, fl, 'The Maple Syrup Heist', t, T0, th_h, rank=1), ui(c, fl, th_h, 1, t, T0 + 0.58))),
        ('Querformat · gedockt, Top 10', th_s, T0 + 3.1, lambda c, t: (number_card(c, fl, 7, t, T0, th_s, total=10), title_plate(c, fl, 'The Mona Lisa Walkout', t, T0, th_s), meta_tag(c, fl, 'Paris', 1911, t, T0 + T_META, th_s), stat_plate(c, fl, '¥294M', 'gone', t, T0 + 2.4, th_s), keyword(c, fl, 'Never caught', t, T0 + 2.2, None, th_s), ui(c, fl, th_s, 8, t, total=10))),
    ]
    if quick:
        frames_p, frames_l = frames_p[:2], frames_l[:1]
    sc_p, sc_l = 0.32, 0.28
    cols = 5
    pw, ph = int(fp.W * sc_p), int(fp.H * sc_p)
    lw, lh = int(fl.W * sc_l), int(fl.H * sc_l)
    gap = 18
    W = cols * (pw + gap) + gap + 8
    rows_p = (len(frames_p) + cols - 1) // cols
    y_p = 110
    y_l = y_p + rows_p * (ph + 44 + gap)
    y_parts = y_l + lh + 44 + gap + 10
    parts_h = 0 if quick else 1180
    H = y_parts + parts_h + 40
    fr = Frame(W, H)
    c = fr.c
    c.fill('#0D0D12')
    c.text('CARDS · Nummernkarten, Tafeln, Album-Leiste · Peel & Pop', 36, 48, F.font('display', 40), th_c['ink'], 'left', 'middle')
    c.text('Hochformat 0.32 · Querformat 0.28 · rote Linien = Sicherheitszonen · t0 = Beginn des Nummernwechsels', 36, 84, F.font('mono', 18), th_c['ink_soft'], 'left', 'middle')
    fm = F.font('mono', 14)
    for i, (name, th, t, draw) in enumerate(frames_p):
        x0 = gap + 4 + (i % cols) * (pw + gap)
        y0 = y_p + (i // cols) * (ph + 44 + gap)
        arr = _frame(fp, th, lambda cc, d=draw, tt=t: d(cc, tt), t)
        c.image(arr, x0, y0, pw, ph)
        c.rect(x0, y0, pw, ph, th_c['ink_soft'], r=6, alpha=0.3, stroke=1)
        c.text(name, x0 + pw / 2, y0 + ph + 20, fm, th_c['ink_soft'], 'center', 'middle')
    for i, (name, th, t, draw) in enumerate(frames_l):
        x0 = gap + 4 + i * (lw + gap)
        y0 = y_l
        arr = _frame(fl, th, lambda cc, d=draw, tt=t: d(cc, tt), t)
        c.image(arr, x0, y0, lw, lh)
        c.rect(x0, y0, lw, lh, th_c['ink_soft'], r=6, alpha=0.3, stroke=1)
        c.text(name, x0 + lw / 2, y0 + lh + 20, fm, th_c['ink_soft'], 'center', 'middle')
    if not quick:
        _sheet_parts(c, fp, th_h, th_r, y_parts, W)
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    fr.save_png(out_path)
    return out_path


def _sheet_parts(c, fmt, th, th_r, y0, W):
    """Einzelteile 1:2 auf dem Bogen: Karten 5 … 1 und 10, Badges, Stat-Zählwerk, Meta-Tipp, Album-Zustände, Stempel, Flip-Karte."""
    M = metrics(fmt)
    fm = F.font('mono', 14)
    c.text('EINZELTEILE (1 : 2) · Sammelkarten 5 … 1 und 10 (Haltezeit) · Badges · Zählwerk · Meta · Album · Stempel · Flip', 36, y0 + 10, F.font('mono', 18), th['ink_soft'], 'left', 'middle')
    row_y = y0 + 40
    cx0 = M['card_c'][0]
    cy0 = M['card_c'][1]
    # Karten 1:2
    for i, rank in enumerate((5, 4, 3, 2, 1, 10)):
        x = 36 + i * 360
        with c.tf(x=x - (cx0 - 190) * 0.5, y=row_y - (cy0 - 340) * 0.5, sx=0.5, px=0, py=0):
            thx = th if rank != 10 else TH.get('curious')
            number_card(c, fmt, rank, 2.9, 2.0, thx, total=10 if rank == 10 else 5, effects=False)
    row_y += 400
    # Badges 1:2 (mit Pop-Out-Stufen) und Mini-Fächer
    for i, rank in enumerate((5, 4, 3, 2, 1)):
        x = 36 + i * 170
        with c.tf(x=x - (M['badge_c'][0] - 100) * 0.5, y=row_y - (M['badge_c'][1] - 100) * 0.5, sx=0.5, px=0, py=0):
            number_card(c, fmt, rank, 5.0, 2.0, th, k_out=1.0 if i < 3 else (0.8 if i == 3 else 0.45), effects=False)
    c.text('Badges 240 px · rechts: Pop-Out k_out 0.8 / 0.45', 36, row_y + 150, fm, th['ink_soft'], 'left', 'middle')
    # Album-Zustände 1:1
    px0 = 920
    for j, (rank, tf, tt, thx, nm) in enumerate(((6, None, 0.3, th, 'leer (Hook), #5 pulsiert'), (4, 3.0, 2.95, th, 'Mini-Flug zu #4'), (4, 3.0, 3.05, th, 'Landung #4 (Squash, Glanz)'), (1, 3.0, 3.2, th, 'Album voll (Glow, Funkeln)'), (2, None, 0.3, th_r, 'Respekt: Elfenbein'))):
        yy = row_y + j * 64
        with c.tf(x=px0 - fmt.progress.x, y=yy - fmt.progress.y, px=0, py=0):
            progress(c, fmt, rank, 5, tt, thx, tf)
        c.text(nm, px0 + 270, yy + 22, fm, th['ink_soft'], 'left', 'middle')
    row_y += 330
    # Stat-Zählwerk 1:2: drei Zeitpunkte
    for i, (tt, nm) in enumerate(((2.18, 't0+0.18'), (2.55, 't0+0.55'), (2.86, 't0+0.86 · Pop der letzten Ziffer'))):
        x = 36 + i * 330
        with c.tf(x=x - (M['stat_c'][0] - 110) * 0.5, y=row_y - (M['stat_c'][1] - 40) * 0.5, sx=0.5, px=0, py=0):
            stat_plate(c, fmt, '300,000', 'pounds', tt, 2.0, th)
        c.text(nm, x + 110, row_y + 100, fm, th['ink_soft'], 'center', 'middle')
    with c.tf(x=1050 - (M['stat_c'][0] - 110) * 0.5, y=row_y - (M['stat_c'][1] - 40) * 0.5, sx=0.5, px=0, py=0):
        stat_plate(c, fmt, '$18M', 'of syrup', 4.0, 2.0, th)
    with c.tf(x=1330 - (M['stat_c'][0] - 110) * 0.5, y=row_y - (M['stat_c'][1] - 40) * 0.5, sx=0.5, px=0, py=0):
        stat_plate(c, fmt, '22 t', 'of cheddar', 4.0, 2.0, th)
    # Meta-Tipp 1:1
    for i, tt in enumerate((2.05, 2.2, 2.6)):
        with c.tf(x=1780 - M['meta_right'], y=row_y + 10 + i * 64 - M['meta_cy'], px=0, py=0):
            meta_tag(c, fmt, 'London', 2024, tt, 2.0, th)
    c.text('Meta-Pille tippt (t0+0.05 / 0.2 / 0.6)', 1780, row_y + 210, fm, th['ink_soft'], 'right', 'middle')
    row_y += 250
    # Stempel und Flip 1:2
    for i, (tt, nm) in enumerate(((2.06, 'Einschlag t0+0.06 (Scale 1.3)'), (2.5, 'Stempel'))):
        x = 200 + i * 360
        with c.tf(x=x, y=row_y + 60, sx=0.5, px=0, py=0):
            stamp(c, fmt, 'Verified odd' if i else 'Never paid', tt, 2.0, th, 0, 0)
        c.text(nm, x, row_y + 130, fm, th['ink_soft'], 'center', 'middle')
    for i, (tt, nm) in enumerate(((2.0, 'Flip vorn'), (2.09, 'klappt t0+0.09'), (2.5, 'Rückseite: Stempel'))):
        x = 1000 + i * 260
        with c.tf(x=x, y=row_y + 60, sx=0.5, px=0, py=0):
            flip_card(c, fmt, 'Approved', 'Fake', tt, 2.0, th, 0, 0)
        c.text(nm, x, row_y + 130, fm, th['ink_soft'], 'center', 'middle')
