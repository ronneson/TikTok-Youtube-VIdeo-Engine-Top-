"""Tonvorrat „Holz, Glas und Papier“ (STIL.md 6): alle Töne der Engine, prozedural aus ``engine.audio.synth``.

Charakter: warm, trocken, nah. Mallets (Sinus + 3./4. Teilton), gezupfte Saiten, Papier-Klicks und Pops aus
gefiltertem Rauschen, Glasglöckchen (hohe Sinus-Cluster) für alles Glänzende. Hall nur als Tupfer (decay ≤ 1.6 s,
Respekt-Modus). Jeder Ton ist geschichtet (Transient + Körper + Schweif), deterministisch über ``seed``.

API
    SOUNDS = {id: fn}                       Bausteine (fn(seed=0, **kw) -> Mono oder Stereo, roh)
    render(id, seed=0) -> (n, 2) float32    fertiger Ton: exakte Länge, ohne Gleichanteil, weiche Ränder,
                                            Spitze PEAK_DB (-1 dBFS); gecacht je (id, seed, Tonart)
    catalog() -> [{'id', 'use', 'dur', 'gain_db', 'group'}]
    render_all(out_dir) -> dict             schreibt <id>.wav und catalog.json
    has(id) -> bool                         auch für Varianten wie 'card_hit_3' / 'card_hit#3'
    set_key(root, mode=None) -> [midi]      Rang-Leiter auf den Grundton des Musikbetts stimmen (Standard D);
                                            mix.build ruft sfx.set_key(music.key(bed_id)) vor den Cues
    key() -> midi, ladder(total) -> [midi], rank_note(rank, total) -> midi, motif() -> [midi]

Rang-Leiter (STIL.md 6.1): Stufen 1-2-4-5-8 über dem Grundton (#5 = Grundton … #1 = Oktave), Oktave 5 für
Grundtöne bis F, sonst Oktave 4; Top 10: #10 … #6 eine Oktave tiefer. Markenmotiv „Odd-Ding“: 1-5-8, kurz, kurz,
lang (0.18 / 0.18 / 0.60 s), nur in ``outro_chime`` und ``end_sting``.

Pegel: ``gain_db`` im Katalog ist der Cue-Pegel relativ zu ``mix.sfx_db`` (Akzente lauter, Ticks leiser); die
Signale selbst sind auf PEAK_DB normiert, ``mix.py`` setzt den Zielpegel je Cue über das RMS des Tons.
"""
from __future__ import annotations
import json
import os
import re
import numpy as np
from . import SR, wav
from . import synth as S
from .synth import seconds_to_samples as _n

PEAK_DB = -1.0                      # Spitzenpegel jedes gerenderten Tons
DEFAULT_KEY = 'D'                   # Grundton ohne Musikbett (cabinet_swing, D-Dorisch)
DEGREES = (1, 2, 4, 5, 8)           # Rang-Leiter: #5 .. #1
MOTIF = (1, 5, 8)                   # Markenmotiv Odd-Ding
MOTIF_RHYTHM = (0.18, 0.18, 0.60)
_DEGREE_SEMIS = {1: 0, 2: 2, 3: None, 4: 5, 5: 7, 6: 9, 7: None, 8: 12}
_THIRDS = {'major': 4, 'ionian': 4, 'lydian': 4, 'mixolydian': 4, 'minor': 3, 'aeolian': 3, 'dorian': 3,
           'phrygian': 3, 'harmonic_minor': 3, 'melodic_minor': 3, 'dorisch': 3, 'moll': 3, 'dur': 4, 'lydisch': 4}
# Grundtöne der Betten aus design/sounds.json: Rückfall, wenn music.key fehlt (set_key('heist_tiptoe') geht auch)
BED_KEYS = {'cabinet_swing': 'D dorian', 'cabinet_swing_pulse': 'D dorian', 'heist_tiptoe': 'E minor',
            'cave_drip': 'A minor', 'safari_bounce': 'G major', 'orbit_glow': 'F# lydian',
            'orbit_glow_ocean': 'F# lydian', 'parlour_waltz': 'Bb major'}

SOUNDS = {}         # id -> Baustein
_META = {}          # id -> {'use', 'dur', 'gain_db', 'group', 'fade_in', 'fade_out'}
_CACHE = {}
_KEY = {'root': 74, 'mode': 'dorian'}   # D5
_VARIANT_RE = re.compile(r'^(card_hit)[_#](\d+)$')


# ----------------------------------------------------------------------------------------------------------------
# Tonart und Leiter
# ----------------------------------------------------------------------------------------------------------------

def set_key(root=None, mode: str = None, octave: int = None) -> list:
    """Grundton der Rang-Leiter setzen und den Cache leeren. Gibt die Leiter (MIDI, #5 … #1) zurück.

    ``root``: Notenname ('D', 'Bb', 'F#'), Name mit Oktave ('E4', bleibt in dieser Oktave), MIDI-Zahl, 'E minor'
    (Modus im selben String), eine Bett-ID aus BED_KEYS oder None (= DEFAULT_KEY). Ohne ausdrückliche Oktave gilt
    STIL.md 6.1: Grundtöne bis F in Oktave 5, sonst Oktave 4. ``mode`` bestimmt nur, ob Akkorde eine Terz bekommen
    (number_one, record_stop); ohne Modus bleiben sie terzfrei.
    """
    if root is None or root == '':
        root = DEFAULT_KEY
    if isinstance(root, str) and root.strip() in BED_KEYS:
        root = BED_KEYS[root.strip()]
    explicit_octave = octave
    if isinstance(root, str):
        parts = root.strip().replace('-', ' ').split()
        if len(parts) > 1 and mode is None:
            mode = parts[1].lower()
        name = parts[0] if parts else DEFAULT_KEY
        if re.search(r'\d', name):
            midi = int(round(S.note_to_midi(name)))
            if explicit_octave is None:
                explicit_octave = midi // 12 - 1
        else:
            midi = int(round(S.note_to_midi(name + '4')))
    else:
        midi = int(round(float(root)))
    pc = midi % 12
    if explicit_octave is None:
        explicit_octave = 5 if pc <= 5 else 4
    _KEY['root'] = (int(explicit_octave) + 1) * 12 + pc
    _KEY['mode'] = str(mode).lower() if mode else None
    _CACHE.clear()
    return ladder()


def key() -> int:
    """Aktueller Grundton der Leiter als MIDI-Nummer (Standard D5 = 74)."""
    return int(_KEY['root'])


def key_name() -> str:
    """Aktueller Grundton als Notenname, z. B. 'D5'."""
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    m = key()
    return f"{names[m % 12]}{m // 12 - 1}"


def ladder(total: int = 5) -> list:
    """Rang-Leiter als MIDI-Liste von #total bis #1 (aufsteigend); ab Top 10 liegen #10 … #6 eine Oktave tiefer."""
    total = max(1, int(total))
    return [rank_note(r, total) for r in range(total, 0, -1)]


def rank_note(rank: int, total: int = None) -> int:
    """Leiterton eines Rangs (MIDI): #5 Grundton, #4 Sekunde, #3 Quarte, #2 Quinte, #1 Oktave; #6 … #10 eine
    Oktave tiefer usw. ``total`` ist nur zur Dokumentation (die Leiter hängt nur vom Rang ab)."""
    r = max(1, int(rank))
    idx = (r - 1) % 5                   # 0 = Oktave (#1) … 4 = Grundton (#5)
    shift = -12 * ((r - 1) // 5)
    return key() + _DEGREE_SEMIS[DEGREES[4 - idx]] + shift


def motif() -> list:
    """Markenmotiv Odd-Ding als MIDI-Liste (Stufen 1, 5, 8)."""
    return [key() + _DEGREE_SEMIS[d] for d in MOTIF]


def _third():
    """Terz (Halbtöne) des gesetzten Modus oder None (terzfrei)."""
    return _THIRDS.get(_KEY['mode'] or '', None)


def _hz(midi) -> float:
    return S.midi_to_freq(midi)


# ----------------------------------------------------------------------------------------------------------------
# Registrierung, Rendern, Katalog
# ----------------------------------------------------------------------------------------------------------------

def sound(sid: str, use: str, dur: float, gain_db: float, group: str = 'general', fade_in: float = 0.001,
          fade_out: float = 0.008):
    """Dekorator: Baustein unter ``sid`` eintragen (Dauer s, Cue-Pegel dB relativ zu sfx_db, Gruppe, Randblenden)."""
    def deco(fn):
        SOUNDS[sid] = fn
        _META[sid] = {'use': use, 'dur': float(dur), 'gain_db': float(gain_db), 'group': group,
                      'fade_in': float(fade_in), 'fade_out': float(fade_out)}
        return fn
    return deco


def resolve(sfx_id: str):
    """ID auflösen: (Basis-ID, Zusatzargumente) oder None. 'card_hit_3' und 'card_hit#3' -> ('card_hit', {'rank': 3})."""
    sid = str(sfx_id).strip()
    if sid in SOUNDS:
        return sid, {}
    m = _VARIANT_RE.match(sid)
    if m and m.group(1) in SOUNDS:
        return m.group(1), {'rank': int(m.group(2))}
    return None


def has(sfx_id: str) -> bool:
    """True, wenn ``render`` die ID liefern kann."""
    return resolve(sfx_id) is not None


def ids() -> list:
    """Alle Basis-IDs in Registrierungsreihenfolge."""
    return list(SOUNDS)


def meta(sfx_id: str) -> dict:
    """Katalogdaten einer ID (Kopie); KeyError bei unbekannter ID."""
    r = resolve(sfx_id)
    if r is None:
        raise KeyError(f"unbekannter Ton: {sfx_id!r}")
    return dict(_META[r[0]])


def default_db(sfx_id: str) -> float:
    """Standard-Cue-Pegel (dB relativ zu sfx_db) einer ID."""
    return meta(sfx_id)['gain_db']


def render(sfx_id: str, seed: int = 0, **kw) -> np.ndarray:
    """Fertiger Ton als Stereo float32 (n, 2): Länge = Katalogdauer, Spitze PEAK_DB, ohne Gleichanteil, weiche Ränder.

    Gecacht je (id, seed, Tonart, kw); Rückgabe ist eine Kopie. KeyError bei unbekannter ID.
    """
    r = resolve(sfx_id)
    if r is None:
        raise KeyError(f"unbekannter Ton: {sfx_id!r}")
    base, extra = r
    args = dict(extra)
    args.update(kw)
    ck = (base, int(seed), _KEY['root'], _KEY['mode'], tuple(sorted(args.items())))
    out = _CACHE.get(ck)
    if out is None:
        m = _META[base]
        raw = SOUNDS[base](seed=int(seed), **args)
        out = _finish(raw, m['dur'], m['fade_in'], m['fade_out'])
        _CACHE[ck] = out
    return out.copy()


def catalog(variants: bool = True) -> list:
    """Katalog [{'id', 'use', 'dur', 'gain_db', 'group'}]; mit ``variants`` auch card_hit_1 … card_hit_10."""
    out = []
    for sid, m in _META.items():
        out.append({'id': sid, 'use': m['use'], 'dur': m['dur'], 'gain_db': m['gain_db'], 'group': m['group']})
        if variants and sid == 'card_hit':
            for r in range(1, 11):
                out.append({'id': f'card_hit_{r}', 'use': f'Odd-Ding Rang #{r} (Leiterton {S.midi_to_freq(rank_note(r)):.0f} Hz bei Grundton {key_name()})',
                            'dur': m['dur'], 'gain_db': m['gain_db'], 'group': m['group']})
    return out


def render_all(out_dir: str, seed: int = 0) -> dict:
    """Alle Töne (inkl. Varianten) als <id>.wav nach ``out_dir`` schreiben, dazu catalog.json mit Messwerten."""
    os.makedirs(out_dir, exist_ok=True)
    entries = []
    for c in catalog():
        x = render(c['id'], seed)
        path = os.path.join(out_dir, c['id'] + '.wav')
        wav.write(path, x, SR)
        e = dict(c)
        e.update({'file': os.path.basename(path), 'samples': int(len(x)), 'peak_db': round(S.to_db(np.abs(x).max()), 2),
                  'rms_db': round(wav.rms_db(x), 2)})
        entries.append(e)
    doc = {'version': '1.0', 'sr': SR, 'key': key_name(), 'ladder': ladder(), 'motif': motif(),
           'peak_db': PEAK_DB, 'count': len(entries), 'sounds': entries}
    with open(os.path.join(out_dir, 'catalog.json'), 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
    return {'dir': out_dir, 'count': len(entries), 'key': key_name(), 'ids': [e['id'] for e in entries]}


# ----------------------------------------------------------------------------------------------------------------
# Helfer
# ----------------------------------------------------------------------------------------------------------------

def _finish(sig, dur: float, fade_in: float = 0.001, fade_out: float = 0.008) -> np.ndarray:
    """Roh -> fertig: Stereo, exakte Länge, NaN weg, Gleichanteil weg (Hochpass 10 Hz + Mittelwert), Randblenden, Spitze PEAK_DB."""
    st = wav.to_stereo(np.nan_to_num(np.asarray(sig, np.float32), nan=0.0, posinf=0.0, neginf=0.0))
    n = _n(dur)
    if len(st) < n:
        st = np.concatenate([st, np.zeros((n - len(st), 2), np.float32)])
    else:
        st = st[:n]
    st = S.highpass(st, 10.0, order=1)
    st = S.fade(st, min(fade_in, dur * 0.1), min(fade_out, dur * 0.3))
    st = st - st.mean(axis=0, keepdims=True)         # Rest des Gleichanteils (kurze Töne mit hartem Einsatz)
    st = S.fade(st, min(0.0003, dur * 0.05), min(0.0003, dur * 0.05))   # Ränder wieder exakt 0
    return S.normalize(st, PEAK_DB)


def _rng(seed: int, salt: int = 0) -> np.random.Generator:
    return np.random.default_rng((int(seed) * 1000003 + int(salt) * 7919) & 0xFFFFFFFF)


def _tone(freq, dur: float, tau: float, harmonics=()) -> np.ndarray:
    """Sinus (Zahl oder Verlauf) mit exponentieller Hüllkurve, optional Obertöne [(Verhältnis, dB), ...]."""
    x = S.sine(freq, dur).astype(np.float64)
    for ratio, g in harmonics:
        f = freq * ratio if np.isscalar(freq) else np.asarray(freq, np.float64) * ratio
        x += S.db(g) * S.sine(f, dur)
    return S.apply(x, S.env_exp(dur, tau))


def _glass_items(freqs, t0: float, stagger: float, dur: float, decay: float, pans, gain_db: float = 0.0) -> list:
    """Glas-Pings als Mixdown-Einträge: je Frequenz ein ``glass`` ab t0 + k·stagger, gepannt."""
    return [(S.pan(S.glass(f, dur, decay), p), t0 + k * stagger, gain_db) for k, (f, p) in enumerate(zip(freqs, pans))]


def _puff(dur: float, cutoff: float, seed: int, shape: str = 'tri') -> np.ndarray:
    """Dumpfer Luftstoß: Rauschen Tiefpass ``cutoff`` mit Dreieck- oder Exponentialhüllkurve."""
    nz = S.lowpass(S.noise(dur, 'white', seed), cutoff, order=2)
    env = S.env_lin([(0.0, 0.0), (dur * 0.35, 1.0), (dur, 0.0)]) if shape == 'tri' else S.env_exp(dur, dur / 4.0)
    return S.apply(nz, env)


def _gated(sig: np.ndarray, block: float, prob: float, seed: int, smooth: float = 0.0005) -> np.ndarray:
    """Zufallsgates: Blöcke von ``block`` s sind mit Wahrscheinlichkeit ``prob`` offen (weich geschaltet)."""
    n = len(sig)
    k = max(1, _n(block))
    g = (_rng(seed, 11).random(-(-n // k)) < prob).astype(np.float64)
    gate = np.repeat(g, k)[:n]
    w = max(1, _n(smooth))
    gate = np.convolve(gate, np.ones(w) / w, mode='same')
    return S.apply(sig, gate)


def _accel_times(t_start: float, t_end: float, f0: float, f1: float) -> np.ndarray:
    """Ereigniszeiten einer von f0 auf f1 Hz (linear) beschleunigenden Folge zwischen t_start und t_end."""
    T = t_end - t_start
    out, t = [], 0.0
    while t < T:
        out.append(t_start + t)
        t += 1.0 / (f0 + (f1 - f0) * t / T)
    return np.array(out)


def _flam_offset(freq: float, nominal: float) -> float:
    """Versatz eines zweiten Anschlags nahe ``nominal`` s, auf (n + 1/4) Perioden von ``freq`` gerundet: die beiden
    Anschläge addieren sich dann um 90° versetzt, statt sich je nach Tonhöhe zu verstärken oder auszulöschen."""
    n = max(1, int(round(nominal * freq - 0.25)))
    return (n + 0.25) / freq


def _flap_raw(seed: int) -> np.ndarray:
    """Zwei dumpfe Rauschstöße (Tiefpass 500 Hz) à 60 ms im Abstand 90 ms (Flügelschlag)."""
    return S.mixdown([(_puff(0.06, 500.0, seed), 0.0, 0.0), (_puff(0.06, 500.0, seed + 1), 0.09, -1.5)])


def _beak_raw(seed: int) -> np.ndarray:
    """Doppelklick: 2 × 8 ms Rauschen Bandpass 2.5–3.5 kHz, Abstand 70 ms, mit Holzkörper."""
    items = []
    for k, t0 in enumerate((0.0, 0.07)):
        items.append((S.burst(0.008, 2500.0, 3500.0, 0.002, seed=seed + k), t0, 0.0 if k == 0 else -2.0))
        items.append((S.click(0.006, 1800.0), t0, -8.0))
    return S.mixdown(items)


# ----------------------------------------------------------------------------------------------------------------
# Pflicht-IDs der Engine
# ----------------------------------------------------------------------------------------------------------------

@sound('hook_hit', 'Erster Frame des Hooks (t 0.05)', 0.45, -6, 'core', fade_out=0.02)
def hook_hit(seed=0):
    """Sub-Pop (Sinus 180 -> 55 Hz in 60 ms) + Papierschlag (Rauschen 1.4–2.2 kHz, 25 ms) + Glas-Ping 2.4 kHz (300 ms), trocken."""
    f = np.concatenate([S.sweep(180.0, 55.0, 0.06), np.full(_n(0.19), 55.0, np.float32)])
    sub = S.drive(_tone(f, 0.25, 0.055), 0.2)
    paper = S.burst(0.025, 1400.0, 2200.0, 0.006, seed=seed)
    ping = S.pan(S.glass(2400.0, 0.3, 0.3), 0.15)
    return S.mixdown([(sub, 0.0, 0.0), (paper, 0.0, -5.0), (ping, 0.004, -13.0)])


@sound('card_whoosh', 'Peel / Seitenwechsel (sc.t0)', 0.30, -8, 'core', fade_in=0.004, fade_out=0.02)
def card_whoosh(seed=0):
    """Weißes Rauschen, Bandpass-Sweep 400 -> 4000 Hz über 240 ms (q 2), Attack 40 ms, Pan -0.8 -> +0.8, Doppler 0.97 -> 1.03."""
    cut = np.concatenate([S.sweep(400.0, 4000.0, 0.24), np.full(_n(0.06), 4000.0, np.float32)])
    x = S.svf(S.noise(0.3, 'white', seed), cut, q=2.0, mode='bp')
    x = S.apply(x, S.env_lin([(0.0, 0.0), (0.04, 1.0), (0.22, 0.6), (0.3, 0.0)]))
    x = S.varispeed(x, S.sweep(0.97, 1.03, 0.3, 'lin'))
    body = S.apply(S.bandpass(S.noise(0.3, 'pink', seed + 1), 200.0, 800.0), S.env_lin([(0.0, 0.0), (0.06, 1.0), (0.3, 0.0)]))
    return S.mixdown([(S.pan_curve(x, S.sweep(-0.8, 0.8, 0.3, 'lin')), 0.0, 0.0), (body, 0.0, -14.0)])


@sound('card_hit', 'Odd-Ding: Karte landet (sc.t0 + 0.55·trans_dur); Rang-Leiter 1-2-4-5-8 über dem Bett-Grundton', 0.55, -5, 'core', fade_out=0.02)
def card_hit(seed=0, rank=5, total=None):
    """Stempel (Sinus 90 Hz 80 ms + Klick 15 ms) | Marimba-Dyade Grundton + Quinte, 2 Anschläge 70 ms versetzt (Decay 260 ms) | 4 Glas-Sinus 3–6 kHz à 120 ms, zufällig gepannt (seed = rank)."""
    midi = rank_note(rank, total)
    f, f5 = _hz(midi), _hz(midi + 7)
    rng = _rng(seed, rank)
    stamp = _tone(90.0, 0.08, 0.022)
    clk = S.click(0.015, 1800.0)
    dy1 = 0.7 * S.marimba(f, 0.46, 0.26, seed=seed) + 0.55 * S.marimba(f5, 0.46, 0.26, seed=seed + 1)
    # zweiter Anschlag (Flam, -6 dB): je Note auf eine Viertelperiode gerundet, damit sich die Anschläge
    # bei keiner Tonhöhe gegenseitig auslöschen (Kammfilter zwischen den Strokes)
    r2 = (0.7 * S.marimba(f, 0.40, 0.21, bright=0.7, seed=seed + 2), 0.003 + _flam_offset(f, 0.07), -6.0)
    q2 = (0.55 * S.marimba(f5, 0.40, 0.21, bright=0.7, seed=seed + 3), 0.003 + _flam_offset(f5, 0.07), -6.0)
    gl = _glass_items(rng.uniform(3000.0, 6000.0, 4), 0.012, 0.012, 0.12, 0.12, rng.uniform(-0.7, 0.7, 4), -15.0)
    return S.mixdown([(stamp, 0.0, -3.0), (clk, 0.0, -10.0), (dy1, 0.003, 0.0), r2, q2] + gl)


@sound('number_one', 'Karte #1 (sc.t0 + 0.6·trans_dur), nach dem Trommelwirbel des riser', 1.6, -5, 'core', fade_out=0.06)
def number_one(seed=0):
    """Glockenakkord Tonika (+ Terz, falls Modus) + Quinte + Oktave (bell, ratio 1.4, Decay 1.2 s, 40 ms versetzt) + Shaker 80 Impulse + Sub 55 Hz + Glas-Cluster auf der Oktave."""
    root = key()
    third = _third()
    voices = [root, root + third, root + 7, root + 12] if third else [root, root + 7, root + 12]
    rng = _rng(seed, 1)
    items = []
    for k, m in enumerate(voices):
        items.append((S.pan(S.bell(_hz(m), 1.2, 1.4), -0.4 + 0.8 * k / max(1, len(voices) - 1)), 0.0 + 0.04 * k, -2.0 - 1.5 * k))
    items += _glass_items([_hz(root + 12) * r for r in (1.0, 2.0, 1.0 * 1.003, 2.0 * 0.997)], 0.10, 0.03, 0.5, 0.45, rng.uniform(-0.6, 0.6, 4), -13.0)
    items.append((S.shaker(80, 0.55, 4500.0, 6500.0, 0.008, tau=0.22, seed=seed), 0.02, -12.0))
    items.append((_tone(np.concatenate([S.sweep(110.0, 55.0, 0.03), np.full(_n(0.09), 55.0, np.float32)]), 0.12, 0.04), 0.0, -1.0))
    return S.mixdown(items)


@sound('stat_pop', 'Stat-Plakette zählt hoch', 0.9, -9, 'core', fade_out=0.03)
def stat_pop(seed=0):
    """Zählwerk: Holzblock-Klicks click(0.012, 2200) im Tempo einer out_cubic-Zählkurve (12–26 Ticks) + Abschluss-Pling (Dreieck, Quinte über dem Grundton, 90 ms)."""
    rng = _rng(seed, 2)
    n_ticks = 12 + (int(seed) * 7 + 6) % 15
    T = 0.74
    items = []
    for k in range(n_ticks):
        t = T * (1.0 - (1.0 - k / n_ticks) ** (1.0 / 3.0))
        items.append((S.click(0.012, 2200.0 * rng.uniform(0.98, 1.02)), t, float(rng.uniform(-3.0, 0.0))))
        items.append((S.burst(0.006, 1200.0, 3000.0, 0.0015, seed=seed + k), t, -12.0))
    pling = S.apply(S.lowpass(S.tri(_hz(key() + 7), 0.14), 6000.0), S.env_exp(0.14, 0.03))
    items.append((S.pan(pling, 0.1), T + 0.02, 0.0))
    items.append((S.glass(_hz(key() + 19), 0.12, 0.1), T + 0.02, -14.0))
    return S.mixdown(items)


@sound('outro_chime', 'Outro-Beginn: Markenmotiv Odd-Ding als Kalimba', 1.6, -8, 'core', fade_out=0.05)
def outro_chime(seed=0):
    """Kalimba (pluck, bright 0.6) auf 1-5-8, Rhythmus 0.18 / 0.18 / 0.60 s, Chorus rate 0.5 mix 0.3, Hall size 0.4 decay 0.9 mix 0.2."""
    notes = motif()
    t0 = np.concatenate([[0.0], np.cumsum(MOTIF_RHYTHM[:-1])])
    items = []
    for k, (m, t) in enumerate(zip(notes, t0)):
        d = 0.55 if k < 2 else 1.1
        items.append((S.pan(S.kalimba(_hz(m), d, 0.6, seed=seed + k), -0.2 + 0.2 * k), float(t), -1.0 + 0.5 * k))
    x = S.chorus(S.mixdown(items), rate=0.5, depth=0.003, mix=0.3)
    return S.reverb(x, size=0.4, decay=0.9, mix=0.2, seed=seed)


@sound('end_sting', 'Letzter Frame (voice_end + 0.25)', 1.8, -7, 'core', fade_out=0.08)
def end_sting(seed=0):
    """Odd-Ding: Marimba 1-5-8 (Decay 400 ms) + Glas-Cluster auf der Oktave + flap unter dem Ausklang + Hall decay 1.2 s."""
    notes = motif()
    t0 = np.concatenate([[0.0], np.cumsum(MOTIF_RHYTHM[:-1])])
    rng = _rng(seed, 3)
    items = []
    for k, (m, t) in enumerate(zip(notes, t0)):
        d = 0.5 if k < 2 else 0.9
        items.append((S.pan(S.marimba(_hz(m), d, 0.4 if k < 2 else 0.6, seed=seed + k), -0.25 + 0.25 * k), float(t), 0.0 + 0.5 * k))
    oct_f = _hz(notes[-1])
    items += _glass_items([oct_f * r for r in (2.0, 3.0, 4.0 * 1.002, 2.0 * 0.998)], float(t0[-1]) + 0.01, 0.03, 0.5, 0.45, rng.uniform(-0.6, 0.6, 4), -12.0)
    items.append((_flap_raw(seed), float(t0[-1]) + 0.08, -11.0))
    items.append((_tone(_hz(notes[0] - 12), 0.6, 0.12), float(t0[-1]), -10.0))
    return S.reverb(S.mixdown(items), size=0.5, decay=1.2, mix=0.22, seed=seed)


# ----------------------------------------------------------------------------------------------------------------
# Sticker und UI
# ----------------------------------------------------------------------------------------------------------------

@sound('pop_in', 'Jeder Sticker-Auftritt (max. 1 je 150 ms)', 0.08, -12, 'ui', fade_out=0.004)
def pop_in(seed=0):
    """Sinus-Sweep 600 -> 1200 Hz 40 ms + Klick 8 ms, env_exp tau 15 ms, Papierhauch."""
    sw = _tone(S.sweep(600.0, 1200.0, 0.05), 0.05, 0.015, [(2.0, -14.0)])
    return S.mixdown([(sw, 0.0, 0.0), (S.click(0.008, 2600.0), 0.0, -9.0), (S.burst(0.012, 2000.0, 6000.0, 0.003, seed=seed), 0.0, -16.0)])


@sound('pop_out', 'Sticker verschwindet (Scale -> 0)', 0.08, -16, 'ui', fade_out=0.004)
def pop_out(seed=0):
    """Sinus-Sweep 1200 -> 500 Hz 50 ms + Klick; der Pegel liegt per Cue 4 dB unter pop_in."""
    sw = _tone(S.sweep(1200.0, 500.0, 0.06), 0.06, 0.017, [(2.0, -16.0)])
    return S.mixdown([(sw, 0.0, 0.0), (S.click(0.006, 2000.0), 0.0, -12.0), (S.burst(0.01, 1500.0, 5000.0, 0.003, seed=seed), 0.0, -18.0)])


@sound('peel', 'Sticker abziehen, Badge löst sich, Peel-Übergang', 0.22, -12, 'ui', fade_in=0.002, fade_out=0.012)
def peel(seed=0):
    """Rauschen Hochpass 3 kHz mit Amplituden-Knistern (Zufallsgates 2 ms), Attack 30 / Release 190 ms, leiser Papierkörper."""
    hi = _gated(S.highpass(S.noise(0.22, 'white', seed), 3000.0, order=2), 0.002, 0.55, seed)
    env = S.adsr(0.22, a=0.03, d=0.19, s=0.0, r=0.0, curve='exp')
    body = S.bandpass(S.noise(0.22, 'white', seed + 5), 400.0, 1200.0)
    return S.mixdown([(S.apply(hi, env), 0.0, 0.0), (S.apply(body, env), 0.0, -13.0)])


@sound('tick', 'Zählwerk-Rolle der Ziffer, Untertitel-Gruppenwechsel optional', 0.012, -30, 'ui', fade_in=0.0003, fade_out=0.003)
def tick(seed=0):
    """click(0.012, 3000) durch Bandpass 2.5–3.5 kHz."""
    return S.bandpass(S.click(0.012, 3000.0), 2500.0, 3500.0)


@sound('stamp', 'Stempel-Sticker schlägt ein', 0.16, -8, 'ui', fade_out=0.01)
def stamp(seed=0):
    """20 ms Stille, dann Sinus 90 Hz 80 ms + Rauschen Tiefpass 600 Hz 50 ms, Drive 0.3."""
    thump = _tone(np.concatenate([S.sweep(120.0, 90.0, 0.02), np.full(_n(0.06), 90.0, np.float32)]), 0.08, 0.024)
    paper = S.apply(S.lowpass(S.noise(0.05, 'white', seed), 600.0), S.env_exp(0.05, 0.012))
    x = S.drive(S.mixdown([(thump, 0.0, 0.0), (paper, 0.0, -4.0)], peak_db=-1.0), 0.3)
    return S.pad_silence(x, 0.0, before=0.02)


@sound('keyword_slam', 'Schlagwort-Sticker (keyword) landet', 0.30, -9, 'ui', fade_out=0.015)
def keyword_slam(seed=0):
    """20 ms Stille, Sub 50 Hz 140 ms + Rausch-Crack Bandpass 1.2–1.8 kHz 25 ms + Glas-Ping 3.2 kHz 120 ms."""
    sub = _tone(np.concatenate([S.sweep(95.0, 50.0, 0.03), np.full(_n(0.11), 50.0, np.float32)]), 0.14, 0.045)
    crack = S.burst(0.025, 1200.0, 1800.0, 0.006, seed=seed)
    ping = S.glass(3200.0, 0.12, 0.12)
    x = S.mixdown([(sub, 0.0, 0.0), (crack, 0.0, -3.0), (ping, 0.003, -12.0)])
    return S.pad_silence(x, 0.0, before=0.02)


@sound('confetti', 'Konfetti-Burst (Karte 24 Impulse, #1/Pointe 80: seed wählt 24–80)', 0.7, -12, 'ui', fade_out=0.02)
def confetti(seed=0, n=None):
    """Shaker: n Rauschimpulse 8 ms, Bandpass 4–6 kHz, zufällig gepannt, Dichte fällt exponentiell über 600 ms."""
    n = int(n) if n else 24 + (int(seed) * 11 + 24) % 57
    return S.shaker(n, 0.62, 4000.0, 6000.0, 0.008, tau=0.2, spread=0.85, seed=seed)


@sound('shiny', 'Edelstein, Beute, Enthüllung, Album voll', 0.5, -12, 'ui', fade_out=0.02)
def shiny(seed=0):
    """Glasglöckchen-Cluster: 5 Sinus 3.5–7 kHz, Decay 400 ms, 30 ms versetzt, widen 0.6."""
    rng = _rng(seed, 4)
    freqs = np.exp(rng.uniform(np.log(3500.0), np.log(7000.0), 5))
    x = S.mixdown(_glass_items(freqs, 0.0, 0.03, 0.42, 0.4, rng.uniform(-0.5, 0.5, 5)))
    return S.widen(x, 0.6)


@sound('riser', 'Letzte 1.5 s vor #1 (automatischer Cue E1.t0 - 1.5) oder vor einer Enthüllung', 1.5, -12, 'ui', fade_in=0.01, fade_out=0.004)
def riser(seed=0):
    """Pinkes Rauschen + Sinus-Sweep 200 -> 2000 Hz über 1.5 s, Lautstärke exponentiell, Hochpass öffnet 300 -> 50 Hz; letzte 900 ms Trommelwirbel (Bursts 250–400 Hz, 8 -> 24 Hz)."""
    T = 1.5
    t = np.arange(_n(T)) / SR
    env = np.exp(4.0 * (t / T - 1.0))
    nz = S.svf(S.noise(T, 'pink', seed), S.sweep(300.0, 50.0, T), q=0.8, mode='hp')
    sw = S.sine(S.sweep(200.0, 2000.0, T), T) + 0.3 * S.sine(S.sweep(400.0, 4000.0, T), T)
    body = S.apply(0.8 * nz + 0.45 * sw, env)
    items = [(body, 0.0, 0.0)]
    for k, tt in enumerate(_accel_times(0.6, T - 0.01, 8.0, 24.0)):
        g = -14.0 + 14.0 * (tt - 0.6) / 0.9
        hit = S.mixdown([(S.burst(0.03, 250.0, 400.0, 0.008, seed=seed + 10 + k), 0.0, 0.0), (_tone(185.0, 0.03, 0.01), 0.0, -4.0)])
        items.append((S.pan(hit, -0.15 if k % 2 else 0.15), float(tt), g))
    return S.mixdown(items)


@sound('record_stop', 'Komisches Innehalten (Pointe)', 0.45, -10, 'ui', fade_out=0.02)
def record_stop(seed=0):
    """Aktueller Akkord als Dreieck-Dreiklang (Grundton, Terz des Modus oder Quinte, Oktave), Tonhöhe -> 0 über 400 ms (Varispeed) + Tiefpass 8 kHz -> 200 Hz."""
    root = key()
    third = _third()
    notes = [root - 12, root - 12 + (third or 7), root - 5, root]
    src = sum(S.tri(_hz(m), 0.6).astype(np.float64) * S.db(-2.0 * k) for k, m in enumerate(notes))
    src = S.apply(src / 2.5, S.adsr(0.6, 0.004, 0.1, 0.8, 0.1))
    ratio = np.clip(1.0 - np.linspace(0.0, 1.0, _n(0.42)), 0.0, 1.0) ** 1.4
    x = S.varispeed(src, ratio)
    x = S.svf(x, S.sweep(8000.0, 200.0, 0.42), q=0.9, mode='lp')
    return S.apply(x, S.env_lin([(0.0, 1.0), (0.3, 0.9), (0.42, 0.0)]))


@sound('fail', 'Gescheiterter Plan, komischer Fehlschlag', 0.4, -10, 'ui', fade_out=0.02)
def fail(seed=0):
    """Zwei Dreieck-Töne A4 -> F4 je 180 ms mit Vibrato 6 Hz (±2 %), Tiefpass 2.5 kHz, exponentielle Hüllkurven."""
    items = []
    for k, (f, t0) in enumerate(((440.0, 0.0), (349.23, 0.19))):
        tt = np.arange(_n(0.2)) / SR
        fr = f * (1.0 + 0.02 * np.sin(2 * np.pi * 6.0 * tt) * np.minimum(1.0, tt / 0.06)) * (1.0 - 0.03 * tt / 0.2)
        x = S.lowpass(S.tri(fr, 0.2), 2500.0)
        items.append((S.apply(x, S.adsr(0.2, 0.01, 0.06, 0.7, 0.08, 'exp')), t0, -1.0 * k))
    return S.mixdown(items)


@sound('flash', 'Blitz bei Konfetti-Cut (#1, Pointe)', 0.08, -14, 'ui', fade_in=0.0005, fade_out=0.006)
def flash(seed=0):
    """Weißes Rauschen Hochpass 6 kHz 60 ms (env_exp) + Sinus 4 kHz 40 ms."""
    return S.mixdown([(S.burst(0.06, 6000.0, None, 0.015, seed=seed), 0.0, 0.0), (_tone(4000.0, 0.04, 0.012), 0.0, -6.0)])


# ----------------------------------------------------------------------------------------------------------------
# Odd (Charakter)
# ----------------------------------------------------------------------------------------------------------------

@sound('flap', 'Flügelschlag, Elster-Lieferung, fly', 0.18, -12, 'odd', fade_in=0.002, fade_out=0.01)
def flap(seed=0):
    """Zwei dumpfe Rauschstöße Tiefpass 500 Hz à 60 ms, Abstand 90 ms, Dreieck-Hüllkurve."""
    return _flap_raw(seed)


@sound('hop', 'Odd hüpft, Landung, sneak-Schritt (-14 dB)', 0.12, -12, 'odd', fade_out=0.01)
def hop(seed=0):
    """pluck('G3', 0.12, bright 0.5) mit winzigem Landungs-Thump."""
    return S.mixdown([(S.pluck('G3', 0.12, bright=0.5, seed=seed), 0.0, 0.0), (_tone(110.0, 0.04, 0.012), 0.0, -12.0)])


@sound('boing', 'Squash & Stretch, Gag-Landung (nie im Respekt-Modus)', 0.35, -10, 'odd', fade_out=0.02)
def boing(seed=0):
    """Sinus 220 Hz mit abklingendem Vibrato 8 Hz, Tiefe 30 % (FM), 350 ms, env_exp, Feder-Oberton."""
    t = np.arange(_n(0.35)) / SR
    idx = (0.3 * 220.0 / 8.0) * np.exp(-t / 0.12)
    x = S.fm(220.0, 8.0, idx, 0.35) + 0.25 * S.fm(440.0, 8.0, idx, 0.35)
    return S.apply(x, S.env_exp(0.35, 0.1))


@sound('blink', 'Blinzeln, nur in Sprechpausen', 0.01, -18, 'odd', fade_in=0.0003, fade_out=0.003)
def blink(seed=0):
    """Holztick click(0.010, 1500) mit Hauch Rauschen."""
    return S.mixdown([(S.click(0.01, 1500.0), 0.0, 0.0), (S.burst(0.005, 1000.0, 3000.0, 0.0012, seed=seed), 0.0, -10.0)])


@sound('beak_click', 'Schnabel schließt, Skepsis, Klopfen', 0.09, -12, 'odd', fade_out=0.006)
def beak_click(seed=0):
    """Doppelklick 2 × 8 ms Rauschen Bandpass 2.5–3.5 kHz, Abstand 70 ms."""
    return _beak_raw(seed)


@sound('gasp', 'shock: Schock-Einatmen, aufsteigend', 0.3, -12, 'odd', fade_in=0.004, fade_out=0.01)
def gasp(seed=0):
    """Rauschen Hochpass 1 kHz mit umgekehrter Hüllkurve (Attack 250 / Release 30 ms) + Formant-Bandpass 700/1200 Hz + aufsteigender Ton 420 -> 880 Hz."""
    env = S.env_lin([(0.0, 0.0), (0.25, 1.0), (0.275, 0.35), (0.3, 0.0)])
    nz = S.highpass(S.noise(0.3, 'white', seed), 1000.0)
    form = S.svf(nz, 700.0, q=4.0, mode='bp') + S.svf(nz, 1200.0, q=4.0, mode='bp') + 0.25 * nz
    tone = S.sine(S.sweep(420.0, 880.0, 0.3), 0.3) + 0.3 * S.sine(S.sweep(840.0, 1760.0, 0.3), 0.3)
    return S.mixdown([(S.apply(form, env), 0.0, 0.0), (S.apply(tone, env ** 1.5), 0.0, -7.0)])


@sound('giggle', 'laugh: Kichern', 0.22, -12, 'odd', fade_out=0.01)
def giggle(seed=0):
    """Drei Sinus-Blips 900/1100/1000 Hz à 50 ms, Pitch-Jitter ±4 %, Formant-Bandpass 800 Hz."""
    rng = _rng(seed, 6)
    items = []
    for k, (f, t0) in enumerate(((900.0, 0.0), (1100.0, 0.07), (1000.0, 0.14))):
        fj = f * rng.uniform(0.96, 1.04)
        x = _tone(fj * np.linspace(1.03, 0.97, _n(0.05)), 0.05, 0.02, [(2.0, -10.0), (3.0, -18.0)])
        x = 0.5 * x + 0.5 * S.svf(x, 800.0, q=1.2, mode='bp') * 2.0
        items.append((S.apply(x, S.adsr(0.05, 0.004, 0.02, 0.6, 0.02)), t0, -1.0 * k))
    return S.mixdown(items)


@sound('hmm', 'think, facepalm: Skepsis', 0.32, -14, 'odd', fade_in=0.01, fade_out=0.03)
def hmm(seed=0):
    """Sägezahn Tiefpass 800 Hz, Tonhöhe E3 -> C3 über 300 ms, Vibrato 5 Hz."""
    t = np.arange(_n(0.32)) / SR
    f = S.sweep(S.note_to_freq('E3'), S.note_to_freq('C3'), 0.32).astype(np.float64) * (1.0 + 0.012 * np.sin(2 * np.pi * 5.0 * t))
    x = S.lowpass(S.saw(f, 0.32), 800.0) + 0.3 * S.sine(f, 0.32)
    return S.apply(x, S.adsr(0.32, 0.03, 0.05, 0.8, 0.1, 'exp'))


@sound('odd_say', "Catchphrase-Sprechblase 'Odd.' (max. 1x je Video)", 0.26, -10, 'odd', fade_out=0.008)
def odd_say(seed=0):
    """Zwei Formant-Töne (Quelle durch Bandpässe 600 + 1100 Hz) A4 -> F4 über 180 ms + beak_click am Ende."""
    f = S.sweep(440.0, 349.23, 0.18)
    src = S.sine(f, 0.18) + 0.5 * S.lowpass(S.saw(f, 0.18), 3000.0)
    voice = S.svf(src, 600.0, q=3.0, mode='bp') + S.svf(src, 1100.0, q=3.0, mode='bp') + 0.35 * S.sine(f, 0.18)
    voice = S.apply(voice, S.adsr(0.18, 0.015, 0.05, 0.7, 0.06, 'exp'))
    return S.mixdown([(voice, 0.0, 0.0), (_beak_raw(seed), 0.175, -7.0)])


# ----------------------------------------------------------------------------------------------------------------
# Themen-Props
# ----------------------------------------------------------------------------------------------------------------

@sound('drip', 'Höhle, Wasser, Tropfen (Script-Cue)', 1.4, -10, 'prop', fade_out=0.05)
def drip(seed=0):
    """Sinus 1800 -> 900 Hz 25 ms + Delay 375 ms feedback 0.45 (3×) + Hall size 0.6 decay 1.4 mix 0.3."""
    ping = _tone(S.sweep(1800.0, 900.0, 0.03), 0.03, 0.009, [(2.0, -12.0)])
    x = S.delay(ping, 0.375, feedback=0.45, mix=0.5, damp=4000.0, pingpong=True, max_taps=3)
    return S.reverb(x, size=0.6, decay=1.4, mix=0.3, seed=seed)


@sound('splash', "Platschen, 'fell in' (Script-Cue)", 0.45, -9, 'prop', fade_out=0.02)
def splash(seed=0):
    """Rauschburst Tiefpass 1.2 kHz 120 ms + 6 Blasen-Chirps 300 -> 900 Hz à 20 ms über 250 ms + Sinus-Plop 120 Hz."""
    rng = _rng(seed, 7)
    items = [(S.apply(S.lowpass(S.noise(0.12, 'white', seed), 1200.0), S.env_exp(0.12, 0.03)), 0.0, 0.0),
             (_tone(S.sweep(160.0, 95.0, 0.08), 0.08, 0.02), 0.0, -2.0)]
    for k in range(6):
        f0 = rng.uniform(260.0, 420.0)
        chirp = _tone(S.sweep(f0, f0 * 3.0, 0.02), 0.02, 0.007)
        items.append((S.pan(chirp, rng.uniform(-0.6, 0.6)), 0.05 + rng.uniform(0.0, 0.25), -10.0 + rng.uniform(-3.0, 0.0)))
    return S.mixdown(items)


@sound('bubble', 'Ozean, Flüssigkeiten', 0.06, -14, 'prop', fade_out=0.005)
def bubble(seed=0):
    """Sinus-Sweep 300 -> 900 Hz 20 ms, danach Resonanz (svf q 8) klingt aus."""
    f = np.concatenate([S.sweep(300.0, 900.0, 0.02), np.full(_n(0.04), 900.0, np.float32)])
    exc = S.apply(S.sine(f, 0.06), S.env_exp(0.06, 0.01))
    return S.svf(exc, f * 1.1, q=8.0, mode='lp')


@sound('coin', 'Geld, Beute, Münze', 0.45, -12, 'prop', fade_out=0.02)
def coin(seed=0):
    """Sinus 1.2 + 1.8 kHz 90 ms + Metallklick (Rauschen 4 kHz 5 ms), Prell-Hüllkurve 3× (180 / 110 / 70 ms)."""
    items = []
    for k, (t0, g, tau) in enumerate(((0.0, 0.0, 0.035), (0.18, -5.0, 0.025), (0.29, -10.0, 0.018))):
        tone = S.apply(S.sine(1200.0, 0.14) + 0.7 * S.sine(1800.0, 0.14) + 0.25 * S.sine(2420.0, 0.14), S.env_exp(0.14, tau))
        items.append((S.pan(tone, 0.1 * k), t0, g))
        items.append((S.burst(0.005, 3500.0, 7000.0, 0.0012, seed=seed + k), t0, g - 6.0))
    return S.mixdown(items)


@sound('page_flip', 'Kalender, Akte, Flip-Karte', 0.14, -12, 'prop', fade_in=0.002, fade_out=0.01)
def page_flip(seed=0):
    """Rauschen Bandpass 0.9–1.5 kHz 120 ms mit Doppelbuckel-Hüllkurve + Papierkörper 300–700 Hz."""
    env = S.env_lin([(0.0, 0.0), (0.02, 1.0), (0.05, 0.3), (0.08, 0.85), (0.14, 0.0)])
    hi = S.apply(S.bandpass(S.noise(0.14, 'white', seed), 900.0, 1500.0), env)
    lo = S.apply(S.bandpass(S.noise(0.14, 'white', seed + 1), 300.0, 700.0), env)
    return S.mixdown([(hi, 0.0, 0.0), (lo, 0.0, -8.0)])


@sound('typewriter', 'Etiketten, Mono-Chips, Meta-Tag (je Zeichen, max. 12 Ticks)', 0.012, -16, 'prop', fade_in=0.0003, fade_out=0.003)
def typewriter(seed=0):
    """click(0.012, 4000) im Zeichenrhythmus mit Hauch Metall."""
    return S.mixdown([(S.click(0.012, 4000.0), 0.0, 0.0), (S.burst(0.004, 3000.0, 8000.0, 0.001, seed=seed), 0.0, -9.0)])


@sound('heartbeat', 'Medizin, Spannung (Wiederholung alle 900 ms per Cue)', 0.3, -10, 'prop', fade_out=0.02)
def heartbeat(seed=0):
    """Zwei Sinus-Thumps 60 Hz (90 und 70 ms) im Abstand 180 ms, Tiefpass 120 Hz."""
    def thump(d):
        f = np.concatenate([S.sweep(78.0, 60.0, 0.02), np.full(_n(d - 0.02), 60.0, np.float32)])
        return S.lowpass(_tone(f, d, d / 3.0), 120.0)
    return S.mixdown([(thump(0.09), 0.0, 0.0), (thump(0.07), 0.18, -3.0)])


@sound('alarm_blip', 'Heist: Laserlinie, Alarm, Ertappt', 0.4, -12, 'prop', fade_out=0.01)
def alarm_blip(seed=0):
    """Rechteck 1100 Hz 60 ms × 3 bei 8 Hz, Tiefpass 3 kHz, env_exp."""
    blip = S.apply(S.lowpass(S.square(1100.0, 0.06), 3000.0), S.env_exp(0.06, 0.02))
    return S.mixdown([(blip, k * 0.125, 0.0) for k in range(3)])


@sound('safe_click', 'Tresor, Schloss, Enthüllung', 0.9, -10, 'prop', fade_out=0.03)
def safe_click(seed=0):
    """5–7 Rasterklicks (Rauschen 2 ms + Sinus 800 Hz 20 ms) ab 12 Hz verlangsamend + Abschluss 'Clunk' Sinus 90 Hz 150 ms."""
    n_clicks = 5 + int(seed) % 3
    items, t = [], 0.0
    for k in range(n_clicks):
        items.append((S.burst(0.003, 2000.0, 8000.0, 0.0008, seed=seed + k), t, 0.0))
        items.append((_tone(800.0, 0.02, 0.006), t, -4.0))
        t += (1.0 / 12.0) * 1.1 ** k
    clunk = S.mixdown([(_tone(np.concatenate([S.sweep(120.0, 90.0, 0.02), np.full(_n(0.13), 90.0, np.float32)]), 0.15, 0.04), 0.0, 0.0),
                       (S.burst(0.03, None, 900.0, 0.008, seed=seed + 20), 0.0, -3.0)])
    items.append((clunk, t + 0.03, 2.0))
    return S.mixdown(items)


@sound('rumble', 'Einsturz, Erdbeben, Gefahr (Höhle)', 1.5, -10, 'prop', fade_in=0.15, fade_out=0.35)
def rumble(seed=0):
    """Braunes Rauschen Tiefpass 90 Hz 1.5 s, Tremolo 6 Hz Tiefe 0.4, Hochpass 25 Hz."""
    x = S.highpass(S.lowpass(S.noise(1.5, 'brown', seed), 90.0), 25.0, order=1)
    return S.tremolo(x, 6.0, 0.4)


@sound('bat_flutter', 'Fledermaus, Mottenschwarm', 0.42, -16, 'prop', fade_in=0.002, fade_out=0.02)
def bat_flutter(seed=0):
    """7 Rausch-Puffs Tiefpass 1.2 kHz bei 18 Hz, Stereo wandernd."""
    rng = _rng(seed, 8)
    items = []
    for k in range(7):
        p = _puff(0.04, 1200.0 * rng.uniform(0.85, 1.15), seed + k)
        items.append((S.pan(p, -0.6 + 1.2 * k / 6.0), k / 18.0, float(rng.uniform(-3.0, 0.0))))
    return S.mixdown(items)


@sound('whistle', 'Tiere, Vogelpfiff, Pointe', 0.25, -14, 'prop', fade_in=0.005, fade_out=0.02)
def whistle(seed=0):
    """Sinus mit Portamento 1.8 -> 2.4 kHz (120 ms), Vibrato 6 Hz, Hauch Atem."""
    t = np.arange(_n(0.25)) / SR
    f = np.concatenate([S.sweep(1800.0, 2400.0, 0.12), np.full(_n(0.13), 2400.0, np.float32)]).astype(np.float64)
    f *= 1.0 + 0.012 * np.sin(2 * np.pi * 6.0 * t) * np.minimum(1.0, t / 0.1)
    x = S.sine(f, 0.25) + 0.12 * S.sine(f * 2.0, 0.25)
    env = S.adsr(0.25, 0.02, 0.03, 0.85, 0.08, 'exp')
    return S.mixdown([(S.apply(x, env), 0.0, 0.0), (S.apply(S.bandpass(S.noise(0.25, 'white', seed), 2000.0, 4500.0), env), 0.0, -24.0)])


# ----------------------------------------------------------------------------------------------------------------
# Respekt
# ----------------------------------------------------------------------------------------------------------------

@sound('ghost_halo', 'Todesfall: Geist-Halo-Sticker erscheint', 2.2, -14, 'respect', fade_in=0.02, fade_out=0.25)
def ghost_halo(seed=0):
    """Sinus-Pad 3 Teiltöne auf A4 (0 / -9 / -15 dB), Attack 600 ms, Hall decay 1.6 s, luftiges Rauschen Hochpass 5 kHz -24 dB."""
    d = 1.5
    pad = sum(S.db(g) * S.sine(440.0 * r, d).astype(np.float64) for r, g in ((1.0, 0.0), (2.0, -9.0), (3.0, -15.0)))
    pad = S.apply(pad, S.adsr(d, 0.6, 0.3, 0.75, 0.55, 'exp'))
    air = S.apply(S.highpass(S.noise(d, 'white', seed), 5000.0), S.adsr(d, 0.6, 0.3, 0.75, 0.55))
    x = S.mixdown([(S.widen(S.chorus(pad, 0.3, 0.002, 0.3), 0.3), 0.0, 0.0), (air, 0.0, -24.0)])
    return S.reverb(x, size=0.7, decay=1.6, mix=0.4, seed=seed)


@sound('respect_hush', 'Jeder erwähnte Todesfall (Respekt-Modus)', 1.6, -18, 'respect', fade_in=0.02, fade_out=0.3)
def respect_hush(seed=0):
    """Raumton (pinkes Rauschen Tiefpass 400 Hz, Schwell 800 ms) + einzelner Sinus G3 -18 dB, Hall decay 1.4 s."""
    d = 1.2
    room = S.apply(S.lowpass(S.noise(d, 'pink', seed), 400.0), S.adsr(d, 0.8, 0.1, 0.9, 0.3))
    tone = S.apply(S.sine(196.0, d) + 0.2 * S.sine(392.0, d), S.adsr(d, 0.4, 0.2, 0.8, 0.4, 'exp'))
    x = S.mixdown([(room, 0.0, 0.0), (tone, 0.0, -18.0)])
    return S.reverb(x, size=0.6, decay=1.4, mix=0.3, seed=seed)


# ----------------------------------------------------------------------------------------------------------------
# Allzweck-Töne
# ----------------------------------------------------------------------------------------------------------------

@sound('tick_low', 'Tiefer Holztick (zweite Zählwerk-Stimme, Schritt)', 0.014, -28, 'general', fade_in=0.0003, fade_out=0.004)
def tick_low(seed=0):
    """click(0.014, 1200) + Hauch Holzrauschen 0.8–2 kHz."""
    return S.mixdown([(S.click(0.014, 1200.0), 0.0, 0.0), (S.burst(0.004, 800.0, 2000.0, 0.001, seed=seed), 0.0, -8.0)])


@sound('pop', 'Papier-Pop, Korken, Blase platzt', 0.09, -12, 'general', fade_out=0.006)
def pop(seed=0):
    """Sinus 420 -> 110 Hz 50 ms (env_exp) + Papierstoß 1–3 kHz 8 ms + Klick."""
    return S.mixdown([(_tone(S.sweep(420.0, 110.0, 0.06), 0.06, 0.018), 0.0, 0.0),
                      (S.burst(0.008, 1000.0, 3000.0, 0.002, seed=seed), 0.0, -6.0), (S.click(0.005, 2400.0), 0.0, -12.0)])


@sound('blip', 'Kurzer heller Ton (UI, Zähler, Hinweis); Oktave über dem Grundton', 0.08, -14, 'general', fade_out=0.006)
def blip(seed=0):
    """Mallet-Blip auf der Oktave des Grundtons: Sinus + 3. Teilton, env_exp tau 20 ms."""
    return S.marimba(_hz(key() + 12), 0.08, 0.1, bright=0.3, seed=seed)


@sound('blip_down', 'Abwärts-Blip (Abbruch, Zurück)', 0.1, -14, 'general', fade_out=0.008)
def blip_down(seed=0):
    """Sinus-Sweep Oktave -> Grundton über 80 ms, 2. Teilton, env_exp."""
    return _tone(S.sweep(_hz(key() + 12), _hz(key()), 0.1), 0.1, 0.03, [(2.0, -12.0)])


@sound('whoosh_soft', 'Weicher Luftzug (Sticker gleitet, Kamerafahrt)', 0.4, -14, 'general', fade_in=0.01, fade_out=0.03)
def whoosh_soft(seed=0):
    """Pinkes Rauschen, Bandpass wandert 300 -> 1500 -> 500 Hz, Attack 150 ms, leichte Bewegung von links nach rechts."""
    cut = S.env_lin([(0.0, 300.0), (0.2, 1500.0), (0.4, 500.0)])
    x = S.svf(S.noise(0.4, 'pink', seed), cut, q=1.2, mode='bp')
    x = S.apply(x, S.adsr(0.4, 0.15, 0.05, 0.9, 0.18))
    return S.pan_curve(x, S.sweep(-0.3, 0.3, 0.4, 'lin'))


@sound('whoosh_up', 'Aufwärts-Whoosh (Enthüllung, Aufstieg, Übergang)', 0.5, -10, 'general', fade_in=0.01, fade_out=0.02)
def whoosh_up(seed=0):
    """Weißes Rauschen, Bandpass-Sweep 200 -> 6000 Hz über 450 ms, exponentiell anschwellend, Pan -0.7 -> +0.7, Doppler 0.9 -> 1.1."""
    t = np.arange(_n(0.5)) / SR
    x = S.svf(S.noise(0.5, 'white', seed), S.sweep(200.0, 6000.0, 0.5), q=1.5, mode='bp')
    env = np.exp(3.0 * (np.minimum(t, 0.42) / 0.42 - 1.0)) * S.env_lin([(0.0, 1.0), (0.42, 1.0), (0.5, 0.0)])
    x = S.varispeed(S.apply(x, env), S.sweep(0.9, 1.1, 0.5, 'lin'))
    return S.pan_curve(x, S.sweep(-0.7, 0.7, 0.5, 'lin'))


@sound('drop', 'Fallen und Landen (Gegenstand fällt, Slapstick)', 0.35, -10, 'general', fade_out=0.015)
def drop(seed=0):
    """Sinus 900 -> 120 Hz über 280 ms (2. Teilton) + Landungs-Plop (Sinus 90 Hz + Rauschen Tiefpass 800 Hz) bei 280 ms."""
    fall = S.apply(S.sine(S.sweep(900.0, 120.0, 0.28), 0.28) + 0.25 * S.sine(S.sweep(1800.0, 240.0, 0.28), 0.28), S.adsr(0.28, 0.005, 0.05, 0.8, 0.03))
    plop = S.mixdown([(_tone(90.0, 0.07, 0.02), 0.0, 0.0), (S.burst(0.02, None, 800.0, 0.006, seed=seed), 0.0, -4.0)])
    return S.mixdown([(fall, 0.0, -4.0), (plop, 0.275, 0.0)])


@sound('swell', 'Anschwellen 1.5 s, bricht ab (vor Enthüllung, Schnitt)', 1.5, -12, 'general', fade_in=0.02, fade_out=0.003)
def swell(seed=0):
    """Pinkes Rauschen (Hochpass öffnet 400 -> 80 Hz) + Sägezahn-Fläche auf Grundton und Quinte eine Oktave tiefer (Tiefpass öffnet 300 -> 4000 Hz), exponentieller Anstieg, harter Stopp."""
    T = 1.5
    t = np.arange(_n(T)) / SR
    env = np.exp(3.5 * (t / T - 1.0))
    nz = S.svf(S.noise(T, 'pink', seed), S.sweep(400.0, 80.0, T), q=0.8, mode='hp')
    root = key() - 12
    pad = S.supersaw(_hz(root), T, n=3, detune=0.006, seed=seed) + 0.7 * S.supersaw(_hz(root + 7), T, n=3, detune=0.006, seed=seed + 1)
    pad = S.svf(pad, S.sweep(300.0, 4000.0, T), q=1.0, mode='lp')
    return S.mixdown([(S.apply(nz, env), 0.0, 0.0), (S.apply(pad, env), 0.0, -5.0)])


@sound('sub_hit', 'Tiefer Schlag (Pointe, Schnitt, Impact)', 0.5, -8, 'general', fade_out=0.03)
def sub_hit(seed=0):
    """Sinus 130 -> 52 Hz in 40 ms, dann 52 Hz, env_exp 120 ms, Drive 0.25, kurzer Klick."""
    f = np.concatenate([S.sweep(130.0, 52.0, 0.04), np.full(_n(0.46), 52.0, np.float32)])
    body = S.drive(_tone(f, 0.5, 0.12), 0.25)
    return S.mixdown([(body, 0.0, 0.0), (S.burst(0.006, None, 3000.0, 0.0015, seed=seed), 0.0, -14.0)])


@sound('boom_far', 'Ferner Donner-/Explosionsschlag (Einsturz, Kanone, weit weg)', 1.2, -10, 'general', fade_in=0.004, fade_out=0.15)
def boom_far(seed=0):
    """Braunes Rauschen Tiefpass 200 Hz + Sinus 45 Hz + Anschlag Tiefpass 600 Hz, Hall size 1.0 decay 1.2, Distanz-Tiefpass 400 Hz."""
    x = S.mixdown([(S.apply(S.lowpass(S.noise(0.9, 'brown', seed), 200.0), S.env_exp(0.9, 0.25)), 0.0, 0.0),
                   (_tone(45.0, 0.9, 0.3), 0.0, -2.0), (S.burst(0.03, None, 600.0, 0.01, seed=seed + 1), 0.0, -2.0)])
    return S.lowpass(S.reverb(x, size=1.0, decay=1.2, mix=0.35, seed=seed), 400.0)


@sound('ping', 'Heller Ping (Hinweis, Treffer); Oktave über dem Grundton', 0.5, -12, 'general', fade_out=0.02)
def ping(seed=0):
    """Glas auf der Oktave des Grundtons (Decay 450 ms) + Mallet-Körper -8 dB."""
    f = _hz(key() + 12)
    return S.mixdown([(S.pan(S.glass(f, 0.5, 0.45), 0.1), 0.0, 0.0), (S.marimba(f, 0.3, 0.2, seed=seed), 0.0, -8.0)])


@sound('ping_low', 'Warmer tiefer Ping (Holz); Grundton eine Oktave tiefer', 0.6, -12, 'general', fade_out=0.02)
def ping_low(seed=0):
    """Marimba auf dem Grundton eine Oktave tiefer (Decay 500 ms) + Glas auf dem Grundton -10 dB."""
    return S.mixdown([(S.marimba(_hz(key() - 12), 0.6, 0.5, seed=seed), 0.0, 0.0), (S.glass(_hz(key()), 0.5, 0.4), 0.005, -10.0)])


@sound('shimmer', 'Glitzern, Magie, Enthüllung (weich, breit)', 1.2, -14, 'general', fade_in=0.01, fade_out=0.15)
def shimmer(seed=0):
    """8 Glas-Pings 4–9 kHz, Einsätze über 600 ms gestreut, Decay 600 ms, zufällig gepannt, Chorus, widen 0.5."""
    rng = _rng(seed, 9)
    freqs = np.exp(rng.uniform(np.log(4000.0), np.log(9000.0), 8))
    items = [(S.pan(S.glass(f, 0.7, 0.6), p), t, g) for f, p, t, g in zip(freqs, rng.uniform(-0.8, 0.8, 8), np.sort(rng.uniform(0.0, 0.6, 8)), rng.uniform(-6.0, 0.0, 8))]
    return S.widen(S.chorus(S.mixdown(items), rate=0.4, depth=0.002, mix=0.3), 0.5)


@sound('bell', 'Glocke auf dem Grundton (Erkenntnis, Stunde, Pointe)', 1.0, -10, 'general', fade_out=0.04)
def bell_(seed=0):
    """bell(Grundton, 1 s, ratio 1.4) + Glas auf der Oktave -12 dB + leiser Sinus-Hum eine Oktave tiefer."""
    f = _hz(key())
    return S.mixdown([(S.bell(f, 1.0, 1.4), 0.0, 0.0), (S.pan(S.glass(f * 2.0, 0.8, 0.6), 0.2), 0.004, -12.0), (_tone(f * 0.5, 0.9, 0.25), 0.0, -16.0)])


@sound('sparkle', 'Funkeln (kurz, hell, verstreut)', 0.6, -14, 'general', fade_out=0.03)
def sparkle(seed=0):
    """12 winzige Glas-Pings 5–10 kHz (Decay 60 ms) zu zufälligen Zeiten über 450 ms, zufällig gepannt, widen 0.6."""
    rng = _rng(seed, 10)
    freqs = np.exp(rng.uniform(np.log(5000.0), np.log(10000.0), 12))
    items = [(S.pan(S.glass(f, 0.1, 0.06), p), t, g) for f, p, t, g in zip(freqs, rng.uniform(-0.8, 0.8, 12), rng.uniform(0.0, 0.45, 12), rng.uniform(-5.0, 0.0, 12))]
    return S.widen(S.mixdown(items), 0.6)


@sound('type', 'Tastatur-Tick (je Zeichen)', 0.03, -20, 'general', fade_in=0.0003, fade_out=0.006)
def type_(seed=0):
    """Klick 2.6 kHz 8 ms + Rauschen 2–5 kHz 5 ms + Thock Sinus 180 Hz 20 ms."""
    return S.mixdown([(S.click(0.008, 2600.0), 0.0, 0.0), (S.burst(0.005, 2000.0, 5000.0, 0.0012, seed=seed), 0.0, -4.0), (_tone(180.0, 0.025, 0.006), 0.0, -8.0)])


@sound('count', 'Schneller Tick-Lauf 0.6 s (Zählwerk, Countdown)', 0.6, -18, 'general', fade_out=0.008)
def count(seed=0):
    """12 Ticks click(0.012, 3000) im Abstand 50 ms mit leichter Pegelstreuung, der letzte eine Spur höher."""
    rng = _rng(seed, 12)
    items = [(S.click(0.012, 3000.0 if k < 11 else 3400.0), 0.05 * k, float(rng.uniform(-2.0, 0.0))) for k in range(12)]
    return S.mixdown(items)


@sound('reverse_cymbal', 'Rückwärts-Becken 1.2 s (Anlauf auf einen Schnitt)', 1.2, -12, 'general', fade_in=0.01, fade_out=0.006)
def reverse_cymbal(seed=0):
    """Metallische Rechtecke (808-Verhältnisse) + Rauschen Hochpass 4 kHz, umgekehrte Exponentialhüllkurve, Hochpass öffnet 6 -> 1.5 kHz, breit."""
    T = 1.2
    t = np.arange(_n(T)) / SR
    metal = sum(S.square(40.0 * r, T).astype(np.float64) for r in (2.0, 3.0, 4.16, 5.43, 6.79, 8.21)) / 6.0
    metal = S.bandpass(metal, 4000.0, 14000.0)
    nz = S.highpass(S.noise(T, 'white', seed), 4000.0)
    x = S.svf(0.7 * metal + 0.7 * nz, S.sweep(6000.0, 1500.0, T), q=0.8, mode='hp')
    x = S.apply(x, np.exp(5.0 * (t / T - 1.0)))
    return S.widen(S.chorus(x, 0.6, 0.002, 0.4), 0.5)


@sound('glitch', 'Digitaler Störer (Fehler, Störung, Glitch-Schnitt)', 0.25, -12, 'general', fade_in=0.0005, fade_out=0.004)
def glitch(seed=0):
    """Rechtecke 2.2 kHz + 1.37 kHz bitcrushed (5 Bit, 9 kHz), Tiefpass 5 kHz + Rauschen 2–6 kHz, Zufallsgates 8 ms, Pan springt je Block."""
    rng = _rng(seed, 13)
    x = S.bitcrush(0.5 * S.square(2200.0, 0.25) + 0.5 * S.square(1370.0, 0.25), bits=5, rate=9000.0)
    x = S.lowpass(x, 5000.0) + 0.4 * S.bandpass(S.noise(0.25, 'white', seed), 2000.0, 6000.0)
    x = _gated(x, 0.008, 0.55, seed, smooth=0.001)
    pos = np.repeat(rng.uniform(-0.8, 0.8, 32), _n(0.008))[:_n(0.25)]
    w = _n(0.001)
    pos = np.convolve(pos, np.ones(w) / w, mode='same')
    return S.pan_curve(x, pos)


@sound('static', 'Radio-Rauschen, Störung 0.8 s', 0.8, -16, 'general', fade_in=0.05, fade_out=0.1)
def static(seed=0):
    """Weißes Rauschen Bandpass 0.8–6 kHz mit Knister-Gates (3 ms) + 30 Knackser 2–8 kHz, Stereo gestreut."""
    nz = _gated(S.bandpass(S.noise(0.8, 'white', seed), 800.0, 6000.0), 0.003, 0.7, seed)
    return S.mixdown([(S.widen(S.pan(nz, 0.0), 0.3), 0.0, 0.0), (S.shaker(30, 0.8, 2000.0, 8000.0, 0.004, seed=seed + 1), 0.0, -4.0)])


@sound('cash', "Kassen-Klingeln 'ka-ching' (Geld, Gewinn)", 0.6, -10, 'general', fade_out=0.03)
def cash(seed=0):
    """'ka': Rauschen Tiefpass 2.5 kHz 25 ms + Klick + Schubladen-Schleifen 0.4–1.2 kHz; 'ching' bei 90 ms: bell C7 + E7 (ratio 1.5) + 3 Glas-Funken."""
    rng = _rng(seed, 14)
    items = [(S.burst(0.025, None, 2500.0, 0.006, seed=seed), 0.0, -2.0), (S.click(0.006, 1500.0), 0.0, -6.0),
             (S.burst(0.06, 400.0, 1200.0, 0.02, seed=seed + 1), 0.01, -10.0),
             (S.pan(S.bell(2093.0, 0.5, 1.5), -0.15), 0.09, 0.0), (S.pan(S.bell(2637.0, 0.5, 1.5), 0.15), 0.1, -3.0)]
    items += _glass_items(np.exp(rng.uniform(np.log(6000.0), np.log(8500.0), 3)), 0.1, 0.025, 0.3, 0.25, rng.uniform(-0.5, 0.5, 3), -14.0)
    return S.mixdown(items)


@sound('lock_click', 'Schloss, Riegel, Verschluss (klick-klack)', 0.18, -12, 'general', fade_out=0.01)
def lock_click(seed=0):
    """Klick (Rauschen 2–5 kHz 3 ms + Sinus 1.3 kHz 12 ms), Klack bei 70 ms (Sinus 160 Hz 50 ms + Rauschen Tiefpass 1.5 kHz) + Metallring 3.1 kHz -14 dB."""
    return S.mixdown([(S.burst(0.003, 2000.0, 5000.0, 0.0008, seed=seed), 0.0, 0.0), (_tone(1300.0, 0.012, 0.004), 0.0, -4.0),
                      (_tone(160.0, 0.05, 0.014), 0.07, 0.0), (S.burst(0.015, None, 1500.0, 0.004, seed=seed + 1), 0.07, -3.0),
                      (S.glass(3100.0, 0.06, 0.05), 0.07, -14.0)])


@sound('glass', 'Glas-Ping (Glas, Kristall, Edelstein, Anstoßen)', 0.5, -12, 'general', fade_out=0.02)
def glass_(seed=0):
    """Glas 2.4 kHz (Decay 450 ms) + Glas ×1.49 -8 dB + winziger Tink, breit."""
    return S.widen(S.mixdown([(S.pan(S.glass(2400.0, 0.5, 0.45), -0.1), 0.0, 0.0), (S.pan(S.glass(3576.0, 0.4, 0.3), 0.15), 0.002, -8.0),
                              (S.burst(0.002, 4000.0, 10000.0, 0.0005, seed=seed), 0.0, -10.0)]), 0.4)


@sound('bubbles', 'Mehrere Blasen (Ozean, Trank, Kochen)', 0.8, -14, 'general', fade_out=0.02)
def bubbles(seed=0):
    """9 Blasen-Chirps (Sinus f0 -> 3·f0, 20–35 ms, Resonanz q 8), f0 220–700 Hz, zufällig in Zeit, Pan und Pegel."""
    rng = _rng(seed, 15)
    items = []
    for k in range(9):
        f0, d = rng.uniform(220.0, 700.0), rng.uniform(0.02, 0.035)
        f = np.concatenate([S.sweep(f0, f0 * 3.0, d), np.full(_n(0.04), f0 * 3.0, np.float32)])
        exc = S.apply(S.sine(f, d + 0.04), S.env_exp(d + 0.04, d * 0.5))
        items.append((S.pan(S.svf(exc, f * 1.1, q=8.0, mode='lp'), rng.uniform(-0.6, 0.6)), rng.uniform(0.0, 0.7), rng.uniform(-8.0, 0.0)))
    return S.mixdown(items)


@sound('wind', 'Wind 1.5 s (Höhe, Weite, Draußen)', 1.5, -16, 'general', fade_in=0.3, fade_out=0.3)
def wind(seed=0):
    """Pinkes Rauschen je Kanal, Bandpass wandert mit LFO 0.7 Hz zwischen 250 und 750 Hz (q 1.3), weiche Schwellung."""
    T = 1.5
    t = np.arange(_n(T)) / SR
    ch = []
    for c in range(2):
        cut = 250.0 + 500.0 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.7 * t + 1.3 * c))
        x = S.svf(S.noise(T, 'pink', seed + c), cut, q=1.3, mode='bp')
        ch.append(S.apply(x, 0.4 + 0.6 * np.sin(np.pi * t / T) ** 2))
    return np.stack(ch, axis=1)


@sound('thunder', 'Donner 1.5 s (Gewitter, Drama)', 1.5, -8, 'general', fade_in=0.002, fade_out=0.25)
def thunder(seed=0):
    """Crack (Rauschen 0.6–3.5 kHz 40 ms) + Grollen (braunes Rauschen Tiefpass 160 Hz, unruhig moduliert) + Sub 42 Hz, Hall size 1.0 decay 1.6."""
    rng = _rng(seed, 16)
    d = 1.1
    t = np.arange(_n(d)) / SR
    mod = 1.0 + 0.5 * np.sin(2 * np.pi * rng.uniform(3.0, 5.0) * t + rng.uniform(0, 6.28)) * np.sin(2 * np.pi * 0.8 * t)
    rum = S.apply(S.lowpass(S.noise(d, 'brown', seed), 160.0), S.env_exp(d, 0.45) * mod)
    x = S.mixdown([(S.burst(0.04, 600.0, 3500.0, 0.012, seed=seed + 1), 0.0, -3.0), (rum, 0.02, 0.0), (_tone(42.0, d, 0.35), 0.03, -4.0)])
    return S.reverb(x, size=1.0, decay=1.6, mix=0.3, predelay=0.03, seed=seed)


@sound('laugh_tiny', 'Kleiner Comedy-Akzent des Maskottchens (hehe)', 0.3, -12, 'odd', fade_out=0.01)
def laugh_tiny(seed=0):
    """Vier Formant-Blips bei 16 Hz, 1300 -> 880 Hz fallend, je mit kleinem Abwärts-Glissando, Hauch Atem."""
    rng = _rng(seed, 17)
    items = []
    for k, f in enumerate((1300.0, 1150.0, 1000.0, 880.0)):
        fj = f * rng.uniform(0.97, 1.03)
        x = _tone(fj * np.linspace(1.0, 0.92, _n(0.045)), 0.045, 0.02, [(2.0, -10.0)])
        x = 0.5 * x + 1.0 * S.svf(x, 900.0, q=0.9, mode='bp')
        items.append((S.apply(x, S.adsr(0.045, 0.004, 0.02, 0.5, 0.02)), 0.06 * k, -1.0 * k))
    items.append((S.apply(S.highpass(S.noise(0.26, 'white', seed), 2000.0), S.env_lin([(0.0, 0.3), (0.2, 1.0), (0.26, 0.0)])), 0.0, -26.0))
    return S.mixdown(items)


@sound('record_scratch', 'Kurzer Plattenkratzer (Stopp, Pointe)', 0.35, -8, 'general', fade_in=0.002, fade_out=0.01)
def record_scratch(seed=0):
    """Dreieck 180 Hz + Rauschen 400–3000 Hz, Varispeed-Zickzack (+2.5 / -2.2 / +1.8 / -1.0), Bandpass 500–4000 Hz, zwei Striche."""
    src = 0.7 * S.lowpass(S.tri(180.0, 0.6), 2500.0) + 0.5 * S.bandpass(S.noise(0.6, 'white', seed), 400.0, 3000.0)
    ratio = np.concatenate([np.full(_n(0.1), 2.5), np.full(_n(0.1), -2.2), np.full(_n(0.08), 1.8), np.full(_n(0.07), -1.0)])
    x = S.varispeed(src, ratio, start=0.25)
    x = S.lowpass(S.bandpass(x, 500.0, 4000.0), 3500.0)
    env = S.env_lin([(0.0, 0.0), (0.01, 1.0), (0.09, 0.8), (0.1, 0.2), (0.11, 1.0), (0.2, 0.7), (0.21, 0.3), (0.28, 0.9), (0.35, 0.0)])
    return S.drive(S.apply(x, env), 0.2)


@sound('drumroll', 'Trommelwirbel 1.2 s mit Schlussakzent', 1.2, -10, 'general', fade_out=0.03)
def drumroll(seed=0):
    """Bursts (Rauschen 250–400 Hz + 1.5–5 kHz, Sinus 190 Hz) von 15 auf 26 Hz beschleunigend, Crescendo -14 -> 0 dB, Hände L/R; Akzent bei 1.08 s."""
    items = []
    for k, tt in enumerate(_accel_times(0.0, 1.05, 15.0, 26.0)):
        hit = S.mixdown([(S.burst(0.03, 250.0, 400.0, 0.008, seed=seed + k), 0.0, 0.0), (S.burst(0.02, 1500.0, 5000.0, 0.004, seed=seed + 100 + k), 0.0, -10.0),
                         (_tone(190.0, 0.03, 0.012), 0.0, -3.0)])
        items.append((S.pan(hit, -0.2 if k % 2 else 0.2), float(tt), -14.0 + 14.0 * tt / 1.05))
    items.append((S.snare(0.12, 190.0, seed=seed + 999), 1.08, 3.0))
    return S.mixdown(items)
