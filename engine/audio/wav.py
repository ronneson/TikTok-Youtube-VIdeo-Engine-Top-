"""WAV lesen und schreiben als numpy float32 (-1..1). Mono (n,) oder Stereo (n, 2)."""
from __future__ import annotations
import subprocess
import numpy as np
from scipy.io import wavfile
from . import SR


def read(path: str, sr: int = SR, mono: bool = False) -> tuple:
    """Liest beliebige Audio-Dateien (über ffmpeg bei Bedarf) als float32 mit Zielrate."""
    try:
        rate, data = wavfile.read(path)
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32768.0
        elif data.dtype == np.int32:
            data = data.astype(np.float32) / 2147483648.0
        elif data.dtype == np.uint8:
            data = (data.astype(np.float32) - 128) / 128.0
        else:
            data = data.astype(np.float32)
        if rate != sr:
            data = resample(data, rate, sr)
    except Exception:
        data = _ffmpeg_decode(path, sr)
    if mono and data.ndim == 2:
        data = data.mean(axis=1)
    return data, sr


def _ffmpeg_decode(path: str, sr: int) -> np.ndarray:
    cmd = ['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le', '-acodec', 'pcm_f32le', '-ac', '2', '-ar', str(sr), '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    arr = np.frombuffer(raw, np.float32).reshape(-1, 2)
    return arr.copy()


def write(path: str, data: np.ndarray, sr: int = SR):
    d = np.clip(np.asarray(data, np.float32), -1.0, 1.0)
    wavfile.write(path, sr, (d * 32767.0).astype(np.int16))


def resample(data: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return data
    from scipy.signal import resample_poly
    from math import gcd
    g = gcd(src, dst)
    return resample_poly(data, dst // g, src // g, axis=0).astype(np.float32)


def to_stereo(d: np.ndarray) -> np.ndarray:
    if d.ndim == 1:
        return np.stack([d, d], axis=1)
    return d


def to_mono(d: np.ndarray) -> np.ndarray:
    return d.mean(axis=1) if d.ndim == 2 else d


def duration(d: np.ndarray, sr: int = SR) -> float:
    return len(d) / sr


def silence(seconds: float, stereo: bool = True, sr: int = SR) -> np.ndarray:
    n = int(round(seconds * sr))
    return np.zeros((n, 2), np.float32) if stereo else np.zeros(n, np.float32)


def db(x: float) -> float:
    return 10 ** (x / 20.0)


def rms_db(d: np.ndarray) -> float:
    m = to_mono(d) if d.ndim == 2 else d
    r = float(np.sqrt(np.mean(m * m) + 1e-12))
    return 20 * np.log10(r + 1e-12)


def measure_lufs(path: str) -> dict:
    """Integrierte Lautheit und True Peak über ffmpeg ebur128."""
    cmd = ['ffmpeg', '-v', 'info', '-nostats', '-i', path, '-af', 'ebur128=peak=true', '-f', 'null', '-']
    res = subprocess.run(cmd, capture_output=True, text=True)
    txt = res.stderr
    out = {'lufs': None, 'true_peak': None, 'lra': None}
    import re
    m = re.search(r"I:\s+(-?[\d.]+) LUFS", txt)
    if m:
        out['lufs'] = float(m.group(1))
    m = re.search(r"LRA:\s+(-?[\d.]+) LU", txt)
    if m:
        out['lra'] = float(m.group(1))
    m = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", txt)
    if m:
        out['true_peak'] = float(m[-1])
    return out
