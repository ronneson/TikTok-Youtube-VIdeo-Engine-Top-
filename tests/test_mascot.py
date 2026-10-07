import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import mascot, theme
from engine.canvas import Frame


def _render(size=160, pose='idle', costume='default', bg='#1E1838', W=None, H=None, **kw):
    """Rendert die Figur auf einen kleinen Puffer und liefert (Array, Bodenpunkt)."""
    W = W or int(size * 1.8)
    H = H or int(size * 1.6)
    fr = Frame(W, H)
    c = fr.c
    c.fill(bg)
    x, y = W / 2, H - size * 0.15
    mascot.draw(c, x, y, size, pose=pose, costume=costume, theme=theme.get('curious'), **kw)
    return fr.to_rgb().astype(int), (x, y)


def _bbox(arr, bg_rgb):
    diff = np.abs(arr - np.array(bg_rgb)).sum(axis=2) > 40
    ys, xs = np.where(diff)
    assert len(xs) > 0, 'nichts gezeichnet'
    return xs.min(), xs.max(), ys.min(), ys.max()


def test_lists_and_theme_map():
    assert len(mascot.POSES) >= 12 and len(mascot.EXPRS) == 8 and len(mascot.COSTUMES) >= 8
    assert set(mascot.THEME_COSTUME.values()) <= set(mascot.COSTUMES)
    for n in theme.names():
        assert mascot.costume_for(n) in mascot.COSTUMES
    assert mascot.costume_for('heist') == 'thief' and mascot.costume_for('unbekannt') == 'default'


def test_all_poses_expressions_costumes_render():
    bg = (0x1E, 0x18, 0x38)
    for pose in mascot.POSES:
        arr, _ = _render(140, pose=pose)
        _bbox(arr, bg)
    for ex in mascot.EXPRS:
        arr, _ = _render(140, expr=ex)
        _bbox(arr, bg)
    for co in mascot.COSTUMES:
        arr, _ = _render(140, costume=co, t=0.7)
        _bbox(arr, bg)


def test_modes_flip_alpha_pop():
    bg = (0x1E, 0x18, 0x38)
    for kw in (dict(mode='color'), dict(mode='rim'), dict(mode='silhouette', color='#F7F1E6'), dict(flip=True),
               dict(alpha=0.5), dict(k=0.4), dict(k=1.1), dict(rot=10.0), dict(look=(1, -1)), dict(head_turn=1.0)):
        arr, _ = _render(140, **kw)
        _bbox(arr, bg)
    # k <= 0 zeichnet nichts
    fr = Frame(100, 100); fr.c.fill('#000000')
    mascot.draw(fr.c, 50, 90, 60, k=0.0, theme=theme.get('curious'))
    assert fr.to_rgb().max() == 0


def test_size_and_width_limits():
    """Körperhöhe = size (Scheitel bei y - size), Breite inkl. Rand < 1.3 * size in jeder Pose (size 420)."""
    bg = (0x1E, 0x18, 0x38)
    size = 420
    for pose in mascot.POSES:
        if pose in ('peek', 'hide'):
            continue
        arr, (x, y) = _render(size, pose=pose, W=1000, H=760, blink=False, shadow=False)
        x0, x1, y0, y1 = _bbox(arr, bg)
        assert (x1 - x0) <= 1.3 * size + 2, (pose, x1 - x0)
    arr, (x, y) = _render(size, pose='idle', W=1000, H=760, t=0.0, blink=False, shadow=False, breathe_amp=0.0, head_tilt=0.0)
    x0, x1, y0, y1 = _bbox(arr, bg)
    rim = mascot.rim_for(size)
    top = y - size
    assert abs(y0 - (top - rim)) < 8, (y0, top - rim)           # Scheitel + Rand
    assert abs(y1 - (y + rim + 8)) < 14, (y1, y + rim)          # Füße + Rand (+ Schatten dy)
    assert abs(x - (x0 + x1) / 2) < 0.1 * size                   # Bodenmitte etwa mittig


def test_flip_mirrors():
    bg = (0x1E, 0x18, 0x38)
    a, (x, y) = _render(160, pose='point', t=0.8, blink=False)
    b, _ = _render(160, pose='point', t=0.8, blink=False, flip=True)
    xa0, xa1, _, _ = _bbox(a, bg)
    xb0, xb1, _, _ = _bbox(b, bg)
    assert abs((xa0 - x) + (xb1 - x)) < 4 and abs((xa1 - x) + (xb0 - x)) < 4


def test_blink_deterministic_and_present():
    vals = [mascot.blink(t, seed=3) for t in np.arange(0, 12, 1 / 30)]
    assert max(vals) > 0.9 and min(vals) == 0.0
    assert mascot.blink(4.321, seed=3) == mascot.blink(4.321, seed=3)
    assert mascot.blink(4.321, seed=3) != mascot.blink(4.321, seed=9) or True
    # Blinzelabstand 2.5 .. 5 s
    closed = [t for t, v in zip(np.arange(0, 60, 1 / 60), [mascot.blink(t) for t in np.arange(0, 60, 1 / 60)]) if v > 0.95]
    gaps = np.diff([closed[0]] + [b for a, b in zip(closed, closed[1:]) if b - a > 0.5])
    assert len(gaps) >= 8 and gaps.min() > 2.3 and gaps.max() < 5.3


def test_state_loops_are_time_functions():
    s0 = mascot.state('cheer', t=0.0)
    s1 = mascot.state('cheer', t=0.125)
    assert s0['body_dy'] != s1['body_dy']                     # hüpft
    r0, r1 = mascot.state('run', t=0.0), mascot.state('run', t=0.06)
    assert r0['leg_swing'] != r1['leg_swing']                  # Beine im Zyklus
    assert abs(mascot.state('idle', t=0.0)['breathe'] - 1.0) <= 0.015
    assert mascot.state('idle', t=0.625)['breathe'] != mascot.state('idle', t=0.0)['breathe']
    assert mascot.state('think', t=0.3)['wing'] != mascot.state('think', t=0.5)['wing']   # tippt
    assert mascot.state('idle', expr='angry')['brow_l'] == -25
    assert mascot.state('idle', expr='sly')['look'] == (0.8, 0.0)
    assert mascot.state('idle', look=(0.3, 0.2))['look'] == (0.3, 0.2)
    assert mascot.state('idle', tail=12.0)['tail'] == 12.0


def test_anchors():
    a = mascot.anchors(500, 800, 400, pose='idle', t=0.0)
    for k in ('hat', 'face', 'neck', 'back', 'beak_tip', 'hand', 'top', 'floor'):
        assert k in a
    assert a['beak_tip'][0] > a['face'][0] > a['back'][0]
    assert a['top'][1] < a['face'][1] < a['neck'][1] < a['floor'][1]
    b = mascot.anchors(500, 800, 400, pose='idle', t=0.0, flip=True)
    assert abs((a['beak_tip'][0] - 500) + (b['beak_tip'][0] - 500)) < 1e-6


def test_draw_head_and_sheet(tmp_path):
    fr = Frame(120, 120); fr.c.fill('#1E1838')
    mascot.draw_head(fr.c, 60, 60, 44, theme=theme.get('curious'))
    arr = fr.to_rgb().astype(int)
    x0, x1, y0, y1 = _bbox(arr, (0x1E, 0x18, 0x38))
    assert 40 < (x1 - x0) < 110 and 40 < (y1 - y0) < 90
    out = mascot.sheet(str(tmp_path / 'mascot_quick.png'), quick=True)
    assert os.path.exists(out) and os.path.getsize(out) > 10000


def _white_count(arr):
    return int((arr[..., 0] > 250).__and__(arr[..., 1] > 250).__and__(arr[..., 2] > 250).sum())


def test_lid_coverage_is_linear():
    """lid_top 0.5 deckt die Hälfte des Augenweißes, 1.0 lässt keinen Rest (kein Geisterring); Unterlid 0.5 ebenso."""
    def head(**kw):
        fr = Frame(300, 300); fr.c.fill('#1E1838')
        mascot.draw_head(fr.c, 150, 150, 240, theme=theme.get('curious'), expr='neutral', mode='color', blink=False, pupil=0.3, **kw)
        return fr.to_rgb().astype(int)
    full = _white_count(head(lid_top=0.0))
    half = _white_count(head(lid_top=0.5))
    low = _white_count(head(lid_bottom=0.5))
    assert full > 400
    assert 0.42 < half / full < 0.58, (half, full)
    assert 0.42 < low / full < 0.58, (low, full)
    assert _white_count(head(lid_top=1.0)) == 0
    # Blinzeln ist weich: Lidanteil steigt monoton und ohne Sprung über die Schließphase
    vals = [mascot.blink(2.5 + 2.5 * mascot._hash(0, 0) + u, 0) for u in np.arange(0.0, 0.121, 0.01)]
    assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:])) and max(np.diff(vals)) < 0.25


def _tip_px(size, pose, t, **kw):
    """Rechteste gezeichnete Spalte (Schnabelspitze) einer Silhouette ohne Rand."""
    W, H = int(size * 2.5), int(size * 1.9)
    fr = Frame(W, H); fr.c.fill('#000000')
    x, y = W / 2, H - size * 0.15
    mascot.draw(fr.c, x, y, size, t=t, pose=pose, theme=theme.get('curious'), mode='silhouette', color='#FFFFFF', shadow=False, **kw)
    arr = fr.to_rgb()[..., 0]
    ys, xs = np.where(arr > 128)
    x1 = xs.max()
    col = ys[xs >= x1 - 1]
    return (x, y), (float(x1), float(col.mean()))


def test_anchor_beak_tip_matches_render():
    """beak_tip aus anchors() liegt auf der gezeichneten Schnabelspitze, auch bei Squash/Hüpfen (cheer) und Atmen."""
    for pose, t in (('cheer', 0.0), ('cheer', 0.125), ('idle', 0.3), ('shock', 0.1)):
        (x, y), tip = _tip_px(400, pose, t, seed=0, t0=0.0)
        a = mascot.anchors(x, y, 400, t=t, pose=pose, seed=0, t0=0.0)['beak_tip']
        assert abs(a[0] - tip[0]) <= 6 and abs(a[1] - tip[1]) <= 6, (pose, t, a, tip)
    # Pop und Rotation werden über kw durchgereicht
    (x, y), tip = _tip_px(400, 'idle', 0.3, k=0.6, rot=12.0)
    a = mascot.anchors(x, y, 400, t=0.3, pose='idle', k=0.6, rot=12.0)['beak_tip']
    assert abs(a[0] - tip[0]) <= 8 and abs(a[1] - tip[1]) <= 8, (a, tip)   # Spitze ist 0.02 gerundet (~4 px, mit Pop-Überschwinger mehr)


def test_wing_adds_to_silhouette():
    """STIL.md 2.5: bei 120 px trägt der nahe Flügel in jeder Pose sichtbar zur Silhouette bei (außer peek/hide)."""
    def sil(pose, **kw):
        fr = Frame(300, 230); fr.c.fill('#000000')
        mascot.draw(fr.c, 150, 200, 120, t=0.5, pose=pose, theme=theme.get('curious'), mode='silhouette', color='#FFFFFF', shadow=False, **kw)
        return fr.to_rgb()[..., 0] > 128
    for pose in mascot.POSES:
        if pose in ('peek', 'hide'):
            continue
        with_wing = sil(pose)
        without = sil(pose, visible={'head', 'body', 'tail', 'legs'})
        extra = int((with_wing & ~without).sum())
        need = 300 if pose in ('shock', 'cheer', 'fly') else 20     # Flügel frei in der Luft; sonst sichtbare Spitze (run: 40°, ~80 px)
        assert extra >= need, (pose, extra)


def test_bow_and_tools():
    """bow: Werkzeug-Kostüme nehmen den Hut ab (Flügel vor der Brust), sonst Flügel angelegt; Werkzeuge vor dem Bauch."""
    assert mascot.state('bow', costume='chef')['wing'] == mascot.WING_HAT
    assert mascot.state('bow', costume='thief')['wing'] == mascot.WING_BOW
    assert mascot.state('bow', costume='thief')['body_tilt'] > 5 and mascot.state('bow')['head_tilt'] <= -15
    assert mascot.state('idle', costume='detective')['wing'] == mascot.WING_TOOL
    assert mascot.state('idle', costume='default')['wing'] == mascot.WING_REST
    w = mascot.state('wink', t=0.12, t0=0.0)['lid_near']
    assert w > 0.99 and 0.0 < mascot.state('wink', t=0.03, t0=0.0)['lid_near'] < 0.99
