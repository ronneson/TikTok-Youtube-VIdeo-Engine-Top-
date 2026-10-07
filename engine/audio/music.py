"""Musikbetten: generativ, szenenbewusst, komplett synthetisiert (STIL.md 6.3, design/sounds.json ``beds``).

Öffentliche Schnittstelle
    BEDS                      {id: {'mood', 'bpm', 'key', 'themes', 'desc', ...}} – die sieben Betten aus STIL.md 6.3
    pick(theme, mood=None)    Bett-ID zu einem Thema aus engine.theme (unbekannte IDs über den längsten gemeinsamen
                              Präfix, z. B. orbit_glow_ocean -> orbit_glow; sonst cabinet_swing); ``mood`` wählt
                              nach Stimmungs-Tag ('respect' -> parlour_waltz)
    key(bed_id)               MIDI-Grundton der Tonart in der Leiter-Oktave (STIL.md 6.1: Oktave 5 bis F, sonst 4),
                              für sfx.set_key
    ladder(bed_id, total=5)   Rang-Leiter 1-2-4-5-8: Liste, Index rank-1 -> MIDI (#5 Grundton … #1 Oktave;
                              #10 … #6 eine Oktave tiefer)
    render(bed_id, duration, seed=0, sections=None, energy=None) -> Stereo float32, exakt ``duration`` Sekunden
    render_all(out_dir, seconds=30) -> [{'id', 'file', ...}]   (Befehl: python3 -m engine music)
    catalog() -> [{'id', 'mood', 'bpm', 'key', 'themes', 'desc'}]

Struktur (``sections`` aus mix.sections_from: [{'t0', 't1', 'kind', 'rank', 'energy', 'respect'?}]):
    Die Musik folgt den Szenen. Ein fester Beat-Raster liegt unter dem ganzen Video; jeder Szenenbeginn (t0 eines
    Eintrags) wird auf den nächsten Beat gerundet und ist ein neuer Taktanfang: Akkordwechsel, ein Beat
    Schlagwerkpause, Akzentlauf (je Bett: Marimba-Lauf, Bongo-Fill, Lichtkegel-Sweep, Kalimba-Glissando, Arpeggio
    eine Oktave höher, Spieluhr-Lauf) und einen Takt vorher ein Rausch-Swell. Der Hook beginnt mit einem 2-Takt-Riser.
    Energie (0..1) schaltet Schichten additiv zu: Schwellen 0.3 / 0.5 / 0.65 / 0.8 / 0.9 (THRESHOLDS); das Pad liegt
    immer darunter. Rang 1 ist der Höhepunkt (alle Schichten + Glas-Crash). Respekt-Abschnitte (``respect``: True)
    spielen nur die Pad-Schichten, ohne Akzent, mit mehr Hall. Das Outro löst in zwei Takten nach Dur auf; der
    Schlussakkord (Pad + Anschlag) klingt bis zum Ende nach, Perkussion und Bass schweigen.

Technik: Sequencer auf Sample-Basis. Noten (Zeit, Instrument, MIDI, Anschlag, Pan, Bus) werden aus Taktraster,
Akkordfolge (4–8 Takte, Variante über ``seed``) und generativen Motiven geplant, leicht humanisiert (±4 ms, ±6 %
Anschlag), je Instrument/Tonhöhe/Dauer einmal mit engine.audio.synth gerendert und zwischengespeichert, dann in vier
Busse (pad, mel, perc, fx) summiert, je Bett nachbearbeitet (Filter-LFO, Sidechain), mit einem Faltungshall versehen
und durch Hochpass + sanften Lookahead-Limiter (-3 dBFS) gegeben. Alles numpy/scipy, deterministisch über ``seed``.
"""
from __future__ import annotations
import math
import os
import time
import numpy as np
from scipy import signal as sps
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from . import SR, wav
from . import synth as S

THRESHOLDS = [0.3, 0.5, 0.65, 0.8, 0.9]      # Energie-Schwellen der fünf Zusatzschichten
LADDER = [0, 2, 5, 7, 12]                   # Stufen 1-2-4-5-8 als Halbtöne über dem Grundton (#5 … #1)
RESPECT_ENERGY = 0.2                        # Energie in Respekt-Abschnitten
PEAK_DB = -3.0                              # Spitze des fertigen Betts
RMS_DB = -21.0                              # Zielpegel (RMS über das ganze Bett) vor dem Limiter
DEFAULT_BED = 'cabinet_swing'

_PC = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8,
       'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}

# Akkordqualitäten als Halbtonintervalle über dem Akkordgrundton
QUAL = {
    'maj': (0, 4, 7), 'min': (0, 3, 7), 'maj7': (0, 4, 7, 11), 'min7': (0, 3, 7, 10), 'dom7': (0, 4, 7, 10),
    'm7b5': (0, 3, 6, 10), 'sus2': (0, 2, 7), 'sus4': (0, 5, 7), 'add9': (0, 4, 7, 14), 'maj9': (0, 4, 7, 11, 14),
    'min9': (0, 3, 7, 10, 14), 'maj6': (0, 4, 7, 9), 'min6': (0, 3, 7, 9), 'dim': (0, 3, 6),
}

# ---------------------------------------------------------------------------------------------------------------
# Die sieben Betten (STIL.md 6.3). Akkorde als (Halbtöne über dem Grundton, Qualität); 'progressions' = Varianten
# der Schleife (Wahl über seed), 'cadence' = zwei Takte Auflösung vor dem Schlussakkord 'final' (Dur).
# ---------------------------------------------------------------------------------------------------------------

BEDS = {
    'cabinet_swing': {
        'mood': 'Wunderkammer, verschmitzt, staunend', 'moods': ['curious', 'playful', 'wonder', 'default'],
        'bpm': 112, 'key': 'D dorian', 'root': 'D', 'mode': 'dorian', 'meter': 4, 'swing': 0.58,
        'themes': ['curious', 'crime'],
        'desc': 'Walking-Bass (pluck) -> Marimba-Stabs auf 2 und 4 -> Besen-Hi-Hat + Fingersnap -> Kalimba-Gegenstimme '
                '-> Glas-Glocke auf der 1. Nummernwechsel: Marimba-Lauf, Schlagwerk pausiert einen Beat.',
        'progressions': [
            [(0, 'min7'), (0, 'min7'), (5, 'dom7'), (5, 'dom7'), (2, 'min7'), (7, 'min7'), (0, 'min7'), (0, 'min7')],
            [(0, 'min7'), (3, 'maj7'), (5, 'dom7'), (0, 'min7'), (0, 'min7'), (2, 'min7'), (7, 'min7'), (5, 'dom7')],
            [(0, 'min9'), (0, 'min9'), (5, 'dom7'), (2, 'min7'), (0, 'min7'), (10, 'maj7'), (7, 'min7'), (5, 'dom7')],
        ],
        'cadence': [(2, 'min7'), (7, 'dom7')], 'final': (0, 'maj'),
        'reverb': {'size': 0.3, 'decay': 0.9, 'mix': 0.12}, 'pad': 'pad_warm', 'variant': 'cabinet',
    },
    'heist_tiptoe': {
        'mood': 'Schleichen, Spionage, Augenzwinkern', 'moods': ['sneaky', 'spy', 'tension', 'heist'],
        'bpm': 100, 'key': 'E minor', 'root': 'E', 'mode': 'minor', 'meter': 4, 'swing': 0.55,
        'themes': ['heist'],
        'desc': 'Pizzicato-Bass auf den Offbeats + Vibraphon-Akkorde -> Holzblock + Bongo-Pops -> Dreieck-Melodie mit '
                'kleiner Sexte -> Laser-Mint-Arpeggio (square 1/16) -> Shaker. Nummernwechsel: Bongo-Fill.',
        'progressions': [
            [(0, 'min'), (0, 'min'), (5, 'min'), (7, 'dom7'), (0, 'min'), (8, 'maj'), (5, 'min'), (7, 'dom7')],
            [(0, 'min'), (0, 'min6'), (5, 'min'), (7, 'dom7'), (0, 'min'), (3, 'maj'), (5, 'min7'), (7, 'dom7')],
            [(0, 'min'), (8, 'maj7'), (5, 'min'), (7, 'dom7'), (0, 'min'), (10, 'maj'), (8, 'maj'), (7, 'dom7')],
        ],
        'cadence': [(5, 'min'), (7, 'dom7')], 'final': (0, 'maj'),
        'reverb': {'size': 0.35, 'decay': 1.0, 'mix': 0.16}, 'pad': 'pad_dark', 'variant': 'heist',
    },
    'cave_drip': {
        'mood': 'Tiefe, Echo, Staunen ohne Grusel', 'moods': ['deep', 'calm', 'echo', 'cave'],
        'bpm': 84, 'key': 'A minor', 'root': 'A', 'mode': 'minor', 'meter': 4, 'swing': 0.5,
        'themes': ['cave'],
        'desc': 'Supersaw-Pad (2 Stimmen, lowpass 300 Hz, Filter-LFO 0.1 Hz) -> Sub-Herzschlag -> pentatonische '
                'Drip-Pings mit Delay 375 ms -> Marimba-Bass auf 1 und 3+ -> Holzpuls -> Glas. Hall 1.6 s. '
                'Nummernwechsel: Lichtkegel-Sweep.',
        'progressions': [
            [(0, 'min'), (0, 'min'), (8, 'maj'), (8, 'maj'), (3, 'maj'), (3, 'maj'), (7, 'min'), (7, 'min')],
            [(0, 'min9'), (0, 'min9'), (5, 'min'), (5, 'min'), (0, 'min'), (0, 'min'), (7, 'min7'), (10, 'maj')],
            [(0, 'min'), (0, 'min'), (3, 'maj7'), (3, 'maj7'), (8, 'maj'), (8, 'maj'), (10, 'maj'), (10, 'maj')],
        ],
        'cadence': [(5, 'min'), (7, 'dom7')], 'final': (0, 'maj'),
        'reverb': {'size': 0.8, 'decay': 1.6, 'mix': 0.32}, 'pad': 'pad_saw', 'variant': 'cave',
    },
    'safari_bounce': {
        'mood': 'Hüpfend, hell, neugierig', 'moods': ['bouncy', 'bright', 'funny', 'animal', 'food'],
        'bpm': 124, 'key': 'G major', 'root': 'G', 'mode': 'major', 'meter': 4, 'swing': 0.52,
        'themes': ['animal', 'food'],
        'desc': 'Kalimba gebrochene Dreiklänge + Bass mit Pitch-Drop -> Shaker Sechzehntel -> Holzblock-Clave 3-2 -> '
                'Pfeif-Melodie alle 4 Takte -> Glocke. Nummernwechsel: Kalimba-Glissando + Clave-Fill.',
        'progressions': [
            [(0, 'maj'), (5, 'maj'), (0, 'maj'), (7, 'maj'), (0, 'maj'), (5, 'maj'), (7, 'dom7'), (0, 'maj')],
            [(0, 'maj'), (9, 'min'), (5, 'maj'), (7, 'maj'), (0, 'maj'), (2, 'min7'), (7, 'dom7'), (0, 'maj')],
            [(0, 'maj6'), (5, 'maj7'), (9, 'min7'), (7, 'dom7'), (0, 'maj'), (5, 'maj'), (7, 'dom7'), (0, 'maj6')],
        ],
        'cadence': [(5, 'maj'), (7, 'dom7')], 'final': (0, 'maj'),
        'reverb': {'size': 0.3, 'decay': 0.8, 'mix': 0.12}, 'pad': 'pad_light', 'variant': 'safari',
    },
    'orbit_glow': {
        'mood': 'Weite, Schweben, Glanz', 'moods': ['space', 'float', 'glow', 'ocean', 'dreamy'],
        'bpm': 96, 'key': 'F# lydian', 'root': 'F#', 'mode': 'lydian', 'meter': 4, 'swing': 0.5,
        'themes': ['space', 'ocean'],
        'desc': 'Sinus-Cluster-Pad -> Sub -> Square-Arpeggio mit ADSR-Filter und Delay 3/16 -> weicher Sinus-Kick mit '
                'Sidechain -> Glas-Sparkle -> hohe Glocke. Nummernwechsel: Arpeggio eine Oktave höher für einen Takt. '
                '(orbit_glow_ocean wird auf dieses Bett abgebildet.)',
        'progressions': [
            [(0, 'maj7'), (0, 'maj7'), (2, 'maj'), (2, 'maj'), (0, 'maj7'), (7, 'maj'), (9, 'min7'), (2, 'maj')],
            [(0, 'maj9'), (2, 'maj'), (0, 'maj9'), (9, 'min7'), (0, 'maj7'), (2, 'maj'), (7, 'maj7'), (7, 'maj7')],
            [(0, 'maj7'), (0, 'maj7'), (9, 'min7'), (9, 'min7'), (2, 'maj'), (2, 'maj'), (0, 'maj7'), (7, 'maj')],
        ],
        'cadence': [(2, 'maj'), (7, 'maj')], 'final': (0, 'maj7'),
        'reverb': {'size': 0.7, 'decay': 1.5, 'mix': 0.28}, 'pad': 'pad_cluster', 'variant': 'orbit',
    },
    'parlour_waltz': {
        'mood': 'Salon, Spieluhr, zart', 'moods': ['respect', 'tender', 'history', 'waltz', 'memorial'],
        'bpm': 72, 'key': 'Bb major', 'root': 'Bb', 'mode': 'major', 'meter': 3, 'swing': 0.5,
        'themes': ['history'],
        'desc': 'Spieluhr-Melodie + gestrichenes Pad (Respekt-Schichten) -> Pizzicato auf 1 -> Cembalo-Arpeggio -> '
                'weiche Pauke -> Spieluhr-Oktave + Glocke. B-Dur und g-Moll wechseln. Respekt: nur Spieluhr + Pad, '
                'Energie 0.2, mehr Hall, kein Akzent.',
        'progressions': [
            [(0, 'maj'), (5, 'maj'), (7, 'dom7'), (0, 'maj'), (9, 'min'), (2, 'min'), (2, 'dom7'), (9, 'min')],
            [(0, 'maj'), (7, 'dom7'), (0, 'maj'), (0, 'maj6'), (9, 'min'), (2, 'dom7'), (9, 'min'), (5, 'maj')],
            [(0, 'maj'), (9, 'min'), (5, 'maj'), (7, 'dom7'), (9, 'min'), (5, 'maj'), (2, 'dom7'), (9, 'min')],
        ],
        'cadence': [(5, 'maj'), (7, 'dom7')], 'final': (0, 'maj'),
        'reverb': {'size': 0.5, 'decay': 1.4, 'mix': 0.26}, 'pad': 'pad_bow', 'variant': 'parlour',
    },
    'cabinet_swing_pulse': {
        'mood': 'Nachtvisite, Klinik mit Augenzwinkern', 'moods': ['medical', 'clinic', 'pulse'],
        'bpm': 104, 'key': 'D dorian', 'root': 'D', 'mode': 'dorian', 'meter': 4, 'swing': 0.56,
        'themes': ['medical'],
        'desc': 'Wie cabinet_swing bei 104 BPM; Fingersnap ersetzt durch Herzschlag auf 1 und 3, Monitor-Piep auf der 4.',
        'progressions': None,                 # wie cabinet_swing
        'cadence': [(2, 'min7'), (7, 'dom7')], 'final': (0, 'maj'),
        'reverb': {'size': 0.3, 'decay': 0.9, 'mix': 0.12}, 'pad': 'pad_warm', 'variant': 'pulse',
    },
}
BEDS['cabinet_swing_pulse']['progressions'] = BEDS['cabinet_swing']['progressions']


# ---------------------------------------------------------------------------------------------------------------
# Auswahl, Tonart, Leiter
# ---------------------------------------------------------------------------------------------------------------

def resolve(bed_id, default: str = DEFAULT_BED) -> str:
    """Bett-ID auflösen: exakt, sonst das Bett, dessen ID der längste gemeinsame Präfix ist (orbit_glow_ocean ->
    orbit_glow), sonst ``default`` (None -> KeyError)."""
    name = str(bed_id or '').strip().lower()
    if name in BEDS:
        return name
    best, best_len = None, 0
    for bid in BEDS:
        if name.startswith(bid) and len(bid) > best_len:
            best, best_len = bid, len(bid)
    if best is None:
        for bid in BEDS:
            k = 0
            for a, b in zip(name, bid):
                if a != b:
                    break
                k += 1
            if k >= 5 and k > best_len:
                best, best_len = bid, k
    if best is not None:
        return best
    if default is None:
        raise KeyError(f"unbekanntes Musikbett: {bed_id!r} ({', '.join(BEDS)})")
    return default


def pick(theme: str = 'auto', mood: str = None) -> str:
    """Bett zu einem Thema (engine.theme.bed) oder einer Stimmung. Jedes Thema aus theme.names() bekommt ein Bett;
    'auto'/None/unbekannt -> cabinet_swing. ``mood`` ('respect', 'sneaky', 'bouncy', …) hat Vorrang."""
    if mood:
        m = str(mood).strip().lower()
        for bid, b in BEDS.items():
            if m == bid or m in b.get('moods', ()):
                return bid
    name = str(theme or 'auto').strip().lower()
    if name in BEDS or any(name.startswith(b) for b in BEDS):
        return resolve(name)
    try:
        from .. import theme as T
        if name in T.names():
            return resolve(T.bed(name))
    except Exception:
        pass
    return DEFAULT_BED


def key(bed_id: str) -> int:
    """MIDI-Grundton des Betts in der Leiter-Oktave (STIL.md 6.1): Oktave 5 für Grundtöne bis F, sonst Oktave 4
    (D -> D5 = 74, E -> 76, A -> A4 = 69, G -> 67, F# -> 66, Bb -> 70)."""
    pc = _PC[BEDS[resolve(bed_id)]['root']]
    octave = 5 if pc <= 5 else 4
    return (octave + 1) * 12 + pc


def ladder(bed_id: str, total: int = 5) -> list:
    """Rang-Leiter: Liste der Länge ``total``; Index rank-1 -> MIDI. Stufen 1-2-4-5-8 über key(bed_id):
    #5 Grundton, #4 Sekunde, #3 Quarte, #2 Quinte, #1 Oktave; #10 … #6 eine Oktave tiefer usw."""
    root = key(bed_id)
    total = max(1, int(total))
    return [ladder_note(bed_id, r, total) for r in range(1, total + 1)]


def ladder_note(bed_id: str, rank: int, total: int = 5) -> int:
    """Leiterton eines Rangs (1 = Spitze). Ränge über 5 liegen gruppenweise eine Oktave tiefer."""
    rank = int(max(1, rank))
    group, k = divmod(rank - 1, 5)
    return key(bed_id) + LADDER[4 - k] - 12 * group


def catalog() -> list:
    return [{'id': bid, 'mood': b['mood'], 'bpm': b['bpm'], 'key': b['key'], 'meter': f"{b['meter']}/4",
             'themes': list(b['themes']), 'desc': b['desc']} for bid, b in BEDS.items()]


def _root_midi(bed: dict, octave: int = 3) -> int:
    return (octave + 1) * 12 + _PC[bed['root']]


def _scale(bed: dict, lo: int, hi: int) -> list:
    """Alle Töne der Bett-Tonleiter zwischen lo und hi (MIDI, inklusive)."""
    steps = S.MODES[bed['mode']]
    pc0 = _PC[bed['root']]
    return [m for m in range(lo, hi + 1) if (m - pc0) % 12 in steps]


class _Chord:
    __slots__ = ('root', 'tones', 'pcs', 'qual', 'idx')

    def __init__(self, bed: dict, spec: tuple, idx: int):
        off, qual = spec
        self.root = _root_midi(bed, 3) + off           # Akkordgrundton in Oktave 3 (bzw. darüber)
        if self.root > _root_midi(bed, 3) + 7:
            self.root -= 12
        self.tones = QUAL[qual]
        self.pcs = sorted({(self.root + t) % 12 for t in self.tones})
        self.qual = qual
        self.idx = idx

    def voicing(self, lo: int, hi: int, n: int = 3) -> list:
        """n Akkordtöne aufsteigend ab dem tiefsten Akkordton >= lo (Grundton zuerst, dann Terz/Quinte/...)."""
        out = []
        for t in self.tones:
            m = self.root + t
            while m < lo:
                m += 12
            while m > hi:
                m -= 12
            out.append(m)
        out = sorted(set(out))
        k = 0
        while len(out) < n and k < 8:
            extra = [m + 12 for m in out if lo <= m + 12 <= hi and m + 12 not in out]
            if not extra:
                break
            out = sorted(set(out + extra))
            k += 1
        return out[:n]

    def snap(self, midi: int, max_dist: int = 2) -> int:
        """Nächster Akkordton (Tonklasse), falls höchstens max_dist Halbtöne entfernt; sonst unverändert."""
        best, bd = midi, 99
        for d in range(-max_dist, max_dist + 1):
            if (midi + d) % 12 in self.pcs and abs(d) < bd:
                best, bd = midi + d, abs(d)
        return best

    def same(self, other) -> bool:
        return other is not None and self.root == other.root and self.qual == other.qual


# ---------------------------------------------------------------------------------------------------------------
# Instrumente: fn(f_hz, dur_s, variant, **kw) -> Mono (n,) oder Stereo (n, 2) float32, Spitze normiert.
# ``variant`` wählt bei rauschbasierten Klängen einen von wenigen Seeds (kein Maschinengewehr-Effekt).
# ---------------------------------------------------------------------------------------------------------------

def _t(n: int) -> np.ndarray:
    return np.arange(n, dtype=np.float64) / SR


def _fin(x, peak_db: float = -1.0, fi: float = 0.001, fo: float = 0.01) -> np.ndarray:
    return S.normalize(S.fade(np.nan_to_num(np.asarray(x, np.float32)), fi, fo), peak_db)


def _vib(f: float, dur: float, rate: float = 6.0, depth: float = 0.01, onset: float = 0.08) -> np.ndarray:
    """Frequenzverlauf mit einsetzendem Vibrato."""
    t = _t(S.seconds_to_samples(dur))
    ramp = np.clip((t - onset) / max(onset, 1e-3), 0.0, 1.0)
    return f * (1.0 + depth * ramp * np.sin(S.TWO_PI * rate * t))


def _i_marimba(f, dur, v, decay=0.26):
    return S.marimba(f, dur, decay=decay, bright=0.45, seed=v)


def _i_marimba_low(f, dur, v):
    return S.marimba(f, dur, decay=0.5, partials=((4.0, -14.0), (2.0, -8.0)), bright=0.25, seed=v)


def _i_kalimba(f, dur, v):
    return S.kalimba(f, dur, bright=0.4, decay=min(dur, 0.25), seed=v)


def _i_kalimba_soft(f, dur, v):
    """Kalimba der Safari: Dreieck + Sinus, Decay 250 ms (weicher als die Zupf-Kalimba)."""
    n = S.seconds_to_samples(dur)
    t = _t(n)
    tau = 0.25 / np.log(1000.0)
    x = (0.55 * S.tri(f, dur) + 0.6 * np.sin(S.TWO_PI * f * t) + 0.12 * np.sin(S.TWO_PI * 2 * f * t)) * np.exp(-t / tau)
    x = S.lowpass(x, 4500.0)
    nc = min(n, S.seconds_to_samples(0.003))
    if nc:
        x[:nc] += 0.25 * S.burst(0.003, 2000.0, 7000.0, seed=v)[:nc]
    return _fin(x, fo=min(0.02, dur / 4.0))


def _i_musicbox(f, dur, v):
    """Spieluhr: Sinus + 3. und 5. Teilton, Decay 300 ms, winziger Zungen-Klick."""
    n = S.seconds_to_samples(dur)
    t = _t(n)
    tau = 0.3 / np.log(1000.0)
    x = np.sin(S.TWO_PI * f * t) * np.exp(-t / tau)
    x += S.db(-12.0) * np.sin(S.TWO_PI * 3 * f * t) * np.exp(-t / (tau * 0.5))
    x += S.db(-18.0) * np.sin(S.TWO_PI * 5 * f * t) * np.exp(-t / (tau * 0.35))
    nc = min(n, S.seconds_to_samples(0.002))
    if nc:
        x[:nc] += 0.15 * S.burst(0.002, 4000.0, None, seed=v)[:nc]
    return _fin(x, fo=min(0.02, dur / 4.0))


def _i_vibes(f, dur, v):
    """Vibraphon: Sinus (+ leiser 4. Teilton), Tremolo 5 Hz, Decay 1.2 s, Mallet-Anschlag 5 ms."""
    n = S.seconds_to_samples(dur)
    t = _t(n)
    tau = 1.2 / np.log(1000.0)
    x = np.sin(S.TWO_PI * f * t) * np.exp(-t / tau) + 0.1 * np.sin(S.TWO_PI * 4 * f * t) * np.exp(-t / (tau * 0.2))
    x = S.tremolo(x, 5.0, 0.35)
    return _fin(x, fi=0.005, fo=min(0.03, dur / 4.0))


def _i_wbass(f, dur, v):
    return S.lowpass(S.pluck(f, dur, bright=0.35, decay=dur * 1.1, seed=v), 1800.0)


def _i_pizz(f, dur, v):
    return S.lowpass(S.pluck(f, dur, bright=0.3, decay=min(dur, 0.3), seed=v), 1500.0)


def _i_bounce_bass(f, dur, v):
    n = S.seconds_to_samples(dur)
    t = _t(n)
    fr = f * (1.0 + 0.6 * np.exp(-t / 0.035))
    x = S.sine(fr, dur).astype(np.float64) + 0.15 * S.sine(fr * 2.0, dur)
    x = S.apply(x, S.adsr(dur, 0.003, 0.08, 0.6, min(0.08, dur * 0.3)))
    return _fin(S.lowpass(x, 900.0), fi=0.002)


def _i_sub(f, dur, v):
    return _fin(S.apply(S.sine(f, dur), S.adsr(dur, 0.05, 0.05, 0.9, min(0.25, dur * 0.3), 'exp')), fi=0.01, fo=0.02)


def _i_kick_soft(f, dur, v):
    return _fin(S.lowpass(S.kick(dur, 48.0, punch=0.5, seed=v), 200.0), fi=0.0005, fo=0.02)


def _i_bongo(f, dur, v):
    x = S.apply(S.sine(S.sweep(180.0, 90.0, dur), dur), S.env_exp(dur, 0.028))
    return _fin(x, fi=0.0008, fo=min(0.02, dur / 4.0))


def _i_woodblock(f, dur, v):
    x = 0.8 * S.click(0.03, 1200.0).astype(np.float64)
    b = S.burst(0.012, 1500.0, 4000.0, seed=v)
    x[:len(b)] += 0.45 * b
    return _fin(x, fi=0.0005, fo=0.005)


def _i_clave(f, dur, v):
    return S.click(0.02, 2500.0)


def _i_hat_brush(f, dur, v):
    return S.burst(0.035, 7000.0, None, tau=0.009, seed=10 + v)


def _i_snap(f, dur, v):
    x = S.burst(0.03, 2000.0, 3200.0, tau=0.006, seed=20 + v).astype(np.float64)
    c = S.click(0.008, 2500.0)
    x[:len(c)] += 0.5 * c
    return _fin(x, fi=0.0003, fo=0.004)


def _i_shaker(f, dur, v):
    n = S.seconds_to_samples(0.03)
    env = S.env_lin([(0.0, 0.0), (0.004, 1.0), (0.03, 0.0)])[:n] * S.env_exp(0.03, 0.008)[:n]
    return _fin(S.apply(S.highpass(S.noise(0.03, 'white', 30 + v), 8000.0), env), fi=0.0005, fo=0.004)


def _i_timpani(f, dur, v):
    x = S.apply(S.sine(S.sweep(80.0, 50.0, dur), dur), S.env_exp(dur, 0.12))
    return _fin(S.drive(x, 0.1), fi=0.002, fo=0.03)


def _i_heartbeat(f, dur, v):
    n = S.seconds_to_samples(0.32)
    x = np.zeros(n, np.float64)
    for off, d in ((0.0, 0.09), (0.18, 0.07)):
        s = S.seconds_to_samples(off)
        th = S.apply(S.sine(60.0, d), S.env_exp(d, d / 3.0))
        x[s:s + len(th)] += th
    return _fin(S.lowpass(x, 120.0), fi=0.003, fo=0.02)


def _i_beep(f, dur, v):
    return _fin(S.sine(1000.0, 0.04), fi=0.003, fo=0.006)


def _i_bell(f, dur, v):
    return S.bell(f, dur)


def _i_glass(f, dur, v):
    return S.glass(f, dur, decay=min(0.4, dur * 0.8))


def _i_drip(f, dur, v):
    """Drip-Ping mit eingebautem Delay 375 ms (3 hörbare Wiederholungen, gedämpft)."""
    x = S.apply(S.sine(f, 0.2), S.env_exp(0.2, 0.04))
    x = S.fade(x, 0.002, 0.01)
    return _fin(S.delay(x, 0.375, feedback=0.45, mix=0.5, damp=3500.0), fi=0.001, fo=0.02)


def _i_whistle(f, dur, v):
    x = S.sine(_vib(f, dur, 6.0, 0.012, 0.1), dur).astype(np.float64) + 0.08 * S.sine(2.0 * f, dur)
    x = S.apply(x, S.adsr(dur, 0.04, 0.05, 0.85, min(0.1, dur * 0.3)))
    return _fin(x, fi=0.005, fo=0.01)


def _i_melody_tri(f, dur, v):
    x = S.lowpass(S.tri(f, dur), 1500.0)
    return _fin(S.apply(x, S.adsr(dur, 0.012, 0.1, 0.7, min(0.1, dur * 0.3))), fi=0.003)


def _i_arp_sq(f, dur, v, delay=0.0):
    """Orbit-Arpeggio: Rechteck -> Tiefpass mit ADSR-artig fallender Grenzfrequenz, kurzer Ton, Delay eingebaut."""
    cut = 500.0 + 2600.0 * S.env_exp(dur, 0.09).astype(np.float64)
    x = S.svf(S.square(f, dur), cut, q=1.1, mode='lp')
    x = S.apply(x, S.adsr(dur, 0.003, 0.08, 0.45, min(0.06, dur * 0.3)))
    x = S.fade(x, 0.002, 0.01)
    if delay > 0:
        x = S.delay(x, delay, feedback=0.35, mix=0.42, damp=4000.0)
    return _fin(x, fi=0.001, fo=0.02)


def _i_laser_arp(f, dur, v):
    x = S.lowpass(S.square(f, dur), 2000.0)
    return _fin(S.apply(x, S.adsr(dur, 0.002, 0.04, 0.5, min(0.04, dur * 0.3))), fi=0.001, fo=0.006)


def _i_cembalo(f, dur, v):
    x = 0.6 * S.square(f, dur).astype(np.float64) + 0.4 * S.saw(f, dur)
    x = S.lowpass(S.highpass(x, 300.0), 2500.0)
    return _fin(S.apply(x, S.env_exp(dur, 0.035)), fi=0.001, fo=min(0.02, dur / 4.0))


def _i_woodpulse(f, dur, v):
    x = S.burst(0.08, 150.0, 300.0, tau=0.02, seed=40 + v).astype(np.float64)
    tone = S.apply(S.sine(S.sweep(200.0, 120.0, 0.06), 0.06), S.env_exp(0.06, 0.02))
    x[:len(tone)] += 0.3 * tone
    return _fin(x, fi=0.001, fo=0.01)


def _stereo_pair(make, f: float, det: float) -> np.ndarray:
    """Zwei leicht gegeneinander verstimmte Stimmen links/rechts: Breite ohne Chorus-Kosten."""
    return np.stack([make(f * (1.0 - det)), make(f * (1.0 + det))], axis=1)


def _pad_env(dur: float, a: float, rel: float) -> np.ndarray:
    return S.adsr(dur, a=min(a, dur * 0.4), d=0.25, s=0.82, r=min(rel, dur * 0.45), curve='exp')


def _i_pad_warm(f, dur, v, rel=0.5):
    def make(fr):
        t = _t(S.seconds_to_samples(dur))
        return (np.sin(S.TWO_PI * fr * t) + 0.35 * np.sin(S.TWO_PI * 2.0 * fr * t + 0.3)
                + 0.12 * np.sin(S.TWO_PI * 3.0 * fr * t + 1.1))
    return _fin(S.apply(_stereo_pair(make, f, 0.002), _pad_env(dur, 0.35, rel)), -6.0, fi=0.005, fo=0.02)


def _i_pad_dark(f, dur, v, rel=0.5):
    def make(fr):
        return S.lowpass(S.tri(fr, dur), 700.0).astype(np.float64)
    return _fin(S.apply(_stereo_pair(make, f, 0.0025), _pad_env(dur, 0.3, rel)), -6.0, fi=0.005, fo=0.02)


def _i_pad_saw(f, dur, v, rel=0.9):
    """Höhlen-Pad: 2 Sägezähne ±7 Cent (links/rechts je eine), der Tiefpass 300 Hz mit LFO liegt auf dem Bus."""
    def make(fr):
        return S.saw(fr, dur).astype(np.float64)
    x = _stereo_pair(make, f, 0.004)
    return _fin(S.apply(x, _pad_env(dur, 0.6, rel)), -6.0, fi=0.005, fo=0.02)


def _i_pad_cluster(f, dur, v, rel=1.0):
    """Orbit-Pad: Sinus-Cluster mit langsamer Phasenmodulation (Chorus-Schweben), zwei Teiltöne."""
    def make(fr, sign):
        t = _t(S.seconds_to_samples(dur))
        wob = 0.5 * np.sin(S.TWO_PI * 0.23 * t + sign * 1.3)
        return (np.sin(S.TWO_PI * fr * t + sign * wob) + 0.45 * np.sin(S.TWO_PI * 2.0 * fr * t - sign * wob)
                + 0.18 * np.sin(S.TWO_PI * 3.0 * fr * t + 0.7))
    x = np.stack([make(f * 0.9985, 1.0), make(f * 1.0015, -1.0)], axis=1)
    return _fin(S.apply(x, _pad_env(dur, 0.8, rel)), -6.0, fi=0.005, fo=0.02)


def _i_pad_bow(f, dur, v, rel=0.5):
    def make(fr):
        return S.lowpass(S.saw(fr, dur), 1200.0).astype(np.float64)
    return _fin(S.apply(_stereo_pair(make, f, 0.003), _pad_env(dur, 0.4, rel)), -6.0, fi=0.005, fo=0.02)


def _i_pad_light(f, dur, v, rel=0.4):
    def make(fr):
        return S.lowpass(0.6 * S.tri(fr, dur).astype(np.float64) + 0.4 * S.sine(fr, dur), 2000.0).astype(np.float64)
    return _fin(S.apply(_stereo_pair(make, f, 0.002), _pad_env(dur, 0.2, rel)), -6.0, fi=0.005, fo=0.02)


# Effekte (ohne Tonhöhe): Riser, Swell, Lichtkegel, Crash
def _i_riser(f, dur, v):
    n = S.seconds_to_samples(dur)
    t = _t(n)
    x = np.linspace(0.0, 1.0, n)
    env = (np.exp(3.5 * x) - 1.0) / (np.exp(3.5) - 1.0)
    nz = S.svf(S.noise(dur, 'pink', 50 + v), 300.0 * (50.0 / 300.0) ** x, q=0.7, mode='hp', block=512)
    sw = S.sine(S.sweep(200.0, 2000.0, dur), dur)
    out = (0.8 * nz.astype(np.float64) + 0.25 * sw) * env
    return _fin(out, fi=0.01, fo=0.05)


def _i_swell(f, dur, v):
    n = S.seconds_to_samples(dur)
    x = np.linspace(0.0, 1.0, n)
    env = (np.exp(4.0 * x) - 1.0) / (np.exp(4.0) - 1.0)
    nz = S.bandpass(S.noise(dur, 'white', 60 + v), 500.0, 3000.0)
    return _fin(nz.astype(np.float64) * env, fi=0.01, fo=0.03)


def _i_lightcone(f, dur, v):
    n = S.seconds_to_samples(dur)
    x = np.linspace(0.0, 1.0, n)
    nz = S.svf(S.noise(dur, 'white', 70 + v), 300.0 * (4000.0 / 300.0) ** x, q=2.5, mode='bp', block=256)
    env = np.sin(np.pi * x) ** 0.7
    return _fin(nz.astype(np.float64) * env, fi=0.01, fo=0.03)


def _i_crash(f, dur, v):
    """Glas-Cluster (5 Sinus 3.5–7 kHz, 30 ms versetzt) + Konfetti-Shaker, Stereo."""
    n = S.seconds_to_samples(dur)
    out = np.zeros((n, 2), np.float64)
    rng = np.random.default_rng(80 + v)
    for k in range(5):
        fr = float(rng.uniform(3500.0, 7000.0))
        g = S.glass(fr, 0.6, decay=0.45)
        s = S.seconds_to_samples(0.03 * k)
        e = min(n, s + len(g))
        a = (float(rng.uniform(-0.8, 0.8)) + 1.0) * np.pi / 4.0
        out[s:e, 0] += g[:e - s] * np.cos(a) * 0.6
        out[s:e, 1] += g[:e - s] * np.sin(a) * 0.6
    sh = S.shaker(40, 0.7, tau=0.25, seed=90 + v)
    out[:len(sh)] += 0.7 * sh[:n]
    return _fin(out, fi=0.001, fo=0.03)


INSTRUMENTS = {
    'marimba': _i_marimba, 'marimba_low': _i_marimba_low, 'kalimba': _i_kalimba, 'kalimba_soft': _i_kalimba_soft,
    'musicbox': _i_musicbox, 'vibes': _i_vibes, 'wbass': _i_wbass, 'pizz': _i_pizz, 'bounce_bass': _i_bounce_bass,
    'sub': _i_sub, 'kick_soft': _i_kick_soft, 'bongo': _i_bongo, 'woodblock': _i_woodblock, 'clave': _i_clave,
    'hat_brush': _i_hat_brush, 'snap': _i_snap, 'shaker': _i_shaker, 'timpani': _i_timpani,
    'heartbeat': _i_heartbeat, 'beep': _i_beep, 'bell': _i_bell, 'glass': _i_glass, 'drip': _i_drip,
    'whistle': _i_whistle, 'melody_tri': _i_melody_tri, 'arp_sq': _i_arp_sq, 'laser_arp': _i_laser_arp,
    'cembalo': _i_cembalo, 'woodpulse': _i_woodpulse,
    'pad_warm': _i_pad_warm, 'pad_dark': _i_pad_dark, 'pad_saw': _i_pad_saw, 'pad_cluster': _i_pad_cluster,
    'pad_bow': _i_pad_bow, 'pad_light': _i_pad_light,
    'riser': _i_riser, 'swell': _i_swell, 'lightcone': _i_lightcone, 'crash': _i_crash,
}
PITCHLESS = {'kick_soft', 'bongo', 'woodblock', 'clave', 'hat_brush', 'snap', 'shaker', 'timpani', 'heartbeat',
             'beep', 'woodpulse', 'riser', 'swell', 'lightcone', 'crash'}
FIXED_DUR = {'woodblock': 0.03, 'clave': 0.02, 'hat_brush': 0.035, 'snap': 0.03, 'shaker': 0.03, 'heartbeat': 0.32,
             'beep': 0.04, 'woodpulse': 0.08, 'drip': 0.2}


class _Bank:
    """Noten-Cache: (Instrument, MIDI, Dauer auf ms, Variante, Extra) -> gerendertes Signal."""

    def __init__(self):
        self.cache = {}
        self.renders = 0

    def get(self, inst: str, midi: float, dur: float, variant: int = 0, **kw) -> np.ndarray:
        dur = FIXED_DUR.get(inst, dur)
        m = 0 if inst in PITCHLESS else int(round(midi))
        k = (inst, m, int(round(dur * 1000)), int(variant), tuple(sorted(kw.items())))
        sig = self.cache.get(k)
        if sig is None:
            f = S.midi_to_freq(m) if inst not in PITCHLESS else 0.0
            sig = INSTRUMENTS[inst](f, max(dur, 0.005), int(variant), **kw)
            self.cache[k] = sig
            self.renders += 1
        return sig


def _place(buf: np.ndarray, sig: np.ndarray, t: float, gain: float, pan: float = 0.0):
    """Signal (Mono mit Pan oder Stereo) bei t Sekunden mit Faktor gain in den Stereo-Puffer addieren."""
    n0 = int(round(t * SR))
    n = len(buf)
    if n0 >= n or gain == 0.0 or len(sig) == 0:
        return
    s0 = 0
    if n0 < 0:
        s0, n0 = -n0, 0
    n1 = min(n, n0 + len(sig) - s0)
    if n1 <= n0:
        return
    seg = sig[s0:s0 + (n1 - n0)]
    if seg.ndim == 2:
        buf[n0:n1] += seg * np.float32(gain)
    else:
        a = (float(np.clip(pan, -1.0, 1.0)) + 1.0) * np.pi / 4.0
        buf[n0:n1, 0] += seg * np.float32(gain * np.cos(a))
        buf[n0:n1, 1] += seg * np.float32(gain * np.sin(a))


# ---------------------------------------------------------------------------------------------------------------
# Raster und Struktur: Beats, Abschnitte, Energie, Akzente, Akkorde
# ---------------------------------------------------------------------------------------------------------------

def demo_sections(duration: float) -> list:
    """Vorführ-Struktur ohne Projekt (render_all): Hook, fünf Einträge mit steigender Energie (#5 0.5 … #1 0.9), Outro."""
    duration = float(duration)
    if duration < 8.0:
        return [{'t0': 0.0, 't1': duration, 'kind': 'entry', 'rank': 3, 'energy': 0.7}]
    hook = float(np.clip(0.14 * duration, 2.5, 6.0))
    outro = float(np.clip(0.14 * duration, 2.5, 6.0))
    mid = duration - hook - outro
    out = [{'t0': 0.0, 't1': hook, 'kind': 'hook', 'rank': None, 'energy': 0.6}]
    for i in range(5):
        t0 = hook + mid * i / 5.0
        out.append({'t0': round(t0, 3), 't1': round(hook + mid * (i + 1) / 5.0, 3), 'kind': 'entry', 'rank': 5 - i,
                    'energy': round(0.5 + 0.1 * i, 2)})
    out.append({'t0': round(hook + mid, 3), 't1': duration, 'kind': 'outro', 'rank': None, 'energy': 0.4})
    return out


class _Layer:
    __slots__ = ('name', 'thr', 'gain', 'bus', 'respect', 'perc', 'pad')

    def __init__(self, name, thr, gain_db, bus='mel', respect=False, perc=False, pad=False):
        self.name, self.thr, self.gain, self.bus = name, float(thr), S.db(gain_db), bus
        self.respect, self.perc, self.pad = bool(respect), bool(perc), bool(pad)


class _Grid:
    def __init__(self, bed: dict, duration: float, sections: list, rng: np.random.Generator):
        self.bpm, self.bpb, self.swing = float(bed['bpm']), int(bed['meter']), float(bed['swing'])
        self.beat = 60.0 / self.bpm
        self.bar = self.beat * self.bpb
        self.duration = float(duration)
        nb = self.nb = int(math.ceil(self.duration / self.beat)) + 1
        self.energy = np.full(nb, 0.6)
        self.respect = np.zeros(nb, bool)
        self.rank = np.zeros(nb, int)
        self.kind = ['entry'] * nb
        self.accents, self.fx_accents = set(), set()
        self.peak_beat, self.outro_beat, self.hook = None, None, False
        secs = sorted((s for s in sections if isinstance(s, dict)), key=lambda s: float(s.get('t0', 0.0)))
        for i, sec in enumerate(secs):
            b0 = max(0, int(round(float(sec.get('t0', 0.0)) / self.beat)))
            b1 = max(b0 + 1, int(round(float(sec.get('t1', self.duration)) / self.beat)))
            b0, b1 = min(b0, nb), min(b1, nb)
            if b0 >= nb:
                continue
            kind = str(sec.get('kind', 'entry'))
            resp = bool(sec.get('respect'))
            e = float(sec.get('energy', 0.6))
            e = min(e, RESPECT_ENERGY) if resp else float(np.clip(e, 0.0, 1.0))
            rank = int(sec.get('rank') or 0)
            self.energy[b0:b1] = e
            self.respect[b0:b1] = resp
            self.rank[b0:b1] = rank
            for b in range(b0, b1):
                self.kind[b] = kind
            if kind == 'hook' and i == 0:
                self.hook = True
            if kind == 'entry' and b0 > 0:
                self.accents.add(b0)
                if not resp:
                    self.fx_accents.add(b0)
                    if rank == 1:
                        self.peak_beat = b0
            if kind == 'outro' and self.outro_beat is None and b0 > 0:
                self.outro_beat = b0
                self.accents.add(b0)
        # Schlussakkord: nach zwei Takten Auflösung, wenn das Outro lang genug ist, sonst früher
        self.final_beat = nb + 8
        if self.outro_beat is not None:
            for bars in (2, 1, 0):
                fb = self.outro_beat + bars * self.bpb
                if fb * self.beat <= self.duration - 1.0 or bars == 0:
                    self.final_beat = fb
                    break
        # Taktphase und Taktzähler relativ zum letzten Szenenbeginn, laufende Abschnittsnummer
        self.phase, self.barno, self.sec_no = np.zeros(nb, int), np.zeros(nb, int), np.zeros(nb, int)
        last, sn = 0, 0
        for b in range(nb):
            if b in self.accents:
                last, sn = b, sn + 1
            self.phase[b], self.barno[b], self.sec_no[b] = (b - last) % self.bpb, (b - last) // self.bpb, sn
        self.chords = self._chords(bed, rng)
        self.change = np.zeros(nb, bool)
        for b in range(1, nb):
            self.change[b] = not self.chords[b].same(self.chords[b - 1])

    def _chords(self, bed: dict, rng) -> list:
        progs = bed['progressions']
        prog = progs[int(rng.integers(0, len(progs)))]
        n = len(prog)
        step = 3 if n % 3 else 2
        off = {}

        def spec_at(b):
            if self.outro_beat is not None and b >= self.outro_beat:
                if b >= self.final_beat:
                    return bed['final']
                cad = bed['cadence']
                avail = max(0, (self.final_beat - self.outro_beat) // self.bpb)
                k = (b - self.outro_beat) // self.bpb
                return cad[max(0, len(cad) - avail) + k] if k < avail else cad[-1]
            sn = int(self.sec_no[b])
            if sn not in off:
                off[sn] = 0 if sn == 0 else int((sn * step + rng.integers(0, 2)) % n)
            return prog[(int(self.barno[b]) + off[sn]) % n]

        chords = [_Chord(bed, spec_at(b), b) for b in range(self.nb)]
        # Szenenbeginn ohne hörbaren Akkordwechsel: Versatz des Abschnitts um einen Akkord verschieben
        for b in sorted(self.accents):
            if 0 < b < self.nb and chords[b].same(chords[b - 1]) and (self.outro_beat is None or b < self.outro_beat):
                sn = int(self.sec_no[b])
                off[sn] = (off[sn] + 1) % n
                for bb in range(b, self.nb):
                    if self.sec_no[bb] != sn:
                        break
                    chords[bb] = _Chord(bed, spec_at(bb), bb)
        return chords

    def tb(self, b: int, frac: float = 0.0) -> float:
        """Zeit eines Beats ``b`` am Bruchteil ``frac`` (0..1) mit Swing (Offbeat-Achtel bei ``swing``)."""
        if frac <= 0.0:
            return b * self.beat
        s = self.swing
        pos = frac * 2.0 * s if frac < 0.5 else s + (frac - 0.5) * 2.0 * (1.0 - s)
        return (b + pos) * self.beat

    def on(self, b: int, layer: _Layer) -> bool:
        if b < 0 or b >= self.nb:
            return False
        if b >= self.final_beat and not layer.pad:
            return False
        if self.respect[b] and not layer.respect:
            return False
        if layer.perc and b in self.fx_accents:
            return False
        return float(self.energy[b]) >= layer.thr - 1e-9

    def regions(self, pad_only_final: bool = True) -> list:
        """[(b0, b1, chord)] zusammenhängende Beats gleichen Akkords (b1 exklusiv, letzte Region bis nb)."""
        out, b0 = [], 0
        for b in range(1, self.nb + 1):
            if b == self.nb or self.change[b]:
                out.append((b0, b, self.chords[b0]))
                b0 = b
        return out


# ---------------------------------------------------------------------------------------------------------------
# Sequencer: plant Noten je Schicht und legt sie direkt in die Busse
# ---------------------------------------------------------------------------------------------------------------

class _Seq:
    BUSES = ('pad', 'mel', 'perc', 'fx')

    def __init__(self, bed: dict, grid: _Grid, bank: _Bank, rng: np.random.Generator, n_buf: int):
        self.bed, self.g, self.bank, self.rng = bed, grid, bank, rng
        self.bus = {k: np.zeros((n_buf, 2), np.float32) for k in self.BUSES}
        self.kick_times = []
        self.pad_notes, self.pad_inst, self.pad_gain = [], None, 1.0      # (t, midi, dur, vel, rel) -> _render_pad
        self.notes = 0

    # --- Grundhelfer -------------------------------------------------------------------------------------------
    def h_t(self, sd: float = 0.004) -> float:
        return float(np.clip(self.rng.normal(0.0, sd), -0.012, 0.012))

    def h_v(self, sd: float = 0.06) -> float:
        return float(np.clip(1.0 + self.rng.normal(0.0, sd), 0.7, 1.25))

    def add(self, layer: _Layer, t: float, inst: str, midi, vel: float = 0.8, pan: float = 0.0, dur: float = 0.5,
            variant: int = None, human: bool = True, **kw):
        if t >= self.g.duration + 0.05:
            return
        if variant is None:
            variant = int(self.rng.integers(0, 4)) if inst in PITCHLESS or inst in ('kalimba', 'wbass', 'pizz') else 0
        sig = self.bank.get(inst, midi, dur, variant, **kw)
        if human:
            t += self.h_t()
            vel *= self.h_v()
        _place(self.bus[layer.bus], sig, max(0.0, t), vel * layer.gain, pan)
        self.notes += 1

    def strum(self, layer, t, inst, midis, vel, pan, dur, spread=0.012, **kw):
        for k, m in enumerate(midis):
            self.add(layer, t + k * spread, inst, m, vel * (1.0 - 0.05 * k), pan + 0.12 * (k - len(midis) / 2.0), dur, **kw)

    def pad_layer(self, layer: _Layer, inst: str, lo: int, hi: int, n: int = 3, root_oct: int = 0, rel: float = 0.5,
                  vel: float = 1.0):
        """Flächenklang je Akkordregion: Grundton (Oktave 3 + root_oct) und n Oberstimmen in lo..hi. Die Noten werden
        gesammelt und in _render_pad mit reduzierter Abtastrate gerendert (ein Oszillator je Tonhöhe)."""
        g = self.g
        self.pad_inst, self.pad_gain = inst, layer.gain
        for b0, b1, ch in g.regions():
            if not g.on(b0, layer):
                continue
            t0 = g.tb(b0)
            t1 = g.tb(b1) if b1 < g.nb else g.duration + 0.5
            if b0 >= g.final_beat:
                t1 = g.duration + 0.5
            t1 = min(t1, g.duration + 0.5)
            dur = max(0.3, t1 - t0) + rel
            voices = ([ch.root + 12 * root_oct] if root_oct is not None else []) + ch.voicing(lo, hi, n)
            e = float(g.energy[b0])
            v = vel * (0.6 + 0.4 * min(1.0, e / 0.9))          # Pad folgt der Energie (-2 dB im Outro, -3 dB Respekt)
            for k, m in enumerate(voices):
                self.pad_notes.append((t0, int(m), dur, v * (1.0 if k == 0 else 0.8), rel))
                self.notes += 1

    def motif(self, lo: int, hi: int, n_beats: int, density: float, subdiv: int = 2, steps=(-3, -2, -1, -1, 0, 1, 1, 2, 3)) -> list:
        """Generatives Motiv: [(Position in Unterteilungen, MIDI)] als eingeschränkter Zufallsgang auf der Tonleiter."""
        sc = _scale(self.bed, lo, hi)
        idx = len(sc) // 2 + int(self.rng.integers(-2, 3))
        out = []
        for p in range(n_beats * subdiv):
            if p == 0 or self.rng.random() < density:
                idx = int(np.clip(idx + int(self.rng.choice(steps)), 0, len(sc) - 1))
                if abs(idx - len(sc) // 2) > len(sc) // 2 - 1:       # zurück zur Mitte
                    idx += -2 if idx > len(sc) // 2 else 2
                    idx = int(np.clip(idx, 0, len(sc) - 1))
                out.append((p, sc[idx]))
        return out

    def play_motif(self, layer: _Layer, inst: str, motif: list, n_bars: int, subdiv: int, pan: float = 0.0,
                   vel: float = 0.8, bars_on=None, legato: float = 0.9, min_dur: float = 0.12, max_dur: float = 1.2,
                   force_pc=None):
        """Motiv (n_bars Takte) wiederholen; starke Zählzeiten auf den Akkord ziehen; kleine Variationen je Durchlauf."""
        g = self.g
        n_beats = n_bars * g.bpb
        total = n_beats * subdiv
        by_pos = {p: m for p, m in motif}
        positions = sorted(by_pos)
        sc = _scale(self.bed, min(by_pos.values()) - 12, max(by_pos.values()) + 12)
        last_rep, var = None, {}
        for b in range(g.nb):
            if not g.on(b, layer):
                continue
            if bars_on is not None and not bars_on(int(g.barno[b])):
                continue
            rep = (int(g.sec_no[b]), int(g.barno[b]) // n_bars)
            if rep != last_rep:                                   # neuer Durchlauf: Variation würfeln
                last_rep, var = rep, {}
                if self.rng.random() < 0.35 and positions:
                    p = positions[int(self.rng.integers(0, len(positions)))]
                    var[p] = int(self.rng.choice([-1, 1]))
                if self.rng.random() < 0.25 and len(positions) > 2:
                    var[positions[int(self.rng.integers(1, len(positions)))]] = None
            mb = (int(g.barno[b]) % n_bars) * g.bpb + int(g.phase[b])
            for k in range(subdiv):
                p = mb * subdiv + k
                if p not in by_pos or (p in var and var[p] is None):
                    continue
                m = by_pos[p]
                if p in var and var[p] is not None and m in sc:
                    m = sc[int(np.clip(sc.index(m) + var[p], 0, len(sc) - 1))]
                if k == 0 and g.phase[b] in (0, 2):
                    m = g.chords[b].snap(m)
                if force_pc is not None and p == positions[-1]:
                    m = g.chords[b].snap(m) if (m - force_pc) % 12 else m
                nxt = next((q for q in positions if q > p), total)
                dur = float(np.clip((nxt - p) / subdiv * g.beat * legato, min_dur, max_dur))
                self.add(layer, g.tb(b, k / subdiv), inst, m, vel * (1.0 if k == 0 else 0.85), pan, dur)

    def swell_and_riser(self, swell_db: float = -20.0, riser_db: float = -18.0):
        g = self.g
        fx = _Layer('fx', 0.0, 0.0, 'fx')
        if g.hook:
            first = min(g.accents) if g.accents else g.nb
            dur = min(2.0 * g.bar, max(g.beat, g.tb(first)))
            self.add(fx, 0.0, 'riser', 0, S.db(riser_db), 0.0, dur, 0, human=False)
        for b in sorted(g.fx_accents):
            b0 = b - g.bpb
            if b0 < 0 or g.respect[b0:b].any() or b >= g.final_beat:
                continue
            self.add(fx, g.tb(b0), 'swell', 0, S.db(swell_db), 0.0, g.bar, int(b % 4), human=False)
        if g.peak_beat is not None:
            self.add(fx, g.tb(g.peak_beat), 'crash', 0, S.db(-18.0), 0.0, 1.0, 0, human=False)

    def final_chord(self, inst: str, lo: int, hi: int, gain_db: float, bass_inst: str = None, bass_db: float = -9.0,
                    bell: bool = True):
        g = self.g
        if g.final_beat >= g.nb:
            return
        lay = _Layer('final', 0.0, gain_db, 'mel', respect=True, pad=True)
        t = g.tb(g.final_beat)
        ch = g.chords[g.final_beat]
        self.strum(lay, t, inst, [ch.root + 12] + ch.voicing(lo, hi, 3), 0.9, 0.0, 1.2, spread=0.018, decay=0.5) \
            if inst == 'marimba' else self.strum(lay, t, inst, [ch.root + 12] + ch.voicing(lo, hi, 3), 0.9, 0.0, 1.5, spread=0.02)
        if bass_inst:
            bl = _Layer('final_bass', 0.0, bass_db, 'mel', respect=True, pad=True)
            self.add(bl, t, bass_inst, ch.root - 12, 0.9, 0.0, 2.5, 0, human=False)
        if bell:
            bl = _Layer('final_bell', 0.0, gain_db - 8.0, 'mel', respect=True, pad=True)
            self.add(bl, t + 0.02, 'bell', ch.root + 24, 0.8, 0.0, 1.6, 0, human=False)


# ---------------------------------------------------------------------------------------------------------------
# Die Betten: Schichten je Energie-Schwelle (THRESHOLDS), Akzente, Schlussakkord
# ---------------------------------------------------------------------------------------------------------------

def _gen_cabinet(q: _Seq, pulse: bool = False):
    g, rng = q.g, q.rng
    pad = _Layer('pad', 0.0, -23.0, 'pad', respect=True, pad=True)
    bass = _Layer('wbass', 0.3, -8.5)
    stab = _Layer('marimba', 0.5, -9.0)
    hat = _Layer('hat', 0.65, -20.0, 'perc', perc=True)
    snap = _Layer('snap', 0.65, -16.0 if not pulse else -10.0, 'perc', perc=True)
    beep = _Layer('beep', 0.65, -22.0, 'perc', perc=True)
    counter = _Layer('kalimba', 0.8, -12.0)
    bell = _Layer('bell', 0.9, -17.0)
    q.pad_layer(pad, 'pad_warm', 57, 74, 2, root_oct=0, rel=0.6)
    # Walking-Bass: Achtel, Grundton auf 1, Terz/Quinte, Annäherung an den nächsten Takt
    for b in range(g.nb):
        if not g.on(b, bass):
            continue
        ch = g.chords[b]
        tones = ch.voicing(38, 52, 4)
        ph = int(g.phase[b])
        nxt = g.chords[min(g.nb - 1, b + 1)]
        if ph == 0:
            m = tones[0]
        elif ph == g.bpb - 1 and g.change[min(g.nb - 1, b + 1)]:
            target = nxt.voicing(38, 52, 1)[0]
            m = target + int(rng.choice([-1, 1, -2, 2]))
        else:
            m = tones[min(len(tones) - 1, int(rng.choice([1, 2, 2, 3])))] if ph != 2 else tones[min(len(tones) - 1, 2)]
        q.add(bass, g.tb(b), 'wbass', m, 0.95 if ph == 0 else 0.8, 0.0, g.beat * 0.95)
        if rng.random() < 0.45 and b + 1 < g.final_beat:
            gm = m if rng.random() < 0.6 else m + int(rng.choice([-2, 2, 1]))
            q.add(bass, g.tb(b, 0.5), 'wbass', gm, 0.45, 0.0, g.beat * (1.0 - g.swing) * 0.95)
    # Marimba-Stabs auf 2 und 4 (manchmal auf 4+ vorgezogen)
    for b in range(g.nb):
        if not g.on(b, stab) or int(g.phase[b]) not in (1, 3):
            continue
        frac = 0.5 if (int(g.phase[b]) == 3 and rng.random() < 0.25) else 0.0
        q.strum(stab, g.tb(b, frac), 'marimba', g.chords[b].voicing(62, 79, 3), 0.8, -0.25, 0.42, spread=0.008)
    # Besen-Hi-Hat Achtel + Fingersnap auf 2 und 4 (Pulse: Herzschlag auf 1 und 3, Piep auf 4)
    for b in range(g.nb):
        ph = int(g.phase[b])
        if g.on(b, hat):
            q.add(hat, g.tb(b), 'hat_brush', 0, 0.55, 0.35, 0.035)
            q.add(hat, g.tb(b, 0.5), 'hat_brush', 0, 0.85, 0.35, 0.035)
        if g.on(b, snap):
            if pulse:
                if ph in (0, 2):
                    q.add(snap, g.tb(b), 'heartbeat', 0, 0.9, 0.0, 0.32)
            elif ph in (1, 3):
                q.add(snap, g.tb(b), 'snap', 0, 0.9, -0.3, 0.03)
        if pulse and g.on(b, beep) and ph == 3:
            q.add(beep, g.tb(b), 'beep', 0, 0.8, 0.45, 0.04)
    # Kalimba-Gegenstimme eine Oktave höher, auf den Offbeats
    mot = q.motif(74, 86, 2 * g.bpb, 0.4, 2)
    mot = [(p if p % 2 else p + 1, m) for p, m in mot if p + 1 < 4 * g.bpb]       # auf die Offbeat-Achtel
    q.play_motif(counter, 'kalimba', mot, 2, 2, pan=0.35, vel=0.75, max_dur=0.5)
    # Glas-Glocke auf jeder 1
    for b in range(g.nb):
        if g.on(b, bell) and int(g.phase[b]) == 0:
            q.add(bell, g.tb(b), 'bell', g.chords[b].root + 36, 0.7, 0.4 if (int(g.barno[b]) % 2) else -0.4, 1.2, 0)
    # Nummernwechsel: Marimba-Lauf 4 Sechzehntel aufwärts in die Karte
    run = _Layer('run', 0.0, -10.0)
    for b in sorted(g.fx_accents):
        if b >= g.final_beat:
            continue
        tones = g.chords[b].voicing(62, 86, 4)
        for k in range(4):
            q.add(run, g.tb(b, k / 4.0), 'marimba', tones[min(k, len(tones) - 1)], 0.6 + 0.12 * k, -0.2 + 0.15 * k, 0.35)
    q.swell_and_riser()
    q.final_chord('marimba', 62, 79, -10.0, 'wbass', -8.5)


def _gen_heist(q: _Seq):
    g, rng = q.g, q.rng
    pad = _Layer('pad', 0.0, -23.0, 'pad', respect=True, pad=True)
    bass = _Layer('pizz', 0.3, -7.5)
    vib = _Layer('vibes', 0.3, -12.0)
    wood = _Layer('wood', 0.5, -14.0, 'perc', perc=True)
    bongo = _Layer('bongo', 0.5, -10.0, 'perc', perc=True)
    mel = _Layer('melody', 0.65, -13.5)
    arp = _Layer('laser', 0.8, -20.0)
    shk = _Layer('shaker', 0.9, -21.0, 'perc', perc=True)
    q.pad_layer(pad, 'pad_dark', 52, 71, 2, root_oct=0, rel=0.6)
    for b in range(g.nb):
        if not g.on(b, bass):
            continue
        ch, ph = g.chords[b], int(g.phase[b])
        tones = ch.voicing(40, 54, 3)
        if ph == 0 and (g.change[b] or rng.random() < 0.3):
            q.add(bass, g.tb(b), 'pizz', tones[0], 0.6, 0.0, 0.4)
        m = tones[0] if ph in (0, 1) else (tones[min(2, len(tones) - 1)] if ph == 2 else tones[0] + int(rng.choice([0, -1, 2])))
        q.add(bass, g.tb(b, 0.5), 'pizz', m, 0.85, 0.0, 0.4)
    for b in range(g.nb):
        if not g.on(b, vib):
            continue
        ph = int(g.phase[b])
        if ph == 0 or (ph == 2 and rng.random() < 0.4):
            q.strum(vib, g.tb(b), 'vibes', g.chords[b].voicing(60, 76, 3), 0.8 if ph == 0 else 0.6, -0.2, 1.5, spread=0.02)
    patterns = [([(0, 0.0), (0, 0.75), (1, 0.5), (2, 0.0), (2, 0.5), (3, 0.25)], [(1, 0.0), (3, 0.5)]),
                ([(0, 0.0), (1, 0.25), (1, 0.75), (2, 0.5), (3, 0.0), (3, 0.5)], [(1, 0.5), (2, 0.0), (3, 0.75)]),
                ([(0, 0.5), (1, 0.0), (1, 0.75), (2, 0.5), (3, 0.25)], [(0, 0.0), (2, 0.0), (3, 0.5)])]
    wb_pat, bg_pat = patterns[int(rng.integers(0, len(patterns)))]
    for b in range(g.nb):
        ph = int(g.phase[b])
        if g.on(b, wood):
            for p, f in wb_pat:
                if p == ph:
                    q.add(wood, g.tb(b, f), 'woodblock', 0, 0.9 if f == 0.0 else 0.7, 0.35, 0.03)
        if g.on(b, bongo):
            for p, f in bg_pat:
                if p == ph:
                    q.add(bongo, g.tb(b, f), 'bongo', 0, 0.85, -0.3, 0.12)
        if g.on(b, shk):
            for k in range(4):
                q.add(shk, g.tb(b, k / 4.0), 'shaker', 0, (0.9, 0.5, 0.7, 0.5)[k], 0.4, 0.03)
    root_pc = _PC[q.bed['root']]
    mot = q.motif(64, 79, 2 * g.bpb, 0.4, 2)
    q.play_motif(mel, 'melody_tri', mot, 2, 2, pan=0.15, vel=0.8, max_dur=0.9, force_pc=(root_pc + 8) % 12)
    for b in range(g.nb):
        if not g.on(b, arp) or int(g.barno[b]) % 2 != 1:
            continue
        tones = g.chords[b].voicing(76, 91, 4)
        order = [0, 1, 2, 3, 2, 1, 0, 1]
        for k in range(4):
            idx = (int(g.phase[b]) * 4 + k) % len(order)
            q.add(arp, g.tb(b, k / 4.0), 'laser_arp', tones[min(order[idx], len(tones) - 1)], 0.7 if k == 0 else 0.55,
                  -0.4 if k % 2 else 0.4, g.beat / 4.0 * 0.9, 0)
    fill = _Layer('fill', 0.0, -12.0, 'perc')
    for b in sorted(g.fx_accents):
        if b >= g.final_beat:
            continue
        for k in range(4):
            q.add(fill, g.tb(b, k / 4.0), 'bongo', 0, 0.55 + 0.12 * k, -0.3 + 0.2 * k, 0.12)
        q.add(fill, g.tb(b + 1), 'woodblock', 0, 1.0, 0.3, 0.03)
    q.swell_and_riser()
    q.final_chord('vibes', 60, 76, -12.0, 'pizz', -9.0)


def _gen_cave(q: _Seq):
    g, rng = q.g, q.rng
    pad = _Layer('pad', 0.0, -16.0, 'pad', respect=True, pad=True)
    heart = _Layer('heart', 0.3, -10.0)
    drip = _Layer('drip', 0.5, -12.0)
    mbass = _Layer('mbass', 0.65, -10.0)
    wood = _Layer('woodpulse', 0.8, -14.0, 'perc', perc=True)
    glass = _Layer('glass', 0.9, -19.0)
    q.pad_layer(pad, 'pad_saw', 45, 64, 3, root_oct=0, rel=1.0)
    pent = _scale({'root': q.bed['root'], 'mode': 'pentatonic_minor'}, 86, 98)
    for b in range(g.nb):
        ph = int(g.phase[b])
        if g.on(b, heart) and ph == 0 and int(g.barno[b]) % 2 == 0:
            q.add(heart, g.tb(b), 'heartbeat', 0, 0.9, 0.0, 0.32, 0)
        if g.on(b, drip):
            for k in range(2):
                if rng.random() < 0.22:
                    q.add(drip, g.tb(b, k / 2.0), 'drip', int(rng.choice(pent)), 0.75, float(rng.uniform(-0.7, 0.7)), 0.2, 0)
        if g.on(b, mbass):
            if ph == 0:
                q.add(mbass, g.tb(b), 'marimba_low', g.chords[b].root - 12, 0.9, 0.0, 0.7)
            elif ph == 2:
                q.add(mbass, g.tb(b, 0.5), 'marimba_low', g.chords[b].root - 12 + (7 if rng.random() < 0.5 else 0), 0.7, 0.0, 0.6)
        if g.on(b, wood) and (ph == 0 or (ph == 2 and rng.random() < 0.3)):
            q.add(wood, g.tb(b), 'woodpulse', 0, 0.9 if ph == 0 else 0.6, 0.2, 0.08)
        if g.on(b, glass):
            if ph == 0 and int(g.barno[b]) % 2 == 0:
                q.add(glass, g.tb(b), 'bell', g.chords[b].root + 24, 0.7, 0.3, 1.4, 0)
            if rng.random() < 0.12:
                q.add(glass, g.tb(b, 0.75), 'glass', int(rng.choice(pent)) + 12, 0.5, float(rng.uniform(-0.8, 0.8)), 0.5, 0)
    acc = _Layer('acc', 0.0, -16.0, 'fx')
    hit = _Layer('hit', 0.0, -10.0)
    for b in sorted(g.fx_accents):
        if b >= g.final_beat:
            continue
        q.add(acc, g.tb(b), 'lightcone', 0, 1.0, 0.0, g.beat, int(b % 4), human=False)
        q.add(hit, g.tb(b), 'marimba_low', g.chords[b].root - 12, 0.9, 0.0, 0.7)
    q.swell_and_riser(swell_db=-22.0)
    q.final_chord('marimba_low', 57, 72, -11.0, None, bell=True)


def _gen_safari(q: _Seq):
    g, rng = q.g, q.rng
    pad = _Layer('pad', 0.0, -24.0, 'pad', respect=True, pad=True)
    kal = _Layer('kalimba', 0.3, -12.5)
    bass = _Layer('bounce', 0.3, -8.5)
    shk = _Layer('shaker', 0.5, -20.0, 'perc', perc=True)
    clave = _Layer('clave', 0.65, -12.0, 'perc', perc=True)
    whistle = _Layer('whistle', 0.8, -15.0)
    bell = _Layer('bell', 0.9, -22.0)
    q.pad_layer(pad, 'pad_light', 62, 79, 2, root_oct=0, rel=0.5)
    orders = [[0, 1, 2, 1, 3, 2, 1, 2], [0, 2, 1, 3, 2, 1, 0, 1], [0, 1, 3, 2, 1, 2, 3, 1]]
    order = orders[int(rng.integers(0, len(orders)))]
    for b in range(g.nb):
        ph = int(g.phase[b])
        ch = g.chords[b]
        if g.on(b, kal):
            tones = ch.voicing(67, 84, 4)
            for k in range(2):
                idx = order[(ph * 2 + k) % len(order)]
                q.add(kal, g.tb(b, k / 2.0), 'kalimba_soft', tones[min(idx, len(tones) - 1)], 0.85 if k == 0 else 0.65, -0.2, 0.3, 0)
        if g.on(b, bass):
            if ph in (0, 2):
                q.add(bass, g.tb(b), 'bounce_bass', ch.root - 12 if ph == 0 else ch.voicing(43, 55, 2)[-1], 0.9, 0.0, 0.3, 0)
            if ph in (1, 3):
                q.add(bass, g.tb(b, 0.5), 'bounce_bass', ch.root - 12, 0.7, 0.0, 0.25, 0)
        if g.on(b, shk):
            for k in range(4):
                q.add(shk, g.tb(b, k / 4.0), 'shaker', 0, (0.9, 0.45, 0.7, 0.5)[k], 0.35, 0.03)
        if g.on(b, clave):
            pat = [(0, 0.0), (1, 0.5), (3, 0.0)] if int(g.barno[b]) % 2 == 0 else [(1, 0.0), (2, 0.0)]
            for p, f in pat:
                if p == ph:
                    q.add(clave, g.tb(b, f), 'clave', 0, 0.9, -0.4, 0.02)
        if g.on(b, bell) and ph == 0:
            q.add(bell, g.tb(b), 'bell', ch.root + 36, 0.65, 0.4, 1.0, 0)
    mot = q.motif(79, 91, 2 * g.bpb, 0.5, 2, steps=(-2, -1, -1, 0, 1, 1, 2))
    q.play_motif(whistle, 'whistle', mot, 2, 2, pan=0.1, vel=0.8, bars_on=lambda k: k % 4 < 2, max_dur=1.0)
    gl = _Layer('gliss', 0.0, -12.0)
    fill = _Layer('fill', 0.0, -17.0, 'perc')
    pent = _scale({'root': q.bed['root'], 'mode': 'pentatonic_major'}, 67, 91)
    for b in sorted(g.fx_accents):
        if b >= g.final_beat:
            continue
        start = pent.index(min(pent, key=lambda m: abs(m - 70)))
        for k in range(6):
            q.add(gl, g.tb(b, k / 6.0), 'kalimba_soft', pent[min(start + k, len(pent) - 1)], 0.55 + 0.08 * k, -0.3 + 0.12 * k, 0.3, 0)
        for f in (0.25, 0.5, 0.75):
            q.add(fill, g.tb(b, f), 'clave', 0, 0.8, -0.4, 0.02)
    q.swell_and_riser()
    q.final_chord('kalimba_soft', 67, 84, -11.0, 'bounce_bass', -9.0)


def _gen_orbit(q: _Seq):
    g, rng = q.g, q.rng
    pad = _Layer('pad', 0.0, -19.0, 'pad', respect=True, pad=True)
    sub = _Layer('sub', 0.3, -15.0)
    arp = _Layer('arp', 0.5, -18.0)
    kick = _Layer('kick', 0.65, -11.0, 'perc', perc=True)
    spark = _Layer('spark', 0.8, -22.0)
    bell = _Layer('bell', 0.9, -19.0)
    q.pad_layer(pad, 'pad_cluster', 54, 78, 3, root_oct=0, rel=1.2)
    for b0, b1, ch in g.regions():
        if not g.on(b0, sub):
            continue
        t0, t1 = g.tb(b0), g.tb(min(b1, g.final_beat))
        if t1 > t0 + 0.1:
            q.add(sub, t0, 'sub', ch.root - 24, 0.9, 0.0, t1 - t0 + 0.2, 0, human=False)
    dly = 3.0 * g.bar / 16.0
    order = [0, 1, 2, 3, 2, 1]
    for b in range(g.nb):
        ph = int(g.phase[b])
        ch = g.chords[b]
        if g.on(b, arp):
            up = 12 if (int(g.barno[b]) == 0 and (b - ph) in g.fx_accents) else 0
            tones = ch.voicing(66, 83, 4)
            for k in range(4):
                idx = order[(ph * 4 + k) % len(order)]
                q.add(arp, g.tb(b, k / 4.0), 'arp_sq', tones[min(idx, len(tones) - 1)] + up, 0.8 if k == 0 else 0.6,
                      -0.35 if k % 2 else 0.35, g.beat / 4.0 * 0.9, 0, delay=round(dly, 3))
        if g.on(b, kick):
            t = g.tb(b)
            q.add(kick, t, 'kick_soft', 0, 0.95 if ph == 0 else 0.8, 0.0, 0.28, 0, human=False)
            q.kick_times.append(t)
        if g.on(b, spark):
            for k in range(4):
                if rng.random() < 0.1:
                    q.add(spark, g.tb(b, k / 4.0), 'glass', int(rng.integers(108, 121)), 0.6, float(rng.uniform(-0.9, 0.9)), 0.4, 0)
        if g.on(b, bell) and ph == 0 and int(g.barno[b]) % 2 == 0:
            q.add(bell, g.tb(b), 'bell', ch.voicing(88, 100, 4)[-1], 0.6, 0.3, 1.5, 0)
    q.swell_and_riser(swell_db=-22.0)
    q.final_chord('vibes', 66, 83, -13.0, 'sub', -15.0)      # Sub wie in der Schicht, der Nachklang bleibt unter dem Höhepunkt


def _gen_parlour(q: _Seq):
    g, rng = q.g, q.rng
    pad = _Layer('pad', 0.0, -24.0, 'pad', respect=True, pad=True)
    box = _Layer('musicbox', 0.2, -10.0, respect=True)
    pizz = _Layer('pizz', 0.5, -10.0)
    cemb = _Layer('cembalo', 0.65, -13.0)
    timp = _Layer('timpani', 0.8, -14.0, 'perc', perc=True)
    high = _Layer('high', 0.9, -17.0)
    q.pad_layer(pad, 'pad_bow', 58, 77, 3, root_oct=0, rel=0.6)
    mot = q.motif(77, 89, 2 * g.bpb, 0.55, 2, steps=(-2, -1, -1, 0, 1, 1, 2, 3))
    q.play_motif(box, 'musicbox', mot, 2, 2, pan=0.1, vel=0.8, max_dur=0.6)
    for b in range(g.nb):
        ph = int(g.phase[b])
        ch = g.chords[b]
        if g.on(b, pizz) and ph == 0:
            q.add(pizz, g.tb(b), 'pizz', ch.root - 12, 0.9, 0.0, 0.5)
        if g.on(b, cemb) and ph in (1, 2):
            tones = ch.voicing(62, 77, 4)
            pair = (tones[0], tones[1]) if ph == 1 else (tones[min(2, len(tones) - 1)], tones[min(1, len(tones) - 1)])
            for k, m in enumerate(pair):
                q.add(cemb, g.tb(b, k / 2.0), 'cembalo', m, 0.75 if k == 0 else 0.6, -0.3, 0.16, 0)
        if g.on(b, timp) and ph == 0:
            q.add(timp, g.tb(b), 'timpani', 0, 0.8, 0.0, 0.5, 0)
        if g.on(b, high) and ph == 0 and int(g.barno[b]) % 2 == 0:
            q.add(high, g.tb(b), 'bell', ch.root + 36, 0.6, -0.3, 1.4, 0)
    run = _Layer('run', 0.0, -12.0)
    sc = _scale(q.bed, 77, 93)
    for b in sorted(g.fx_accents):
        if b >= g.final_beat:
            continue
        start = sc.index(min(sc, key=lambda m: abs(m - (g.chords[b].root + 24))))
        for k in range(6):
            q.add(run, g.tb(b, k / 6.0), 'musicbox', sc[min(start + k, len(sc) - 1)], 0.6 + 0.07 * k, 0.1, 0.4, 0)
    q.swell_and_riser(swell_db=-24.0, riser_db=-22.0)
    q.final_chord('musicbox', 70, 86, -12.0, 'pizz', -10.0)


_GENERATORS = {'cabinet': _gen_cabinet, 'pulse': lambda q: _gen_cabinet(q, pulse=True), 'heist': _gen_heist,
               'cave': _gen_cave, 'safari': _gen_safari, 'orbit': _gen_orbit, 'parlour': _gen_parlour}


# ---------------------------------------------------------------------------------------------------------------
# Nachbearbeitung, Hall, Master
# ---------------------------------------------------------------------------------------------------------------

PAD_DOWN = 4                                # Pad-Engine rechnet bei SR/4 (Inhalt < 6 kHz) und tastet hoch
_PAD_ATTACK = {'pad_warm': 0.35, 'pad_dark': 0.3, 'pad_saw': 0.6, 'pad_cluster': 0.8, 'pad_bow': 0.4, 'pad_light': 0.2}


def _pad_osc(kind: str, f: float, n4: int) -> np.ndarray:
    """Dauerton eines Pads bei SR/PAD_DOWN, Stereo (n4, 2), Spitze 0.5. Trick: ein Oszillator mit Frequenz
    PAD_DOWN·f über n4 Samples bei SR ist genau der Ton f bei SR/PAD_DOWN (auch polyBLEP und Filter stimmen so)."""
    dur4 = n4 / SR
    t = np.arange(n4, dtype=np.float64) * (PAD_DOWN / SR)
    w = S.TWO_PI

    def saw(fr):
        return S.saw(fr * PAD_DOWN, dur4).astype(np.float64)[:n4]

    def tri(fr):
        return S.tri(fr * PAD_DOWN, dur4).astype(np.float64)[:n4]

    def lp(x, fc):
        return S.lowpass(np.asarray(x, np.float32), fc * PAD_DOWN).astype(np.float64)

    if kind == 'pad_warm':
        ch = [np.sin(w * fr * t) + 0.35 * np.sin(w * 2.0 * fr * t + 0.3) + 0.12 * np.sin(w * 3.0 * fr * t + 1.1)
              for fr in (f * 0.998, f * 1.002)]
    elif kind == 'pad_dark':
        ch = [lp(tri(fr), 700.0) for fr in (f * 0.9975, f * 1.0025)]
    elif kind == 'pad_saw':
        ch = [saw(fr) for fr in (f * 0.996, f * 1.004)]
    elif kind == 'pad_cluster':
        ch = []
        for fr, sign in ((f * 0.9985, 1.0), (f * 1.0015, -1.0)):
            wob = 0.5 * np.sin(w * 0.23 * t + sign * 1.3)
            ch.append(np.sin(w * fr * t + sign * wob) + 0.45 * np.sin(w * 2.0 * fr * t - sign * wob)
                      + 0.18 * np.sin(w * 3.0 * fr * t + 0.7))
    elif kind == 'pad_bow':
        ch = [lp(saw(fr), 1200.0) for fr in (f * 0.997, f * 1.003)]
    else:  # pad_light
        ch = [lp(0.6 * tri(fr) + 0.4 * np.sin(w * fr * t), 2000.0) for fr in (f * 0.998, f * 1.002)]
    x = np.stack([c[:n4] for c in ch], axis=1)
    return x * (0.5 / (float(np.abs(x).max()) + 1e-9))


def _render_pad(q: _Seq, variant: str):
    """Gesammelte Pad-Noten bei SR/PAD_DOWN rendern (Oszillator je Tonhöhe gecacht, ADSR je Note), Bett-Filter
    anwenden (Höhle: Tiefpass 300 Hz mit LFO 0.1 Hz; Kabinett/Heist: Tiefpass 2.5 kHz) und in den Pad-Bus hochtasten."""
    if not q.pad_notes:
        return
    n = len(q.bus['pad'])
    n4 = -(-n // PAD_DOWN)
    bus4 = np.zeros((n4, 2), np.float64)
    L4 = int(math.ceil(max(d for _, _, d, _, _ in q.pad_notes) * SR / PAD_DOWN)) + 8
    att = _PAD_ATTACK.get(q.pad_inst, 0.3)
    cache = {}
    for t0, m, dur, vel, rel in q.pad_notes:
        osc = cache.get(m)
        if osc is None:
            osc = cache[m] = _pad_osc(q.pad_inst, S.midi_to_freq(m), L4)
        s0 = int(round(t0 * SR / PAD_DOWN))
        k = min(int(round(dur * SR / PAD_DOWN)), n4 - s0, L4)
        if k <= 0:
            continue
        env = S.adsr(k / SR, a=min(att, dur * 0.4) / PAD_DOWN, d=0.25 / PAD_DOWN, s=0.82,
                     r=min(rel, dur * 0.45) / PAD_DOWN, curve='exp')[:k].astype(np.float64)
        bus4[s0:s0 + k] += osc[:k] * (env * (vel * q.pad_gain))[:, None]
    if variant == 'cave':
        t4 = np.arange(n4, dtype=np.float64) * (PAD_DOWN / SR)
        cut = 300.0 * 2.0 ** (0.7 * np.sin(S.TWO_PI * 0.1 * t4)) * PAD_DOWN
        bus4 = S.svf(bus4.astype(np.float32), cut, q=1.0, mode='lp', block=512).astype(np.float64)
    elif variant in ('cabinet', 'pulse', 'heist'):
        bus4 = S.lowpass(bus4.astype(np.float32), 2500.0 * PAD_DOWN).astype(np.float64)
    up = sps.resample_poly(np.ascontiguousarray(bus4.T), PAD_DOWN, 1, axis=-1)[:, :n].T
    q.bus['pad'][:up.shape[0]] += up.astype(np.float32)


def _post(q: _Seq, variant: str):
    """Sidechain des Orbit-Betts: Pad und Melodie pumpen 6 dB unter dem weichen Kick."""
    n = len(q.bus['pad'])
    if variant == 'orbit' and q.kick_times:
        imp = np.zeros(n)
        idx = np.minimum((np.asarray(q.kick_times) * SR).astype(int), n - 1)
        imp[idx] = 1.0
        a = math.exp(-1.0 / (0.13 * SR))
        env = np.minimum(1.0, sps.lfilter([1.0], [1.0, -a], imp))
        gain = (1.0 - 0.5 * env).astype(np.float32)[:, None]
        q.bus['pad'] *= gain
        q.bus['mel'] *= gain


def _wet_curve(g: _Grid, base: float, n: int) -> np.ndarray:
    """Hallanteil je Sample: Grundwert, in Respekt-Abschnitten mehr (geglättet über 0.4 s)."""
    per_beat = np.where(g.respect, min(0.55, base * 1.7 + 0.08), base)
    nbeat = max(1, int(round(g.beat * SR)))
    curve = np.repeat(per_beat, nbeat)[:n]
    if len(curve) < n:
        curve = np.concatenate([curve, np.full(n - len(curve), curve[-1] if len(curve) else base)])
    return uniform_filter1d(curve, size=int(0.4 * SR), mode='nearest')


def _energy_gain(g: _Grid, n: int) -> np.ndarray:
    """Gesamtpegel folgt der Energie: 7 dB je Energieeinheit um 0.6, begrenzt auf ±2.5 dB, geglättet über 0.5 s
    (Hook 0, #5 -0.7, #1 +2.1, Outro -1.4, Respekt -2.5)."""
    per_beat = np.clip(7.0 * (g.energy - 0.6), -2.5, 2.5)
    nbeat = max(1, int(round(g.beat * SR)))
    curve = np.repeat(per_beat, nbeat)[:n]
    if len(curve) < n:
        curve = np.concatenate([curve, np.full(n - len(curve), curve[-1] if len(curve) else 0.0)])
    return 10.0 ** (uniform_filter1d(curve, size=int(0.5 * SR), mode='nearest') / 20.0)


def _limit(x: np.ndarray, ceiling_db: float = PEAK_DB, lookahead: float = 0.004, release: float = 0.15) -> np.ndarray:
    """Sanfter Lookahead-Limiter (Sample-Peak): Gain wird über ``lookahead`` angefahren, kehrt mit ``release`` zurück."""
    ceil = S.db(ceiling_db)
    env = np.abs(x).max(axis=1)
    g_req = np.minimum(1.0, ceil / np.maximum(env, 1e-9))
    n = len(x)
    if n == 0 or g_req.min() >= 1.0 - 1e-6:
        return x
    L = max(1, int(round(lookahead * SR)))
    held = minimum_filter1d(g_req, size=2 * L + 1, mode='nearest')
    ramp = uniform_filter1d(held, size=L + 1, mode='nearest')
    red = -20.0 * np.log10(np.maximum(ramp, 1e-6))
    hop = max(1, int(round(0.002 * SR)))
    m = -(-n // hop)
    blk = np.concatenate([red, np.zeros(m * hop - n)]).reshape(m, hop).max(axis=1)
    coef = math.exp(-hop / (release * SR))
    rel = np.empty(m)
    e = 0.0
    for i, v in enumerate(blk.tolist()):
        e = v if v > e else e * coef
        rel[i] = e
    total = np.maximum(red, uniform_filter1d(np.repeat(rel, hop)[:n], size=hop, mode='nearest'))
    y = x * (10.0 ** (-total / 20.0)).astype(np.float32)[:, None]
    pk = float(np.abs(y).max())
    if pk > ceil:
        y *= ceil / pk
    return y


def _master(q: _Seq, g: _Grid, bed: dict, n: int, seed: int) -> np.ndarray:
    """Busse summieren (Perkussion und Effekte bandbegrenzt gegen harte Sprünge), Faltungshall (nur nass, Anteil je
    Bett und Respekt), Energie-Verlauf, Hochpass 20 Hz, RMS-Normierung, Limiter -3 dBFS, weiche Ränder."""
    rv = bed['reverb']
    perc = S.lowpass(q.bus['perc'], 8000.0)
    fx = S.lowpass(q.bus['fx'], 8000.0)
    dry = q.bus['pad'] + q.bus['mel']
    send = dry + fx
    send += perc * np.float32(0.4)
    dry += perc
    dry += fx
    del perc, fx
    ir = S._reverb_ir(rv['size'], rv['decay'], 0.015, seed & 0xFF)
    wet = np.stack([sps.oaconvolve(send[:n, c], ir[:, c].astype(np.float32))[:n] for c in range(2)], axis=1)
    del send
    out = dry[:n] + wet * _wet_curve(g, rv['mix'], n).astype(np.float32)[:, None]
    del wet
    out *= _energy_gain(g, n).astype(np.float32)[:, None]
    sos = np.vstack([sps.butter(2, 20.0, 'highpass', fs=SR, output='sos'),
                     sps.butter(2, 14000.0, 'lowpass', fs=SR, output='sos')])      # kein Gleichanteil, keine harten Kanten
    out = np.ascontiguousarray(sps.sosfilt(sos, np.ascontiguousarray(out.T), axis=-1).T, dtype=np.float32)
    flat = out.ravel()
    rms = math.sqrt(float(np.dot(flat, flat)) / max(1, flat.size))
    if rms > 1e-9:
        out *= np.float32(S.db(RMS_DB) / rms)
    out = _limit(out, PEAK_DB)
    fi, fo = min(n, int(0.005 * SR)), min(n, int(0.03 * SR))
    if fi > 1:
        out[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)[:, None]
    if fo > 1:
        out[n - fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)[:, None]
    return np.ascontiguousarray(out, dtype=np.float32)


# ---------------------------------------------------------------------------------------------------------------
# Öffentlich: render, render_all
# ---------------------------------------------------------------------------------------------------------------

def render(bed_id: str, duration: float, seed: int = 0, sections: list = None, energy: float = None,
           stats: dict = None) -> np.ndarray:
    """Musikbett rendern: Stereo float32 (n, 2) mit n = round(duration · SR), Spitze ≤ -3 dBFS.

    ``sections`` aus mix.sections_from (fehlt: demo_sections(duration), eine Hook-Einträge-Outro-Vorführung);
    ``energy`` erzwingt eine konstante Energie (dann ein Abschnitt ohne Akzente). Unbekannte IDs werden über den
    längsten gemeinsamen Präfix aufgelöst (orbit_glow_ocean -> orbit_glow), sonst KeyError.
    ``stats`` (dict) bekommt Messwerte: notes, renders, seconds, bpm, bars.
    """
    bid = resolve(bed_id, default=None)
    bed = BEDS[bid]
    t_start = time.time()
    duration = float(duration)
    n = max(1, int(round(duration * SR)))
    if energy is not None:
        sections = [{'t0': 0.0, 't1': duration, 'kind': 'entry', 'rank': 3, 'energy': float(energy)}]
    elif not sections:
        sections = demo_sections(duration)
    seed = int(seed) & 0xFFFFFFFF
    rng = np.random.default_rng([seed, sum(map(ord, bid))])
    g = _Grid(bed, duration, sections, rng)
    bank = _Bank()
    q = _Seq(bed, g, bank, rng, n + int(3.0 * SR))
    _GENERATORS[bed['variant']](q)
    _render_pad(q, bed['variant'])
    _post(q, bed['variant'])
    out = _master(q, g, bed, n, seed)
    if stats is not None:
        stats.update({'notes': q.notes, 'renders': bank.renders, 'seconds': round(time.time() - t_start, 3),
                      'bpm': bed['bpm'], 'bars': round(duration / g.bar, 2), 'accents': sorted(g.accents),
                      'final_beat': int(g.final_beat) if g.final_beat < g.nb else None})
    return out


def measure(x: np.ndarray) -> dict:
    """Messwerte eines Signals: Spitze (dBFS), RMS (dBFS), Gleichanteil, größter Sprung zwischen Nachbarsamples, NaN."""
    x = np.asarray(x, np.float64)
    st = x if x.ndim == 2 else x[:, None]
    peak = float(np.abs(st).max()) if st.size else 0.0
    return {'peak_db': round(20.0 * math.log10(peak + 1e-12), 2), 'rms_db': round(wav.rms_db(st.astype(np.float32)), 2),
            'dc': round(float(np.abs(st.mean(axis=0)).max()), 5),
            'max_step': round(float(np.abs(np.diff(st, axis=0)).max()) if len(st) > 1 else 0.0, 4),
            'finite': bool(np.isfinite(st).all()), 'samples': int(len(st)), 'seconds': round(len(st) / SR, 3)}


def render_all(out_dir: str, seconds: float = 30.0, seed: int = 0) -> dict:
    """Alle Betten mit Vorführ-Struktur nach <out_dir>/<id>.wav rendern; Messwerte je Bett."""
    os.makedirs(out_dir, exist_ok=True)
    beds = []
    for bid in BEDS:
        st = {}
        x = render(bid, seconds, seed=seed, stats=st)
        path = os.path.join(out_dir, f'{bid}.wav')
        wav.write(path, x, SR)
        m = measure(x)
        beds.append({'id': bid, 'file': path, 'bpm': BEDS[bid]['bpm'], 'key': BEDS[bid]['key'], 'dur': m['seconds'],
                     'peak_db': m['peak_db'], 'rms_db': m['rms_db'], 'dc': m['dc'], 'max_step': m['max_step'],
                     'notes': st['notes'], 'render_s': st['seconds']})
    return {'dir': out_dir, 'seconds': seconds, 'beds': beds}
