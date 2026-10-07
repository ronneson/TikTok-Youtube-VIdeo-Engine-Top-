"""Tests für engine/audio/music.py: Betten, Auswahl, Tonart/Leiter, Signalqualität, Struktur (Energie, Respekt,
Outro), Determinismus, exakte Dauer, Laufzeit, render_all, Einbindung in mix.build."""
from __future__ import annotations
import json
import os
import sys
import time

import numpy as np
import pytest
from scipy.signal import butter, sosfilt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import theme as T                          # noqa: E402
from engine.audio import SR, music as M, wav           # noqa: E402

PEAK = 10 ** (M.PEAK_DB / 20.0)
SECTIONS = [
    {'t0': 0.0, 't1': 3.1, 'kind': 'hook', 'rank': None, 'energy': 0.6},
    {'t0': 3.1, 't1': 8.7, 'kind': 'entry', 'rank': 3, 'energy': 0.5},
    {'t0': 8.7, 't1': 14.2, 'kind': 'entry', 'rank': 2, 'energy': 0.7},
    {'t0': 14.2, 't1': 20.3, 'kind': 'entry', 'rank': 1, 'energy': 0.9},
    {'t0': 20.3, 't1': 26.0, 'kind': 'outro', 'rank': None, 'energy': 0.4},
]


def _rms_db(x, t0, t1):
    seg = np.asarray(x[int(t0 * SR):int(t1 * SR)], np.float64)
    return 10.0 * np.log10(np.mean(seg * seg) + 1e-12)


def _hf_db(x, t0, t1, fc=5000.0):
    seg = np.asarray(x[int(t0 * SR):int(t1 * SR)], np.float64)
    seg = sosfilt(butter(4, fc, 'highpass', fs=SR, output='sos'), seg, axis=0)
    return 10.0 * np.log10(np.mean(seg * seg) + 1e-12)


def _check_signal(x, duration):
    assert x.dtype == np.float32 and x.ndim == 2 and x.shape[1] == 2
    assert x.shape[0] == int(round(duration * SR))                       # Dauer exakt
    assert np.isfinite(x).all()
    assert float(np.abs(x).max()) <= PEAK + 1e-3                         # Spitze <= -3 dBFS (also <= -1 dBFS)
    assert float(np.abs(x.astype(np.float64).mean(axis=0)).max()) < 1e-3  # kein Gleichanteil
    assert float(np.abs(np.diff(x, axis=0)).max()) < 0.3                 # keine Clicks
    assert x[0].max() == 0.0 and x[-1].max() == 0.0                      # weiche Ränder


# --- Katalog, Auswahl, Tonart --------------------------------------------------------------------------------

def test_beds_catalog_and_pick():
    assert set(M.BEDS) == {'cabinet_swing', 'heist_tiptoe', 'cave_drip', 'safari_bounce', 'orbit_glow',
                           'parlour_waltz', 'cabinet_swing_pulse'}
    for bid, b in M.BEDS.items():
        assert {'mood', 'bpm', 'key', 'themes', 'desc'} <= set(b)
        assert b['bpm'] == {'cabinet_swing': 112, 'heist_tiptoe': 100, 'cave_drip': 84, 'safari_bounce': 124,
                            'orbit_glow': 96, 'parlour_waltz': 72, 'cabinet_swing_pulse': 104}[bid]
    assert M.BEDS['parlour_waltz']['meter'] == 3
    assert [c['id'] for c in M.catalog()] == list(M.BEDS)
    # jedes Thema bekommt ein Bett; Präfix-Auflösung; Standard
    for name in T.names():
        bid = M.pick(name)
        assert bid in M.BEDS
        assert T.bed(name).startswith(bid)
    assert M.pick('ocean') == 'orbit_glow' and M.resolve('orbit_glow_ocean') == 'orbit_glow'
    assert M.pick('auto') == 'cabinet_swing' and M.pick(None) == 'cabinet_swing' and M.pick('gibtsnicht') == 'cabinet_swing'
    assert M.pick('heist_tiptoe') == 'heist_tiptoe' and M.pick('cave', mood='respect') == 'parlour_waltz'
    assert M.pick('space', mood='sneaky') == 'heist_tiptoe'
    with pytest.raises(KeyError):
        M.resolve('xyz', default=None)


def test_key_and_ladder_follow_stil():
    assert {b: M.key(b) for b in M.BEDS} == {'cabinet_swing': 74, 'heist_tiptoe': 76, 'cave_drip': 69, 'safari_bounce': 67,
                                             'orbit_glow': 66, 'parlour_waltz': 70, 'cabinet_swing_pulse': 74}
    assert M.ladder('cabinet_swing') == [86, 81, 79, 76, 74]             # #1 D6 … #5 D5
    assert M.ladder('heist_tiptoe') == [88, 83, 81, 78, 76]              # E6 B5 A5 F#5 E5
    assert M.ladder('parlour_waltz') == [82, 77, 75, 72, 70]             # Bb5 F5 Eb5 C5 Bb4
    ten = M.ladder('cabinet_swing', 10)
    assert ten[:5] == M.ladder('cabinet_swing') and ten[5:] == [m - 12 for m in M.ladder('cabinet_swing')]
    assert M.ladder_note('safari_bounce', 5) == 67 and M.ladder_note('safari_bounce', 1) == 79
    assert M.key('orbit_glow_ocean') == 66


# --- Signalqualität je Bett --------------------------------------------------------------------------------------

@pytest.mark.parametrize('bed_id', sorted(M.BEDS))
def test_render_quality(bed_id):
    st = {}
    x = M.render(bed_id, 12.0, seed=2, stats=st)
    _check_signal(x, 12.0)
    assert st['notes'] > 20
    assert -30.0 < _rms_db(x, 1.0, 11.5) < -12.0                           # hörbar, aber nicht zu heiß
    assert not np.allclose(x[:, 0], x[:, 1])                               # Stereo-Breite
    mono = (x[:, 0].astype(np.float64) + x[:, 1]) * 0.5
    assert _rms_db(mono[:, None], 1.0, 11.5) > _rms_db(x[:, :1], 1.0, 11.5) - 4.0   # monokompatibel: keine Auslöschung


def test_render_odd_durations_and_short():
    for d in (0.5, 1.0, 2.75, 7.999, 12.345):
        _check_signal(M.render('safari_bounce', d, seed=1), d)
    assert M.render('cave_drip', 0.01).shape == (480, 2)


def test_render_is_deterministic_and_seed_varies():
    a = M.render('heist_tiptoe', 5.0, seed=3)
    b = M.render('heist_tiptoe', 5.0, seed=3)
    c = M.render('heist_tiptoe', 5.0, seed=4)
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_unknown_bed_resolves_or_raises():
    assert M.render('orbit_glow_ocean', 2.0).shape == (2 * SR, 2)
    with pytest.raises(KeyError):
        M.render('kein_bett', 1.0)


# --- Struktur: Energie, Akzente, Respekt, Outro --------------------------------------------------------------------

@pytest.mark.parametrize('bed_id', ['cabinet_swing', 'heist_tiptoe', 'orbit_glow'])
def test_sections_shape_the_energy(bed_id):
    st = {}
    x = M.render(bed_id, 26.0, seed=5, sections=SECTIONS, stats=st)
    _check_signal(x, 26.0)
    hook, e3, e2, e1, outro = (_rms_db(x, s['t0'] + 0.8, s['t1'] - 0.4) for s in SECTIONS)
    assert e1 > e3 + 2.0 and e1 > hook                                   # Höhepunkt bei Rang 1
    assert e2 >= e3 - 0.5                                                # mehr Schichten je Eintrag
    assert outro < e1 - 2.5                                              # Outro: Auflösung, Perkussion weg
    assert _hf_db(x, 14.9, 19.9) > _hf_db(x, 21.0, 25.5) + 6.0           # Hats/Shaker im Outro verschwunden
    assert st['accents'] and st['final_beat'] is not None
    beat = 60.0 / M.BEDS[bed_id]['bpm']
    for s in SECTIONS[1:]:                                                # Szenenbeginn liegt im Takt (auf einem Beat)
        assert any(abs(a * beat - s['t0']) <= beat / 2 + 1e-6 for a in st['accents'])
    # Schlussakkord klingt nach: in der letzten Sekunde noch Signal, aber leiser als der Höhepunkt
    assert -60.0 < _rms_db(x, 25.0, 25.9) < e1


def test_respect_sections_are_pad_only():
    secs = [dict(s) for s in SECTIONS]
    secs[2]['respect'] = True
    normal = M.render('cabinet_swing', 26.0, seed=5, sections=SECTIONS)
    quiet = M.render('cabinet_swing', 26.0, seed=5, sections=secs)
    t0, t1 = SECTIONS[2]['t0'] + 0.8, SECTIONS[2]['t1'] - 0.4
    assert _hf_db(quiet, t0, t1) < _hf_db(normal, t0, t1) - 8.0           # kein Schlagwerk, kein Lauf
    assert _rms_db(quiet, t0, t1) < _rms_db(normal, t0, t1) - 3.0
    assert _rms_db(quiet, t0, t1) > -45.0                                 # aber nicht still: das Pad bleibt
    # Energie-Parameter: konstante Energie ohne Akzente
    st = {}
    M.render('cabinet_swing', 6.0, energy=0.95, stats=st)
    assert st['accents'] == []


def test_demo_sections_cover_duration():
    secs = M.demo_sections(30.0)
    assert secs[0]['kind'] == 'hook' and secs[-1]['kind'] == 'outro' and len(secs) == 7
    assert [s['rank'] for s in secs[1:-1]] == [5, 4, 3, 2, 1]
    assert secs[0]['t0'] == 0.0 and secs[-1]['t1'] == 30.0
    for a, b in zip(secs, secs[1:]):
        assert abs(a['t1'] - b['t0']) < 1e-6
    assert M.demo_sections(4.0)[0]['kind'] == 'entry'


# --- Laufzeit, render_all, Einbindung -----------------------------------------------------------------------------

def test_render_90s_under_budget():
    secs = M.demo_sections(90.0)
    t = time.time()
    x = M.render('cabinet_swing', 90.0, seed=9, sections=secs)
    assert time.time() - t < 8.0
    _check_signal(x, 90.0)


def test_render_all_writes_files(tmp_path):
    res = M.render_all(str(tmp_path), seconds=4.0)
    assert [b['id'] for b in res['beds']] == list(M.BEDS)
    for b in res['beds']:
        assert os.path.exists(b['file'])
        d, sr = wav.read(b['file'], SR)
        assert sr == SR and d.shape == (4 * SR, 2)
        assert b['peak_db'] <= M.PEAK_DB + 0.05 and b['dc'] < 1e-3 and b['max_step'] < 0.3 and b['dur'] == 4.0


def test_mix_build_uses_music(tmp_path):
    """mix.build zieht das Bett des Themas über music.pick/render (kein Platzhalter) und stimmt die Töne."""
    from engine import config as CFG
    from engine.audio import mix
    words = [('H1', 'Short', 0.30, 0.55), ('H1', 'hook.', 0.60, 0.90), ('E1.0', 'One.', 1.60, 1.95), ('O1', 'Bye.', 2.60, 2.95)]
    script = {'title': 'Music Test', 'slug': 'musictest', 'format': 'portrait', 'lang': 'en', 'theme': 'heist', 'tail': 1.5,
              'music': 'auto', 'seed': 3, 'hook': {'lines': ['Short hook.']},
              'entries': [{'rank': 1, 'title': 'One', 'lines': ['One.']}], 'outro': {'lines': ['Bye.']}}
    d = tmp_path / 'proj'
    d.mkdir()
    (d / 'script.json').write_text(json.dumps(script), encoding='utf-8')
    n = int(3.3 * SR)
    t = np.arange(n) / SR
    v = np.zeros(n, np.float32)
    for _, _, t0, t1 in words:
        a, b = int(t0 * SR), int(t1 * SR)
        v[a:b] = (0.1 * np.sin(2 * np.pi * 180 * t[a:b])).astype(np.float32)
    wav.write(str(d / 'voice.wav'), v, SR)
    (d / 'words.json').write_text(json.dumps({'source': 'test', 'duration': n / SR,
                                              'words': [{'w': w, 't0': t0, 't1': t1, 'line': ln} for ln, w, t0, t1 in words]}), encoding='utf-8')
    res = mix.build(str(d), CFG.load(ROOT), ROOT)
    assert res['music'] == 'heist_tiptoe'
    assert not any(w.startswith('music') or 'Platzhalter-Musik' in w for w in res['warnings'])
    assert res['true_peak'] <= -0.9
