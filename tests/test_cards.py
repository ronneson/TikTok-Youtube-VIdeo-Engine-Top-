"""Nummernkarten und Tafeln: Choreografie über t, Sticker-Rand, Slots und Sicherheitszonen, Zählwerk, Album-Leiste, Bogen."""
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import cards, layout, theme
from engine.canvas import Frame

CFG = {'brand': {'name': 'ODD CABINET', 'handle': '@oddcabinet'}}
T0 = 2.0


def _fmt(name='portrait'):
    return layout.get_format(name)


def _frame(fmt, th=None, marks=False):
    fr = Frame(fmt.W, fmt.H)
    th = th or theme.get('heist')
    fr.c.gradient_bg(th['bg0'], th['bg1'])
    if marks:
        fr.c.marks = []
    return fr


def _painted(fr, bg):
    a, b = fr.to_rgb().astype(int), bg.to_rgb().astype(int)
    return int((np.abs(a - b).sum(axis=2) > 30).sum())


def _bbox(fr, bg):
    a, b = fr.to_rgb().astype(int), bg.to_rgb().astype(int)
    ys, xs = np.where(np.abs(a - b).sum(axis=2) > 30)
    assert len(xs), 'nichts gezeichnet'
    return xs.min(), xs.max(), ys.min(), ys.max()


def _overlap(m, z):
    x0, y0 = max(m['x'], z[0]), max(m['y'], z[1])
    x1, y1 = min(m['x'] + m['w'], z[0] + z[2]), min(m['y'] + m['h'], z[1] + z[3])
    if x1 <= x0 or y1 <= y0 or m['w'] <= 0 or m['h'] <= 0:
        return 0.0
    return (x1 - x0) * (y1 - y0) / (m['w'] * m['h'])


def test_metrics_follow_stil():
    M = cards.metrics(_fmt())
    assert M['card'] == 560 and M['badge'] == 240 and M['digit'] == 420 and M['digit_one'] == 500
    assert M['card_c'] == (540, 860) and M['badge_c'] == (220, 500)
    assert M['slot'] == 40 and M['slot_gap'] == 12 and M['title_top'] == 1160
    L = cards.metrics(_fmt('landscape'))
    assert L['card'] == 460 and L['badge'] == 200 and L['slot'] == 32 and L['slot_gap'] == 20


def test_number_card_phases_portrait_and_landscape():
    """Flug (klein, oben rechts) -> Landung in der Mitte -> Badge oben links; davor nichts; Variante B per Iris."""
    for fname in ('portrait', 'landscape'):
        fmt = _fmt(fname)
        th = theme.get('heist')
        M = cards.metrics(fmt)
        bg = _frame(fmt, th)
        fr = _frame(fmt, th)
        cards.number_card(fr.c, fmt, 5, T0 - 0.5, T0, th, variant='A')
        assert _painted(fr, bg) == 0
        fr = _frame(fmt, th)
        cards.number_card(fr.c, fmt, 5, T0 + 0.05, T0, th, variant='A', effects=False)
        x0, x1, y0, y1 = _bbox(fr, bg)
        assert (x0 + x1) / 2 > M['card_c'][0] and (y0 + y1) / 2 < M['card_c'][1], 'Flug beginnt oben rechts'
        fr = _frame(fmt, th)
        cards.number_card(fr.c, fmt, 5, T0 + 0.9, T0, th, variant='A', effects=False)
        x0, x1, y0, y1 = _bbox(fr, bg)
        assert abs((x0 + x1) / 2 - M['card_c'][0]) < 30 and abs((y0 + y1) / 2 - M['card_c'][1]) < 40
        assert M['card'] * 0.95 < x1 - x0 < M['card'] * 1.15
        fr = _frame(fmt, th)
        cards.number_card(fr.c, fmt, 5, T0 + 3.0, T0, th, variant='A')
        x0, x1, y0, y1 = _bbox(fr, bg)
        assert abs((x0 + x1) / 2 - M['badge_c'][0]) < 20 and abs((y0 + y1) / 2 - M['badge_c'][1]) < 20
        assert M['badge'] * 0.95 < x1 - x0 < M['badge'] * 1.2
        # Variante B: Iris wächst
        a = _frame(fmt, th); cards.number_card(a.c, fmt, 4, T0 + 0.04, T0, th, variant='B')
        b = _frame(fmt, th); cards.number_card(b.c, fmt, 4, T0 + 0.2, T0, th, variant='B')
        assert 0 < _painted(a, bg) < _painted(b, bg)


def test_number_one_special_and_k_out():
    fmt = _fmt()
    th = theme.get('heist')
    bg = _frame(fmt, th)
    big = _frame(fmt, th)
    cards.number_card(big.c, fmt, 1, T0 + 1.0, T0, th)
    x0, x1, y0, y1 = _bbox(big, bg)
    assert x1 - x0 > 560 * 1.1, '#1 ist größer (1.15) plus Krone/Strahlen'
    plain = _frame(fmt, th)
    cards.number_card(plain.c, fmt, 1, T0 + 1.0, T0, th, effects=False)
    assert _painted(big, bg) > _painted(plain, bg), 'Strahlen, Funkeln und Konfetti nur mit effects'
    # Respekt-Modus: keine Effekte, aber Karte
    r = _frame(fmt, theme.respect(th))
    cards.number_card(r.c, fmt, 1, T0 + 1.0, T0, theme.respect(th))
    assert _painted(r, _frame(fmt, theme.respect(th))) > 10000
    # k_out schrumpft den Badge
    full = _frame(fmt, th); cards.number_card(full.c, fmt, 2, T0 + 3.0, T0, th, k_out=1.0)
    half = _frame(fmt, th); cards.number_card(half.c, fmt, 2, T0 + 3.0, T0, th, k_out=0.5)
    gone = _frame(fmt, th); cards.number_card(gone.c, fmt, 2, T0 + 3.0, T0, th, k_out=0.0)
    assert _painted(half, bg) < _painted(full, bg) * 0.5 and _painted(gone, bg) == 0


def test_card_has_white_rim_and_flight_helpers():
    fmt = _fmt()
    th = theme.get('curious')
    fr = Frame(fmt.W, fmt.H); fr.c.fill('#000000')
    cards.number_card(fr.c, fmt, 3, T0 + 0.9, T0, th, effects=False)
    rgb = fr.to_rgb()
    assert (rgb.min(axis=2) > 235).sum() > 15000, 'weißer Sticker-Rand 12 px'
    assert cards.flight_pos(fmt, T0 - 0.1, T0) is None and cards.flight_pos(fmt, T0 + 0.33, T0) is None
    x, y, rot, sc = cards.flight_pos(fmt, T0 + 0.1, T0, 'A')
    assert x > fmt.cx and sc < 1.0 and rot < 0
    x2, y2, rot2, sc2 = cards.flight_pos(fmt, T0 + 0.32, T0, 'A')
    assert abs(x2 - 540) < 1 and abs(y2 - 860) < 20 and abs(rot2) < 1.5 and sc2 > 0.98
    bp = cards.beak_point(fmt, T0 + 0.1, T0, 'A')
    assert bp is not None and bp[1] < y
    assert cards.beak_point(fmt, T0 + 0.25, T0, 'A') is None
    bg = _frame(fmt, th); fr2 = _frame(fmt, th)
    cards.card_flight(fr2.c, fmt, 1, T0 + 0.15, T0, th, variant='one')
    assert _painted(fr2, bg) > 2000


def test_title_hold_then_header_long_titles_readable():
    fmt = _fmt()
    th = theme.get('heist')
    bg = _frame(fmt, th)
    for title in ('The Antwerp Sandwich', 'The Night the Whole Village Vanished Without a Trace'):
        fr = _frame(fmt, th)
        cards.title_plate(fr.c, fmt, title, T0 + 0.3, T0, th)
        assert _painted(fr, bg) == 0, 'vor t0 + 0.55 kein Titel'
        hold = _frame(fmt, th, marks=True)
        cards.title_plate(hold.c, fmt, title, T0 + 1.1, T0, th)
        x0, x1, y0, y1 = _bbox(hold, bg)
        assert y0 >= 1150 and x0 >= 150 and x1 <= 930, 'Haltezeit: zentriert unter der Karte, frei von der Knopfleiste'
        head = _frame(fmt, th, marks=True)
        cards.title_plate(head.c, fmt, title, T0 + 2.5, T0, th)
        x0, x1, y0, y1 = _bbox(head, bg)
        assert x0 >= 60 and y0 >= 655 and y1 <= 790 and x1 <= 700, (title, x0, x1, y0, y1)
        m = [m for m in head.c.marks if m['label'] == 'title'][0]
        assert m['kind'] == 'text' and m['h'] >= 30
    # Zwischenzustand liegt zwischen beiden Lagen
    mid = _frame(fmt, th)
    cards.title_plate(mid.c, fmt, 'The Antwerp Sandwich', T0 + 1.46, T0, th)
    x0, x1, y0, y1 = _bbox(mid, bg)
    assert 700 < (y0 + y1) / 2 < 1180


def test_stat_counts_tabular_and_parses_value():
    assert cards.split_value('$18M') == ('$', '18', 'M')
    assert cards.split_value('22 t') == ('', '22', ' t')
    assert cards.split_value('300,000') == ('', '300,000', '')
    assert cards.split_value('1.5 km') == ('', '1.5', ' km')
    assert cards._format_like(123456.0, '300,000') == '123,456' and cards._format_like(1.26, '1.5') == '1.3'
    fmt = _fmt()
    th = theme.get('heist')
    bg = _frame(fmt, th)
    a = _frame(fmt, th); cards.stat_plate(a.c, fmt, '300,000', 'pounds', T0 + 0.3, T0, th)
    b = _frame(fmt, th); cards.stat_plate(b.c, fmt, '300,000', 'pounds', T0 + 2.0, T0, th)
    assert _painted(a, bg) > 3000 and _painted(b, bg) > 3000
    assert (np.abs(a.to_rgb().astype(int) - b.to_rgb().astype(int)).sum(axis=2) > 30).sum() > 500, 'Zahl zählt hoch'
    # Plakette gleich groß, egal welcher Zwischenwert (nichts springt)
    ba, bb = _bbox(a, bg), _bbox(b, bg)
    assert abs((ba[1] - ba[0]) - (bb[1] - bb[0])) < 6
    c0 = _frame(fmt, th); cards.stat_plate(c0.c, fmt, '$18M', 'of syrup', T0 + 5, T0, th, count=False)
    assert _painted(c0, bg) > 3000
    before = _frame(fmt, th); cards.stat_plate(before.c, fmt, '$18M', 'x', T0 - 0.2, T0, th)
    assert _painted(before, bg) == 0


def test_progress_slots_fill_and_fly():
    fmt = _fmt()
    th = theme.get('heist')
    M = cards.metrics(fmt)
    bg = _frame(fmt, th)
    empty = _frame(fmt, th); cards.progress(empty.c, fmt, 6, 5, 0.3, th)
    three = _frame(fmt, th); cards.progress(three.c, fmt, 3, 5, 0.3, th)
    full = _frame(fmt, th); cards.progress(full.c, fmt, 1, 5, 0.3, th)
    assert _painted(empty, bg) < _painted(three, bg) < _painted(full, bg)
    x0, x1, y0, y1 = _bbox(full, bg)
    p = fmt.progress
    assert x0 >= p.x - 8 and x1 <= p.x1 + 8 and y0 >= fmt.safe_top and y1 <= p.y1 + 8, 'Fächer im Slot, unter safe_top'
    # Fach für rank füllt sich erst bei t_fill; vorher fliegt der Mini-Sticker
    pend = _frame(fmt, th); cards.progress(pend.c, fmt, 3, 5, 3.0, th, t_fill=3.4)
    done = _frame(fmt, th); cards.progress(done.c, fmt, 3, 5, 3.6, th, t_fill=3.4)
    assert _painted(pend, bg) > _painted(empty, bg)
    bx0, bx1, by0, by1 = _bbox(pend, bg)
    assert by1 > p.y1 + 40, 'Mini-Sticker unterwegs unterhalb der Leiste'
    dx0, dx1, dy0, dy1 = _bbox(done, bg)
    assert dy1 <= p.y1 + 8
    # Top 10 im Hochformat: zwei Reihen; Querformat: eine Reihe mit 10
    pos = cards._slot_positions(fmt, M, 10)
    assert len(set(round(y) for _, y in pos)) == 2
    fl = _fmt('landscape')
    posl = cards._slot_positions(fl, cards.metrics(fl), 10)
    assert len(set(round(y) for _, y in posl)) == 1 and max(x for x, _ in posl) <= fl.progress.x1
    # Respekt: Füllung Elfenbein (kein Gold)
    r = theme.respect(th)
    fr = _frame(fmt, r); cards.progress(fr.c, fmt, 1, 5, 0.3, r, t_fill=0.0)
    rgb = fr.to_rgb()
    gold = ((rgb[..., 0] > 200) & (rgb[..., 1] > 150) & (rgb[..., 1] < 200) & (rgb[..., 2] < 120)).sum()
    assert gold < 50


def test_ui_elements_respect_safe_zones_and_mark():
    """Alle Marken (Text) liegen außerhalb von safe_top und der Knopfleiste; Karten höchstens 25 % darin."""
    fmt = _fmt()
    th = theme.get('space')
    fr = _frame(fmt, th, marks=True)
    c = fr.c
    t = T0 + 3.1
    cards.number_card(c, fmt, 3, t, T0, th)
    cards.title_plate(c, fmt, 'The Mona Lisa Walkout', t, T0, th)
    cards.meta_tag(c, fmt, 'Paris', 1911, t, T0 + 1.7, th)
    cards.stat_plate(c, fmt, '$100M+', 'in diamonds', t, T0 + 2.4, th, pair=True)
    cards.keyword(c, fmt, 'Nobody noticed', t, T0 + 2.2, None, th, pair=True)
    cards.stamp(c, fmt, 'Never found', t, T0 + 2.9, th, 700, 960)
    cards.series_label(c, fmt, 'CURIOUS HEISTS · 017', th)
    cards.progress(c, fmt, 4, 5, t, th)
    cards.watermark(c, fmt, CFG, th, t=t)
    cards.hook_title(c, fmt, 'Five real heists that *SOUND MADE UP.*', 0.5, 0.0, th)
    labels = {m['label'] for m in c.marks}
    for need in ('card#3', 'title', 'meta', 'stat', 'keyword', 'stamp', 'label', 'progress', 'watermark', 'hook'):
        assert need in labels, need
    zones = {'top': (0, 0, fmt.W, fmt.safe_top), 'bottom': (0, fmt.H - fmt.safe_bottom, fmt.W, fmt.safe_bottom),
             'buttons': (fmt.buttons.x, fmt.buttons.y, fmt.buttons.w, fmt.buttons.h)}
    for m in c.marks:
        lim = 0.02 if m['kind'] == 'text' else 0.25
        for zn, z in zones.items():
            assert _overlap(m, z) <= lim, (m['label'], zn, _overlap(m, z))


def test_keyword_hook_stamp_flip_watermark_draw_and_time():
    fmt = _fmt()
    th = theme.get('heist')
    bg = _frame(fmt, th)
    # Schlagwort: vor t0 nichts, nach t1 nichts, dazwischen Sticker-Text in accent
    for tt, expect in ((T0 - 0.2, False), (T0 + 0.4, True), (T0 + 2.0, True), (T0 + 3.05, False)):
        fr = _frame(fmt, th)
        cards.keyword(fr.c, fmt, 'Never caught', tt, T0, T0 + 3.0, th)
        assert (_painted(fr, bg) > 1000) == expect, tt
    # Hook: steht ab t0 (kein Pop), Schlüsselwort in Gold, max. 3 Zeilen, unter safe_top
    fr = _frame(fmt, th, marks=True)
    cards.hook_title(fr.c, fmt, 'Five real heists that *SOUND MADE UP.*', 0.0, 0.0, th)
    x0, x1, y0, y1 = _bbox(fr, bg)
    assert y0 > 600 and y1 < 1200 and x0 > 150 and x1 < 930
    rgb = fr.to_rgb()
    assert ((rgb[..., 0] > 220) & (rgb[..., 1] > 150) & (rgb[..., 1] < 210) & (rgb[..., 2] < 130)).sum() > 500, 'Gold im Hook'
    words, marked = cards._split_markup('Five real heists that sound made up.', keyword='sound made up')
    assert marked == {4, 5, 6}
    # Stempel: Einschlag groß -> normal, nie im Respekt-Modus
    a = _frame(fmt, th); cards.stamp(a.c, fmt, 'never paid', T0 + 0.01, T0, th, 700, 900)
    b = _frame(fmt, th); cards.stamp(b.c, fmt, 'never paid', T0 + 0.5, T0, th, 700, 900)
    ba, bb = _bbox(a, bg), _bbox(b, bg)
    assert (ba[1] - ba[0]) > (bb[1] - bb[0]) * 1.3 and bb[1] - bb[0] <= 440
    r = theme.respect(th)
    fr = _frame(fmt, r); cards.stamp(fr.c, fmt, 'never paid', T0 + 0.5, T0, r, 700, 900)
    assert _painted(fr, _frame(fmt, r)) == 0
    # Flip-Karte: Vorderseite, Mitte schmal, Rückseite
    f0 = _frame(fmt, th); cards.flip_card(f0.c, fmt, 'approved', 'fake', T0 - 0.1, T0, th, 700, 1100)
    f1 = _frame(fmt, th); cards.flip_card(f1.c, fmt, 'approved', 'fake', T0 + 0.13, T0, th, 700, 1100)
    f2 = _frame(fmt, th); cards.flip_card(f2.c, fmt, 'approved', 'fake', T0 + 0.5, T0, th, 700, 1100)
    w0, w1, w2 = [(_bbox(f, bg)[1] - _bbox(f, bg)[0]) for f in (f0, f1, f2)]
    assert w1 < w0 * 0.3 and abs(w0 - w2) < 20
    # Wasserzeichen und Etikett im Slot
    fr = _frame(fmt, th)
    cards.watermark(fr.c, fmt, CFG, th)
    x0, x1, y0, y1 = _bbox(fr, bg)
    w = fmt.watermark
    assert x0 >= w.x - 6 and x1 <= w.x1 + 6 and y0 >= w.y - 8 and y1 <= w.y1 + 8
    fr = _frame(fmt, th)
    cards.series_label(fr.c, fmt, 'CURIOUS HEISTS · 017', th)
    x0, x1, y0, y1 = _bbox(fr, bg)
    assert x0 >= 68 and y0 >= fmt.safe_top and x1 <= 560


def test_meta_tag_types_in():
    fmt = _fmt()
    th = theme.get('heist')
    bg = _frame(fmt, th)
    a = _frame(fmt, th); cards.meta_tag(a.c, fmt, 'London', 2024, T0 + 0.05, T0, th)
    b = _frame(fmt, th); cards.meta_tag(b.c, fmt, 'London', 2024, T0 + 1.0, T0, th)
    wa, wb = _bbox(a, bg), _bbox(b, bg)
    assert (wa[1] - wa[0]) < (wb[1] - wb[0]) and wb[1] <= 1016 and wb[1] - wb[0] <= 372
    assert abs(wb[1] - wa[1]) < 8, 'rechtsbündig verankert'
    # Pop-Out über k_out
    z = _frame(fmt, th); cards.meta_tag(z.c, fmt, 'London', 2024, T0 + 1.0, T0, th, k_out=0.0)
    assert _painted(z, bg) == 0


def test_sheet_quick(tmp_path):
    t0 = time.time()
    out = cards.sheet(str(tmp_path / 'cards.png'), quick=True)
    assert os.path.exists(out) and os.path.getsize(out) > 20000
    assert time.time() - t0 < 20
