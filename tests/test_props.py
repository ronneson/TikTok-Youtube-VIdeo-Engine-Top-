"""Piktogramm-Repertoire: Pflichtliste, Zeichnen in allen Modi, Platzhalter, Bewegung über t, Bogen."""
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import props, theme
from engine.canvas import Frame

REQUIRED = """money money_bag coin gold_bar diamond safe vault_door key lock mask crowbar barrel syrup_bottle water_drop cheese
cheese_wheel painting frame museum police handcuffs car motorcycle helicopter truck bank building house map pin clock calendar
hourglass skull bone cave rock lantern rope bat fish octopus bird cat dog rat snake bug tree mountain wave cloud sun moon star
planet rocket telescope microscope syringe pill heart brain bomb fire lightning question exclamation arrow_up arrow_down trophy
medal crown book scroll letter phone camera tv newspaper magnifier footprints sandwich tunnel drill ladder suitcase globe""".split()

STIL = """question exclaim speech_bubble thought_bubble stamp flip_card stat_chip keyword calendar map_pin country_chip arrow magnifier
clock newspaper money_bag money gem diamond coin crown ghost_halo candle closed_label skull_friendly cheese_wheel truck painting
police vault_door sandwich motorcycle car fire barrel syrup_bottle water_drop ladder mask_domino handcuffs safe getaway_car bridge
wheelbarrow helmet_lamp rope flashlight bat stalactite_set narrow_passage paw feather egg rocket planet_ring satellite space_helmet
scroll sword_shield column ship quill submarine anchor bubbles jellyfish treasure_chest syringe heart_anatomy microbe pill
stethoscope tooth scales gavel file_folder""".split()


def _frame(w=400, h=400, th=None):
    fr = Frame(w, h)
    th = th or theme.get('curious')
    fr.c.gradient_bg(th['bg0'], th['bg1'])
    return fr


def _painted(fr, bg_fr):
    a, b = fr.to_rgb().astype(int), bg_fr.to_rgb().astype(int)
    return int((np.abs(a - b).sum(axis=2) > 30).sum())


def test_required_names_present():
    missing = [n for n in REQUIRED + STIL if not props.has(n)]
    assert not missing, missing
    assert len(props.names()) >= 45
    assert all(n not in props.ALIASES for n in props.names())


def test_draw_all_modes_and_motion():
    """Jedes Piktogramm zeichnet in allen Modi ohne Fehler, hinterlässt Pixel und bewegt sich über t."""
    th = theme.get('heist')
    bg = _frame(th=th)
    bg_px = bg.to_rgb()
    t0 = time.time()
    for n in props.names():
        fr = _frame(th=th)
        props.draw(fr.c, n, 200, 200, 220, 0.3, th)
        assert _painted(fr, bg) > 1500, n
        a = fr.to_rgb().astype(int)
        moved = 0
        for tt in (0.77, 1.31, 1.9):   # nichts steht länger als 2 s still (STIL.md 1.1); unregelmäßige Abtastung
            fr2 = _frame(th=th)
            props.draw(fr2.c, n, 200, 200, 220, tt, th)
            moved = max(moved, int((np.abs(a - fr2.to_rgb().astype(int)).sum(axis=2) > 30).sum()))
        assert moved > 20, f'{n} ohne Eigenbewegung'
        for mode in ('color', 'rim', 'silhouette'):
            fr3 = _frame(th=th)
            props.draw(fr3.c, n, 200, 200, 120, 0.5, th, mode=mode)
            assert _painted(fr3, bg) > 300, (n, mode)
    assert time.time() - t0 < 60


def test_silhouette_is_single_color():
    th = theme.get('curious')
    for n in ('key', 'cheese_wheel', 'rocket', 'stamp'):
        fr = Frame(300, 300)
        fr.c.fill('#000000')
        props.draw(fr.c, n, 150, 150, 200, 0.2, th, mode='silhouette', color='#FF0000')
        rgb = fr.to_rgb()
        mask = rgb.sum(axis=2) > 40
        assert mask.sum() > 500
        # nur Rot (Antialias-Kanten erlaubt): Grün/Blau bleiben unter dem Rotwert
        assert (rgb[mask][:, 1] <= rgb[mask][:, 0]).all() and (rgb[mask][:, 2] <= rgb[mask][:, 0]).all(), n


def test_sticker_rim_is_white_outside_shape():
    """Der Sticker-Rand liegt als weiße Kontur um die Form (Zwei-Pass-Weißrand)."""
    th = theme.get('curious')
    fr = Frame(300, 300)
    fr.c.fill('#000000')
    props.draw(fr.c, 'coin', 150, 150, 200, 0.0, th, shadow=False)
    rgb = fr.to_rgb()
    white = (rgb.min(axis=2) > 235).sum()
    assert white > 2000
    fr2 = Frame(300, 300)
    fr2.c.fill('#000000')
    props.draw(fr2.c, 'coin', 150, 150, 200, 0.0, th, shadow=False, rim=0)
    assert (fr2.to_rgb().min(axis=2) > 235).sum() < white * 0.3


def test_unknown_name_draws_placeholder_without_error():
    th = theme.get('space')
    fr = _frame(th=th)
    bg = _frame(th=th)
    props.draw(fr.c, 'definitely_unknown_prop', 200, 200, 200, 0.0, th)
    assert _painted(fr, bg) > 1500
    assert not props.has('definitely_unknown_prop')


def test_k_alpha_rot_and_kwargs():
    th = theme.get('ocean')
    bg = _frame(th=th)
    fr = _frame(th=th)
    props.draw(fr.c, 'diamond', 200, 200, 200, 0.0, th, k=0.0)
    assert _painted(fr, bg) == 0
    fr = _frame(th=th)
    props.draw(fr.c, 'diamond', 200, 200, 200, 0.0, th, k=0.5, alpha=0.5, rot=30)
    assert 0 < _painted(fr, bg) < 20000
    fr = _frame(th=th)
    props.draw(fr.c, 'barrel', 200, 200, 200, 0.0, th, level=0.9, liquid='water')
    props.draw(fr.c, 'stamp', 200, 300, 150, 0.0, th, text='NEVER FOUND')
    props.draw(fr.c, 'flip_card', 100, 100, 150, 0.0, th, front='APPROVED', back='FAKE', flip=0.8)
    props.draw(fr.c, 'arrow', 300, 100, 100, 0.0, th, dir='left')
    props.draw(fr.c, 'stat_chip', 300, 300, 120, 0.0, th, value=18, label='MILLION', k=0.4)
    assert _painted(fr, bg) > 5000


def test_respect_theme_without_glow():
    th = theme.respect(theme.get('heist'))
    assert th['glow'] is None
    fr = _frame(th=th)
    bg = _frame(th=th)
    for n in ('candle', 'ghost_halo', 'closed_label', 'lantern', 'fire'):
        props.draw(fr.c, n, 200, 200, 160, 0.4, th)
    assert _painted(fr, bg) > 2000


def test_hull_and_sheet(tmp_path):
    w, h = props.hull('ladder', 300)
    assert 0 < w <= 300 and 0 < h <= 300
    out = props.sheet(str(tmp_path / 'props.png'), cols=12, size=60, cell=(150, 120))
    assert os.path.exists(out) and os.path.getsize(out) > 10000
