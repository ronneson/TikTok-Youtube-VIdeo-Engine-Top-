"""Stimme erzeugen: ElevenLabs (mit Wortzeiten) oder espeak-ng als Platzhalter.

Ergebnis je Projekt: raw_voice.wav (unbearbeitet) und words_raw.json (Wortzeiten, flach).
Der Schritt `voice` (voice.py) macht daraus voice.wav und words.json.
"""
from __future__ import annotations
import base64
import json
import os
import re
import subprocess
import tempfile
import numpy as np
from .. import config as CFG
from .. import script as S
from . import SR, wav

ELEVEN_URL = 'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps'
MAX_CHARS = 4500   # je Anfrage; längere Texte werden an Zeilengrenzen gestückelt


def provider(cfg: dict, root: str) -> str:
    p = cfg['voice'].get('provider', 'auto')
    if p == 'auto':
        return 'elevenlabs' if (CFG.get_key('elevenlabs', root) and cfg['voice'].get('voice_id')) else 'espeak'
    return p


def synthesize(project_dir: str, cfg: dict, root: str, force_provider: str = None) -> dict:
    """Erzeugt raw_voice.wav und words_raw.json im Projekt. Gibt eine Zusammenfassung zurück."""
    s = S.load(project_dir)
    lines = S.lines(s)
    prov = force_provider or provider(cfg, root)
    if prov == 'elevenlabs':
        audio, words, meta = _elevenlabs(lines, cfg, root)
    elif prov == 'espeak':
        audio, words, meta = _espeak(lines, cfg, s.get('lang', 'en'))
    else:
        raise ValueError(f"unbekannter Stimm-Anbieter: {prov}")
    wav.write(os.path.join(project_dir, 'raw_voice.wav'), audio, SR)
    mapped = _map(lines, words)
    out = {'source': prov, 'duration': round(len(audio) / SR, 3), 'words': mapped, 'meta': meta}
    with open(os.path.join(project_dir, 'words_raw.json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=0, ensure_ascii=False)
    return {'provider': prov, 'duration': out['duration'], 'words': len(mapped), 'chars': sum(len(l['text']) for l in lines), **meta}


def _map(lines: list, flat: list) -> list:
    """Flache Wörter den Zeilen zuordnen; bei Abweichungen Zeile für Zeile proportional füllen."""
    out = []
    k = 0
    for ln in lines:
        toks = S.tokens(ln['text'])
        for tok in toks:
            if k < len(flat):
                wd = flat[k]
                out.append({'w': tok, 't0': round(float(wd['t0']), 3), 't1': round(float(wd['t1']), 3), 'line': ln['id']})
            else:
                last = out[-1]['t1'] if out else 0.0
                out.append({'w': tok, 't0': last, 't1': last + 0.3, 'line': ln['id']})
            k += 1
    return out


# ---------------- ElevenLabs ----------------

def _chunks(lines: list) -> list:
    """Zeilen zu Textblöcken <= MAX_CHARS bündeln (je Block: Liste von Zeilen)."""
    blocks, cur, n = [], [], 0
    for ln in lines:
        L = len(ln['text']) + 1
        if cur and n + L > MAX_CHARS:
            blocks.append(cur)
            cur, n = [], 0
        cur.append(ln)
        n += L
    if cur:
        blocks.append(cur)
    return blocks


def _elevenlabs(lines: list, cfg: dict, root: str):
    import requests
    key = CFG.get_key('elevenlabs', root)
    vid = cfg['voice'].get('voice_id')
    if not key:
        raise RuntimeError("Kein ElevenLabs-Schlüssel: ELEVENLABS_API_KEY setzen oder config/keys/elevenlabs.txt anlegen")
    if not vid:
        raise RuntimeError("Keine voice_id: in config/engine.json unter voice.voice_id eintragen (python3 -m engine voices zeigt die Stimmen)")
    settings = dict(cfg['voice'].get('settings', {}))
    speed = settings.pop('speed', None)
    if speed and abs(speed - 1.0) > 1e-6:
        settings['speed'] = speed
    audio_parts, words, offset = [], [], 0.0
    gap = 0.35
    total_chars = 0
    for block in _chunks(lines):
        text = '\n'.join(ln['text'] for ln in block)
        total_chars += len(text)
        body = {'text': text, 'model_id': cfg['voice'].get('model_id', 'eleven_multilingual_v2'), 'voice_settings': settings}
        r = requests.post(ELEVEN_URL.format(voice_id=vid), params={'output_format': 'mp3_44100_128'},
                          headers={'xi-api-key': key, 'Content-Type': 'application/json'}, json=body, timeout=300)
        if r.status_code != 200:
            raise RuntimeError(f"ElevenLabs antwortet {r.status_code}: {r.text[:300]}")
        data = r.json()
        mp3 = base64.b64decode(data['audio_base64'])
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tf:
            tf.write(mp3)
            tmp = tf.name
        try:
            a, _ = wav.read(tmp, SR, mono=True)
        finally:
            os.unlink(tmp)
        al = data.get('alignment') or data.get('normalized_alignment')
        ws = _words_from_alignment(al, text)
        if len(ws) != len(S.tokens(text)):
            ws = _proportional(text, 0.0, len(a) / SR)
        for w in ws:
            words.append({'w': w['w'], 't0': w['t0'] + offset, 't1': w['t1'] + offset})
        audio_parts.append(a)
        offset += len(a) / SR + gap
        audio_parts.append(np.zeros(int(gap * SR), np.float32))
    audio = np.concatenate(audio_parts[:-1]) if len(audio_parts) > 1 else audio_parts[0]
    return audio, words, {'chars_billed': total_chars, 'model_id': cfg['voice'].get('model_id')}


def _words_from_alignment(al: dict, text: str) -> list:
    if not al:
        return []
    chars = al['characters']
    t0s = al['character_start_times_seconds']
    t1s = al['character_end_times_seconds']
    words, cur, a, b = [], '', None, None
    for ch, s0, s1 in zip(chars, t0s, t1s):
        if ch.isspace():
            if cur:
                words.append({'w': cur, 't0': a, 't1': b})
                cur, a, b = '', None, None
        else:
            if not cur:
                a = s0
            cur += ch
            b = s1
    if cur:
        words.append({'w': cur, 't0': a, 't1': b})
    return words


def _proportional(text: str, t0: float, t1: float) -> list:
    from ..timeline import _syllables, _digits_syll
    toks = S.tokens(text)
    weights = [(_syllables(t) + _digits_syll(t)) + (0.9 if t.endswith(('.', '!', '?')) else 0.3 if t.endswith((',', ';', ':')) else 0.1) for t in toks]
    tot = sum(weights) or 1.0
    out, t = [], t0
    for tok, w in zip(toks, weights):
        d = (t1 - t0) * w / tot
        pause = d * (0.9 / (w) if tok.endswith(('.', '!', '?')) else 0.3 / w if tok.endswith((',', ';', ':')) else 0.1 / w)
        out.append({'w': tok, 't0': t, 't1': t + d - pause})
        t += d
    return out


def list_voices(root: str) -> list:
    import requests
    key = CFG.get_key('elevenlabs', root)
    if not key:
        raise RuntimeError("Kein ElevenLabs-Schlüssel")
    r = requests.get('https://api.elevenlabs.io/v1/voices', headers={'xi-api-key': key}, timeout=60)
    r.raise_for_status()
    return [{'voice_id': v['voice_id'], 'name': v['name'], 'labels': v.get('labels', {})} for v in r.json().get('voices', [])]


# ---------------- espeak-ng (Platzhalter) ----------------

def _trim(a: np.ndarray, thresh: float = 0.01) -> np.ndarray:
    idx = np.where(np.abs(a) > thresh)[0]
    if len(idx) == 0:
        return a
    return a[max(0, idx[0] - int(0.02 * SR)):min(len(a), idx[-1] + int(0.05 * SR))]


def _espeak(lines: list, cfg: dict, lang: str = 'en'):
    voice = cfg['voice'].get('espeak_voice', 'en-us+m3')
    if lang.startswith('de') and voice.startswith('en'):
        voice = 'de+m3'
    wpm = int(cfg['voice'].get('espeak_wpm', 160))
    parts, words, t = [], [], 0.0
    lead = 0.3
    parts.append(np.zeros(int(lead * SR), np.float32))
    t = lead
    with tempfile.TemporaryDirectory() as td:
        for ln in lines:
            p = os.path.join(td, 'l.wav')
            subprocess.run(['espeak-ng', '-v', voice, '-s', str(wpm), '-p', '45', '-a', '170', '-w', p, ln['text']], check=True, capture_output=True)
            a, _ = wav.read(p, SR, mono=True)
            a = _trim(a)
            d = len(a) / SR
            for w in _proportional(ln['text'], t, t + d):
                words.append(w)
            parts.append(a)
            t += d
            g = 0.28 + float(ln.get('gap_after', 0.0))
            parts.append(np.zeros(int(g * SR), np.float32))
            t += g
    audio = np.concatenate(parts)
    audio = audio / (np.max(np.abs(audio)) + 1e-6) * 0.7
    return audio.astype(np.float32), words, {'espeak_voice': voice, 'placeholder': True}
