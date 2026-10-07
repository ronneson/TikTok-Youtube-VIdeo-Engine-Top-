"""Tests für engine/audio/synth.py: Längen, Wertebereiche, Stereo-Form, Effekt-Semantik, Determinismus, klickfreie Ränder."""
import numpy as np
import pytest

from engine.audio import SR
from engine.audio import synth as s


def _rms(x):
    x = np.asarray(x, np.float64)
    return float(np.sqrt(np.mean(x * x) + 1e-30))


def _peak_near(x, f, rel=0.02):
    """Stärkste Spektrallinie im Fenster ±30 % um f liegt innerhalb ``rel`` von f."""
    x = np.asarray(x, np.float64)
    if x.ndim == 2:
        x = x.mean(axis=1)
    w = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    fr = np.fft.rfftfreq(len(x), 1.0 / SR)
    m = (fr > f * 0.7) & (fr < f * 1.3)
    pf = fr[m][np.argmax(w[m])]
    return abs(pf / f - 1.0) < rel


def _tilt(x):
    """Energie 100..300 Hz geteilt durch 5..10 kHz (spektrale Neigung)."""
    w = np.abs(np.fft.rfft(np.asarray(x, np.float64))) ** 2
    f = np.fft.rfftfreq(len(x), 1.0 / SR)
    return w[(f > 100) & (f < 300)].mean() / w[(f > 5000) & (f < 10000)].mean()


# --------------------------------------------------------------------------- Oszillatoren

@pytest.mark.parametrize('fn', [s.sine, s.saw, s.square, s.tri])
def test_oscillator_basics(fn):
    x = fn(440.0, 0.25)
    assert x.shape == (12000,) and x.dtype == np.float32
    assert np.isfinite(x).all()
    assert np.abs(x).max() <= 1.0 + 1e-5
    assert np.abs(x).max() > 0.9
    assert abs(float(x.mean())) < 0.02
    assert _peak_near(x, 440.0)


def test_oscillator_frequency_array_and_sweep():
    n = s.seconds_to_samples(0.5)
    sw = s.sweep(100.0, 1000.0, 0.5)
    assert sw.shape == (n,) and sw.dtype == np.float32
    assert abs(sw[0] - 100.0) < 1e-3 and abs(sw[-1] - 1000.0) < 1e-2
    assert abs(sw[n // 2] - np.sqrt(100.0 * 1000.0)) < 2.0          # exponentiell: Mitte = geometrisches Mittel
    lin = s.sweep(100.0, 1000.0, 0.5, 'lin')
    assert abs(lin[n // 2] - 550.0) < 2.0
    with pytest.raises(ValueError):
        s.sweep(1, 2, 0.1, 'foo')
    assert s.sine(sw, 0.5).shape == (n,)
    assert s.saw(sw, 0.5).shape == (n,)
    # konstantes Array == Skalar
    assert np.allclose(s.sine(np.full(n, 440.0), 0.5), s.sine(440.0, 0.5), atol=1e-4)
    assert np.allclose(s.sine(440.0, 0.1, phase=np.pi / 2), np.cos(2 * np.pi * 440.0 * np.arange(4800) / SR), atol=1e-4)


def test_square_duty_and_impulse_train():
    assert abs(float(s.square(100.0, 1.0, duty=0.25).mean()) + 0.5) < 0.01
    it = s.impulse_train(100.0, 1.0)
    assert it.shape == (SR,) and it.sum() == 100 and it[0] == 1.0
    assert set(np.unique(it)) == {0.0, 1.0}
    assert s.impulse_train(100.0, 1.0, phase=np.pi)[0] == 0.0


def test_fm_and_supersaw():
    x = s.fm(200.0, 300.0, 2.0, 0.2)
    assert x.shape == (9600,) and np.abs(x).max() <= 1.0 + 1e-5
    xi = s.fm(200.0, 300.0, s.env_exp(0.2, 0.05) * 3.0, 0.2)       # Index als Verlauf
    assert xi.shape == (9600,) and np.isfinite(xi).all()
    a = s.supersaw(110.0, 0.2, n=5, detune=0.01, seed=1)
    b = s.supersaw(110.0, 0.2, n=5, detune=0.01, seed=1)
    c = s.supersaw(110.0, 0.2, n=5, detune=0.01, seed=2)
    assert np.array_equal(a, b) and not np.array_equal(a, c)
    assert abs(np.abs(a).max() - 1.0) < 1e-5
    assert _peak_near(a, 110.0, rel=0.03)
    assert s.supersaw(s.sweep(100, 200, 0.1), 0.1, n=3).shape == (4800,)


def test_noise_kinds_seed_and_spectrum():
    for kind in ('white', 'pink', 'brown'):
        x = s.noise(0.5, kind, seed=3)
        assert x.shape == (24000,) and x.dtype == np.float32
        assert np.isfinite(x).all() and np.abs(x).max() <= 1.0 + 1e-6
        assert np.array_equal(x, s.noise(0.5, kind, seed=3))
        assert not np.array_equal(x, s.noise(0.5, kind, seed=4))
    w, p, b = (_tilt(s.noise(1.0, k, seed=0)) for k in ('white', 'pink', 'brown'))
    assert 0.5 < w < 2.0 and p > 5.0 * w and b > 5.0 * p
    with pytest.raises(ValueError):
        s.noise(0.1, 'blue')


# --------------------------------------------------------------------------- Hüllkurven

def test_adsr_env_exp_env_lin_apply():
    e = s.adsr(0.5, a=0.05, d=0.1, s=0.6, r=0.1)
    assert e.shape == (24000,) and e.dtype == np.float32
    assert e[0] == 0.0 and e[-1] == 0.0 and abs(e.max() - 1.0) < 1e-5
    assert abs(e[12000] - 0.6) < 1e-5                                 # Sustain-Phase
    assert np.all(np.diff(e[:2400]) >= 0)                             # Attack steigt
    squeezed = s.adsr(0.1, a=0.2, d=0.2, s=0.5, r=0.2)                # zu lang -> gestaucht
    assert squeezed.shape == (4800,) and squeezed[-1] == 0.0 and squeezed.max() <= 1.0
    ex = s.adsr(0.3, 0.01, 0.1, 0.5, 0.1, curve='exp')
    assert ex.shape == (14400,) and ex[-1] == 0.0

    x = s.env_exp(1.0, 0.2)
    assert x[0] == 1.0 and np.all(np.diff(x) <= 0) and abs(x[9600] - np.exp(-1)) < 1e-3

    l = s.env_lin([(0.0, 0.0), (0.1, 1.0), (0.3, 0.0)])
    assert l.shape == (14400,) and abs(l[4800] - 1.0) < 1e-3 and abs(l[2400] - 0.5) < 1e-3

    sig = np.ones(1000, np.float32)
    out = s.apply(sig, np.full(500, 0.5, np.float32))                 # kürzere Hüllkurve -> Rest 0
    assert out.shape == (1000,) and out[0] == 0.5 and out[-1] == 0.0
    st = s.apply(np.ones((1000, 2), np.float32), np.linspace(0, 1, 2000))
    assert st.shape == (1000, 2) and st.dtype == np.float32


# --------------------------------------------------------------------------- Filter

def test_filters_attenuation_and_shapes():
    lo, hi = s.sine(100.0, 0.5), s.sine(8000.0, 0.5)
    assert _rms(s.lowpass(lo, 1000.0)) > 0.6 and _rms(s.lowpass(hi, 1000.0)) < 0.05
    assert _rms(s.highpass(hi, 1000.0)) > 0.6 and _rms(s.highpass(lo, 1000.0)) < 0.05
    mid = s.sine(1000.0, 0.5)
    assert _rms(s.bandpass(mid, 500.0, 2000.0)) > 0.6
    assert _rms(s.bandpass(lo, 500.0, 2000.0)) < 0.1 and _rms(s.bandpass(hi, 500.0, 2000.0)) < 0.1
    assert _rms(s.notch(mid, 1000.0, 30.0)[12000:]) < 0.01 and _rms(s.notch(lo, 1000.0, 30.0)) > 0.6
    res = s.lowpass(mid, 1000.0, res=6.0)
    assert np.abs(res[10000:]).max() > 3.0                            # Resonanz hebt die Grenzfrequenz an
    assert s.lowpass(mid, 1000.0, order=4, res=2.0).shape == mid.shape
    st = np.stack([lo, hi], axis=1)
    out = s.lowpass(st, 1000.0, order=4)
    assert out.shape == (24000, 2) and out.dtype == np.float32
    assert _rms(out[:, 0]) > 0.6 and _rms(out[:, 1]) < 0.01
    assert s.highpass(np.zeros(0, np.float32), 100.0).shape == (0,)


def test_svf_moving_cutoff():
    x = s.noise(0.5, 'white', seed=1)
    cut = s.sweep(200.0, 8000.0, 0.5)
    y = s.svf(x, cut, q=1.0)
    assert y.shape == x.shape and y.dtype == np.float32 and np.isfinite(y).all()
    # Anfang (tiefe Grenzfrequenz) hat weniger Höhen als Ende
    assert _rms(s.highpass(y[:8000], 4000.0)) < 0.3 * _rms(s.highpass(y[-8000:], 4000.0))
    yst = s.svf(np.stack([x, x], axis=1), 1000.0, q=0.707, mode='hp')
    assert yst.shape == (24000, 2) and np.allclose(yst[:, 0], yst[:, 1])
    bp = s.svf(s.sine(100.0, 0.3), 3000.0, q=2.0, mode='bp')
    assert _rms(bp[5000:]) < 0.1
    with pytest.raises(ValueError):
        s.svf(x, 1000.0, mode='xx')


# --------------------------------------------------------------------------- Effekte

def test_delay_mix_and_length():
    x = s.sine(440.0, 0.1)
    n, d = len(x), s.seconds_to_samples(0.05)
    wet = s.delay(x, 0.05, feedback=0.0, mix=1.0)
    assert wet.shape == (n + d,) and wet.dtype == np.float32
    assert np.abs(wet[:d]).max() == 0.0 and np.allclose(wet[d:d + n], x, atol=1e-6)
    dry = s.delay(x, 0.05, feedback=0.5, mix=0.0)
    assert np.allclose(dry[:n], x, atol=1e-6) and np.abs(dry[n:]).max() == 0.0
    fb = s.delay(x, 0.05, feedback=0.5, mix=1.0)
    taps = int(np.floor(-3.0 / np.log10(0.5)) + 1)
    assert fb.shape == (n + taps * d,)
    short = s.sine(440.0, 0.03)                                        # kürzer als die Verzögerung: Echos getrennt
    ns = len(short)
    fb = s.delay(short, 0.05, feedback=0.5, mix=1.0)
    assert _rms(fb[d:d + ns]) > _rms(fb[2 * d:2 * d + ns]) > _rms(fb[3 * d:3 * d + ns]) > 0
    assert abs(_rms(fb[2 * d:2 * d + ns]) / _rms(fb[d:d + ns]) - 0.5) < 0.02
    half = s.delay(x, 0.05, feedback=0.0, mix=0.5)
    assert np.allclose(half[:d], 0.5 * x[:d], atol=1e-6)                  # vor dem ersten Echo nur halbes Original
    pp = s.delay(short, 0.05, feedback=0.5, mix=1.0, pingpong=True)
    assert pp.shape == (ns + taps * d, 2)
    assert _rms(pp[d:d + ns, 0]) > 0.5 and _rms(pp[d:d + ns, 1]) < 1e-9  # 1. Echo links
    assert _rms(pp[2 * d:2 * d + ns, 1]) > 0.2 and _rms(pp[2 * d:2 * d + ns, 0]) < 1e-9
    hi = s.sine(8000.0, 0.1)
    damped = s.delay(hi, 0.05, feedback=0.5, mix=1.0, damp=1000.0)
    assert _rms(damped[d:d + n]) < 0.3 * _rms(s.delay(hi, 0.05, 0.5, 1.0)[d:d + n])
    st = s.delay(np.stack([x, x], axis=1), 0.05, 0.3, 0.5)
    assert st.shape[1] == 2


def test_reverb_shape_mix_and_determinism():
    x = s.sine(440.0, 0.1)
    n = len(x)
    rv = s.reverb(x, size=0.5, decay=1.0, mix=0.3, predelay=0.02)
    assert rv.ndim == 2 and rv.shape[1] == 2 and rv.dtype == np.float32
    assert rv.shape[0] == n + s.seconds_to_samples(1.0) + s.seconds_to_samples(0.02) - 1
    assert np.isfinite(rv).all()
    assert _rms(rv[n:]) > 0.0                                          # Nachhall nach dem Signalende
    assert not np.allclose(rv[:, 0], rv[:, 1])                        # dekorreliert
    dry = s.reverb(x, decay=1.0, mix=0.0)
    assert np.allclose(dry[:n, 0], x, atol=1e-6) and np.abs(dry[n:]).max() == 0.0
    wet = s.reverb(x, decay=1.0, mix=1.0, predelay=0.02)
    assert np.abs(wet[:s.seconds_to_samples(0.02)]).max() < 1e-6     # Vorverzögerung (FFT-Rauschen toleriert)
    assert np.array_equal(rv, s.reverb(x, size=0.5, decay=1.0, mix=0.3, predelay=0.02))
    assert not np.array_equal(rv, s.reverb(x, size=0.5, decay=1.0, mix=0.3, predelay=0.02, seed=7))
    mono = s.reverb(x, decay=0.5, stereo=False)
    assert mono.ndim == 1
    st = s.reverb(np.stack([x, x], axis=1), decay=0.5)
    assert st.shape[1] == 2


def test_chorus_drive_bitcrush_tremolo_sidechain():
    x = s.sine(440.0, 0.3)
    ch = s.chorus(x, rate=1.0, depth=0.003, mix=0.5)
    assert ch.shape == x.shape and ch.dtype == np.float32 and np.isfinite(ch).all()
    assert not np.allclose(ch, x) and np.allclose(s.chorus(x, mix=0.0), x, atol=1e-6)
    cst = s.chorus(np.stack([x, x], axis=1), rate=1.0)
    assert cst.shape == (14400, 2) and not np.allclose(cst[:, 0], cst[:, 1])

    dr = s.drive(x, 0.8)
    assert np.abs(dr).max() <= 1.0 + 1e-6 and _rms(dr) > _rms(x)        # lauter, aber nie über 1
    assert np.array_equal(s.drive(x, 0.0), x)

    bc = s.bitcrush(x, bits=3)
    assert len(np.unique(bc)) <= 2 ** 3 + 1
    held = s.bitcrush(s.noise(0.1, seed=1), bits=16, rate=8000.0)
    assert np.all(held[:6] == held[0]) and held[6] != held[0]
    assert s.bitcrush(np.stack([x, x], axis=1), 8, 12000.0).shape == (14400, 2)

    tr = s.tremolo(np.ones(SR, np.float32), rate=2.0, depth=0.5)
    assert abs(tr.min() - 0.5) < 1e-3 and abs(tr.max() - 1.0) < 1e-3 and tr[0] == 1.0
    sq = s.tremolo(np.ones(SR, np.float32), rate=2.0, depth=1.0, shape='square')
    assert set(np.unique(sq)) <= {0.0, 1.0}

    env = s.env_exp(0.3, 0.05)
    sc = s.sidechain(np.ones(SR // 2, np.float32), env, depth=0.8)
    assert abs(sc[0] - 0.2) < 1e-5 and sc[-1] == 1.0                   # ohne Hüllkurve kein Ducking
    assert s.sidechain(np.ones((100, 2), np.float32), np.ones(100), 1.0).max() == 0.0


# --------------------------------------------------------------------------- Werkzeuge

def test_db_normalize_fade():
    assert abs(s.db(0.0) - 1.0) < 1e-9 and abs(s.db(-6.0206) - 0.5) < 1e-4
    assert abs(s.to_db(0.5) + 6.0206) < 1e-3 and s.to_db(0.0) < -200
    assert np.allclose(s.to_db(np.array([1.0, 0.1])), [0.0, -20.0])
    x = s.sine(440.0, 0.1) * 0.1
    assert abs(np.abs(s.normalize(x, -1.0)).max() - s.db(-1.0)) < 1e-5
    assert np.abs(s.normalize(np.zeros(100, np.float32))).max() == 0.0
    f = s.fade(np.ones(4800, np.float32), 0.01, 0.02)
    assert f[0] == 0.0 and f[-1] == 0.0 and f[2400] == 1.0 and f.dtype == np.float32
    assert f[479] < 1.0 and f[480] == 1.0
    assert s.fade(np.ones((4800, 2), np.float32), 0.01, 0.01).shape == (4800, 2)
    assert s.fade(np.ones(10, np.float32), 1.0, 1.0)[-1] == 0.0       # länger als Signal: geklemmt


def test_pan_widen_mixdown():
    m = s.sine(440.0, 0.1)
    st = s.pan(m, 0.3)
    assert st.shape == (4800, 2) and st.dtype == np.float32
    assert np.allclose((st ** 2).sum(axis=1), m ** 2, atol=1e-5)        # konstante Leistung
    assert np.allclose(s.pan(m, -1.0)[:, 1], 0.0, atol=1e-6) and np.allclose(s.pan(m, 1.0)[:, 0], 0.0, atol=1e-6)
    assert np.allclose(s.pan(st, 0.0), st, atol=1e-5)                   # Stereo in Mitte unverändert
    w = s.widen(st, 1.0)
    assert w.shape == st.shape and _rms(w[:, 0] - w[:, 1]) > _rms(st[:, 0] - st[:, 1]) * 1.5
    assert np.allclose(s.widen(st, 0.0), st, atol=1e-6)
    assert np.allclose(s.widen(m, 1.0)[:, 0], s.widen(m, 1.0)[:, 1])  # Mono bleibt mittig
    mixed = s.mixdown([(m, 0.0, 0.0), (m, 0.05, -6.0206), (np.stack([m, m], axis=1), 0.2, 0.0)])
    assert mixed.shape == (s.seconds_to_samples(0.3), 2) and mixed.dtype == np.float32
    assert np.allclose(mixed[:2400, 0], m[:2400], atol=1e-6)
    assert np.allclose(mixed[2400:4800, 0], m[2400:] + 0.5 * m[:2400], atol=1e-4)
    assert np.allclose(mixed[4800:7200, 0], 0.5 * m[2400:], atol=1e-4)
    assert np.allclose(mixed[7200:9600], 0.0)
    assert s.mixdown([m], tail=0.1).shape == (9600, 2)
    assert abs(np.abs(s.mixdown([m, m, m], peak_db=-1.0)).max() - s.db(-1.0)) < 1e-5   # optionale Spitzennormierung
    assert s.mix is s.mixdown
    assert s.mixdown([(m, -0.05)]).shape == (2400, 2)                  # negativer Versatz schneidet den Anfang ab


def test_pad_concat_silence_samples():
    m = s.sine(440.0, 0.1)
    assert s.pad_silence(m, 0.1).shape == (9600,) and s.pad_silence(m, 0.1, before=0.05).shape == (12000,)
    assert np.abs(s.pad_silence(m, 0.1)[4800:]).max() == 0.0
    assert s.pad(m, 0.1).shape == (9600,)                               # Verteiler: Array -> Stille
    assert s.pad(110.0, 0.2).shape == (9600, 2)                         # Verteiler: Zahl -> Flächenklang
    assert s.pad(np.stack([m, m], axis=1), 0.1).shape == (9600, 2)
    c = s.concat(m, m)
    assert c.shape == (9600,) and np.array_equal(c[4800:], m)
    assert s.concat([m, np.stack([m, m], axis=1)]).shape == (9600, 2)   # Stereo gewinnt
    cf = s.concat(m, m, crossfade=0.02)
    assert cf.shape == (9600 - 960,)
    assert s.concat([]).shape == (0,)
    assert s.silence(0.5).shape == (24000, 2) and s.silence(0.5, stereo=False).shape == (24000,)
    assert s.seconds_to_samples(1.0) == SR and s.seconds_to_samples(-1.0) == 0 and s.seconds_to_samples(0.6 / SR) == 1


def test_notes_and_scales():
    assert abs(s.note_to_freq('A4') - 440.0) < 1e-9 and abs(s.note_to_freq(69) - 440.0) < 1e-9
    assert abs(s.note_to_freq('C4') - 261.6256) < 1e-3 and abs(s.midi_to_freq(60) - 261.6256) < 1e-3
    assert s.note_to_midi('C#4') == 61 and s.note_to_midi('Db4') == 61 and s.note_to_midi('Bb2') == 46
    assert s.note_to_midi('a4') == 69 and s.note_to_midi('C-1') == 0
    with pytest.raises(ValueError):
        s.note_to_freq('H4')
    assert s.scale('C4', 'major') == [60, 62, 64, 65, 67, 69, 71]
    assert s.scale(57, 'minor') == [57, 59, 60, 62, 64, 65, 67]
    assert s.scale('C4', 'pentatonic_minor', octaves=2) == [60, 63, 65, 67, 70, 72, 75, 77, 79, 82]
    assert len(s.scale('C4', 'chromatic')) == 12 and s.scale('C4', 'aeolian') == s.scale('C4', 'minor')
    with pytest.raises(ValueError):
        s.scale('C4', 'klingon')


# --------------------------------------------------------------------------- Instrumente

INSTRUMENTS = [
    ('click', lambda: s.click(), 0.012, 1),
    ('kick', lambda: s.kick(0.4), 0.4, 1),
    ('snare', lambda: s.snare(0.2), 0.2, 1),
    ('hat', lambda: s.hat(0.08), 0.08, 1),
    ('hat_open', lambda: s.hat(0.3, open=True), 0.3, 1),
    ('pluck', lambda: s.pluck(220.0, 0.5), 0.5, 1),
    ('bell', lambda: s.bell(880.0, 0.6), 0.6, 1),
    ('pad_synth', lambda: s.pad_synth(110.0, 0.8), 0.8, 2),
    ('bass', lambda: s.bass(55.0, 0.3), 0.3, 1),
]


@pytest.mark.parametrize('name,fn,dur,ch', INSTRUMENTS, ids=[i[0] for i in INSTRUMENTS])
def test_instrument_quality(name, fn, dur, ch):
    x = fn()
    n = s.seconds_to_samples(dur)
    assert x.dtype == np.float32 and np.isfinite(x).all()
    assert x.shape == ((n,) if ch == 1 else (n, 2))
    peak = float(np.abs(x).max())
    assert peak <= s.db(-1.0) + 1e-3 and peak > 0.5                     # normiert, nie übersteuert
    edge = np.abs(x[[0, -1]]).max()
    assert edge < 0.01                                                   # keine Clicks an den Rändern
    assert np.array_equal(x, fn())                                       # deterministisch


def test_instrument_pitch_and_seed():
    for f in (55.0, 220.0, 440.0, 1000.0):
        assert _peak_near(s.pluck(f, 1.0), f, rel=0.02), f
    assert _peak_near(s.bass(110.0, 0.5), 110.0, rel=0.02)
    assert _peak_near(s.pad_synth(220.0, 0.6), 220.0, rel=0.03)
    assert _peak_near(s.pluck('A3', 0.5), 220.0, rel=0.02)              # Notenname erlaubt
    assert not np.array_equal(s.snare(0.2, seed=0), s.snare(0.2, seed=1))
    assert not np.array_equal(s.pluck(220.0, 0.3, seed=0), s.pluck(220.0, 0.3, seed=1))
    assert _rms(s.kick(0.4)[-2000:]) < 0.02                              # klingt aus
    assert _rms(s.hat(0.3, open=True)[7000:9000]) > _rms(s.hat(0.3, open=False)[7000:9000])


# --------------------------------------------------------------------------- Randfälle (Review)

def test_apply_scalar_and_zero_length_edge_cases():
    """apply mit Zahl = fester Faktor (nicht nur das erste Sample); Länge 0 darf nirgends abstürzen."""
    out = s.apply(np.ones(100, np.float32), 0.5)
    assert out.shape == (100,) and np.allclose(out, 0.5)
    assert np.allclose(s.apply(np.ones((10, 2), np.float32), np.float32(2.0)), 2.0)
    assert s.supersaw(110.0, 0.0).shape == (0,)
    assert s.pad_synth(110.0, 0.0).shape == (0, 2)
    for fn in (s.click, s.kick, s.snare, s.hat):
        assert fn(0.0).shape == (0,)
    for fn in (s.pluck, s.bell, s.bass):
        assert fn(220.0, 0.0).shape == (0,)
    for osc in (s.sine, s.saw, s.square, s.tri):
        assert osc(440.0, 0.0).shape == (0,) and osc(440.0, 1 / SR).shape == (1,)
    assert s.delay(np.zeros(0, np.float32), 0.1).shape[0] >= 0
    assert s.reverb(np.zeros(0, np.float32), decay=0.1).shape == (0, 2)


# --------------------------------------------------------------------------- Ergänzungen für sfx/music

def test_varispeed_scalar_and_curve():
    x = s.sine(440.0, 0.5)
    y = s.varispeed(x, 2.0)
    assert y.shape == (12000,) and y.dtype == np.float32 and _peak_near(y, 880.0)
    z = s.varispeed(x, 0.5)
    assert z.shape == (48000,) and _peak_near(z, 220.0)
    stop = s.varispeed(x, np.linspace(1.0, 0.0, 24000))         # Band läuft aus: liest nur die erste Hälfte
    assert stop.shape == (24000,) and np.isfinite(stop).all()
    st = s.varispeed(s.to_stereo(x), -1.0, dur=0.1, start=0.2)   # rückwärts ab 0.2 s, Stereo bleibt Stereo
    assert st.shape == (4800, 2) and np.abs(st).max() > 0.9
    assert s.varispeed(np.zeros(0, np.float32), 2.0).shape == (0,)


def test_pan_curve_moves_left_to_right():
    x = s.pan_curve(np.ones(4800, np.float32), np.linspace(-1.0, 1.0, 4800))
    assert x.shape == (4800, 2)
    assert x[0, 0] > 0.99 and abs(x[0, 1]) < 1e-3 and x[-1, 1] > 0.99 and abs(x[-1, 0]) < 1e-3
    assert abs(x[2400, 0] - x[2400, 1]) < 0.01                   # Mitte: gleich laut
    assert s.pan_curve(np.ones((100, 2), np.float32), 0.0).shape == (100, 2)


def test_burst_shaker_bands_and_shapes():
    b = s.burst(0.05, 1000.0, 3000.0, 0.01, seed=3)
    assert b.shape == (2400,) and np.abs(b).max() <= 1.0 and np.abs(b[-1]) < 1e-3
    w = np.abs(np.fft.rfft(b.astype(np.float64)))
    f = np.fft.rfftfreq(len(b), 1.0 / SR)
    assert w[(f > 1000) & (f < 3000)].mean() > 10 * w[(f > 8000)].mean()
    assert s.burst(0.02, None, 500.0).shape == (960,) and s.burst(0.02, 5000.0, None).shape == (960,)
    sh = s.shaker(40, 0.5, tau=0.15, seed=1)
    assert sh.shape == (24000, 2) and np.isfinite(sh).all() and abs(np.abs(sh).max() - 10 ** (-1 / 20)) < 1e-3
    env = np.abs(sh).mean(axis=1)
    assert env[:12000].sum() > 2 * env[12000:].sum()               # Dichte fällt
    assert not np.array_equal(sh, s.shaker(40, 0.5, tau=0.15, seed=2))
    assert s.shaker(0, 0.1).shape == (4800, 2)


@pytest.mark.parametrize('fn, dur', [(s.marimba, 0.4), (s.kalimba, 0.5), (s.glass, 0.4)])
def test_mallets_pitch_decay_and_edges(fn, dur):
    x = fn('A5', dur)
    assert x.shape == (s.seconds_to_samples(dur),) and x.dtype == np.float32 and np.isfinite(x).all()
    assert _peak_near(x[: int(0.15 * SR)], 880.0)
    assert np.abs(x[-1]) < 1e-3 and abs(float(x.mean())) < 0.01
    assert _rms(x[: int(0.05 * SR)]) > 3 * _rms(x[-int(0.05 * SR):])  # klingt ab
    assert fn(440.0, 0.0).shape == (0,)


def _band_peak(x, lo, hi):
    """Stärkste Linie zwischen lo und hi Hz (Hann-Fenster über die ersten 60 ms, wo Teiltöne noch klingen)."""
    m = np.asarray(x[: int(0.06 * SR)], np.float64)
    w = np.abs(np.fft.rfft(m * np.hanning(len(m))))
    f = np.fft.rfftfreq(len(m), 1.0 / SR)
    return w[(f > lo) & (f < hi)].max()


def test_marimba_partials_and_glass_inharmonic():
    m = s.marimba(440.0, 0.3, partials=((3.0, -6.0),))
    assert _band_peak(m, 1280, 1360) > 0.2 * _band_peak(m, 400, 480)                 # 3. Teilton -6 dB beim Anschlag
    assert _band_peak(s.marimba(440.0, 0.3, partials=()), 1280, 1360) < 0.05 * _band_peak(m, 400, 480)
    g = s.glass(2000.0, 0.3, partials=((2.32, -6.0),))
    assert _band_peak(g, 4580, 4700) > 0.2 * _band_peak(g, 1940, 2060)               # unharmonischer Teilton 2.32


def test_additive_partials_stop_below_nyquist():
    """Teiltöne über 0.45·SR werden weggelassen (sonst Aliasing: 3.05 · 10 kHz = 30.5 kHz fiele auf 17.5 kHz zurück)."""
    def band_db(x, lo, hi):
        w = np.abs(np.fft.rfft(np.asarray(x, np.float64))) ** 2
        fr = np.fft.rfftfreq(len(x), 1.0 / SR)
        return 10.0 * np.log10(w[(fr >= lo) & (fr < hi)].sum() + 1e-20)
    g = s.glass(10000.0, 0.3)                                   # beide Teiltöne (23.2 / 30.5 kHz) entfallen
    assert _peak_near(g, 10000.0)
    main = band_db(g, 9500, 10500)                              # 30.5 kHz fiele auf 17.5 kHz, 23.2 kHz läge direkt da
    assert band_db(g, 17000, 18000) < main - 50 and band_db(g, 22700, 23700) < main - 50
    g9 = s.glass(9000.0, 0.3)                                   # 2.32 · 9 kHz = 20.9 kHz bleibt, 27.5 kHz entfällt
    assert band_db(g9, 20000, 21500) > band_db(g9, 8500, 9500) - 15
    assert band_db(g9, 17000, 18000) < band_db(g9, 8500, 9500) - 60
    b = s.bell(5000.0, 0.5)                                     # 5.4 · 5 kHz = 27 kHz entfällt (sonst 21 kHz)
    assert band_db(b, 20500, 21500) < band_db(b, 4800, 5200) - 50
    m = s.marimba(6000.0, 0.2)                                  # 4 · 6 kHz = 24 kHz entfällt, 3 · 6 kHz = 18 kHz bleibt
    assert band_db(m, 17800, 18200) > band_db(m, 5800, 6200) - 30
    # unterhalb der Schwelle unverändert: alle Teiltöne vorhanden
    g2 = s.glass(2000.0, 0.3)
    assert band_db(g2, 4500, 4800) > band_db(g2, 1900, 2100) - 20 and band_db(g2, 6000, 6200) > band_db(g2, 1900, 2100) - 30
