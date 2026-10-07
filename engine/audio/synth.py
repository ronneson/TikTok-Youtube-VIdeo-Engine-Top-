"""Prozedurale Klangsynthese: Oszillatoren, Hüllkurven, Filter, Effekte, Werkzeuge und kleine Instrumente.

Alles reines numpy/scipy ohne Python-Schleifen über einzelne Samples (höchstens blockweise).
Signale sind float32, Mono ``(n,)`` oder Stereo ``(n, 2)``; Zeiten in Sekunden; Abtastrate ``SR``
(48 kHz) aus ``engine.audio``. Frequenzen dürfen Zahlen oder Arrays (ein Wert je Sample) sein,
dann wird die Phase akkumuliert. Zufall (Rauschen, Supersaw-Phasen, Hall) ist über ``seed``
deterministisch.

Namenskonflikt der Vorgabe: ``pad(sig, seconds)`` (Stille anhängen) und ``pad(freq, dur)``
(Flächenklang) heißen hier ``pad_silence`` und ``pad_synth``; ``pad`` verteilt nach dem ersten
Argument (Array -> Stille, Zahl/Note -> Flächenklang).
"""
from __future__ import annotations
import functools
import re
import numpy as np
from scipy import signal as sps
from . import SR
from .wav import to_stereo, to_mono, silence  # noqa: F401  (werden mit angeboten)

TWO_PI = 2.0 * np.pi


# ---------------------------------------------------------------------------
# Grundhelfer
# ---------------------------------------------------------------------------

def seconds_to_samples(seconds: float) -> int:
    """Sekunden -> Anzahl Samples (gerundet, nie negativ)."""
    return max(0, int(round(float(seconds) * SR)))


def _f32(x) -> np.ndarray:
    """Beliebige Eingabe als float32-Array."""
    return np.asarray(x, dtype=np.float32)


def _time(n: int) -> np.ndarray:
    """Zeitachse in Sekunden für n Samples (float64)."""
    return np.arange(n, dtype=np.float64) / SR


def _control(x, n: int) -> np.ndarray:
    """Steuerverlauf als float64-Array der Länge n: Skalar wird ausgefüllt, andere Länge linear interpoliert."""
    if np.isscalar(x):
        return np.full(n, float(x))
    arr = np.asarray(x, dtype=np.float64).ravel()
    if len(arr) == n:
        return arr
    if len(arr) == 0:
        return np.zeros(n)
    if len(arr) == 1 or n <= 1:
        return np.full(n, float(arr[0]))
    return np.interp(np.linspace(0.0, 1.0, n), np.linspace(0.0, 1.0, len(arr)), arr)


def _phase(freq, n: int, phase: float = 0.0) -> np.ndarray:
    """Phase in Zyklen je Sample: Skalar -> lineare Rampe, Array -> Phasenakkumulation (cumsum)."""
    if n <= 0:
        return np.zeros(0)
    if np.isscalar(freq):
        ph = np.arange(n, dtype=np.float64) * (float(freq) / SR)
    else:
        f = _control(freq, n)
        ph = np.empty(n)
        ph[0] = 0.0
        np.cumsum(f[:-1] / SR, out=ph[1:])
    return ph + phase / TWO_PI


def _step(freq, n: int):
    """Phasenschritt je Sample (Zyklen), Skalar oder Array; für polyBLEP."""
    if np.isscalar(freq):
        return abs(float(freq)) / SR
    return np.abs(_control(freq, n)) / SR


def _blep(t: np.ndarray, dt) -> np.ndarray:
    """polyBLEP-Korrektur für eine Sprungstelle bei t=0 (t in Zyklen 0..1, dt Phasenschritt)."""
    dt = np.broadcast_to(np.maximum(dt, 1e-12), t.shape)
    out = np.zeros_like(t)
    m = t < dt
    x = t[m] / dt[m]
    out[m] = x + x - x * x - 1.0
    m = t > 1.0 - dt
    x = (t[m] - 1.0) / dt[m]
    out[m] = x * x + x + x + 1.0
    return out


def _as_2d(sig: np.ndarray) -> np.ndarray:
    """Mono -> (n, 1), Stereo bleibt (n, 2)."""
    return sig[:, None] if sig.ndim == 1 else sig


# ---------------------------------------------------------------------------
# Oszillatoren
# ---------------------------------------------------------------------------

def sine(freq, dur: float, phase: float = 0.0) -> np.ndarray:
    """Sinus. ``freq`` Zahl oder Array (je Sample), ``phase`` in Radiant."""
    n = seconds_to_samples(dur)
    return _f32(np.sin(TWO_PI * _phase(freq, n, phase)))


def saw(freq, dur: float, phase: float = 0.0) -> np.ndarray:
    """Sägezahn (steigend, -1..1) mit polyBLEP gegen Aliasing."""
    n = seconds_to_samples(dur)
    t = _phase(freq, n, phase) % 1.0
    return _f32(2.0 * t - 1.0 - _blep(t, _step(freq, n)))


def square(freq, dur: float, duty: float = 0.5, phase: float = 0.0) -> np.ndarray:
    """Rechteck mit Tastverhältnis ``duty`` (0.01..0.99), polyBLEP an beiden Flanken."""
    n = seconds_to_samples(dur)
    duty = float(np.clip(duty, 0.01, 0.99))
    t = _phase(freq, n, phase) % 1.0
    dt = _step(freq, n)
    out = np.where(t < duty, 1.0, -1.0)
    out += _blep(t, dt) - _blep((t - duty) % 1.0, dt)
    return _f32(out)


def tri(freq, dur: float, phase: float = 0.0) -> np.ndarray:
    """Dreieck (-1..1), beginnt bei 0 steigend."""
    n = seconds_to_samples(dur)
    t = _phase(freq, n, phase) % 1.0
    return _f32(1.0 - 4.0 * np.abs(((t + 0.25) % 1.0) - 0.5))


def noise(dur: float, kind: str = 'white', seed: int = 0) -> np.ndarray:
    """Rauschen: 'white' (gleichverteilt -1..1), 'pink' (1/f) oder 'brown' (1/f²), Spitze 1, deterministisch über ``seed``."""
    n = seconds_to_samples(dur)
    rng = np.random.default_rng(seed)
    if kind == 'white':
        return _f32(rng.uniform(-1.0, 1.0, n))
    if kind not in ('pink', 'brown'):
        raise ValueError(f"unbekannte Rauschart: {kind!r} (white, pink, brown)")
    if n < 2:
        return np.zeros(n, np.float32)
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.maximum(np.fft.rfftfreq(n, 1.0 / SR), 20.0)      # unter 20 Hz flach, kein Gleichanteil
    spec = spec / np.sqrt(f) if kind == 'pink' else spec / f
    spec[0] = 0.0
    out = np.fft.irfft(spec, n)
    return _f32(out / (np.max(np.abs(out)) + 1e-12))


def impulse_train(freq, dur: float, phase: float = 0.0) -> np.ndarray:
    """Impulsfolge: ein Sample mit Wert 1 je Periodenbeginn, sonst 0."""
    n = seconds_to_samples(dur)
    out = np.zeros(n, np.float32)
    if n == 0:
        return out
    cyc = np.floor(_phase(freq, n, phase) + 1e-9)
    prev = np.empty_like(cyc)
    prev[1:] = cyc[:-1]
    prev[0] = cyc[0] - 1.0 if abs((phase / TWO_PI) % 1.0) < 1e-9 else cyc[0]
    out[cyc > prev] = 1.0
    return out


def sweep(f0: float, f1: float, dur: float, curve: str = 'exp') -> np.ndarray:
    """Frequenzverlauf von f0 nach f1 über ``dur`` ('exp' = gleichmäßig in Oktaven, 'lin' = linear), als Array für die Oszillatoren."""
    n = seconds_to_samples(dur)
    x = np.linspace(0.0, 1.0, n)
    if curve == 'exp':
        f0, f1 = max(float(f0), 1e-3), max(float(f1), 1e-3)
        return _f32(f0 * (f1 / f0) ** x)
    if curve == 'lin':
        return _f32(float(f0) + (float(f1) - float(f0)) * x)
    raise ValueError(f"unbekannte Kurve: {curve!r} (exp, lin)")


def fm(carrier, mod, index, dur: float, phase: float = 0.0) -> np.ndarray:
    """Frequenzmodulation: Sinus-Träger, Sinus-Modulator, ``index`` = Modulationstiefe (Zahl oder Verlauf)."""
    n = seconds_to_samples(dur)
    phc = _phase(carrier, n, phase)
    phm = _phase(mod, n)
    idx = float(index) if np.isscalar(index) else _control(index, n)
    return _f32(np.sin(TWO_PI * phc + idx * np.sin(TWO_PI * phm)))


def supersaw(freq, dur: float, n: int = 5, detune: float = 0.01, seed: int = 0) -> np.ndarray:
    """n leicht verstimmte Sägezähne (±detune relativ, zufällige Startphasen) auf Spitze 1 normiert."""
    if seconds_to_samples(dur) == 0:
        return np.zeros(0, np.float32)
    n = max(1, int(n))
    rng = np.random.default_rng(seed)
    ratios = 1.0 + detune * np.linspace(-1.0, 1.0, n) if n > 1 else np.array([1.0])
    phases = rng.uniform(0.0, TWO_PI, n)
    base = freq if np.isscalar(freq) else np.asarray(freq, np.float64)
    acc = None
    for r, p in zip(ratios, phases):
        s = saw(base * r, dur, p).astype(np.float64)
        acc = s if acc is None else acc + s
    return _f32(acc / (np.max(np.abs(acc)) + 1e-12))


# ---------------------------------------------------------------------------
# Hüllkurven
# ---------------------------------------------------------------------------

def _decay_curve(k: int, curve: str) -> np.ndarray:
    """Abfall 1 -> 0 über k Samples (letztes Sample 0), linear oder exponentiell."""
    if k <= 0:
        return np.zeros(0)
    x = np.linspace(0.0, 1.0, k)
    if curve == 'exp':
        e5 = np.exp(-5.0)
        return (np.exp(-5.0 * x) - e5) / (1.0 - e5)
    return 1.0 - x


def adsr(dur: float, a: float = 0.01, d: float = 0.1, s: float = 0.7, r: float = 0.1, curve: str = 'lin') -> np.ndarray:
    """ADSR-Hüllkurve der Gesamtlänge ``dur`` (Release endet bei ``dur``). Zu lange Phasen werden proportional gestaucht."""
    n = seconds_to_samples(dur)
    na, nd, nr = seconds_to_samples(a), seconds_to_samples(d), seconds_to_samples(r)
    tot = na + nd + nr
    if tot > n:
        k = n / tot
        na, nd = int(na * k), int(nd * k)
        nr = n - na - nd
    ns = n - na - nd - nr
    s = float(np.clip(s, 0.0, 1.0))
    att = np.linspace(0.0, 1.0, na, endpoint=False)
    dec = s + (1.0 - s) * _decay_curve(nd + 1, curve)[:-1] if nd > 0 else np.zeros(0)
    sus = np.full(ns, s)
    rel = s * _decay_curve(nr, curve)
    return _f32(np.concatenate([att, dec, sus, rel]))


def env_exp(dur: float, tau: float) -> np.ndarray:
    """Exponentieller Abfall exp(-t/tau) über ``dur`` (endet nicht exakt bei 0: bei Bedarf ``fade`` anhängen)."""
    n = seconds_to_samples(dur)
    return _f32(np.exp(-_time(n) / max(float(tau), 1e-6)))


def env_lin(points) -> np.ndarray:
    """Stückweise lineare Hüllkurve aus Punkten [(t, wert), ...]; Länge = letzte Zeit."""
    pts = sorted((float(t), float(v)) for t, v in points)
    if not pts:
        return np.zeros(0, np.float32)
    ts = np.array([p[0] for p in pts])
    vs = np.array([p[1] for p in pts])
    n = seconds_to_samples(ts[-1])
    return _f32(np.interp(_time(n), ts, vs))


def apply(sig: np.ndarray, env: np.ndarray) -> np.ndarray:
    """Signal mit Hüllkurve multiplizieren (kürzere Hüllkurve wird mit 0 verlängert, längere abgeschnitten; Zahl = fester Faktor)."""
    sig = _f32(sig)
    env = _f32(env)
    n = len(sig)
    if env.ndim == 0:
        return _f32(sig * float(env))
    env = env.ravel()
    if len(env) < n:
        env = np.concatenate([env, np.zeros(n - len(env), np.float32)])
    else:
        env = env[:n]
    if sig.ndim == 2:
        env = env[:, None]
    return _f32(sig * env)


# ---------------------------------------------------------------------------
# Filter (scipy, SOS, kausal)
# ---------------------------------------------------------------------------

def _clamp_freq(f: float, lo: float = 10.0) -> float:
    """Frequenz in den stabilen Bereich (10 Hz .. 0.45·SR) bringen."""
    return float(np.clip(float(f), lo, SR * 0.45))


def _below_nyquist(f: float) -> bool:
    """True, wenn ein Teilton bei ``f`` Hz noch im Nutzband (< 0.45·SR) liegt; darüber würde er nur als Aliasing
    zurückfalten und wird von den additiven Instrumenten (marimba, bell, glass) weggelassen."""
    return float(f) < SR * 0.45


def _butter(kind: str, freq, order: int) -> np.ndarray:
    """Butterworth-Filter als SOS; ``freq`` Zahl oder (lo, hi). Entwürfe werden gecacht (Musikbetten filtern
    hunderte Noten mit denselben Grenzfrequenzen), jeder Aufruf bekommt eine eigene Kopie."""
    key = tuple(float(f) for f in np.atleast_1d(freq))
    return _butter_cached(kind, key, max(1, int(order))).copy()    # Kopie: sosfilt braucht beschreibbare Puffer


@functools.lru_cache(maxsize=256)
def _butter_cached(kind: str, freq: tuple, order: int) -> np.ndarray:
    f = freq[0] if len(freq) == 1 else list(freq)
    return sps.butter(order, f, kind, fs=SR, output='sos')


def _rbj(mode: str, fc: float, q: float) -> np.ndarray:
    """Biquad nach RBJ-Kochbuch als eine SOS-Zeile: 'lp', 'hp', 'bp' (0 dB Spitze) oder 'notch'."""
    w0 = TWO_PI * _clamp_freq(fc) / SR
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2.0 * max(float(q), 0.1))
    if mode == 'lp':
        b0, b1, b2 = (1.0 - cw) / 2.0, 1.0 - cw, (1.0 - cw) / 2.0
    elif mode == 'hp':
        b0, b1, b2 = (1.0 + cw) / 2.0, -(1.0 + cw), (1.0 + cw) / 2.0
    elif mode == 'bp':
        b0, b1, b2 = alpha, 0.0, -alpha
    elif mode == 'notch':
        b0, b1, b2 = 1.0, -2.0 * cw, 1.0
    else:
        raise ValueError(f"unbekannter Filtermodus: {mode!r} (lp, hp, bp, notch)")
    a0, a1, a2 = 1.0 + alpha, -2.0 * cw, 1.0 - alpha
    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])


def _filt(sos: np.ndarray, sig: np.ndarray) -> np.ndarray:
    """SOS-Filter kausal anwenden (Mono oder Stereo), Ergebnis float32."""
    sig = _f32(sig)
    if len(sig) == 0:
        return sig
    return _f32(sps.sosfilt(sos, sig.astype(np.float64), axis=0))


def lowpass(sig: np.ndarray, cutoff: float, order: int = 2, res: float = None) -> np.ndarray:
    """Tiefpass. ``res`` = Güte Q (None = Butterworth, 0.707 flach, 2..10 zunehmend resonant); bei ``order`` > 2 folgt ein Butterworth-Rest."""
    fc = _clamp_freq(cutoff)
    if res is None:
        sos = _butter('lowpass', fc, order)
    else:
        sos = _rbj('lp', fc, res)
        if order > 2:
            sos = np.vstack([sos, _butter('lowpass', fc, order - 2)])
    return _filt(sos, sig)


def highpass(sig: np.ndarray, cutoff: float, order: int = 2, res: float = None) -> np.ndarray:
    """Hochpass, Parameter wie ``lowpass``."""
    fc = _clamp_freq(cutoff)
    if res is None:
        sos = _butter('highpass', fc, order)
    else:
        sos = _rbj('hp', fc, res)
        if order > 2:
            sos = np.vstack([sos, _butter('highpass', fc, order - 2)])
    return _filt(sos, sig)


def bandpass(sig: np.ndarray, lo: float, hi: float, order: int = 2) -> np.ndarray:
    """Bandpass zwischen ``lo`` und ``hi`` Hz (Butterworth)."""
    lo, hi = _clamp_freq(lo), _clamp_freq(hi)
    if hi <= lo:
        lo, hi = min(lo, hi), max(lo, hi) + 1.0
    return _filt(_butter('bandpass', [lo, hi], order), sig)


def notch(sig: np.ndarray, freq: float, q: float = 30.0) -> np.ndarray:
    """Kerbfilter bei ``freq`` Hz mit Güte ``q`` (höher = schmaler)."""
    return _filt(_rbj('notch', freq, q), sig)


def svf(sig: np.ndarray, cutoff, q: float = 0.707, mode: str = 'lp', block: int = 128) -> np.ndarray:
    """Filter mit bewegter Grenzfrequenz (``cutoff`` Zahl oder Verlauf je Sample): blockweise Biquads mit übernommenem Zustand.

    ``mode`` 'lp', 'hp' oder 'bp'; ``q`` Güte; ``block`` Samples je Koeffizientensatz.
    """
    sig = _f32(sig)
    n = len(sig)
    if n == 0:
        return sig
    cut = _control(cutoff, n)
    x = _as_2d(sig).astype(np.float64)
    y = np.empty_like(x)
    zi = np.zeros((1, 2, x.shape[1]))
    block = max(8, int(block))
    for s in range(0, n, block):
        e = min(n, s + block)
        sos = _rbj(mode, float(cut[s:e].mean()), q)
        y[s:e], zi = sps.sosfilt(sos, x[s:e], axis=0, zi=zi)
    return _f32(y[:, 0] if sig.ndim == 1 else y)


# ---------------------------------------------------------------------------
# Effekte
# ---------------------------------------------------------------------------

def delay(sig: np.ndarray, time: float, feedback: float = 0.4, mix: float = 0.5, damp: float = None,
          pingpong: bool = False, max_taps: int = 64) -> np.ndarray:
    """Echo mit Rückkopplung. Das Ergebnis ist um die hörbaren Wiederholungen länger als die Eingabe.

    ``mix`` 0 = nur trocken, 1 = nur Echo; ``damp`` dämpft jede Wiederholung mit einem Tiefpass (Hz);
    ``pingpong`` wechselt die Wiederholungen zwischen links und rechts (Ergebnis dann Stereo).
    """
    sig = _f32(sig)
    n = len(sig)
    d = max(1, seconds_to_samples(time))
    fb = float(np.clip(feedback, 0.0, 0.98))
    taps = 1 if fb <= 0.0 else int(min(max_taps, np.floor(-3.0 / np.log10(fb)) + 1))
    taps = max(1, taps)
    x = _as_2d(sig)
    ch = 2 if (x.shape[1] == 2 or pingpong) else 1
    m = n + taps * d
    wet = np.zeros((m, ch), np.float64)
    dry = np.zeros((m, ch), np.float64)
    dry[:n] = x if x.shape[1] == ch else np.repeat(x, ch, axis=1)
    cur = x.astype(np.float64)
    mono_tap = cur.mean(axis=1) if pingpong else None
    for k in range(1, taps + 1):
        g = fb ** (k - 1)
        if damp:
            if pingpong:
                mono_tap = lowpass(mono_tap, damp, order=1).astype(np.float64)
            else:
                cur = lowpass(cur, damp, order=1).astype(np.float64)
        if pingpong:
            wet[k * d:k * d + n, (k - 1) % 2] += g * mono_tap
        else:
            wet[k * d:k * d + n] += g * cur
    mix = float(np.clip(mix, 0.0, 1.0))
    out = dry * (1.0 - mix) + wet * mix
    return _f32(out[:, 0] if ch == 1 else out)


_IR_CACHE = {}


def _reverb_ir(size: float, decay: float, predelay: float, seed: int) -> np.ndarray:
    """Synthetische Stereo-Impulsantwort (m, 2): frühe Reflexionen + exponentiell abklingendes, oben schneller sterbendes Rauschen."""
    key = (round(size, 4), round(decay, 4), round(predelay, 4), int(seed))
    ir = _IR_CACHE.get(key)
    if ir is not None:
        return ir
    size = float(np.clip(size, 0.05, 1.0))
    decay = max(0.05, float(decay))
    m = seconds_to_samples(decay)
    t = _time(m)
    rng = np.random.default_rng(seed)
    tau = decay / np.log(1000.0)                                  # -60 dB nach ``decay`` Sekunden
    nz = rng.standard_normal((m, 2))
    lo = sps.sosfilt(_butter('lowpass', 2500.0, 2), nz, axis=0)
    hi = nz - lo
    tail = lo * np.exp(-t / tau)[:, None] + hi * np.exp(-t / (tau * (0.3 + 0.3 * size)))[:, None]
    tail *= (1.0 - np.exp(-t / (0.004 + 0.04 * size)))[:, None]  # Dichte baut sich auf
    early = np.zeros((m, 2))
    k = 8
    times = np.sort(rng.uniform(0.003, 0.012 + 0.07 * size, k))
    gains = np.linspace(0.6, 0.2, k) * rng.uniform(0.7, 1.0, k)
    idx = np.minimum((times * SR).astype(int), m - 1)
    chan = np.arange(k) % 2
    np.add.at(early, (idx, chan), gains)
    np.add.at(early, (np.minimum(idx + 7, m - 1), 1 - chan), gains * 0.5)
    ir = early + tail * 0.9
    pre = seconds_to_samples(predelay)
    if pre > 0:
        ir = np.concatenate([np.zeros((pre, 2)), ir])
    ir /= np.sqrt(np.sum(ir * ir, axis=0, keepdims=True)) + 1e-12  # Einheitsenergie je Kanal
    _IR_CACHE[key] = ir
    return ir


def reverb(sig: np.ndarray, size: float = 0.5, decay: float = 2.0, mix: float = 0.3, predelay: float = 0.02,
           seed: int = 0, stereo: bool = True) -> np.ndarray:
    """Hall durch Faltung mit einer synthetischen Impulsantwort (Länge ``decay`` + ``predelay``), Ergebnis entsprechend länger.

    ``size`` 0..1 (Raumgröße: Reflexionsabstand und Helligkeit), ``decay`` = Nachhallzeit bis -60 dB, ``mix`` 0..1.
    Mono wird zu Stereo (``stereo=False`` behält Mono).
    """
    sig = _f32(sig)
    n = len(sig)
    ir = _reverb_ir(size, decay, predelay, seed)
    if sig.ndim == 1:
        x = to_stereo(sig) if stereo else sig[:, None]
    else:
        x = sig
    ch = x.shape[1]
    m = n + len(ir) - 1
    if n == 0:
        return np.zeros((0, 2), np.float32) if ch == 2 else np.zeros(0, np.float32)
    # oaconvolve (Overlap-Add) ist bei langen Signalen mit kurzer Impulsantwort (Musikbetten) deutlich schneller
    # als fftconvolve und numerisch gleich (Differenz ~1e-16); bei kurzen Signalen wählt es selbst die beste Methode.
    wet = np.stack([sps.oaconvolve(x[:, c].astype(np.float64), ir[:, c % 2]) for c in range(ch)], axis=1)
    dry = np.zeros((m, ch))
    dry[:n] = x
    mix = float(np.clip(mix, 0.0, 1.0))
    out = dry * (1.0 - mix) + wet * mix
    return _f32(out[:, 0] if ch == 1 else out)


def chorus(sig: np.ndarray, rate: float = 0.8, depth: float = 0.003, mix: float = 0.5, voices: int = 2,
           base: float = 0.015) -> np.ndarray:
    """Chorus: ``voices`` modulierte Verzögerungen (``base`` ± ``depth`` Sekunden, LFO ``rate`` Hz); bei Stereo je Kanal versetzt."""
    sig = _f32(sig)
    n = len(sig)
    if n == 0:
        return sig
    x = _as_2d(sig).astype(np.float64)
    i = np.arange(n, dtype=np.float64)
    t = i / SR
    voices = max(1, int(voices))
    wet = np.zeros_like(x)
    for c in range(x.shape[1]):
        for v in range(voices):
            ph = TWO_PI * (v / voices + 0.25 * c)
            d = (base + depth * 0.5 * (1.0 + np.sin(TWO_PI * rate * t + ph))) * SR
            wet[:, c] += np.interp(i - d, i, x[:, c], left=0.0)
    wet /= voices
    mix = float(np.clip(mix, 0.0, 1.0))
    out = x * (1.0 - mix) + wet * mix
    return _f32(out[:, 0] if sig.ndim == 1 else out)


def drive(sig: np.ndarray, amount: float = 0.5) -> np.ndarray:
    """Weiche Verzerrung (tanh). ``amount`` 0 = unverändert, 1 = stark; Spitze bleibt ≤ 1 für Eingaben ≤ 1."""
    sig = _f32(sig)
    amount = float(np.clip(amount, 0.0, 1.0))
    if amount <= 0.0:
        return sig.copy()
    g = 1.0 + 24.0 * amount
    return _f32(np.tanh(sig * g) / np.tanh(g))


def bitcrush(sig: np.ndarray, bits: int = 8, rate: float = None) -> np.ndarray:
    """Bit-Reduktion (``bits`` Auflösung) und optional Sample-Halten auf ``rate`` Hz."""
    sig = _f32(sig)
    q = 2.0 ** (int(np.clip(bits, 1, 24)) - 1)
    out = np.round(sig * q) / q
    n = len(sig)
    if rate and rate < SR and n:
        step = SR / float(rate)
        idx = np.minimum((np.floor(np.arange(n) / step) * step).astype(np.int64), n - 1)
        out = out[idx]
    return _f32(out)


def tremolo(sig: np.ndarray, rate: float = 5.0, depth: float = 0.5, shape: str = 'sine') -> np.ndarray:
    """Lautstärke-Zittern: Verstärkung schwankt zwischen 1 und 1-``depth`` mit ``rate`` Hz ('sine' oder 'square')."""
    sig = _f32(sig)
    lfo = 0.5 - 0.5 * np.cos(TWO_PI * rate * _time(len(sig)))
    if shape == 'square':
        lfo = (lfo > 0.5).astype(np.float64)
    return apply(sig, 1.0 - float(np.clip(depth, 0.0, 1.0)) * lfo)


def sidechain(sig: np.ndarray, env: np.ndarray, depth: float = 0.8) -> np.ndarray:
    """Pumpen: Signal um ``depth``·``env`` absenken (``env`` 0..1 je Sample, z. B. aus Kick-Hüllkurven; kürzer -> danach kein Ducking)."""
    sig = _f32(sig)
    e = _f32(env)
    if e.ndim == 2:
        e = e.mean(axis=1)
    n = len(sig)
    e = np.abs(e[:n])
    if len(e) < n:
        e = np.concatenate([e, np.zeros(n - len(e), np.float32)])
    gain = 1.0 - float(np.clip(depth, 0.0, 1.0)) * np.clip(e, 0.0, 1.0)
    return apply(sig, gain)


# ---------------------------------------------------------------------------
# Werkzeuge
# ---------------------------------------------------------------------------

def db(x: float) -> float:
    """Dezibel -> linearer Faktor."""
    return 10.0 ** (float(x) / 20.0)


def to_db(x) -> float:
    """Linearer Faktor (oder Array) -> Dezibel; 0 ergibt -240 dB."""
    out = 20.0 * np.log10(np.maximum(np.abs(np.asarray(x, np.float64)), 1e-12))
    return float(out) if out.ndim == 0 else out


def normalize(sig: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    """Auf Spitzenpegel ``peak_db`` dBFS skalieren (Stille bleibt Stille)."""
    sig = _f32(sig)
    p = float(np.max(np.abs(sig))) if sig.size else 0.0
    if p < 1e-9:
        return sig.copy()
    return _f32(sig * (db(peak_db) / p))


def fade(sig: np.ndarray, in_s: float = 0.005, out_s: float = 0.005) -> np.ndarray:
    """Ein-/Ausblenden (Halbkosinus) über ``in_s`` / ``out_s`` Sekunden; letztes Sample wird 0."""
    sig = _f32(sig)
    n = len(sig)
    g = np.ones(n, np.float64)
    ni = min(seconds_to_samples(in_s), n)
    no = min(seconds_to_samples(out_s), n)
    if ni > 0:
        g[:ni] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(ni) / ni)
    if no > 0:
        g[n - no:] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(no)[::-1] / no)
    return apply(sig, g)


def pan(mono: np.ndarray, pos: float = 0.0) -> np.ndarray:
    """Mono -> Stereo mit konstanter Leistung, ``pos`` -1 (links) .. 0 (Mitte) .. 1 (rechts). Stereo-Eingabe wird balanciert."""
    sig = _f32(mono)
    a = (float(np.clip(pos, -1.0, 1.0)) + 1.0) * np.pi / 4.0
    gl, gr = np.cos(a), np.sin(a)
    if sig.ndim == 2:
        return _f32(np.stack([sig[:, 0] * gl * np.sqrt(2.0), sig[:, 1] * gr * np.sqrt(2.0)], axis=1))
    return _f32(np.stack([sig * gl, sig * gr], axis=1))


def widen(stereo: np.ndarray, amount: float = 0.5) -> np.ndarray:
    """Stereobreite über Mitte/Seite: Seitensignal um (1 + ``amount``) verstärken (0 = unverändert, negativ = schmaler)."""
    st = to_stereo(_f32(stereo))
    mid = (st[:, 0] + st[:, 1]) * 0.5
    side = (st[:, 0] - st[:, 1]) * 0.5 * (1.0 + float(amount))
    return _f32(np.stack([mid + side, mid - side], axis=1))


def mixdown(items, tail: float = 0.0, peak_db: float = None) -> np.ndarray:
    """Spuren zusammenmischen: ``items`` = [(signal, offset_s=0, gain_db=0), ...] -> Stereo, Länge nach dem längsten Ende (+ ``tail``).

    Summiert ohne Begrenzung; ``peak_db`` (z. B. -1) normiert das Ergebnis zusätzlich auf diesen Spitzenpegel.
    """
    rows = []
    end = 0
    for it in items:
        if isinstance(it, np.ndarray):
            it = (it,)
        s = to_stereo(_f32(it[0]))
        off = int(round(float(it[1]) * SR)) if len(it) > 1 else 0   # darf negativ sein (Anfang wird abgeschnitten)
        gain = db(it[2]) if len(it) > 2 else 1.0
        if off < 0:
            s, off = s[-off:], 0
        rows.append((s, off, gain))
        end = max(end, off + len(s))
    out = np.zeros((end + seconds_to_samples(tail), 2), np.float64)
    for s, off, gain in rows:
        out[off:off + len(s)] += s * gain
    return normalize(out, peak_db) if peak_db is not None else _f32(out)


mix = mixdown


def pad_silence(sig: np.ndarray, seconds: float, before: float = 0.0) -> np.ndarray:
    """Stille anhängen (``seconds``) und optional voranstellen (``before``)."""
    sig = _f32(sig)
    na, nb = seconds_to_samples(seconds), seconds_to_samples(before)
    shape = (nb,) + sig.shape[1:]
    return np.concatenate([np.zeros(shape, np.float32), sig, np.zeros((na,) + sig.shape[1:], np.float32)])


def concat(*sigs, crossfade: float = 0.0) -> np.ndarray:
    """Signale hintereinander (Liste oder Einzelargumente), optional mit Überblendung ``crossfade`` Sekunden; Stereo gewinnt."""
    if len(sigs) == 1 and isinstance(sigs[0], (list, tuple)):
        sigs = sigs[0]
    arrs = [_f32(s) for s in sigs]
    if not arrs:
        return np.zeros(0, np.float32)
    if any(a.ndim == 2 for a in arrs):
        arrs = [to_stereo(a) for a in arrs]
    nx = seconds_to_samples(crossfade)
    out = arrs[0]
    for a in arrs[1:]:
        k = min(nx, len(out), len(a))
        if k > 0:
            x = np.arange(k, dtype=np.float64) / k
            fo = (0.5 + 0.5 * np.cos(np.pi * x))
            fi = 1.0 - fo
            if out.ndim == 2:
                fo, fi = fo[:, None], fi[:, None]
            head = out[:-k]
            cross = out[-k:] * fo + a[:k] * fi
            out = np.concatenate([head, _f32(cross), a[k:]])
        else:
            out = np.concatenate([out, a])
    return _f32(out)


_NOTE_RE = re.compile(r'^\s*([A-Ga-g])([#b]?)(-?\d+)\s*$')
_SEMIS = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def note_to_midi(note) -> float:
    """Notenname ('A4', 'C#3', 'Bb2') oder MIDI-Zahl -> MIDI-Nummer (A4 = 69)."""
    if isinstance(note, (int, float, np.integer, np.floating)):
        return float(note)
    m = _NOTE_RE.match(str(note))
    if not m:
        raise ValueError(f"ungültige Note: {note!r}")
    semi = _SEMIS[m.group(1).upper()] + {'#': 1, 'b': -1, '': 0}[m.group(2)]
    return float((int(m.group(3)) + 1) * 12 + semi)


def midi_to_freq(midi) -> float:
    """MIDI-Nummer -> Frequenz in Hz (69 = 440 Hz)."""
    return float(440.0 * 2.0 ** ((float(midi) - 69.0) / 12.0))


def note_to_freq(note) -> float:
    """'A4' oder MIDI-Nummer -> Frequenz in Hz."""
    return midi_to_freq(note_to_midi(note))


MODES = {
    'major': [0, 2, 4, 5, 7, 9, 11], 'minor': [0, 2, 3, 5, 7, 8, 10],
    'dorian': [0, 2, 3, 5, 7, 9, 10], 'phrygian': [0, 1, 3, 5, 7, 8, 10],
    'lydian': [0, 2, 4, 6, 7, 9, 11], 'mixolydian': [0, 2, 4, 5, 7, 9, 10],
    'locrian': [0, 1, 3, 5, 6, 8, 10], 'harmonic_minor': [0, 2, 3, 5, 7, 8, 11],
    'melodic_minor': [0, 2, 3, 5, 7, 9, 11], 'pentatonic_major': [0, 2, 4, 7, 9],
    'pentatonic_minor': [0, 3, 5, 7, 10], 'blues': [0, 3, 5, 6, 7, 10],
    'whole_tone': [0, 2, 4, 6, 8, 10], 'chromatic': list(range(12)),
}
MODES['ionian'], MODES['aeolian'], MODES['pentatonic'] = MODES['major'], MODES['minor'], MODES['pentatonic_major']


def scale(root, mode: str = 'major', octaves: int = 1) -> list:
    """Tonleiter als Liste von MIDI-Nummern ab ``root`` ('C4' oder MIDI) über ``octaves`` Oktaven (ohne Wiederholung des Grundtons)."""
    steps = MODES.get(mode)
    if steps is None:
        raise ValueError(f"unbekannter Modus: {mode!r} ({', '.join(sorted(MODES))})")
    base = int(round(note_to_midi(root)))
    return [base + 12 * o + s for o in range(max(1, int(octaves))) for s in steps]


# ---------------------------------------------------------------------------
# Rhythmus und Instrumente
# ---------------------------------------------------------------------------

def _finish(sig: np.ndarray, peak_db: float = -1.0, fade_in: float = 0.001, fade_out: float = 0.01) -> np.ndarray:
    """Instrument abschließen: NaN entfernen, Ränder ausblenden, auf ``peak_db`` normieren."""
    sig = np.nan_to_num(_f32(sig), nan=0.0, posinf=0.0, neginf=0.0)
    return normalize(fade(sig, fade_in, fade_out), peak_db)


def click(dur: float = 0.012, freq: float = 2000.0) -> np.ndarray:
    """Kurzer Klick (Sinusburst mit schnellem Abfall), z. B. für Metronom und Zähler."""
    return _finish(apply(sine(freq, dur), env_exp(dur, dur / 4.0)), fade_out=min(0.004, dur / 3.0))


def kick(dur: float = 0.5, freq: float = 50.0, punch: float = 1.0, seed: int = 0) -> np.ndarray:
    """Bassdrum: Sinus mit schnellem Tonhöhenfall auf ``freq``, kurzer Anschlagsklick, leichte Sättigung."""
    n = seconds_to_samples(dur)
    t = _time(n)
    f = freq * (1.0 + 6.0 * punch * np.exp(-t / 0.025))
    body = apply(sine(f, dur), env_exp(dur, dur / 6.0)).astype(np.float64)
    nc = min(n, seconds_to_samples(0.004))
    if nc > 0:
        clk = noise(0.004, 'white', seed)[:nc] * env_exp(0.004, 0.0012)[:nc]
        body[:nc] += 0.25 * clk
    return _finish(drive(body, 0.3))


def snare(dur: float = 0.25, tone: float = 200.0, seed: int = 0) -> np.ndarray:
    """Snare: kurzer Ton mit Tonhöhenfall plus bandbegrenztes Rauschen."""
    n = seconds_to_samples(dur)
    t = _time(n)
    body = apply(sine(tone * (1.0 + 0.5 * np.exp(-t / 0.02)), dur), env_exp(dur, 0.05))
    nz = apply(bandpass(noise(dur, 'white', seed), 800.0, 9000.0), env_exp(dur, dur / 5.0))
    return _finish(drive(0.6 * body + 0.9 * nz, 0.15))


def hat(dur: float = 0.08, open: bool = False, seed: int = 0) -> np.ndarray:
    """Hi-Hat: sechs unharmonische Rechtecke (808-Verhältnisse) plus Rauschen, hochpassgefiltert; ``open`` klingt länger aus."""
    base = 40.0
    metal = sum(square(base * r, dur).astype(np.float64) for r in (2.0, 3.0, 4.16, 5.43, 6.79, 8.21)) / 6.0
    metal = bandpass(metal, 5000.0, 14000.0, order=2)
    nz = highpass(noise(dur, 'white', seed), 7000.0, order=2)
    tau = dur / (2.5 if open else 4.0)
    return _finish(apply(0.7 * metal + 0.6 * nz, env_exp(dur, tau)))


def pluck(freq, dur: float, bright: float = 0.7, decay: float = None, seed: int = 0) -> np.ndarray:
    """Zupfsaite (Karplus-Strong, blockweise je Periode): ``bright`` 0..1 Anschlagshelligkeit, ``decay`` Sekunden bis -60 dB (Standard ``dur``)."""
    n = seconds_to_samples(dur)
    if n == 0:
        return np.zeros(0, np.float32)
    f = float(np.clip(note_to_freq(freq) if isinstance(freq, str) else float(freq), 20.0, 10000.0))
    period = SR / f
    N = int(np.floor(period - 0.5))
    frac = period - 0.5 - N                      # Feinstimmung über lineare Interpolation
    w0, w1, w2 = 0.5 * (1.0 - frac), 0.5, 0.5 * frac
    passes = max(1.0, float(decay if decay else dur) * f)
    g = 10.0 ** (-3.0 / passes)
    rng = np.random.default_rng(seed)
    exc = lowpass(rng.uniform(-1.0, 1.0, N), 800.0 + 12000.0 * float(np.clip(bright, 0.0, 1.0)), order=1).astype(np.float64)
    y = np.zeros(n + 2)
    y[2:2 + min(N, n)] = exc[:n]
    for s in range(N, n, N):
        e = min(n, s + N)
        m = e - s
        y[2 + s:2 + e] = g * (w0 * y[2 + s - N:2 + s - N + m] + w1 * y[1 + s - N:1 + s - N + m] + w2 * y[s - N:s - N + m])
    out = highpass(y[2:], 30.0, order=1)
    return _finish(out, fade_out=min(0.02, dur / 4.0))


def bell(freq, dur: float, ratio: float = 1.4) -> np.ndarray:
    """Glocke: FM mit unharmonischem Verhältnis und abklingendem Index plus zwei additive Teiltöne."""
    f = note_to_freq(freq) if isinstance(freq, str) else float(freq)
    n = seconds_to_samples(dur)
    t = _time(n)
    idx = 1.6 * np.exp(-t / (dur / 5.0))
    car = fm(f, f * ratio, idx, dur) * env_exp(dur, dur / 4.0)
    part = np.zeros(n)
    for r, g, k in ((2.76, 0.35, 7.0), (5.4, 0.2, 10.0)):
        if _below_nyquist(f * r):                 # Teiltöne über dem Nutzband würden nur zurückfalten (Aliasing)
            part += g * apply(sine(f * r, dur), env_exp(dur, dur / k))
    return _finish(car + part, fade_out=min(0.03, dur / 4.0))


def pad_synth(freq, dur: float, detune: float = 0.012, cutoff: float = 2200.0, seed: int = 0) -> np.ndarray:
    """Flächenklang: Supersaw + Suboktave -> Tiefpass -> Chorus -> langsame ADSR, Stereo, Spitze -3 dB."""
    f = note_to_freq(freq) if isinstance(freq, str) else float(freq)
    osc = supersaw(f, dur, n=7, detune=detune, seed=seed).astype(np.float64) + 0.25 * sine(f * 0.5, dur)
    st = lowpass(to_stereo(_f32(osc)), cutoff, order=2)
    st = chorus(st, rate=0.35, depth=0.004, mix=0.5, voices=2)
    env = adsr(dur, a=min(0.6, dur * 0.3), d=0.2, s=0.85, r=min(0.8, dur * 0.3), curve='exp')
    return _finish(apply(st, env), -3.0, fade_in=0.005, fade_out=0.02)


def pad(*args, **kw) -> np.ndarray:
    """Verteiler: ``pad(signal, seconds)`` hängt Stille an (``pad_silence``), ``pad(freq, dur)`` erzeugt den Flächenklang (``pad_synth``)."""
    first = args[0] if args else kw.get('sig', kw.get('freq'))
    if isinstance(first, np.ndarray) or 'sig' in kw:
        return pad_silence(*args, **kw)
    return pad_synth(*args, **kw)


def bass(freq, dur: float, cutoff: float = 2500.0, amount: float = 0.25) -> np.ndarray:
    """Synthbass: Sägezahn + Sinus, resonanter Tiefpass mit fallender Grenzfrequenz, Sättigung ``amount``, knackige ADSR."""
    f = note_to_freq(freq) if isinstance(freq, str) else float(freq)
    osc = 0.6 * saw(f, dur) + 0.4 * sine(f, dur)
    cut = f * 2.5 + float(cutoff) * env_exp(dur, 0.12).astype(np.float64)
    out = drive(svf(osc, cut, q=1.8, mode='lp'), amount)
    env = adsr(dur, 0.004, 0.08, 0.8, min(0.08, dur * 0.3))
    return _finish(apply(out, env))


# ---------------------------------------------------------------------------
# Ergänzungen für den Tonvorrat (sfx.py) und die Musikbetten: Mallets, Glas, Streuung, Bandmaschine
# ---------------------------------------------------------------------------

def varispeed(sig: np.ndarray, ratio, dur: float = None, start: float = 0.0) -> np.ndarray:
    """Wiedergabe mit veränderlicher Geschwindigkeit (Bandmaschine): ``ratio`` 1 = Original, 2 = doppelt so
    schnell und hoch, 0.5 = halb, 0 = steht, negativ = rückwärts.

    ``ratio`` Zahl (Ergebnis dann len/ratio lang) oder Verlauf je Ausgabesample (Länge = Ergebnislänge, sonst
    ``dur``); ``start`` Leseposition in Sekunden. Außerhalb der Quelle ist das Ergebnis 0, lineare Interpolation.
    """
    sig = _f32(sig)
    n = len(sig)
    if n == 0:
        return sig
    if np.isscalar(ratio):
        m = seconds_to_samples(dur) if dur else max(1, int(round(n / max(abs(float(ratio)), 1e-6))))
        r = np.full(m, float(ratio))
    else:
        m = seconds_to_samples(dur) if dur else len(np.asarray(ratio, np.float64).ravel())
        r = _control(ratio, m)
    pos = float(start) * SR + np.concatenate([[0.0], np.cumsum(r[:-1])])
    idx = np.arange(n, dtype=np.float64)
    x = _as_2d(sig).astype(np.float64)
    out = np.stack([np.interp(pos, idx, x[:, c], left=0.0, right=0.0) for c in range(x.shape[1])], axis=1)
    return _f32(out[:, 0] if sig.ndim == 1 else out)


def pan_curve(mono: np.ndarray, pos) -> np.ndarray:
    """Mono -> Stereo mit bewegter Position (``pos`` Verlauf -1..1 je Sample oder Zahl), konstante Leistung."""
    sig = _f32(mono)
    if sig.ndim == 2:
        sig = sig.mean(axis=1)
    a = (np.clip(_control(pos, len(sig)), -1.0, 1.0) + 1.0) * np.pi / 4.0
    return _f32(np.stack([sig * np.cos(a), sig * np.sin(a)], axis=1))


def burst(dur: float, lo: float = None, hi: float = None, tau: float = None, kind: str = 'white', seed: int = 0) -> np.ndarray:
    """Rauschstoß (Papier, Luft, Crack): Rauschen, optional bandbegrenzt (``lo``/``hi`` Hz, eines darf fehlen),
    mit exponentieller Hüllkurve ``tau`` (Standard dur/4), auf Spitze -1 dBFS."""
    n = seconds_to_samples(dur)
    if n == 0:
        return np.zeros(0, np.float32)
    nz = noise(dur, kind, seed)
    if lo and hi:
        nz = bandpass(nz, lo, hi)
    elif hi:
        nz = lowpass(nz, hi)
    elif lo:
        nz = highpass(nz, lo)
    return _finish(apply(nz, env_exp(dur, tau or dur / 4.0)), fade_in=min(0.0005, dur / 8.0), fade_out=min(0.004, dur / 4.0))


def shaker(n_pulses: int, dur: float, lo: float = 4000.0, hi: float = 6000.0, pulse: float = 0.008,
           tau: float = None, spread: float = 0.8, seed: int = 0) -> np.ndarray:
    """Shaker, Konfetti, Rascheln: ``n_pulses`` kurze Rauschimpulse (Bandpass ``lo``..``hi``, je ``pulse`` s) zu
    zufälligen Zeiten in ``dur``; mit ``tau`` fällt die Dichte exponentiell (Zeitkonstante s), sonst gleichmäßig.
    Stereo (n, 2), jeder Impuls zufällig innerhalb ±``spread`` gepannt, Spitze -1 dBFS."""
    n = seconds_to_samples(dur)
    out = np.zeros((n, 2), np.float64)
    if n == 0 or n_pulses <= 0:
        return _f32(out)
    rng = np.random.default_rng(seed)
    if tau:
        u = rng.uniform(0.0, 1.0, int(n_pulses))
        times = -float(tau) * np.log(1.0 - u * (1.0 - np.exp(-dur / float(tau))))
    else:
        times = rng.uniform(0.0, dur, int(n_pulses))
    k = max(4, seconds_to_samples(pulse))
    src = bandpass(noise(dur + pulse, 'white', seed + 1), lo, hi).astype(np.float64)
    env = env_exp(pulse, pulse / 3.0)[:k].astype(np.float64)
    ramp = min(k // 2, max(1, seconds_to_samples(0.0003)))
    env[:ramp] *= np.linspace(0.0, 1.0, ramp, endpoint=False)      # kein Sprung am Kornanfang
    gains = rng.uniform(0.45, 1.0, len(times))
    pans = rng.uniform(-abs(spread), abs(spread), len(times))
    for t0, g, p in zip(np.sort(times), gains, pans):
        s = int(t0 * SR)
        e = min(n, s + k)
        if e <= s:
            continue
        o = int(rng.integers(0, max(1, len(src) - k)))
        grain = src[o:o + e - s] * env[:e - s] * g
        a = (p + 1.0) * np.pi / 4.0
        out[s:e, 0] += grain * np.cos(a)
        out[s:e, 1] += grain * np.sin(a)
    return _finish(out, fade_in=0.0005, fade_out=min(0.01, dur / 4.0))


def marimba(freq, dur: float, decay: float = 0.26, partials=((3.0, -10.0), (4.0, -16.0)), bright: float = 0.5,
            seed: int = 0) -> np.ndarray:
    """Mallet-Ton (Marimba, Holzblock-Familie): Sinus-Grundton + Teiltöne ``partials`` [(Verhältnis, dB), ...],
    die schneller abklingen, plus Anschlagsklick (``bright`` 0..1); ``decay`` Sekunden bis -60 dB."""
    f = note_to_freq(freq) if isinstance(freq, str) else float(freq)
    n = seconds_to_samples(dur)
    if n == 0:
        return np.zeros(0, np.float32)
    tau = max(float(decay), 0.01) / np.log(1000.0)
    t = _time(n)
    out = np.sin(TWO_PI * f * t) * np.exp(-t / tau)
    for k, (ratio, g) in enumerate(partials):
        if _below_nyquist(f * ratio):
            out += db(g) * np.sin(TWO_PI * f * ratio * t) * np.exp(-t / (tau / (2.2 + 0.8 * k)))
    nc = min(n, seconds_to_samples(0.004))
    if nc > 0:
        b = float(np.clip(bright, 0.0, 1.0))
        clk = bandpass(noise(0.004, 'white', seed), 1500.0 + 3000.0 * b, 9000.0)[:nc] * env_exp(0.004, 0.0012)[:nc]
        out[:nc] += (0.12 + 0.3 * b) * clk
    return _finish(out, fade_in=0.0012, fade_out=min(0.02, dur / 4.0))


def kalimba(freq, dur: float, bright: float = 0.6, decay: float = None, seed: int = 0) -> np.ndarray:
    """Kalimba (Daumenklavier): Zupfsaite (``pluck``) + Sinus-Körper + kurzer metallischer Zungen-Teilton."""
    f = note_to_freq(freq) if isinstance(freq, str) else float(freq)
    n = seconds_to_samples(dur)
    if n == 0:
        return np.zeros(0, np.float32)
    t = _time(n)
    tau = max(float(decay or dur), 0.02) / np.log(1000.0)
    body = pluck(f, dur, bright=bright, decay=decay, seed=seed).astype(np.float64)
    tone = 0.6 * np.sin(TWO_PI * f * t) * np.exp(-t / tau)
    tine = 0.12 * np.sin(TWO_PI * f * 5.4 * t) * np.exp(-t / (tau * 0.12))
    return _finish(0.8 * body + tone + tine, fade_in=0.001, fade_out=min(0.02, dur / 4.0))


def glass(freq, dur: float, decay: float = 0.4, partials=((2.32, -9.0), (3.05, -15.0))) -> np.ndarray:
    """Glasglöckchen: Sinus mit unharmonischen Teiltönen ``partials`` [(Verhältnis, dB), ...], die halb so lang
    klingen, sehr kurzer Anschlag; ``decay`` Sekunden bis -60 dB."""
    f = note_to_freq(freq) if isinstance(freq, str) else float(freq)
    n = seconds_to_samples(dur)
    if n == 0:
        return np.zeros(0, np.float32)
    tau = max(float(decay), 0.01) / np.log(1000.0)
    t = _time(n)
    out = np.sin(TWO_PI * f * t) * np.exp(-t / tau)
    for ratio, g in partials:
        if _below_nyquist(f * ratio):             # 3.05 · 8 kHz läge über 24 kHz und faltete auf 17–22 kHz zurück
            out += db(g) * np.sin(TWO_PI * f * ratio * t) * np.exp(-t / (tau * 0.5))
    return _finish(out, fade_in=0.0004, fade_out=min(0.02, dur / 4.0))
