"""Komposition: aus Skript + Timeline den Plan (Szenen, Übergänge, Töne, Untertitel) bauen und Bilder zeichnen.

Die Zeichenarbeit selbst liegt in scenes.py (Szenenvorlagen), cards.py, captions.py usw.
compose.py kennt nur die Zeiten und ruft die Vorlagen auf. Alles ist eine reine Funktion der Zeit.
"""
from __future__ import annotations
import importlib.util
import json
import os
from dataclasses import dataclass, field
from . import ROOT
from . import config as CFG
from . import layout as L
from . import script as S
from . import timeline as T


@dataclass
class Scene:
    id: str                 # 'hook', 'E5', 'E4', ..., 'outro'
    kind: str               # hook | entry | outro
    t0: float               # Beginn (inkl. Übergang hinein)
    t1: float               # Ende (Beginn der nächsten Szene)
    rank: int | None = None
    entry: dict | None = None
    visual: dict = field(default_factory=dict)
    trans_in: str = 'wipe'
    trans_dur: float = 0.6
    lines: list = field(default_factory=list)   # Line-Objekte dieser Szene
    @property
    def dur(self): return self.t1 - self.t0
    def contains(self, t): return self.t0 <= t < self.t1


class Composition:
    """Alles, was der Renderer braucht: Format, Dauer, draw(c, t)."""

    def __init__(self, project_dir: str, cfg: dict = None, root: str = None):
        self.root = root or ROOT
        self.project_dir = project_dir
        self.cfg = cfg or CFG.load(self.root)
        self.script = S.load(project_dir)
        self.fmt = L.get_format(self.script.get('format', self.cfg.get('format', 'portrait')))
        words = T.load_words(project_dir)
        self.tl = T.build(self.script, words, self.cfg, self.fmt.fps)
        self.tail = float(self.script.get('tail', self.cfg['mix'].get('tail', 2.0)))
        self.duration = self.tl.voice_end() + self.tail
        self.scenes = build_scenes(self.script, self.tl, self.duration)
        self.theme_name = self.script.get('theme', 'curious')
        self.custom = _load_custom(project_dir)
        from . import scenes as SC
        self.renderer = SC.SceneRenderer(self)

    def scene_at(self, t: float) -> Scene:
        for sc in self.scenes:
            if sc.contains(t):
                return sc
        return self.scenes[-1] if t >= self.scenes[-1].t0 else self.scenes[0]

    def draw(self, c, t: float):
        """Ein Bild zur Zeit t auf Canvas c zeichnen."""
        self.renderer.draw(c, t)

    def plan(self) -> dict:
        return {
            'title': self.script['title'], 'format': self.fmt.name, 'fps': self.fmt.fps,
            'duration': round(self.duration, 3), 'voice_source': self.tl.source, 'voice_end': round(self.tl.voice_end(), 3),
            'words': len(self.tl.words), 'theme': self.theme_name,
            'scenes': [{'id': sc.id, 'kind': sc.kind, 't0': round(sc.t0, 3), 't1': round(sc.t1, 3), 'rank': sc.rank,
                        'trans_in': sc.trans_in, 'lines': [ln.id for ln in sc.lines]} for sc in self.scenes],
            'lines': [{'id': ln.id, 't0': round(ln.t0, 3), 't1': round(ln.t1, 3), 'text': ln.text, 'kind': ln.kind,
                       'mismatch': bool(ln.meta.get('mismatch'))} for ln in self.tl.lines],
            'cues': self.cues(),
            'warnings': self.warnings(),
        }

    def cues(self) -> list:
        """Tonereignisse [{'t': s, 'sfx': id, 'db': x, 'why': ...}]: automatische plus die aus dem Skript."""
        out = []
        for sc in self.scenes:
            if sc.kind == 'hook':
                out.append({'t': round(max(0.0, sc.t0 + 0.05), 3), 'sfx': 'hook_hit', 'db': -6, 'why': 'hook'})
            elif sc.kind == 'entry':
                out.append({'t': round(sc.t1 - sc.trans_dur * 0.5 if False else sc.t0, 3), 'sfx': 'card_whoosh', 'db': -8, 'why': f'Übergang {sc.id}'})
                out.append({'t': round(sc.t0 + sc.trans_dur * 0.55, 3), 'sfx': 'card_hit', 'db': -5, 'why': f'Nummer {sc.rank}'})
                if sc.rank == 1:
                    out.append({'t': round(sc.t0 + sc.trans_dur * 0.6, 3), 'sfx': 'number_one', 'db': -5, 'why': 'Nummer 1'})
                st = (sc.entry or {}).get('stat')
                if st:
                    anchor = st.get('at') or st.get('value', '')
                    tt = self.tl.at(anchor, default=sc.t0 + 2.0) if anchor else sc.t0 + 2.0
                    out.append({'t': round(tt, 3), 'sfx': 'stat_pop', 'db': -9, 'why': f'Stat {sc.id}'})
            elif sc.kind == 'outro':
                out.append({'t': round(sc.t0 + 0.3, 3), 'sfx': 'outro_chime', 'db': -8, 'why': 'outro'})
        for sc in self.scenes:
            src = sc.entry if sc.entry else self.script.get(sc.kind, {})
            for cue in (src or {}).get('cues', []):
                anchor, sfx = cue[0], cue[1]
                db = cue[2] if len(cue) > 2 else -8
                lid = sc.lines[0].id if sc.lines else None
                tt = self.tl.at(anchor, default=None) if not isinstance(anchor, (int, float)) else sc.t0 + float(anchor)
                if tt is None:
                    continue
                out.append({'t': round(tt, 3), 'sfx': sfx, 'db': db, 'why': f'Skript {sc.id}'})
        end = self.tl.voice_end()
        out.append({'t': round(end + 0.25, 3), 'sfx': 'end_sting', 'db': -7, 'why': 'Schluss'})
        return sorted(out, key=lambda c: c['t'])

    def warnings(self) -> list:
        w = []
        for ln in self.tl.lines:
            if ln.meta.get('mismatch'):
                w.append(f"Zeile {ln.id}: Text passt nicht zur Aufnahme (Wortzahl) – tts neu ausführen")
        for sc in self.scenes:
            if sc.kind == 'entry' and sc.dur < 6.0:
                w.append(f"Szene {sc.id} dauert nur {sc.dur:.1f} s (unter 6 s wirkt gehetzt)")
            if sc.kind == 'entry' and sc.dur > 26.0 and self.fmt.portrait:
                w.append(f"Szene {sc.id} dauert {sc.dur:.1f} s (über 26 s im Hochformat: Zeilen kürzen oder zweiten Bildwechsel setzen)")
        if self.duration < 60 and self.fmt.portrait:
            w.append(f"Video nur {self.duration:.1f} s lang (unter 60 s)")
        if self.duration > 92 and self.fmt.portrait:
            w.append(f"Video {self.duration:.1f} s lang (über 90 s)")
        n = S.word_count(self.script)
        if self.fmt.portrait and n > 215:
            w.append(f"{n} Wörter: zu viele für 60–90 s")
        return w


def build_scenes(script: dict, tl: T.Timeline, duration: float) -> list:
    """Szenenfolge: hook -> Einträge (Countdown) -> outro. Ein Übergang beginnt vor dem ersten Wort der nächsten Szene."""
    scenes = []
    hook_lines = tl.lines_of('hook')
    entries = S.entries_desc(script)
    outro_lines = tl.lines_of('outro')
    trans = 0.6

    def first_t(lines):
        return lines[0].t0 if lines else None

    # Startzeiten der Szenen = erstes Wort minus halber Übergang (die erste Szene beginnt bei 0)
    starts = []
    if hook_lines:
        starts.append(('hook', 0.0, None, None, hook_lines))
    for e in entries:
        r = int(e['rank'])
        ls = tl.lines_of(rank=r)
        if not ls:
            continue
        t_first = ls[0].t0
        starts.append((f'E{r}', max(0.0, t_first - trans * 0.5), r, e, ls))
    if outro_lines:
        starts.append(('outro', max(0.0, outro_lines[0].t0 - trans * 0.5), None, None, outro_lines))
    if starts and starts[0][1] > 0:
        starts[0] = (starts[0][0], 0.0, starts[0][2], starts[0][3], starts[0][4])
    for i, (sid, t0, rank, entry, ls) in enumerate(starts):
        t1 = starts[i + 1][1] if i + 1 < len(starts) else duration
        kind = 'hook' if sid == 'hook' else 'outro' if sid == 'outro' else 'entry'
        vis = dict((entry or script.get(kind, {}) or {}).get('visual', {}) or {})
        tr = vis.get('transition', 'wipe' if kind == 'entry' else 'fade')
        scenes.append(Scene(sid, kind, t0, t1, rank, entry, vis, tr, float(vis.get('transition_dur', trans)), ls))
    return scenes


def _load_custom(project_dir: str):
    """Optionale scenes.py im Projekt: darf Hooks definieren (background/overlay/entry_<rank>) für eigene Bilder."""
    p = os.path.join(project_dir, 'scenes.py')
    if not os.path.exists(p):
        return None
    spec = importlib.util.spec_from_file_location('project_scenes', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load(project_dir: str, root: str = None) -> Composition:
    return Composition(project_dir, root=root)


def write_plan(project_dir: str, comp: Composition) -> dict:
    plan = comp.plan()
    with open(os.path.join(project_dir, 'plan.json'), 'w', encoding='utf-8') as fh:
        json.dump(plan, fh, indent=1, ensure_ascii=False)
    return plan
