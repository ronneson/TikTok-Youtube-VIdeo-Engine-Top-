"""Projekte: Ordner projects/<datum>_<slug>/ mit script.json anlegen und finden."""
from __future__ import annotations
import datetime as _dt
import glob
import json
import os
from . import ROOT

TEMPLATE = {
    "title": "Top 5 Curious Heists",
    "slug": "curious-heists",
    "format": "portrait",
    "lang": "en",
    "theme": "heist",
    "series": "CURIOUS HEISTS",
    "caption": "Five heists too strange to be fiction. #heist #history #curious",
    "hashtags": ["#curious", "#history", "#top5"],
    "tempo": 1.0,
    "tail": 2.0,
    "music": "auto",
    "announce": "number_title",
    "hook": {"lines": ["These five heists were too dumb to be fake."], "keyword": "TOO DUMB TO BE FAKE", "visual": {"backdrop": "spotlight"}},
    "entries": [
        {"rank": 2, "title": "The Second Thing", "lines": ["Second sentence here.", "And a twist."],
         "place": "Somewhere", "year": 2001, "stat": {"value": "42", "label": "UNITS"},
         "visual": {"backdrop": "night", "props": ["bag"], "mascot": {"pose": "think", "costume": "default"}}},
        {"rank": 1, "title": "The First Thing", "lines": ["First sentence here.", "The payoff."],
         "visual": {"backdrop": "spotlight", "props": [], "mascot": {"pose": "shock"}}}
    ],
    "outro": {"lines": ["Which one would you have tried?"], "visual": {"mascot": {"pose": "wink"}}},
    "sources": []
}


def projects_dir(root: str = None) -> str:
    return os.path.join(root or ROOT, 'projects')


def new(slug: str, title: str, root: str = None, fmt: str = 'portrait', theme: str = 'curious', series: str = '') -> str:
    root = root or ROOT
    date = _dt.date.today().isoformat()
    d = os.path.join(projects_dir(root), f"{date}_{slug}")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, 'script.json')
    if not os.path.exists(p):
        s = json.loads(json.dumps(TEMPLATE))
        s.update({'title': title, 'slug': slug, 'format': fmt, 'theme': theme, 'series': series or theme.upper()})
        with open(p, 'w', encoding='utf-8') as fh:
            json.dump(s, fh, indent=1, ensure_ascii=False)
    return d


def find(name: str, root: str = None) -> str:
    """Projekt nach Pfad oder (Teil des) Ordnernamens."""
    root = root or ROOT
    if os.path.isdir(name):
        return os.path.abspath(name)
    cands = sorted(glob.glob(os.path.join(projects_dir(root), f"*{name}*")))
    if not cands:
        raise FileNotFoundError(f"Projekt nicht gefunden: {name}")
    return os.path.abspath(cands[-1])


def listing(root: str = None) -> list:
    root = root or ROOT
    out = []
    for d in sorted(glob.glob(os.path.join(projects_dir(root), '*'))):
        if os.path.isdir(d) and os.path.exists(os.path.join(d, 'script.json')):
            with open(os.path.join(d, 'script.json'), encoding='utf-8') as fh:
                s = json.load(fh)
            out.append({'dir': os.path.basename(d), 'title': s.get('title'), 'voice': os.path.exists(os.path.join(d, 'voice.wav')),
                        'mix': os.path.exists(os.path.join(d, 'mix.wav')), 'video': sorted(glob.glob(os.path.join(d, '*.mp4')))})
    return out


def status(root: str = None) -> dict:
    import shutil
    from . import config as CFG
    root = root or ROOT
    cfg = CFG.load(root)
    key = CFG.get_key('elevenlabs', root)
    free = shutil.disk_usage(root).free / 1e9
    return {
        'root': root,
        'ffmpeg': shutil.which('ffmpeg') is not None,
        'espeak': shutil.which('espeak-ng') is not None,
        'elevenlabs_key': bool(key),
        'voice_id': bool(cfg['voice'].get('voice_id')),
        'provider': cfg['voice'].get('provider'),
        'free_gb': round(free, 1),
        'projects': len(listing(root)),
    }
