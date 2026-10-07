import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import anim, color, fonts, layout, script as S, timeline as T
from engine.canvas import Frame


def test_easing_bounds():
    for name, fn in anim.EASE.items():
        assert abs(fn(0.0)) < 1e-6 or name in ('out_elastic',), name
        assert abs(fn(1.0) - 1.0) < 1e-6, name


def test_tween_and_appear():
    assert anim.tween(0, 1, 1) == 0.0
    assert anim.tween(2, 1, 1) == 1.0
    assert 0 < anim.tween(1.5, 1, 1) < 1
    assert anim.appear(10, 1, 5) == 0.0
    assert anim.appear(2, 1, 5) == 1.0


def test_keyframes():
    k = anim.Keyframes([(0, (0, 0)), (1, (10, 20))])
    v = k.at(0.5)
    assert 0 < v[0] < 10 and 0 < v[1] < 20


def test_color():
    assert color.parse('#FF0000') == (1.0, 0.0, 0.0, 1.0)
    assert color.hexs(color.mix('#000000', '#FFFFFF', 0.5)) == '#808080'
    assert color.contrast('#000', '#FFF') > 20
    assert color.text_on('#000000') == '#FFFFFF'


def test_fonts_variable_weight():
    f3 = fonts.font('display', 100, weight=300)
    f8 = fonts.font('display', 100, weight=800)
    assert fonts.measure('Hamburg', f3) < fonts.measure('Hamburg', f8)
    assert fonts.wrap('one two three four five six seven', 'body', 40, 200)


def test_layout():
    p = layout.get_format('portrait'); l = layout.get_format('landscape')
    assert (p.W, p.H) == (1080, 1920) and (l.W, l.H) == (1920, 1080)
    assert p.caption.y1 < p.H - p.safe_bottom + 1
    assert p.buttons.x >= 890


SCRIPT = {"title": "T", "slug": "t", "hook": {"lines": ["Hook line here."]},
          "entries": [{"rank": 2, "title": "Two", "lines": ["Line a.", {"text": "Line b.", "gap_after": 0.5}]},
                      {"rank": 1, "title": "One", "lines": ["Line c."]}],
          "outro": {"lines": ["Bye."]}}


def test_script_lines_and_timeline():
    S.validate(SCRIPT)
    ids = [l['id'] for l in S.lines(SCRIPT)]
    assert ids == ['H1', 'E2.0', 'E2.1', 'E2.2', 'E1.0', 'E1.1', 'O1']
    tl = T.build(SCRIPT)
    assert tl.duration > 5
    assert tl.at('Hook') < tl.at('Bye')
    assert tl.at('E2.2:Line') > tl.at('E2.1:Line')
    assert tl.find('nothing-here') is None
    assert tl.at('Line$+0.1') > tl.at('Line')
    t0, t1 = tl.entry_span(2)
    assert t1 - t0 > 0.5  # gap_after gilt


def test_words_mapping_roundtrip():
    tl = T.build(SCRIPT)
    wj = tl.to_json()
    tl2 = T.build(SCRIPT, wj)
    assert len(tl2.words) == len(tl.words)
    assert not any(l.meta.get('mismatch') for l in tl2.lines)


def test_canvas_draws():
    fr = Frame(200, 300)
    c = fr.c
    c.gradient_bg('#000000', '#FFFFFF')
    c.circle(100, 150, 50, '#FF0000')
    c.text('Hi', 100, 150, fonts.font('display', 40, weight=700), '#00FF00', 'center', 'middle')
    with c.layer(alpha=0.5):
        c.rect(10, 10, 50, 50, '#0000FF', r=8)
    with c.tf(rot=20, px=100, py=150):
        c.rect_c(100, 150, 40, 40, '#FFFF00')
    c.grain(0.05); c.vignette(0.3)
    arr = fr.to_array()
    assert arr.shape == (300, 200, 4)
    assert arr[150, 100, 0] > 100  # Kreis ist rot
