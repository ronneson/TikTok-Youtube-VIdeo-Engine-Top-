"""Konfiguration: Standardwerte, überschrieben von config/engine.json. Schlüssel aus Umgebung oder config/keys/."""
from __future__ import annotations
import json
import os
from . import ROOT

DEFAULTS = {
    "format": "portrait",
    "fps": 30,
    "lang": "en",
    "voice": {
        "provider": "elevenlabs",          # elevenlabs | espeak | auto (elevenlabs wenn Schlüssel da, sonst espeak)
        "voice_id": "",
        "model_id": "eleven_multilingual_v2",
        "settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True, "speed": 1.0},
        "tempo": 1.0,                       # nachträgliche Tempoänderung (1.05 = 5 % schneller)
        "max_gap": 0.75,                    # längste erlaubte Pause zwischen Wörtern (wird gestrafft)
        "wpm_estimate": 150,                # Schätzung ohne Stimme
        "espeak_voice": "en-us+m3",
        "espeak_wpm": 160,
    },
    "mix": {
        "voice_lufs": -16.0,
        "master_lufs": -14.0,
        "true_peak_db": -1.0,
        "music_db": -14.0,                  # Musik relativ zur Stimme beim Sprechen
        "music_solo_db": -6.0,              # Musik ohne Stimme (Hook-Pause, Schluss)
        "sfx_db": -8.0,
        "duck_attack": 0.08,
        "duck_release": 0.45,
        "tail": 2.0,                        # Standzeit nach dem letzten Wort
        "music": "auto",                    # Bett-ID oder auto (nach Thema)
    },
    "look": {
        "grain": 0.045,
        "vignette": 0.28,
        "captions": True,
        "watermark": True,
        "progress": True,
        "label": True,
        "caption_style": "odd",            # odd | word | karaoke | line
        "caption_size": 60,
        "caption_max_words": 4,
        "caption_max_chars": 22,
        "caption_plate_alpha": 0.92,
        "caption_weight": 700,
        "push_in": 0.03,                   # langsamer Push-In der Szene je Eintrag
    },
    "brand": {
        "name": "ODD CABINET",
        "handle": "@oddcabinet",
        "mascot": "Odd",
        "exhibit_no": 1,                   # Archivnummer, zählt je Video hoch (Serienetikett)
    },
    "render": {
        "workers": 4,
        "crf": 17,
        "preset": "medium",
        "tune": "animation",
    },
}


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


_CACHE = {}


def load(root: str = None, extra: dict = None) -> dict:
    root = root or ROOT
    path = os.path.join(root, 'config', 'engine.json')
    cfg = DEFAULTS
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            cfg = _merge(cfg, json.load(fh))
    if extra:
        cfg = _merge(cfg, extra)
    return cfg


def save_value(root: str, dotted: str, value):
    """Einen Wert in config/engine.json setzen, z. B. save_value(root, 'voice.voice_id', 'abc')."""
    path = os.path.join(root, 'config', 'engine.json')
    data = {}
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    cur = data
    parts = dotted.split('.')
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)


def get_key(name: str, root: str = None) -> str | None:
    """Schlüssel 'elevenlabs' aus ELEVENLABS_API_KEY oder config/keys/elevenlabs.txt. Nie ausgeben."""
    env = os.environ.get(name.upper() + '_API_KEY') or os.environ.get(name.upper() + '_KEY')
    if env:
        return env.strip()
    root = root or ROOT
    for fn in (name + '.txt', name + '.key', name):
        p = os.path.join(root, 'config', 'keys', fn)
        if os.path.exists(p):
            with open(p, encoding='utf-8') as fh:
                v = fh.read().strip()
                if v:
                    return v
    return None
