import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import backdrops as B, layout as L, theme as TH
from engine.canvas import Frame

PF, LF = L.get_format('portrait'), L.get_format('landscape')
REQUIRED = ['plain', 'spotlight', 'vault', 'warehouse', 'night_city', 'museum', 'cave', 'forest', 'ocean', 'space', 'desert', 'snow',
            'lab', 'hospital', 'courtroom', 'map', 'archive', 'stage', 'road', 'sky_day', 'storm', 'dungeon', 'kitchen', 'bank_hall']
MAGENTA = np.array([255, 0, 255])


def _render(name, fmt, t=0.0, theme=None, scale=0.2, over=0.0, **kw):
    """Kulisse verkleinert rendern; over > 0 lässt rundum einen Rand frei, der nur vom Überhang gefüllt werden kann."""
    W, H = int((fmt.W + 2 * over) * scale), int((fmt.H + 2 * over) * scale)
    fr = Frame(W, H)
    c = fr.c
    c.fill('#FF00FF')
    with c.tf(x=over * scale, y=over * scale, sx=scale):
        B.draw(c, name, fmt, t, theme, **kw)
    return fr.to_rgb().astype(int)


def _magenta(arr):
    return int((np.abs(arr - MAGENTA).sum(axis=2) < 30).sum())


def test_names_aliases_and_fallback():
    ns = B.names()
    for n in REQUIRED:
        assert n in ns and n in B.BACKDROPS, n
    assert B.resolve('night') == 'night_city' and B.resolve('jungle') == 'forest' and B.resolve('STAGE') == 'stage'
    assert B.resolve('gibtsnicht') == 'plain' and B.resolve(None) == 'plain' and B.has('vault') and not B.has('nix')
    a, b = _render('gibtsnicht', PF, 0.7), _render('plain', PF, 0.7)
    assert np.array_equal(a, b)


def test_all_render_in_both_formats_and_cover_everything():
    for n in B.names():
        for fmt in (PF, LF):
            arr = _render(n, fmt, 1.3, TH.get(B.SHEET_THEME[n]))
            assert _magenta(arr) == 0, f'{n} {fmt.name}: Fläche nicht gedeckt'
            assert arr.std() > 2, f'{n} {fmt.name}: nichts gezeichnet'


def test_overhang_200px():
    for n in ('plain', 'vault', 'ocean', 'sky_day', 'storm'):
        for fmt in (PF, LF):
            arr = _render(n, fmt, 0.4, over=B.OVER)
            assert _magenta(arr) == 0, f'{n} {fmt.name}: Überhang nicht gedeckt'


def test_deterministic_and_moving():
    for n in B.names():
        a = _render(n, PF, 0.0)
        b = _render(n, PF, 0.0)
        assert np.array_equal(a, b), f'{n}: nicht deterministisch'
        c_ = _render(n, PF, 1.5)
        assert np.abs(a - c_).max() >= 2, f'{n}: keine Bewegung zwischen t=0 und t=1.5'


def test_themes_respect_and_kwargs():
    th = TH.respect(TH.get('heist'))
    assert th['glow'] is None
    for n in ('spotlight', 'night_city', 'dungeon', 'map'):
        arr = _render(n, PF, 0.9, th)
        assert _magenta(arr) == 0
    arr = _render('space', LF, 2.0, 'space', seed=3, grain=0, particles=False, light=0.5)
    assert _magenta(arr) == 0 and arr.std() > 2
    # Lichtfaktor 0 dunkelt Lampen ab, Kulisse bleibt gedeckt
    arr0 = _render('spotlight', PF, 0.5, light=0.0)
    arr1 = _render('spotlight', PF, 0.5, light=1.0)
    assert arr1.mean() > arr0.mean()


def test_sheet(tmp_path):
    out = B.sheet(str(tmp_path / 'backdrops.png'), scale=0.08, cols=6, landscape=True)
    assert os.path.exists(out) and os.path.getsize(out) > 10000
