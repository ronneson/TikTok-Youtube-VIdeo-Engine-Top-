"""Skriptformat (script.json) laden, prüfen, in eine Zeilenfolge für Stimme und Timeline auflösen.

Aufbau:
{
 "title": "Top 5 Curious Heists", "slug": "curious-heists", "format": "portrait", "lang": "en", "theme": "heist",
 "series": "CURIOUS HEISTS", "caption": "...", "hashtags": ["#heist"], "tempo": 1.0, "tail": 2.0, "music": "auto",
 "announce": "number_title",        # number_title | number | none  (was der Sprecher bei jeder Nummer sagt)
 "hook":    {"lines": ["..."], "keyword": "...", "visual": {...}},
 "entries": [{"rank": 5, "title": "...", "lines": ["...", {"text": "...", "gap_after": 0.4}],
              "place": "...", "year": 2012, "stat": {"value": "$18M", "label": "OF SYRUP", "at": "18"},
              "visual": {"backdrop": "warehouse", "props": [...], "mascot": {"pose": "sneak", "costume": "thief"}},
              "cues": [["word", "sfx_id", -6]]}],
 "outro":   {"lines": ["..."], "visual": {...}},
 "sources": [{"claim": "...", "url": "..."}]
}
Eine Zeile ist ein Gedanke (ein bis drei kurze Sätze). Jede Zeile bekommt eine ID: H1.., E5.0 (Ansage), E5.1.., O1..
"""
from __future__ import annotations
import json
import os
import re

NUMBER_WORDS = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten',
                11: 'eleven', 12: 'twelve', 13: 'thirteen', 14: 'fourteen', 15: 'fifteen', 20: 'twenty'}
NUMBER_WORDS_DE = {1: 'eins', 2: 'zwei', 3: 'drei', 4: 'vier', 5: 'fünf', 6: 'sechs', 7: 'sieben', 8: 'acht', 9: 'neun', 10: 'zehn'}


class ScriptError(ValueError):
    pass


def load(path: str) -> dict:
    if os.path.isdir(path):
        path = os.path.join(path, 'script.json')
    with open(path, encoding='utf-8') as fh:
        s = json.load(fh)
    validate(s)
    return s


def validate(s: dict):
    for k in ('title', 'slug', 'entries'):
        if k not in s:
            raise ScriptError(f"script.json: Feld '{k}' fehlt")
    if not isinstance(s['entries'], list) or not s['entries']:
        raise ScriptError("script.json: 'entries' muss eine nicht leere Liste sein")
    ranks = [e.get('rank') for e in s['entries']]
    if any(r is None for r in ranks):
        raise ScriptError("script.json: jeder Eintrag braucht 'rank'")
    if len(set(ranks)) != len(ranks):
        raise ScriptError("script.json: doppelte 'rank'-Werte")
    for e in s['entries']:
        if 'title' not in e or not e.get('lines'):
            raise ScriptError(f"script.json: Eintrag {e.get('rank')} braucht 'title' und 'lines'")
    if s.get('format', 'portrait') not in ('portrait', 'landscape', 'tiktok', 'youtube', '9:16', '16:9'):
        raise ScriptError(f"script.json: unbekanntes Format {s.get('format')!r}")


def _norm_line(item, lid: str, kind: str, rank=None) -> dict:
    if isinstance(item, str):
        d = {'text': item}
    else:
        d = dict(item)
    d['id'] = lid
    d['kind'] = kind
    d['rank'] = rank
    d['text'] = ' '.join(str(d.get('text', '')).split())
    d.setdefault('gap_after', 0.0)
    return d


def announce_text(entry: dict, style: str, lang: str = 'en') -> str:
    if 'announce' in entry:
        return ' '.join(str(entry['announce']).split())
    if style == 'none':
        return ''
    r = int(entry['rank'])
    if lang.startswith('de'):
        num = f"Nummer {NUMBER_WORDS_DE.get(r, r)}."
    else:
        num = f"Number {NUMBER_WORDS.get(r, r)}."
    if style == 'number':
        return num
    title = entry['title'].strip()
    if not title.endswith(('.', '!', '?')):
        title += '.'
    return f"{num} {title}"


def lines(s: dict) -> list:
    """Alle gesprochenen Zeilen in Reihenfolge, mit IDs. Einträge absteigend nach rank (Countdown)."""
    out = []
    style = s.get('announce', 'number_title')
    lang = s.get('lang', 'en')
    for i, item in enumerate(s.get('hook', {}).get('lines', []), 1):
        out.append(_norm_line(item, f'H{i}', 'hook'))
    for e in sorted(s['entries'], key=lambda e: -int(e['rank'])):
        r = int(e['rank'])
        ann = announce_text(e, style, lang)
        if ann:
            d = _norm_line({'text': ann, 'gap_after': e.get('announce_gap', 0.25)}, f'E{r}.0', 'announce', r)
            out.append(d)
        for j, item in enumerate(e['lines'], 1):
            out.append(_norm_line(item, f'E{r}.{j}', 'entry', r))
    for i, item in enumerate(s.get('outro', {}).get('lines', []), 1):
        out.append(_norm_line(item, f'O{i}', 'outro'))
    for ln in out:
        if not ln['text']:
            raise ScriptError(f"Zeile {ln['id']} ist leer")
    return out


def narration(s: dict, sep: str = '\n') -> str:
    """Gesamter Sprechtext in Zeilen (so geht er zur Stimme)."""
    return sep.join(ln['text'] for ln in lines(s))


_WORD_RE = re.compile(r"\S+")


def tokens(text: str) -> list:
    """Wörter wie sie in words.json stehen (an Leerzeichen getrennt, Satzzeichen bleiben dran)."""
    return _WORD_RE.findall(text)


def word_count(s: dict) -> int:
    return sum(len(tokens(ln['text'])) for ln in lines(s))


def clean_word(w: str) -> str:
    """Zum Vergleich: klein, ohne Satzzeichen am Rand."""
    return re.sub(r"^[^\w$€£%]+|[^\w%]+$", '', w.lower())


def entries_desc(s: dict) -> list:
    return sorted(s['entries'], key=lambda e: -int(e['rank']))


def hashtags(s: dict) -> str:
    tags = s.get('hashtags') or []
    return ' '.join(t if t.startswith('#') else '#' + t for t in tags)


def save(s: dict, path: str):
    if os.path.isdir(path):
        path = os.path.join(path, 'script.json')
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(s, fh, indent=1, ensure_ascii=False)
