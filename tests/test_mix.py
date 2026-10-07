"""Tests für engine.audio.mix: Ducking, Länge, Limiter, Lautheit, Maskierung, mask()."""
from __future__ import annotations
import json
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import config as CFG                      # noqa: E402
from engine.audio import SR, mix, wav                 # noqa: E402

TAIL = 2.0
# Wörter des Mini-Projekts: (Zeile, Wort, t0, t1). Jede Zeile hat so viele Wörter wie ihr Text.
WORDS = [
    ('H1', 'Short', 0.30, 0.55), ('H1', 'hook.', 0.60, 0.90),
    ('E2.0', 'Number', 1.60, 1.95), ('E2.0', 'two.', 2.00, 2.25), ('E2.0', 'Second.', 2.30, 2.65),
    ('E2.1', 'Second', 2.90, 3.20), ('E2.1', 'line.', 3.25, 3.55),
    ('E1.0', 'Number', 4.30, 4.65), ('E1.0', 'one.', 4.70, 4.95), ('E1.0', 'First.', 5.00, 5.35),
    ('E1.1', 'First', 5.60, 5.90), ('E1.1', 'line.', 5.95, 6.25),
    ('O1', 'Bye.', 6.90, 7.25),
]


def _synth_voice(words, seed=0) -> np.ndarray:
    """Stimmähnliches Signal: harmonischer Summton + Rauschen in jeder Wortspanne, sonst Stille."""
    rng = np.random.default_rng(seed)
    n = int((words[-1][3] + 0.3) * SR)
    v = np.zeros(n, np.float32)
    t = np.arange(n) / SR
    for _, _, t0, t1 in words:
        a, b = int(t0 * SR), int(t1 * SR)
        seg = t[a:b]
        tone = sum(np.sin(2 * np.pi * 160 * k * seg) / k for k in range(1, 7))
        x = 0.12 * tone + 0.03 * rng.standard_normal(len(seg))
        env = np.minimum(1.0, np.minimum(np.arange(len(seg)), np.arange(len(seg))[::-1]) / (0.02 * SR))
        v[a:b] = (x * env).astype(np.float32)
    return v


@pytest.fixture()
def project(tmp_path):
    """Mini-Projekt mit script.json, words.json und synthetischer voice.wav; ein Skript-Cue mit +10 dB auf 'Second'."""
    script = {
        'title': 'Mix Test', 'slug': 'mixtest', 'format': 'portrait', 'lang': 'en', 'theme': 'curious',
        'tail': TAIL, 'music': 'auto', 'announce': 'number_title', 'seed': 7,
        'hook': {'lines': ['Short hook.']},
        'entries': [
            {'rank': 2, 'title': 'Second', 'lines': ['Second line.'], 'cues': [['Second', 'card_hit', 10]]},
            {'rank': 1, 'title': 'First', 'lines': ['First line.']},
        ],
        'outro': {'lines': ['Bye.']},
    }
    d = tmp_path / 'proj'
    d.mkdir()
    (d / 'script.json').write_text(json.dumps(script), encoding='utf-8')
    voice = _synth_voice(WORDS)
    wav.write(str(d / 'voice.wav'), voice, SR)
    (d / 'words.json').write_text(json.dumps({
        'source': 'test', 'duration': len(voice) / SR,
        'words': [{'w': w, 't0': t0, 't1': t1, 'line': ln} for ln, w, t0, t1 in WORDS]}), encoding='utf-8')
    return str(d)


def _cfg(**mix_over) -> dict:
    cfg = CFG.load(ROOT)
    cfg = json.loads(json.dumps(cfg))
    cfg['mix'].update(mix_over)
    return cfg


# --- Ducking -------------------------------------------------------------------------------------------------

def test_duck_lowers_music_during_voice():
    rng = np.random.default_rng(3)
    v = np.zeros(SR * 4, np.float32)
    v[SR:2 * SR] = (0.2 * rng.standard_normal(SR)).astype(np.float32)
    mcfg = {'music_db': -14.0, 'music_solo_db': -6.0, 'duck_attack': 0.08, 'duck_release': 0.45}
    curve = mix.duck_curve(v, mcfg)
    assert curve.shape == v.shape
    ref = mix.voice_level_db(v)
    silent = float(curve[int(0.1 * SR):int(0.8 * SR)].mean())
    speech = float(curve[int(1.3 * SR):int(1.9 * SR)].mean())
    assert abs(silent - (ref - 6.0)) < 1.0                  # ohne Stimme: music_solo_db unter dem Sprechpegel
    assert abs(speech - (ref - 14.0)) < 2.0                 # beim Sprechen: music_db unter dem Stimmpegel
    assert silent - speech > 6.0
    assert float(np.abs(np.diff(curve)).max()) < 0.02       # keine Sprünge (weiche Übergänge)
    # Vorlauf: die Musik ist bereits beim ersten Stimmsample unten
    assert float(curve[SR]) < silent - 4.0
    # Halten: kurz nach dem Ende der Stimme noch unten; Rückkehr: gut eine Sekunde danach wieder oben
    assert float(curve[int(2.3 * SR)]) < silent - 4.0
    assert float(curve[int(3.2 * SR)]) > silent - 1.0


# --- Limiter und Messung ---------------------------------------------------------------------------------------

def test_limiter_holds_true_peak():
    rng = np.random.default_rng(1)
    x = (0.1 * rng.standard_normal((SR * 3, 2))).astype(np.float32)
    for p in (SR, 2 * SR):
        x[p:p + 3] = 1.5
    assert mix.true_peak_db(x) > 0.0
    y, red = mix.limit(x, -1.0)
    assert y.shape == x.shape and y.dtype == np.float32
    assert mix.true_peak_db(y) <= -1.0 + 0.05
    assert red > 3.0
    far = slice(int(1.9 * SR), int(2.0 * SR) - 600)          # nach der Rückkehr, vor der nächsten Rampe: praktisch unverändert
    assert np.allclose(x[far], y[far], atol=2e-3)
    # Signal ohne Spitzen bleibt exakt
    z, red0 = mix.limit(x[int(1.5 * SR):int(1.8 * SR)], -1.0)
    assert red0 == 0.0


def test_lufs_numpy_matches_reference_sine():
    t = np.arange(SR * 3) / SR
    s = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    st = np.stack([s, s], axis=1)
    est = mix.lufs_numpy(st)
    assert abs(est - (-6.0)) < 0.5                            # ffmpeg ebur128 misst -6.0 LUFS für diesen Ton
    assert mix.lufs_numpy(np.zeros((SR, 2), np.float32)) == float('-inf')
    m = mix._lufs_measure(st)
    assert abs(m['lufs'] - est) < 0.5
    assert abs(m['true_peak'] - (-6.0)) < 0.3


# --- Vollständige Mischung ---------------------------------------------------------------------------------------

def test_build_length_loudness_and_stems(project, monkeypatch):
    monkeypatch.setattr(mix, '_optional', lambda name: None)   # music/sfx fehlen: Platzhalter erzwingen
    cfg = _cfg(stems=True)
    res = mix.build(project, cfg, ROOT)
    from engine import compose
    comp = compose.load(project, ROOT)
    data, sr = wav.read(os.path.join(project, 'mix.wav'), SR)
    assert sr == SR and data.ndim == 2 and data.shape[1] == 2
    assert data.shape[0] == int(round(comp.duration * SR)) == res['samples']
    assert abs(res['duration'] - comp.duration) < 1e-3
    assert abs(res['lufs'] - cfg['mix']['master_lufs']) < 1.0
    assert res['true_peak'] <= cfg['mix']['true_peak_db'] + 0.1
    assert res['music'] == 'placeholder'
    assert res['cues'] >= 6 and res['skipped_cues'] == 0
    assert set(res['missing_sfx']) >= {'hook_hit', 'card_whoosh', 'card_hit', 'number_one', 'outro_chime', 'end_sting'}
    assert res['masked'] >= 1                                  # der +10-dB-Cue auf 'Second' wurde begrenzt
    for stem in ('voice_stem.wav', 'music_stem.wav', 'sfx_stem.wav'):
        p = os.path.join(res['stems'], stem)
        assert os.path.exists(p)
        d, _ = wav.read(p, SR)
        assert d.shape[0] == res['samples']
    # Stems summieren sich (vor dem Limiter) ungefähr zur Mischung
    stems = sum(wav.read(os.path.join(res['stems'], s), SR)[0] for s in ('voice_stem.wav', 'music_stem.wav', 'sfx_stem.wav'))
    assert np.corrcoef(stems[:, 0], data[:, 0])[0, 1] > 0.98
    # Platzhalterbett liegt im Mix unter der Stimme: Musikspur deutlich leiser als die Stimme während der Wörter
    music, _ = wav.read(os.path.join(res['stems'], 'music_stem.wav'), SR)
    voice, _ = wav.read(os.path.join(res['stems'], 'voice_stem.wav'), SR)
    a, b = int(4.3 * SR), int(5.35 * SR)
    assert wav.rms_db(voice[a:b]) - wav.rms_db(music[a:b]) > 10.0
    # ... und in der Stille des Schlussteils (vor dem Ausblenden) lauter als beim Sprechen
    c, d_ = int((comp.duration - 0.95) * SR), int((comp.duration - 0.55) * SR)
    assert wav.rms_db(music[c:d_]) > wav.rms_db(music[a:b]) + 4.0


def test_build_without_music(project, monkeypatch):
    monkeypatch.setattr(mix, '_optional', lambda name: None)
    res = mix.build(project, _cfg(), ROOT, music='none')
    assert res['music'] == 'none' and res['music_gain_db'] is None
    assert abs(res['lufs'] - (-14.0)) < 1.0


def test_build_uses_music_and_sfx_modules_when_present(project, monkeypatch):
    """Vorhandene Module werden mit der vereinbarten Schnittstelle gerufen; unbekannte SFX-IDs fallen zurück."""
    calls = {}

    class FakeMusic:
        @staticmethod
        def pick(theme):
            calls['theme'] = theme
            return 'bed_x'

        @staticmethod
        def render(bed_id, duration, seed=0, sections=None):
            calls['render'] = (bed_id, duration, seed, sections)
            t = np.arange(int(duration * SR)) / SR
            s = (0.05 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
            return np.stack([s, s], axis=1)

    class FakeSfx:
        @staticmethod
        def render(sfx_id):
            if sfx_id != 'card_hit':
                raise KeyError(sfx_id)
            t = np.arange(int(0.1 * SR)) / SR
            s = (0.5 * np.sin(2 * np.pi * 800 * t) * np.exp(-t / 0.03)).astype(np.float32)
            return np.stack([s, s], axis=1)

    monkeypatch.setattr(mix, '_optional', lambda name: {'music': FakeMusic, 'sfx': FakeSfx}[name])
    res = mix.build(project, _cfg(), ROOT)
    assert res['music'] == 'bed_x' and calls['theme'] == 'curious'
    bed_id, duration, seed, sections = calls['render']
    assert seed == 7 and abs(duration - res['duration']) < 1e-3
    assert [s['kind'] for s in sections] == ['hook', 'entry', 'entry', 'outro']
    assert [s['energy'] for s in sections] == [0.6, 0.5, 0.9, 0.4]
    assert 'card_hit' not in res['missing_sfx'] and 'hook_hit' in res['missing_sfx']


# --- Maskierung ------------------------------------------------------------------------------------------------

def test_mask_lists_words_close_to_sounds(project, monkeypatch):
    monkeypatch.setattr(mix, '_optional', lambda name: None)
    out = mix.mask(project, _cfg(), ROOT)
    assert isinstance(out, list) and out
    hit = [o for o in out if o['sfx'] == 'card_hit' and o['w'] == 'Second.']
    assert hit, out
    for o in out:
        assert {'w', 'line', 't0', 't1', 'word_db', 'sfx', 't', 'sfx_db', 'distance_db', 'why'} <= set(o)
        assert o['distance_db'] < 8.0
    assert abs(hit[0]['distance_db'] - 6.0) < 0.6              # auf das Wort begrenzt: genau 6 dB darunter


def test_sections_and_placeholders():
    bed = mix.placeholder_bed(2.0, seed=3)
    assert bed.shape == (2 * SR, 2) and bed.dtype == np.float32
    assert abs(10 * np.log10(np.mean(bed.astype(np.float64) ** 2)) - (-30.0)) < 0.5   # RMS je Kanal
    assert abs(wav.rms_db(bed) - (-30.0)) < 2.0                                           # monokompatibel
    assert np.array_equal(bed, mix.placeholder_bed(2.0, seed=3))  # deterministisch
    blip = mix.placeholder_blip()
    assert blip.shape == (int(0.06 * SR), 2) and float(np.abs(blip).max()) <= 0.5


# --- Randfälle (Review) ------------------------------------------------------------------------------------------

def test_truncated_cue_fades_out_at_video_end():
    """Ein Ton, der über das Videoende hinausragt, wird abgeschnitten und in den letzten 10 ms ausgeblendet."""
    n_total = SR // 2
    snd = np.ones((SR, 2), np.float32) * 0.5                     # 1 s Dauerton, Video nur 0,5 s
    placed = [{'sound': snd, 'n0': n_total - SR // 4, 'gain': 1.0}]
    out = mix._render_cues(placed, n_total)
    assert out.shape == (n_total, 2)
    assert abs(out[-1, 0]) < 1e-6 and abs(out[-480, 0] - 0.5) < 1e-3   # letztes Sample 0, 10 ms davor voll
    assert np.all(np.diff(out[-480:, 0]) <= 1e-6)                        # monoton fallend, kein Sprung
    # Ton, der ins Video passt, bleibt unverändert
    placed = [{'sound': snd[:SR // 8], 'n0': 0, 'gain': 2.0}]
    out = mix._render_cues(placed, n_total)
    assert np.allclose(out[:SR // 8], 1.0) and np.all(out[SR // 8:] == 0.0)


def test_fade_edges_mono_and_stereo():
    m = mix._fade_edges(np.ones(1000, np.float32), 0.01, 0.01)
    assert m.shape == (1000,) and m[0] == 0.0 and m[-1] == 0.0 and m[500] == 1.0
    st = mix._fade_edges(np.ones((1000, 2), np.float32), 0.0, 0.01)
    assert st.shape == (1000, 2) and st[0, 0] == 1.0 and st[-1, 1] == 0.0


def test_lufs_numpy_mono_and_fast_measure():
    t = np.arange(SR * 2) / SR
    s = (0.25 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    mono = mix.lufs_numpy(s)
    st = mix.lufs_numpy(np.stack([s, s], axis=1))
    assert abs(st - mono - 3.0103) < 0.05                        # zwei gleiche Kanäle: +3 dB
    assert abs(mono - (-12.0 - 0.691 - 3.0103 + 0.691 - 0.0)) < 1.5  # grob: -15 LUFS (Sinus -12 dBFS RMS, 1 kHz)
    m = mix._lufs_measure(s, fast=True)
    assert m['source'] == 'numpy' and m['true_peak'] is None and abs(m['lufs'] - mono) < 1e-9
    full = mix._lufs_measure(s)
    assert abs(full['lufs'] - mono) < 0.3


def test_seed_is_robust():
    import types
    assert mix._seed(types.SimpleNamespace(script={'seed': 7})) == 7
    assert mix._seed(types.SimpleNamespace(script={'seed': '11'})) == 11
    s = mix._seed(types.SimpleNamespace(script={'seed': 'abc', 'slug': 'x'}))
    assert isinstance(s, int) and 0 <= s <= 0xFFFF
    assert mix._seed(types.SimpleNamespace(script={'slug': 'y'})) == mix._seed(types.SimpleNamespace(script={'slug': 'y'}))


def test_stat_cue_value_is_a_word_not_seconds(project):
    """stat.value ohne 'at': als gesprochenes Wort gesucht (erst in der Szene), nie als Sekunden; sonst 2 s nach Szenenbeginn."""
    from engine import compose
    p = os.path.join(project, 'script.json')
    script = json.loads(open(p, encoding='utf-8').read())
    script['entries'][0]['stat'] = {'value': 'line', 'label': 'X'}        # Rang 2: 'line.' kommt in E2.1 und E1.1 vor
    script['entries'][1]['stat'] = {'value': '42', 'label': 'UNITS'}      # Rang 1: nicht gesprochen -> Standard
    open(p, 'w', encoding='utf-8').write(json.dumps(script))
    comp = compose.load(project, ROOT)
    pops = {c['why']: c['t'] for c in comp.cues() if c['sfx'] == 'stat_pop'}
    e2 = [sc for sc in comp.scenes if sc.kind == 'entry' and sc.rank == 2][0]
    e1 = [sc for sc in comp.scenes if sc.kind == 'entry' and sc.rank == 1][0]
    assert abs(pops[f'Stat {e2.id}'] - 3.25) < 1e-3                       # 'line.' der eigenen Szene (E2.1), nicht E1.1
    assert abs(pops[f'Stat {e1.id}'] - (e1.t0 + 2.0)) < 1e-3
    assert all(0 <= t < comp.duration for t in pops.values())
    script['entries'][1]['stat'] = {'value': '42', 'at': 1.5}
    open(p, 'w', encoding='utf-8').write(json.dumps(script))
    comp = compose.load(project, ROOT)
    t1 = [c['t'] for c in comp.cues() if c['why'] == f'Stat {e1.id}'][0]
    assert abs(t1 - (e1.t0 + 1.5)) < 1e-3                                 # Zahl bei 'at' = Sekunden ab Szenenbeginn


def test_build_fades_truncated_voice(project, monkeypatch):
    """Ist voice.wav länger als das Video (tail 0), wird sie abgeschnitten, gewarnt und am Ende ausgeblendet."""
    monkeypatch.setattr(mix, '_optional', lambda name: None)
    p = os.path.join(project, 'script.json')
    script = json.loads(open(p, encoding='utf-8').read())
    script['tail'] = 0.0
    open(p, 'w', encoding='utf-8').write(json.dumps(script))
    voice = _synth_voice(WORDS)[:int(7.0 * SR)]                           # ab 7,0 s (im letzten Wort) ein 1-s-Dauerton:
    voice = np.concatenate([voice, np.full(SR, 0.2, np.float32)])        # er ragt über das Videoende (7,25 s) hinaus
    wav.write(os.path.join(project, 'voice.wav'), voice, SR)
    res = mix.build(project, _cfg(stems=True), ROOT, music='none')
    assert any('abgeschnitten' in w for w in res['warnings'])
    v, _ = wav.read(os.path.join(res['stems'], 'voice_stem.wav'), SR)
    assert res['samples'] == int(round(WORDS[-1][3] * SR))
    assert abs(v[-1]).max() < 1e-3 and abs(v[-600]).max() > 0.05          # Ende 0, 12 ms davor noch Signal
