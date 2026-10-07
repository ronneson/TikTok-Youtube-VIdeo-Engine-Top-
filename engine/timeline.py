"""Timeline: Zeilen und Wörter mit Zeiten (aus words.json oder geschätzt).

words.json: {"source": "elevenlabs|espeak|estimate", "duration": 71.2,
             "words": [{"w": "Number", "t0": 0.10, "t1": 0.42, "line": "E5.0"}, ...]}
"""
from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass, field
from . import script as S


@dataclass
class Word:
    w: str
    t0: float
    t1: float
    line: str
    i: int = 0            # Index innerhalb der Zeile
    @property
    def clean(self): return S.clean_word(self.w)
    @property
    def dur(self): return self.t1 - self.t0


@dataclass
class Line:
    id: str
    text: str
    kind: str
    rank: int | None
    words: list = field(default_factory=list)
    gap_after: float = 0.0
    meta: dict = field(default_factory=dict)
    @property
    def t0(self): return self.words[0].t0 if self.words else 0.0
    @property
    def t1(self): return self.words[-1].t1 if self.words else 0.0
    @property
    def dur(self): return self.t1 - self.t0


class Timeline:
    def __init__(self, lines: list, duration: float, source: str = 'estimate', fps: int = 30):
        self.lines = lines
        self.by_id = {ln.id: ln for ln in lines}
        self.words = [w for ln in lines for w in ln.words]
        self.duration = duration
        self.source = source
        self.fps = fps

    # --- Zugriff ---
    def line(self, lid: str) -> Line:
        return self.by_id[lid]

    def lines_of(self, kind=None, rank=None) -> list:
        return [ln for ln in self.lines if (kind is None or ln.kind == kind) and (rank is None or ln.rank == rank)]

    def entry_span(self, rank: int) -> tuple:
        ls = [ln for ln in self.lines if ln.rank == rank]
        return (ls[0].t0, ls[-1].t1 + ls[-1].gap_after) if ls else (0.0, 0.0)

    def span(self, kind: str) -> tuple:
        ls = self.lines_of(kind)
        return (ls[0].t0, ls[-1].t1 + ls[-1].gap_after) if ls else (0.0, 0.0)

    def voice_end(self) -> float:
        return self.words[-1].t1 if self.words else 0.0

    def find(self, anchor: str, line_id: str = None) -> Word | None:
        """Wort nach Anker finden: 'syrup', 'syrup#2' (2. Vorkommen), 'E5.1:syrup' (in Zeile), 'syrup$' (Wortende -> t1 verwenden)."""
        a = anchor
        if ':' in a and not a.startswith(':'):
            line_id, a = a.split(':', 1)
        a = a.rstrip('$')
        m = re.match(r"^(.*?)(?:#(\d+))?$", a)
        base, occ = m.group(1), int(m.group(2) or 1)
        base_c = S.clean_word(base)
        pool = self.line(line_id).words if line_id else self.words
        exact = [w for w in pool if w.clean == base_c]
        if len(exact) >= occ:
            return exact[occ - 1]
        prefix = [w for w in pool if w.clean.startswith(base_c)]
        if len(prefix) >= occ:
            return prefix[occ - 1]
        return None

    def at(self, anchor, line_id: str = None, default: float = 0.0) -> float:
        """Zeit eines Ankers. Echte Zahl (int/float) -> Sekunden. String -> Wort: 'wort' Wortbeginn, 'wort$' Wortende,
        Versatz erlaubt ('wort$+0.2', '18-0.1'). Ein Zahlen-String ('18', '9,500') meint das gesprochene Wort;
        nur wenn es kein solches Wort gibt, gilt er als Sekunden."""
        if isinstance(anchor, (int, float)):
            return float(anchor)
        s = str(anchor).strip()
        off = 0.0
        # Versatz abtrennen, aber nur, wenn davor noch ein Anker übrig bleibt
        m = re.match(r"^(.+?)([+-]\d*\.\d+|[+-]\d+)$", s)
        if m and self.find(m.group(1), line_id) is not None:
            s, off = m.group(1), float(m.group(2))
        elif m and not re.match(r"^[+-]?\d*\.?\d+$", m.group(1)):
            s, off = m.group(1), float(m.group(2))
        end = s.endswith('$')
        w = self.find(s, line_id)
        if w is not None:
            return (w.t1 if end else w.t0) + off
        if re.match(r"^[+-]?\d*\.?\d+$", s):
            return float(s) + off
        return default + off

    def to_json(self) -> dict:
        return {'source': self.source, 'duration': self.duration,
                'words': [{'w': w.w, 't0': round(w.t0, 3), 't1': round(w.t1, 3), 'line': w.line} for w in self.words]}


# --- Schätzung ohne Stimme ---

def _syllables(word: str) -> int:
    w = re.sub(r"[^a-zäöüß]", '', word.lower())
    if not w:
        return 1
    groups = re.findall(r"[aeiouyäöü]+", w)
    n = len(groups)
    if w.endswith('e') and n > 1 and not w.endswith(('le', 'ee', 'ie')):
        n -= 1
    return max(1, n)


def _digits_syll(word: str) -> int:
    d = re.sub(r"\D", '', word)
    return int(round(len(d) * 1.3)) if d else 0


def estimate_words(lines_spec: list, wpm: float = 150.0, lead_in: float = 0.35) -> tuple:
    """Verteilt Wortzeiten nach Silben; Satzzeichen geben Pausen. Gibt (Zeilen, Dauer) zurück."""
    # Kalibriert an Aufnahmen: 194 Wörter (1.094 Zeichen) ergaben 85 s bei 160 wpm espeak; ElevenLabs liegt bei etwa 145-150 wpm inkl. Pausen.
    sec_per_syll = 60.0 / (wpm * 2.15)
    t = lead_in
    lines = []
    for spec in lines_spec:
        ln = Line(spec['id'], spec['text'], spec['kind'], spec.get('rank'), gap_after=float(spec.get('gap_after', 0.0)),
                  meta={k: v for k, v in spec.items() if k not in ('id', 'text', 'kind', 'rank', 'gap_after')})
        toks = S.tokens(spec['text'])
        for i, tok in enumerate(toks):
            syl = _syllables(tok) + _digits_syll(tok)
            dur = sec_per_syll * syl + 0.03
            w = Word(tok, t, t + dur, ln.id, i)
            ln.words.append(w)
            t += dur
            if tok.endswith(('.', '!', '?')):
                t += 0.38
            elif tok.endswith((',', ';', ':', '—', '–')):
                t += 0.16
            else:
                t += 0.035
        t += ln.gap_after
        lines.append(ln)
    return lines, t


def build(script: dict, words_json: dict = None, cfg: dict = None, fps: int = 30) -> Timeline:
    """Timeline aus Skript und (optional) words.json. Ohne words.json wird geschätzt."""
    cfg = cfg or {}
    spec = S.lines(script)
    if not words_json:
        wpm = float(cfg.get('voice', {}).get('wpm_estimate', 150))
        lines, dur = estimate_words(spec, wpm)
        return Timeline(lines, dur, 'estimate', fps)
    by_line: dict = {}
    for wd in words_json['words']:
        by_line.setdefault(wd['line'], []).append(wd)
    lines = []
    t_last = 0.0
    for sp in spec:
        ln = Line(sp['id'], sp['text'], sp['kind'], sp.get('rank'), gap_after=float(sp.get('gap_after', 0.0)),
                  meta={k: v for k, v in sp.items() if k not in ('id', 'text', 'kind', 'rank', 'gap_after')})
        ws = by_line.get(sp['id'], [])
        toks = S.tokens(sp['text'])
        if len(ws) != len(toks):
            # Text geändert seit der Aufnahme: Wörter notdürftig verteilen
            if ws:
                t0, t1 = ws[0]['t0'], ws[-1]['t1']
            else:
                t0, t1 = t_last, t_last + 0.4 * max(1, len(toks))
            n = max(1, len(toks))
            for i, tok in enumerate(toks):
                a = t0 + (t1 - t0) * i / n
                b = t0 + (t1 - t0) * (i + 1) / n
                ln.words.append(Word(tok, a, b, ln.id, i))
            ln.meta['mismatch'] = True
        else:
            for i, (tok, wd) in enumerate(zip(toks, ws)):
                ln.words.append(Word(tok, float(wd['t0']), float(wd['t1']), ln.id, i))
        if ln.words:
            t_last = ln.t1
        lines.append(ln)
    duration = float(words_json.get('duration') or (t_last))
    return Timeline(lines, duration, words_json.get('source', 'voice'), fps)


def load_words(project_dir: str) -> dict | None:
    p = os.path.join(project_dir, 'words.json')
    if os.path.exists(p):
        with open(p, encoding='utf-8') as fh:
            return json.load(fh)
    return None


def map_words_to_lines(script: dict, flat_words: list) -> list:
    """Flache Wortliste [{'w','t0','t1'}] (aus TTS) den Zeilen zuordnen (Reihenfolge ist die des Sprechtexts)."""
    spec = S.lines(script)
    out = []
    k = 0
    for sp in spec:
        toks = S.tokens(sp['text'])
        for tok in toks:
            if k < len(flat_words):
                wd = flat_words[k]
                out.append({'w': tok, 't0': round(float(wd['t0']), 3), 't1': round(float(wd['t1']), 3), 'line': sp['id']})
                k += 1
    return out
