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
        """Tonereignisse [{'t','sfx','db','why'}] (STIL.md 5.2 und 10.6): automatische Choreografie plus Skript-Cues."""
        out = []
        tl = self.tl
        def add(t, sfx, db, why):
            out.append({'t': round(float(t), 3), 'sfx': sfx, 'db': db, 'why': why})
        entries = [sc for sc in self.scenes if sc.kind == 'entry']
        for i, sc in enumerate(self.scenes):
            t0, td = sc.t0, sc.trans_dur
            if sc.kind == 'hook':
                add(max(0.0, t0 + 0.05), 'hook_hit', -6, 'hook')
            elif sc.kind == 'entry':
                variant = sc.visual.get('card_variant') or ('B' if (sc.rank or 1) % 2 == 0 else 'A')
                respect_mode = bool((sc.entry or {}).get('respect'))
                if sc.rank == 1:
                    add(t0 - 1.5, 'riser', -12, 'Riser vor #1')
                    add(t0, 'flash', -14, 'Konfetti-Cut #1')
                    add(t0, 'confetti', -10, 'Konfetti #1')
                else:
                    add(t0, 'card_whoosh', -8, f'Übergang {sc.id}')
                    add(t0, 'peel', -12, f'Peel {sc.id}')
                if variant == 'A' or sc.rank == 1:
                    add(t0, 'flap', -12, 'Elster-Lieferung')
                    add(t0 + 0.40, 'hop', -12, 'Odd landet')
                    if sc.rank != 1 and not respect_mode:
                        add(t0 + 0.33, 'confetti', -12, 'Landung')
                else:
                    for k in range(5):
                        add(t0 + 0.05 + k * 0.055, 'tick', -30, 'Zählwerk')
                add(t0 + td * 0.55, f'card_hit_{sc.rank}', -5, f'Nummer {sc.rank}')
                if sc.rank == 1:
                    add(t0 + 0.36, 'number_one', -5, 'Nummer 1')
                add(t0 + 0.58, 'pop_in', -6, 'Badge im Album-Fach')
                if not respect_mode:
                    add(t0 + 0.58, 'shiny', -12, 'Fach füllt sich')
                # Titelwörter in der Haltezeit
                title = (sc.entry or {}).get('title', '')
                for k, _w in enumerate(title.split()[:6]):
                    add(t0 + 0.55 + k * 0.045, 'pop_in', -10, 'Titelwort')
                # Meta-Pille tippt sich ein
                meta = f"{(sc.entry or {}).get('place', '')} {(sc.entry or {}).get('year', '')}".strip()
                for k in range(min(12, len(meta))):
                    add(t0 + 1.70 + k * 0.033, 'typewriter', -16, 'Meta-Pille')
                # Hero / Begleiter / Schlagworte / Stat an ihren Ankern
                vis = sc.visual or {}
                first_line = sc.lines[0].id if sc.lines else None
                def anchor_time(at, fallback):
                    if at in (None, ''):
                        return fallback
                    if isinstance(at, (int, float)):
                        return t0 + float(at)
                    return tl.at(at, default=fallback)
                props = vis.get('props') or []
                for j, pr in enumerate(props):
                    at = pr.get('at') if isinstance(pr, dict) else None
                    tt = anchor_time(at, min(t0 + 1.8, sc.t1 - 0.5) + j * 0.25)
                    add(tt, 'pop_in', -8, f'Sticker {pr.get("name") if isinstance(pr, dict) else pr}')
                for kw in vis.get('keywords') or []:
                    tt = anchor_time(kw.get('at'), t0 + 2.0)
                    add(tt, 'keyword_slam', -6, f'Schlagwort {kw.get("text", "")[:16]}')
                for b in vis.get('beats') or []:
                    tt = anchor_time(b.get('at'), t0 + sc.dur * 0.5)
                    if b.get('stamp'):
                        add(tt, 'stamp', -5, f'Stempel {b.get("stamp")}')
                    elif b.get('respect'):
                        add(tt, 'respect_hush', -12, 'Respekt')
                    else:
                        add(tt, 'pop_in', -9, 'Beat')
                if vis.get('stamp'):
                    tt = anchor_time(vis['stamp'].get('at') if isinstance(vis['stamp'], dict) else None, sc.t1 - 1.2)
                    add(tt, 'stamp', -5, 'Stempel')
                st = (sc.entry or {}).get('stat')
                if st:
                    default = t0 + 2.0
                    at = st.get('at')
                    if at not in (None, ''):
                        tt = t0 + float(at) if isinstance(at, (int, float)) else tl.at(at, default=default)
                    else:
                        tt = self._stat_word_time(sc, str(st.get('value', '')).strip(), default)
                    add(tt, 'stat_pop', -9, f'Stat {sc.id}')
                if vis.get('say') or (sc.entry or {}).get('say'):
                    tt = anchor_time((vis.get('say') or {}).get('at') if isinstance(vis.get('say'), dict) else None, sc.t1 - 1.5)
                    add(tt, 'odd_say', -8, 'Sprechblase')
            elif sc.kind == 'outro':
                add(sc.t0 + 0.3, 'outro_chime', -8, 'outro')
                add(sc.t0 + 0.6, 'confetti', -12, 'Outro-Konfetti')
        # Skript-Cues
        for sc in self.scenes:
            src = sc.entry if sc.entry else self.script.get(sc.kind, {})
            for cue in (src or {}).get('cues', []):
                anchor, sfx = cue[0], cue[1]
                db = cue[2] if len(cue) > 2 else -8
                tt = sc.t0 + float(anchor) if isinstance(anchor, (int, float)) else tl.at(anchor, default=None)
                if tt is None:
                    continue
                add(tt, sfx, db, f'Skript {sc.id}')
        end = tl.voice_end()
        add(end + 0.25, 'end_sting', -7, 'Schluss')
        out = [c for c in out if c['t'] >= -0.001 and c['t'] <= self.duration]
        return sorted(out, key=lambda c: c['t'])

    def _stat_word_time(self, sc, value: str, default: float) -> float:
        """Beginn des gesprochenen Stat-Werts: erst in den Zeilen der Szene, dann im ganzen Text; sonst default."""
        if not value:
            return default
        pools = [ln.id for ln in sc.lines] + [None]
        for lid in pools:
            try:
                w = self.tl.find(value, lid)
            except Exception:
                w = None
            if w is not None:
                return w.t0
        return default

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
        # STIL.md 10.10: Längen von Titel, Ort, Serienetikett; Stempel und Sprechblase je Video
        for e in self.script['entries']:
            if len(str(e.get('title', ''))) > 24:
                w.append(f"Eintrag {e.get('rank')}: Titel länger als 24 Zeichen ({len(e['title'])}) – passt nicht in die Kopfzeile")
            if len(str(e.get('place', '') or '')) > 12:
                w.append(f"Eintrag {e.get('rank')}: Ort länger als 12 Zeichen – nur die Stadt nennen")
        if len(str(self.script.get('series', '') or '')) > 22:
            w.append("Serienetikett länger als 22 Zeichen")
        stamps = sum(1 for e in self.script['entries'] if (e.get('visual') or {}).get('stamp') or any(b.get('stamp') for b in (e.get('visual') or {}).get('beats', [])))
        if stamps > len(self.script['entries']):
            w.append("mehr als ein Stempel je Eintrag")
        says = sum(1 for e in self.script['entries'] if (e.get('visual') or {}).get('say') or e.get('say'))
        if says > 1:
            w.append("Sprechblase Odd. höchstens einmal je Video")
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
