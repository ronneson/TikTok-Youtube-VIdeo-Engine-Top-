"""Tests für engine/audio/sfx.py: Pflicht-IDs, numerische Güte jedes Tons, Rang-Leiter/Tonart, Katalog, render_all,
Anbindung an mix (set_key)."""
from __future__ import annotations
import json
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.audio import SR, sfx, wav, mix          # noqa: E402
from engine.audio import synth as S                 # noqa: E402

PEAK = 10 ** (sfx.PEAK_DB / 20.0)
# Von compose.cues() verwendete IDs (plus Leiter-Varianten) und der Allzweck-Vorrat aus der Aufgabe
ENGINE_IDS = ['hook_hit', 'card_whoosh', 'peel', 'flap', 'hop', 'tick', 'number_one', 'pop_in', 'pop_out', 'shiny',
              'confetti', 'flash', 'riser', 'typewriter', 'keyword_slam', 'stamp', 'stat_pop', 'odd_say',
              'respect_hush', 'outro_chime', 'end_sting'] + [f'card_hit_{r}' for r in range(1, 11)]
GENERAL_IDS = ['tick', 'tick_low', 'pop', 'blip', 'blip_down', 'whoosh_soft', 'whoosh_up', 'drop', 'drip', 'swell',
               'sub_hit', 'boom_far', 'ping', 'ping_low', 'shimmer', 'bell', 'sparkle', 'type', 'count', 'riser',
               'reverse_cymbal', 'glitch', 'static', 'coin', 'cash', 'lock_click', 'glass', 'splash', 'bubble',
               'bubbles', 'wind', 'thunder', 'heartbeat', 'laugh_tiny', 'gasp', 'record_scratch', 'drumroll']


@pytest.fixture(autouse=True)
def _default_key():
    sfx.set_key(None)
    yield
    sfx.set_key(None)


def _design_ids():
    with open(os.path.join(ROOT, 'design', 'sounds.json'), encoding='utf-8') as fh:
        return [s['id'] for s in json.load(fh)['sounds']]


def _peak_freq(x, t0, t1, fmin=250.0):
    """Stärkste Spektrallinie (Hz) des Monosignals im Zeitfenster t0..t1 oberhalb fmin."""
    m = np.asarray(x, np.float64).mean(axis=1)[int(t0 * SR):int(t1 * SR)]
    w = np.abs(np.fft.rfft(m * np.hanning(len(m))))
    fr = np.fft.rfftfreq(len(m), 1.0 / SR)
    w[fr < fmin] = 0.0
    return float(fr[np.argmax(w)])


def _isolated_jumps(x, limit=0.3, win=0.002, factor=3.0):
    """Sprünge über ``limit``, die zugleich das 3-fache des 95. Perzentils ihrer Umgebung (±2 ms) übersteigen: Klicks."""
    d = np.abs(np.diff(np.asarray(x, np.float64).mean(axis=1)))
    w = int(win * SR)
    out = 0
    for i in np.flatnonzero(d > limit):
        ctx = np.concatenate([d[max(0, i - w):i], d[i + 1:i + 1 + w]])
        if len(ctx) and d[i] > factor * np.percentile(ctx, 95):
            out += 1
    return out


# --- IDs und Katalog ----------------------------------------------------------------------------------------------

def test_all_design_ids_exist():
    ids = _design_ids()
    assert len(ids) == 42
    missing = [i for i in ids if not sfx.has(i)]
    assert missing == []
    for i in ENGINE_IDS + GENERAL_IDS:
        assert sfx.has(i), i
    assert sfx.has('card_hit#4') and sfx.has('card_hit_10')
    assert not sfx.has('nope') and not sfx.has('card_hit_x')
    with pytest.raises(KeyError):
        sfx.render('nope')


def test_catalog_fields_and_levels():
    cat = sfx.catalog()
    ids = [c['id'] for c in cat]
    assert len(ids) == len(set(ids))
    assert {'id', 'use', 'dur', 'gain_db', 'group'} <= set(cat[0])
    by = {c['id']: c for c in cat}
    assert by['hook_hit']['gain_db'] > by['pop_in']['gain_db'] > by['tick']['gain_db']       # Akzente lauter als Ticks
    assert by['card_hit']['gain_db'] == -5 and by['tick']['gain_db'] == -30 and by['respect_hush']['gain_db'] == -18
    assert {f'card_hit_{r}' for r in range(1, 11)} <= set(ids)
    assert len(sfx.catalog(variants=False)) == len(sfx.ids()) >= 71
    assert sfx.default_db('tick') == -30 and sfx.meta('card_hit_3')['dur'] == 0.55
    # Dauern wie in design/sounds.json (bat_flutter: 7 Puffs bei 18 Hz brauchen 0.42 s)
    with open(os.path.join(ROOT, 'design', 'sounds.json'), encoding='utf-8') as fh:
        for s in json.load(fh)['sounds']:
            assert abs(by[s['id']]['dur'] - s['dur_s']) < 1e-9, s['id']
            assert by[s['id']]['gain_db'] == s['gain_db'], s['id']


# --- Numerische Güte jedes Tons -------------------------------------------------------------------------------------

@pytest.mark.parametrize('sid', [c['id'] for c in sfx.catalog()])
def test_render_numeric_quality(sid):
    m = sfx.meta(sid)
    x = sfx.render(sid)
    n = int(round(m['dur'] * SR))
    assert x.shape == (n, 2) and x.dtype == np.float32
    assert np.isfinite(x).all()
    pk = float(np.abs(x).max())
    assert pk <= PEAK + 1e-4 and pk > PEAK * 0.98                       # Spitze -1 dBFS (normiert)
    assert float(np.abs(x.mean(axis=0)).max()) < 0.002                   # kein Gleichanteil
    assert abs(float(x[0].mean())) < 1e-3 and abs(float(x[-1].mean())) < 1e-3   # Ränder auf 0
    assert _isolated_jumps(x) == 0                                       # keine Klicks (isolierte Sprünge)


def test_render_is_cached_copy_and_deterministic():
    a = sfx.render('confetti')
    b = sfx.render('confetti')
    assert a is not b and np.array_equal(a, b)
    a[:] = 0
    assert np.abs(sfx.render('confetti')).max() > 0.5
    c = sfx.render('confetti', seed=1)
    assert not np.array_equal(b, c)                                      # seed verändert Rauschen und Streuung
    assert np.array_equal(sfx.render('card_hit_3'), sfx.render('card_hit#3'))
    assert np.array_equal(sfx.render('card_hit'), sfx.render('card_hit_5'))  # ohne Suffix = Stufe #5


# --- Rang-Leiter und Tonart -----------------------------------------------------------------------------------------

def test_ladder_default_and_transposition():
    assert sfx.set_key(None) == [74, 76, 79, 81, 86]                     # D5 E5 G5 A5 D6
    assert sfx.key() == 74 and sfx.key_name() == 'D5'
    assert sfx.set_key('E minor') == [76, 78, 81, 83, 88]                # E5 F#5 A5 B5 E6
    assert sfx.set_key('A') == [69, 71, 74, 76, 81]                      # A4 B4 D5 E5 A5 (Oktave 4 ab F#)
    assert sfx.set_key('G major') == [67, 69, 72, 74, 79]
    assert sfx.set_key('F#') == [66, 68, 71, 73, 78]
    assert sfx.set_key('Bb') == [70, 72, 75, 77, 82]
    assert sfx.set_key(62) == [74, 76, 79, 81, 86]                       # MIDI: Oktavregel gilt
    assert sfx.set_key('E4')[0] == 64                                    # Name mit Oktave: bleibt
    assert sfx.set_key('heist_tiptoe')[0] == 76                          # Bett-ID über BED_KEYS
    sfx.set_key('D')
    assert sfx.ladder(10) == [62, 64, 67, 69, 74, 74, 76, 79, 81, 86]
    assert sfx.rank_note(10) == sfx.rank_note(5) - 12 and sfx.rank_note(1) == 86
    assert sfx.motif() == [74, 81, 86]


def test_card_hit_pitch_follows_ladder_and_key():
    for root in ('D', 'E minor'):
        lad = sfx.set_key(root)
        for rank in range(1, 6):
            f = _peak_freq(sfx.render(f'card_hit_{rank}'), 0.09, 0.4, fmin=300.0)
            want = S.midi_to_freq(lad[5 - rank])
            assert abs(f / want - 1.0) < 0.03, (root, rank, f, want)
    sfx.set_key('D')
    assert not np.array_equal(sfx.render('card_hit_1'), sfx.render('card_hit_5'))


def test_brand_motif_in_outro_and_sting():
    notes = [S.midi_to_freq(m) for m in sfx.motif()]
    for sid in ('outro_chime', 'end_sting'):
        x = sfx.render(sid)
        for (t0, t1), want in zip(((0.02, 0.17), (0.2, 0.35), (0.4, 0.8)), notes):
            f = _peak_freq(x, t0, t1, fmin=300.0)
            assert abs(f / want - 1.0) < 0.03, (sid, t0, f, want)


# --- Charakter einzelner Töne -----------------------------------------------------------------------------------------

def _rms(x):
    return float(np.sqrt(np.mean(np.asarray(x, np.float64) ** 2) + 1e-30))


def test_envelope_shapes():
    sw = sfx.render('swell')
    assert _rms(sw[-int(0.1 * SR):-int(0.001 * SR)]) > 4 * _rms(sw[:int(0.3 * SR)])   # schwillt an, bricht ab
    ri = sfx.render('riser')
    assert _rms(ri[-int(0.2 * SR):]) > 4 * _rms(ri[:int(0.3 * SR)])
    ga = sfx.render('gasp')
    assert _rms(ga[int(0.18 * SR):int(0.25 * SR)]) > 2 * _rms(ga[:int(0.07 * SR)])          # umgekehrte Hüllkurve
    st = sfx.render('stamp')
    assert np.abs(st[:int(0.018 * SR)]).max() < 1e-3                                        # 20 ms Stille vorab
    ks = sfx.render('keyword_slam')
    assert np.abs(ks[:int(0.018 * SR)]).max() < 1e-3
    hb = sfx.render('heartbeat')
    env = np.abs(hb.mean(axis=1))
    assert env[int(0.19 * SR):int(0.24 * SR)].max() > 3 * env[int(0.13 * SR):int(0.17 * SR)].max()   # zweiter Schlag
    wh = sfx.render('card_whoosh')
    assert _rms(wh[:int(0.06 * SR), 0]) > _rms(wh[:int(0.06 * SR), 1])                      # Pan von links ...
    assert _rms(wh[int(0.2 * SR):int(0.28 * SR), 1]) > _rms(wh[int(0.2 * SR):int(0.28 * SR), 0])   # ... nach rechts


def test_count_and_typewriter_are_tick_trains():
    c = sfx.render('count')
    env = np.abs(c.mean(axis=1))
    hits = [env[int((0.05 * k + 0.002) * SR):int((0.05 * k + 0.012) * SR)].max() for k in range(12)]
    gaps = [env[int((0.05 * k + 0.03) * SR):int((0.05 * k + 0.048) * SR)].max() for k in range(11)]
    assert min(hits) > 0.2 and max(gaps) < 0.05
    assert len(sfx.render('typewriter')) == len(sfx.render('tick')) == 576


# --- Dateien und Anbindung an mix -------------------------------------------------------------------------------------

def test_render_all_writes_wavs_and_catalog(tmp_path):
    res = sfx.render_all(str(tmp_path))
    assert res['count'] == len(sfx.catalog()) and res['key'] == 'D5'
    with open(tmp_path / 'catalog.json', encoding='utf-8') as fh:
        doc = json.load(fh)
    assert doc['count'] == res['count'] and doc['ladder'] == [74, 76, 79, 81, 86]
    for e in doc['sounds'][:5]:
        assert os.path.exists(tmp_path / e['file']) and e['peak_db'] <= -0.99 and e['file'] == e['id'] + '.wav'
    d, _ = wav.read(str(tmp_path / 'number_one.wav'), SR)
    assert d.shape == (int(round(1.6 * SR)), 2) and np.abs(d).max() <= PEAK + 1e-3


def test_mix_tunes_sfx_key(monkeypatch):
    class FakeMusic:
        @staticmethod
        def key(bed_id):
            return {'bed_e': 'E minor'}[bed_id]

    monkeypatch.setattr(mix, '_optional', lambda name: {'music': FakeMusic, 'sfx': sfx}[name])
    w = []
    assert mix._tune_sfx('bed_e', w) == 'E5' and sfx.key() == 76 and w == []
    assert mix._tune_sfx('bed_unknown', w) == 'D5' and len(w) == 1          # KeyError gemeldet, Standard bleibt
    assert mix._tune_sfx('placeholder', []) == 'D5'
    monkeypatch.setattr(mix, '_optional', lambda name: {'music': None, 'sfx': sfx}[name])
    assert mix._tune_sfx('heist_tiptoe', []) == 'E5'                       # ohne music.key: BED_KEYS
    assert mix._tune_sfx('none', []) == 'D5'

    class NoKeySfx:
        @staticmethod
        def render(sfx_id):
            return np.zeros((100, 2), np.float32)

    monkeypatch.setattr(mix, '_optional', lambda name: {'music': FakeMusic, 'sfx': NoKeySfx}[name])
    assert mix._tune_sfx('bed_e', []) is None                              # tolerant ohne set_key


def test_mix_sound_lookup_uses_real_sfx():
    cache, missing = {}, []
    for sid in ENGINE_IDS:
        snd, lvl, dur = mix._sound(sid, sfx, cache, missing)
        assert snd.shape[1] == 2 and lvl > -40 and dur > 0.005
    assert missing == []


def test_mix_tune_passes_bed_mode_for_chords(monkeypatch):
    """mix._tune_sfx reicht den Modus des Betts (music.BEDS) weiter: number_one bekommt die Terz des Betts."""
    class FakeMusic:
        BEDS = {'bed_e': {'mode': 'minor'}, 'bed_g': {'mode': 'major'}, 'bed_x': {}}

        @staticmethod
        def resolve(bed_id, default=None):
            return bed_id

        @staticmethod
        def key(bed_id):
            return {'bed_e': 76, 'bed_g': 67, 'bed_x': 74}[bed_id]

    def line_db(x, f):
        m = np.asarray(x[int(0.15 * SR):int(0.6 * SR)], np.float64).mean(axis=1)
        w = np.abs(np.fft.rfft(m * np.hanning(len(m)))) ** 2
        fr = np.fft.rfftfreq(len(m), 1.0 / SR)
        return 10.0 * np.log10(w[(fr > f * 0.985) & (fr < f * 1.015)].sum() + 1e-20)

    monkeypatch.setattr(mix, '_optional', lambda name: {'music': FakeMusic, 'sfx': sfx}[name])
    assert mix._tune_sfx('bed_e', []) == 'E5' and sfx._third() == 3
    minor = sfx.render('number_one')
    assert mix._tune_sfx('bed_x', []) == 'D5' and sfx._third() is None   # ohne Modus terzfrei
    sfx.set_key(76)                                                    # gleicher Grundton E5, kein Modus
    plain = sfx.render('number_one')
    g5 = S.midi_to_freq(79)                                            # kleine Terz G5 nur mit Modus
    assert line_db(minor, g5) > line_db(plain, g5) + 12
    assert mix._tune_sfx('bed_g', []) == 'G4' and sfx._third() == 4
    sfx.set_key(None)
