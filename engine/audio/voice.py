"""Stimme aufbereiten: Stille kürzen, Pausen straffen, Tempo, Klang -> voice.wav + words.json."""
from __future__ import annotations
import json
import os
import subprocess
import tempfile
import numpy as np
from scipy.signal import butter, sosfilt
from . import SR, wav


def process(project_dir: str, cfg: dict) -> dict:
    raw_p = os.path.join(project_dir, 'raw_voice.wav')
    wr_p = os.path.join(project_dir, 'words_raw.json')
    if not os.path.exists(raw_p) or not os.path.exists(wr_p):
        raise FileNotFoundError("raw_voice.wav / words_raw.json fehlen: erst `tts` ausführen")
    audio, _ = wav.read(raw_p, SR, mono=True)
    with open(wr_p, encoding='utf-8') as fh:
        wr = json.load(fh)
    words = [dict(w) for w in wr['words']]
    vcfg = cfg['voice']

    # 1. Anfang: 0,25 s vor dem ersten Wort beginnen
    lead = 0.25
    if words:
        cut = max(0, int((words[0]['t0'] - lead) * SR))
        audio = audio[cut:]
        shift = cut / SR
        for w in words:
            w['t0'] -= shift; w['t1'] -= shift

    # 2. Pausen straffen: Lücken > max_gap auf max_gap kürzen (Schnitt in der Mitte der Lücke)
    max_gap = float(vcfg.get('max_gap', 0.75))
    pieces, pos, removed = [], 0, 0.0
    for a, b in zip(words, words[1:]):
        gap = b['t0'] - a['t1']
        if gap > max_gap:
            extra = gap - max_gap
            s0 = int((a['t1'] + max_gap * 0.5) * SR)
            s1 = int(s0 + extra * SR)
            pieces.append(audio[pos:s0])
            pos = s1
            dt = (s1 - s0) / SR
            b['_shift'] = removed + dt
            removed += dt
        else:
            b['_shift'] = removed
    pieces.append(audio[pos:])
    audio = np.concatenate(pieces)
    for w in words:
        sh = w.pop('_shift', 0.0)
        w['t0'] -= sh; w['t1'] -= sh

    # 3. Ende: nach dem letzten Wort 0,3 s stehen lassen
    if words:
        end = int(min(len(audio), (words[-1]['t1'] + 0.3) * SR))
        audio = audio[:end]

    # 4. Tempo (ffmpeg atempo hält die Tonhöhe)
    tempo = float(vcfg.get('tempo', 1.0))
    s = _load_script_tempo(project_dir)
    if s:
        tempo *= s
    if abs(tempo - 1.0) > 1e-3:
        audio = _atempo(audio, tempo)
        for w in words:
            w['t0'] /= tempo; w['t1'] /= tempo

    # 5. Klang: Hochpass 80 Hz, sanfte Präsenz, Normalisierung auf -3 dBFS Spitze
    sos = butter(2, 80, 'hp', fs=SR, output='sos')
    audio = sosfilt(sos, audio).astype(np.float32)
    audio = _presence(audio)
    audio = _compress(audio)
    peak = float(np.max(np.abs(audio)) + 1e-9)
    audio = audio / peak * 0.7

    wav.write(os.path.join(project_dir, 'voice.wav'), audio, SR)
    dur = len(audio) / SR
    out = {'source': wr.get('source'), 'duration': round(dur, 3), 'words': [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in w.items()} for w in words], 'tempo': tempo}
    with open(os.path.join(project_dir, 'words.json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=0, ensure_ascii=False)
    n = len(words)
    wpm = n / (words[-1]['t1'] - words[0]['t0']) * 60 if n > 1 else 0
    return {'duration': round(dur, 2), 'words': n, 'wpm': round(wpm, 1), 'tempo': tempo, 'removed_pause_s': round(removed, 2), 'source': wr.get('source')}


def _load_script_tempo(project_dir: str) -> float:
    p = os.path.join(project_dir, 'script.json')
    try:
        with open(p, encoding='utf-8') as fh:
            return float(json.load(fh).get('tempo', 1.0))
    except Exception:
        return 1.0


def _atempo(audio: np.ndarray, tempo: float) -> np.ndarray:
    with tempfile.TemporaryDirectory() as td:
        i, o = os.path.join(td, 'i.wav'), os.path.join(td, 'o.wav')
        wav.write(i, audio, SR)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', i, '-af', f'atempo={tempo}', '-ar', str(SR), o], check=True)
        a, _ = wav.read(o, SR, mono=True)
    return a


def _presence(a: np.ndarray, gain_db: float = 2.0) -> np.ndarray:
    """Leichte Anhebung um 3 kHz für Verständlichkeit."""
    sos = butter(2, [2200, 4500], 'bandpass', fs=SR, output='sos')
    band = sosfilt(sos, a)
    return (a + band * (10 ** (gain_db / 20) - 1)).astype(np.float32)


def _compress(a: np.ndarray, thresh_db: float = -18.0, ratio: float = 2.5, attack: float = 0.005, release: float = 0.12) -> np.ndarray:
    """Einfacher RMS-Kompressor (Hüllkurve mit Attack/Release)."""
    env = np.abs(a)
    out_env = np.empty_like(env)
    ga = np.exp(-1.0 / (attack * SR)); gr = np.exp(-1.0 / (release * SR))
    e = 0.0
    # blockweise, um Python-Schleifen zu sparen
    block = 256
    for i in range(0, len(env), block):
        seg = env[i:i + block]
        m = float(seg.max()) if len(seg) else 0.0
        if m > e:
            e = ga ** block * e + (1 - ga ** block) * m
        else:
            e = gr ** block * e + (1 - gr ** block) * m
        out_env[i:i + block] = e
    env_db = 20 * np.log10(out_env + 1e-6)
    over = np.maximum(0.0, env_db - thresh_db)
    gain_db = -over * (1 - 1 / ratio)
    return (a * 10 ** (gain_db / 20)).astype(np.float32)
