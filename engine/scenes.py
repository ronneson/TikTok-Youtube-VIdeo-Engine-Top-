"""Szenenvorlagen „Peel & Pop“: Hook, Eintrag (Countdown), Outro, Übergänge, Ebenenaufbau (STIL.md 1.4, 5.2).

SceneRenderer(comp).draw(c, t):
  Seite (Kulisse + Lichtinsel + Sticker-Ebene + Partikel, mit Push-In)  -> Übergang zur Vorseite (Peel/Cut/Fade)
  -> UI-Ebene (Nummernkarte, Kopfzeile, Meta-Pille, Serienetikett, Album-Leiste, Wasserzeichen, Untertitel) -> Vignette.
Alles ist eine reine Funktion der Zeit. Projekt-eigene scenes.py darf Hooks liefern: background, overlay, hook, entry, outro.
"""
from __future__ import annotations
import math
import re
from . import anim as A
from . import backdrops as BD
from . import captions as CAP
from . import cards as CD
from . import fonts as F
from . import fx as FX
from . import mascot as M
from . import props as PR
from . import theme as TH

THEME_ICON = {'heist': 'money_bag', 'cave': 'cave', 'animal': 'paw', 'space': 'rocket', 'history': 'scroll', 'ocean': 'wave',
              'medical': 'pill', 'crime': 'magnifier', 'food': 'cheese', 'curious': 'question'}
THEME_BACKDROP = {'heist': 'vault', 'cave': 'cave', 'animal': 'forest', 'space': 'space', 'history': 'archive', 'ocean': 'ocean',
                  'medical': 'lab', 'crime': 'courtroom', 'food': 'kitchen', 'curious': 'cabinet'}
POSE_CYCLE = ['point', 'think', 'sneak', 'laugh', 'idle', 'cheer', 'wink']
TRANS_DUR = 0.3     # Peel 300 ms (STIL.md 1.6)


def _anchor(tl, at, t0, fallback):
    """Anker aus dem Skript: Zahl = Sekunden ab Szenenbeginn, String = Wort (tl.at), None = fallback."""
    if at in (None, ''):
        return fallback
    if isinstance(at, (int, float)):
        return t0 + float(at)
    return tl.at(at, default=fallback)


def _norm_prop(pr):
    return dict(pr) if isinstance(pr, dict) else {'name': str(pr)}


class SceneRenderer:
    def __init__(self, comp):
        self.comp = comp
        self.fmt = comp.fmt
        self.cfg = comp.cfg
        self.script = comp.script
        self.tl = comp.tl
        self.theme = TH.get(comp.theme_name)
        self.total = len(self.script['entries'])
        self.custom = comp.custom
        self.series = self._series_text()
        self._plans = {sc.id: self._plan_scene(sc) for sc in comp.scenes}

    # ---------- Vorbereitung je Szene ----------
    def _series_text(self):
        s = str(self.script.get('series') or self.script.get('theme', '')).upper()
        no = self.cfg.get('brand', {}).get('exhibit_no')
        if no and '·' not in s:
            s = f"{s} · {int(no):03d}"
        return s[:22]

    def _plan_scene(self, sc):
        """Zeiten für Piktogramme, Beats, Schlagworte, Stats, Stempel einmal ausrechnen."""
        tl, t0 = self.tl, sc.t0
        vis = sc.visual or {}
        entry = sc.entry or {}
        plan = {'respect': bool(entry.get('respect') or vis.get('respect'))}
        plan['variant'] = vis.get('card_variant') or ('one' if sc.rank == 1 else ('B' if (sc.rank or 1) % 2 == 0 else 'A'))
        # Kulisse
        plan['backdrop'] = vis.get('backdrop') or ('spotlight' if sc.kind == 'hook' else THEME_BACKDROP.get(self.theme['name'], 'cabinet'))
        # Maskottchen
        m = dict(vis.get('mascot') or {})
        idx = (self.total - (sc.rank or 0)) % len(POSE_CYCLE) if sc.rank else 0
        m.setdefault('pose', 'peek' if sc.kind == 'hook' else 'cheer' if sc.kind == 'outro' else ('bow' if plan['respect'] else POSE_CYCLE[idx]))
        m.setdefault('costume', M.costume_for(self.theme['name']))
        m['t_in'] = _anchor(tl, m.get('at'), t0, t0 + (0.40 if plan['variant'] in ('A', 'one') else 0.5))
        plan['mascot'] = m
        # Piktogramme: erstes = Hero, weitere = Begleiter
        props = [_norm_prop(p) for p in (vis.get('props') or [])]
        for j, pr in enumerate(props):
            pr['t_in'] = _anchor(tl, pr.get('at'), t0, min(t0 + 1.8, sc.t1 - 0.5) + j * 0.25)
            pr.setdefault('anim', 'pop')
            pr['role'] = 'hero' if j == 0 else 'side'
        plan['props'] = props
        # Beats (Wechsel innerhalb des Eintrags)
        beats = []
        for b in (vis.get('beats') or []):
            tb = _anchor(tl, b.get('at'), t0, t0 + sc.dur * 0.5)
            bp = [_norm_prop(p) for p in (b.get('props') or [])]
            for j, pr in enumerate(bp):
                pr['t_in'] = _anchor(tl, pr.get('at'), t0, tb + j * 0.2)
                pr.setdefault('anim', 'pop')
                pr['role'] = 'hero' if j == 0 else 'side'
            beats.append({'t': tb, 'props': bp, 'mascot': b.get('mascot'), 'backdrop': b.get('backdrop'), 'stamp': b.get('stamp'), 'respect': b.get('respect'), 'keep_props': b.get('keep_props', False)})
        plan['beats'] = sorted(beats, key=lambda b: b['t'])
        # Schlagworte
        kws = []
        for kw in (vis.get('keywords') or []):
            tk = _anchor(tl, kw.get('at'), t0, t0 + 2.0)
            kws.append({'text': kw.get('text', ''), 't0': tk})
        kws.sort(key=lambda k: k['t0'])
        for i, kw in enumerate(kws):
            nxt = kws[i + 1]['t0'] if i + 1 < len(kws) else sc.t1 - 0.05
            kw['t1'] = max(kw['t0'] + 1.5, min(nxt - 0.1, sc.t1 - 0.05))
        plan['keywords'] = kws
        # Stat
        st = entry.get('stat')
        if st:
            at = st.get('at')
            if at not in (None, ''):
                ts = t0 + float(at) if isinstance(at, (int, float)) else tl.at(at, default=t0 + 2.0)
            else:
                ts = self.comp._stat_word_time(sc, str(st.get('value', '')).strip(), t0 + 2.0)
            digits = re.sub(r'\D', '', str(st.get('value', '')))
            auto_count = bool(digits) and int(digits or 0) >= 20
            plan['stat'] = {'value': str(st.get('value', '')), 'label': str(st.get('label', '')), 't0': ts, 'count': bool(st.get('count', auto_count))}
        else:
            plan['stat'] = None
        # Stempel
        stp = vis.get('stamp')
        if isinstance(stp, str):
            stp = {'text': stp}
        if stp:
            plan['stamp'] = {'text': stp.get('text', 'VERIFIED ODD'), 't0': _anchor(tl, stp.get('at'), t0, sc.t1 - 1.4)}
        else:
            plan['stamp'] = None
        # Sprechblase
        say = vis.get('say') or entry.get('say')
        if say:
            d = say if isinstance(say, dict) else {}
            plan['say'] = {'t0': _anchor(tl, d.get('at'), t0, sc.t1 - 1.5)}
        else:
            plan['say'] = None
        return plan

    # ---------- Hilfen ----------
    def _stage_pt(self, u, v):
        st = self.fmt.stage
        return st.x + u * st.w, st.y + v * st.h

    def _theme_for(self, sc, t):
        plan = self._plans[sc.id]
        respect_mode = plan['respect'] or any(b['respect'] and t >= b['t'] for b in plan['beats'])
        return (TH.respect(self.theme) if respect_mode else self.theme), respect_mode

    def _mascot_spot(self, size=None):
        if self.fmt.portrait:
            x, y = self._stage_pt(0.28, 0.86)
            return x, y, size or 400
        x, y = self._stage_pt(0.14, 0.92)
        return x, y, size or 320

    def _hero_spot(self):
        return self._stage_pt(0.69, 0.60) if self.fmt.portrait else self._stage_pt(0.62, 0.56)

    def _prop_place(self, pr, j, n_side):
        """Position/Größe eines Piktogramms: Skriptwerte (Bühnenanteile) oder Standardlayout."""
        st = self.fmt.stage
        hero_size = 300 if self.fmt.portrait else 360
        if pr['role'] == 'hero':
            x, y = self._hero_spot()
            size = hero_size
        else:
            hx, hy = self._hero_spot()
            if j == 0:
                x, y, size = hx - hero_size * 0.42, hy - hero_size * 0.42, 130
            else:
                x, y, size = hx + hero_size * 0.42, hy - hero_size * 0.46 - (j - 1) * 110, 110
        if 'x' in pr:
            x = st.x + float(pr['x']) * st.w
        if 'y' in pr:
            y = st.y + float(pr['y']) * st.h
        if 'size' in pr:
            size = float(pr['size'])
        # nie in der Knopfleiste
        if self.fmt.buttons and x + size / 2 > self.fmt.buttons.x and y + size / 2 > self.fmt.buttons.y:
            x = self.fmt.buttons.x - size / 2 - 10
        return x, y, size

    def _draw_prop(self, c, pr, t, th, j=0, n_side=0, t_out=None, seed=0):
        t_in = pr['t_in']
        if t < t_in - 0.06:
            return
        x, y, size = self._prop_place(pr, j, n_side)
        anim = pr.get('anim', 'pop')
        u = A.clamp01((t - t_in) / 0.45)
        k = 1.0
        dx = dy = 0.0
        alpha = 1.0
        if anim == 'drop':
            dy = -(1 - A.out_bounce(u)) * 260
            alpha = A.clamp01(u * 4)
        elif anim == 'slide':
            dx = (1 - A.out_cubic(u)) * 320 * (1 if x > self.fmt.cx else -1)
            alpha = A.clamp01(u * 4)
        elif anim == 'fade':
            alpha = A.out_sine(u)
        else:
            k = A.pop(t, t_in, 0.42, 1.14) if t >= t_in else 0.0
            if t < t_in:
                # Schatten-Antizipation 60 ms
                FX.floor_shadow(c, x, y + size * 0.42, size * 0.8, alpha=0.18 * A.clamp01((t - t_in + 0.06) / 0.06))
                return
        if t_out is not None and t > t_out - 0.18:
            k *= 1 - A.in_cubic(A.clamp01((t - (t_out - 0.18)) / 0.18))
        if k <= 0.01 or alpha <= 0.01:
            return
        rot = float(pr.get('rot', 0.0)) + 2.5 * math.sin(t * 0.8 + j)
        PR.draw(c, pr['name'], x + dx, y + dy + 4 * math.sin(t * 0.9 + j * 1.3), size, t=t, theme=th, alpha=alpha, rot=rot, k=min(k, 1.3), seed=seed + j)
        c.mark(x - size / 2, y - size / 2, size, size, pr['name'], 'sticker')

    # ---------- Hauptaufruf ----------
    def draw(self, c, t):
        comp, fmt = self.comp, self.fmt
        sc = comp.scene_at(t)
        prev = next((s for s in comp.scenes if abs(s.t1 - sc.t0) < 1e-6 and s is not sc), None)
        th, _ = self._theme_for(sc, t)
        trans = sc.trans_in if sc.kind != 'entry' else ('cut' if sc.rank == 1 else 'peel')
        if sc.kind == 'outro':
            trans = 'fade'
        tdur = 0.4 if trans == 'fade' else TRANS_DUR
        k = A.clamp01((t - sc.t0) / tdur) if prev is not None else 1.0

        def page_new(cc):
            self._page(cc, sc, t)

        def page_old(cc):
            self._page(cc, prev, t, ending=True)

        if prev is not None and k < 1.0 and trans != 'cut':
            FX.transition(c, fmt, trans, k, th, page_old, page_new)
        else:
            page_new(c)
            if sc.kind == 'entry' and sc.rank == 1 and prev is not None:
                FX.flash(c, fmt, t, sc.t0, th['glow'] or th['ink'], 0.12, 0.7)
        self._ui(c, sc, prev, t, th)
        if self.custom and hasattr(self.custom, 'overlay'):
            self.custom.overlay(c, comp, t)
        c.vignette(self.cfg['look'].get('vignette', 0.28))

    # ---------- Seite (Kulisse + Inhalt) ----------
    def _page(self, c, sc, t, ending=False):
        fmt = self.fmt
        th, respect_mode = self._theme_for(sc, t)
        plan = self._plans[sc.id]
        push = self.cfg['look'].get('push_in', 0.03)
        u = A.clamp01((t - sc.t0) / max(1.0, sc.dur))
        scale = 1.0 + push * u if sc.kind == 'entry' else 1.0
        with c.tf(sx=scale, px=fmt.cx, py=fmt.cy * 1.05):
            # Kulisse (mit Beat-Wechsel)
            bd = plan['backdrop']
            for b in plan['beats']:
                if b['backdrop'] and t >= b['t']:
                    bd = b['backdrop']
            if self.custom and hasattr(self.custom, 'background'):
                self.custom.background(c, self.comp, t)
            else:
                BD.draw(c, bd, fmt, t=t, theme=th, seed=(sc.rank or 0) + 3, grain=self.cfg['look'].get('grain', 0.045), light=0.6 if respect_mode else 1.0)
            # Lichtinsel folgt dem Hero
            hx, hy = self._hero_spot()
            col = th.get('light_island') or th.get('glow') or th['ink']
            c.spotlight(hx, hy, 520 if fmt.portrait else 600, col, 0.18 if respect_mode else 0.14)
            if sc.kind == 'hook':
                self._hook(c, sc, t, th)
            elif sc.kind == 'entry':
                self._entry(c, sc, t, th, respect_mode)
            else:
                self._outro(c, sc, t, th)

    # ---------- Hook ----------
    def _hook(self, c, sc, t, th):
        if self.custom and hasattr(self.custom, 'hook'):
            return self.custom.hook(c, self.comp, sc, t)
        fmt = self.fmt
        hook = self.script.get('hook', {})
        plan = self._plans[sc.id]
        FX.light_rays(c, fmt.cx, fmt.stage.y + 80, t, th, n=6, length=1500, alpha=0.08, spread=14, speed=3)
        FX.particles(c, fmt, t, 'dust', th, seed=1, n=28, alpha=0.5)
        text = ' '.join(ln['text'] if isinstance(ln, dict) else str(ln) for ln in hook.get('lines', []))
        CD.hook_title(c, fmt, text, t, 0.0, th, keyword=hook.get('keyword'))
        # kleine Sticker um die Headline
        props = plan['props']
        spots = [(0.16, 0.14, 150), (0.84, 0.12, 140), (0.80, 0.78, 150), (0.18, 0.80, 130)]
        for j, pr in enumerate(props[:4]):
            sx, sy, ss = spots[j]
            pr = dict(pr)
            pr.setdefault('x', sx); pr.setdefault('y', sy); pr.setdefault('size', ss)
            pr['t_in'] = min(pr['t_in'], 0.35 + j * 0.18)
            pr['role'] = 'side'
            self._draw_prop(c, pr, t, th, j=j, seed=11)
        # Odd lugt herein
        m = plan['mascot']
        x, y = self._stage_pt(float(m.get('x', 0.30)), float(m.get('y', 1.0)))
        size = float(m.get('size', 360 if fmt.portrait else 300))
        k = A.pop(t, 0.25, 0.5, 1.18)
        if k > 0:
            with c.clip_rect(fmt.stage.x - 100, fmt.stage.y, fmt.stage.w + 200, fmt.stage.h + 40):
                M.draw(c, x, y + size * 0.22, size, t=t, pose=m.get('pose', 'peek'), expr=m.get('expr'), costume=m.get('costume'), look=(0.0, -0.3), theme=th, k=min(1.0, k), t0=0.25)

    # ---------- Eintrag ----------
    def _entry(self, c, sc, t, th, respect_mode):
        if self.custom and hasattr(self.custom, 'entry'):
            return self.custom.entry(c, self.comp, sc, t)
        fmt, plan, t0 = self.fmt, self._plans[sc.id], sc.t0
        rank = sc.rank
        # Partikel je Thema
        if not respect_mode:
            FX.particles(c, fmt, t, 'dust', th, seed=rank, n=22, alpha=0.35)
        # Beat-Zustand
        props = list(plan['props'])
        mascot_over = None
        active_beat = None
        for b in plan['beats']:
            if t >= b['t']:
                active_beat = b
                if b['props']:
                    props = (props if b['keep_props'] else []) + b['props']
                if b['mascot']:
                    mascot_over = dict(b['mascot'], t_in=b['t'])
        n_side = max(0, len(props) - 1)
        # Piktogramme (Hero zuerst, damit Begleiter davor liegen)
        for j, pr in enumerate(props):
            # alte Hero-Sticker blenden aus, wenn ein Beat neue bringt
            t_out = None
            if active_beat and active_beat['props'] and not active_beat['keep_props'] and pr not in active_beat['props']:
                t_out = active_beat['t']
            self._draw_prop(c, pr, t, th, j=max(0, j - 1), n_side=n_side, t_out=t_out, seed=rank * 7)
        # Odd
        m = dict(plan['mascot'])
        pose_t0 = m['t_in']
        if mascot_over:
            m.update({k: v for k, v in mascot_over.items() if k in ('pose', 'expr', 'costume', 'look', 'x', 'y', 'size')})
            pose_t0 = mascot_over['t_in']
        if respect_mode:
            m['pose'] = 'bow'
        mx, my, msize = self._mascot_spot(m.get('size'))
        if 'x' in m:
            mx = fmt.stage.x + float(m['x']) * fmt.stage.w
        if 'y' in m:
            my = fmt.stage.y + float(m['y']) * fmt.stage.h
        look = tuple(m.get('look', (0.6, -0.1)))
        variant = plan['variant']
        flip = bool(m.get('flip', False))
        if variant == 'A' and t < t0 + 0.40:
            # Elster-Lieferung: Odd fliegt mit der Karte am Schnabel von oben rechts herein, lässt sie bei t0+0.22 los
            # und landet bei t0+0.40 auf ihrem Platz
            anc = M.anchors(0.0, 0.0, msize, t=t, pose='fly', t0=t0)
            ox, oy = anc.get('beak_tip', (msize * 0.5, -msize * 0.76))
            bp = CD.beak_point(fmt, min(t, t0 + 0.21), t0, 'A')
            if bp is None:
                bp = (fmt.W + 100, fmt.stage.y + 0.1 * fmt.stage.h)
            fx_, fy_ = bp[0] - ox, bp[1] - oy
            if t < t0 + 0.22:
                gx, gy = fx_, fy_
            else:
                u = A.out_cubic(A.clamp01((t - t0 - 0.22) / 0.18))
                gx, gy = fx_ + (mx - fx_) * u, fy_ + (my - fy_) * u
            k = A.clamp01((t - t0) / 0.06)
            M.draw(c, gx, gy, msize, t=t, pose='fly', expr=m.get('expr'), costume=m.get('costume'), look=(0.4, 0.3), theme=th, k=k, t0=t0, seed=rank)
            if t < t0 + 0.33:
                CD.card_flight(c, fmt, rank, t, t0, th, variant='A', word=self._card_word(), icon=self._card_icon())
        else:
            t_in = m['t_in'] if variant != 'A' else t0 + 0.40
            if variant == 'one':
                t_in = t0
            k = A.pop(t, t_in, 0.45, 1.12) if t >= t_in else 0.0
            if variant == 'A' and t >= t0 + 0.40:
                k = 1.0
            if k > 0:
                M.draw(c, mx, my, msize, t=t, pose=m.get('pose', 'idle'), expr=m.get('expr'), costume=m.get('costume'), look=look, flip=flip, theme=th, k=min(k, 1.25), t0=pose_t0, seed=rank)
                c.mark(mx - msize * 0.55, my - msize, msize * 1.1, msize, 'odd', 'sticker')
        # Sprechblase
        if plan['say'] and t >= plan['say']['t0'] and not respect_mode:
            ks = A.pop(t, plan['say']['t0'], 0.4, 1.2)
            PR.draw(c, 'speech_bubble', mx + msize * 0.55, my - msize * 1.05, 190, t=t, theme=th, k=min(ks, 1.3), text='Odd.')
        # Schlagworte und Stat
        pair = plan['stat'] is not None and plan['keywords'] and any(kw['t0'] <= t < kw['t1'] for kw in plan['keywords']) and t >= plan['stat']['t0']
        for kw in plan['keywords']:
            if kw['t0'] - 0.1 <= t < kw['t1'] + 0.2:
                CD.keyword(c, fmt, kw['text'], t, kw['t0'], kw['t1'], th, pair=bool(pair), seed=rank)
        if plan['stat'] and t >= plan['stat']['t0'] - 0.1:
            CD.stat_plate(c, fmt, plan['stat']['value'], plan['stat']['label'], t, plan['stat']['t0'], th, count=plan['stat']['count'], pair=bool(pair), seed=rank)
        # Stempel (Beat oder Szene)
        stamp = plan['stamp']
        for b in plan['beats']:
            if b['stamp']:
                stamp = {'text': b['stamp'] if isinstance(b['stamp'], str) else b['stamp'].get('text', 'VERIFIED ODD'), 't0': b['t'] + 0.3}
        if stamp and t >= stamp['t0'] and not respect_mode:
            hx, hy = self._hero_spot()
            CD.stamp(c, fmt, stamp['text'], t, stamp['t0'], th, hx + 40, hy - 60, seed=rank)
        # Konfetti bei #1 (Cut)
        if rank == 1 and not respect_mode:
            FX.confetti_burst(c, fmt.cx, fmt.cy * 0.9, t, t0, th, n=60, seed=5)

    def _card_word(self):
        return str(self.script.get('card_word') or self.theme['name']).upper()[:10]

    def _card_icon(self):
        return self.script.get('card_icon') or THEME_ICON.get(self.theme['name'], 'question')

    # ---------- Outro ----------
    def _outro(self, c, sc, t, th):
        if self.custom and hasattr(self.custom, 'outro'):
            return self.custom.outro(c, self.comp, sc, t)
        fmt, plan = self.fmt, self._plans[sc.id]
        FX.particles(c, fmt, t, 'dust', th, seed=9, n=30, alpha=0.45)
        text = ' '.join(ln['text'] if isinstance(ln, dict) else str(ln) for ln in self.script.get('outro', {}).get('lines', []))
        with c.tf(y=-(230 if fmt.portrait else 120)):
            CD.hook_title(c, fmt, text, t, sc.t0 + 0.3, th, keyword=self.script.get('outro', {}).get('keyword'))
        m = plan['mascot']
        if fmt.portrait:
            mx, my, msize = self._stage_pt(float(m.get('x', 0.30)), float(m.get('y', 0.99)))[0], self._stage_pt(0.0, float(m.get('y', 0.99)))[1], float(m.get('size', 330))
        else:
            mx, my, msize = self._stage_pt(float(m.get('x', 0.14)), float(m.get('y', 0.95)))[0], self._stage_pt(0.0, float(m.get('y', 0.95)))[1], float(m.get('size', 300))
        k = A.pop(t, sc.t0 + 0.35, 0.5, 1.15)
        if k > 0:
            M.draw(c, mx, my, msize, t=t, pose=m.get('pose', 'cheer'), expr=m.get('expr'), costume=m.get('costume'), look=(0.3, -0.3), theme=th, k=min(k, 1.25), t0=sc.t0 + 0.35, seed=1)
        FX.confetti_burst(c, fmt.cx, fmt.cy, t, sc.t0 + 0.6, th, n=50, seed=3)

    # ---------- UI-Ebene ----------
    def _ui(self, c, sc, prev, t, th):
        fmt, cfg = self.fmt, self.cfg
        look = cfg['look']
        total = self.total
        # Serienetikett: im Hook in den letzten 0,5 s getippt
        if look.get('label', True) and self.series:
            typed = 1.0
            if sc.kind == 'hook':
                typed = A.clamp01((t - (sc.t1 - 0.5)) / 0.4)
            if typed > 0:
                CD.series_label(c, fmt, self.series, th, alpha=1.0, typed=typed)
        if sc.kind == 'entry':
            rank, t0 = sc.rank, sc.t0
            plan = self._plans[sc.id]
            variant = plan['variant']
            # vorige Karte/Kopfzeile poppt aus
            if prev is not None and prev.kind == 'entry' and t < t0 + 0.2:
                ko = 1 - A.clamp01((t - t0) / 0.16)
                CD.number_card(c, fmt, prev.rank, t, prev.t0, th, total=total, k_out=ko, variant=self._plans[prev.id]['variant'], word=self._card_word(), icon=self._card_icon(), flight=False, effects=False)
                CD.title_plate(c, fmt, (prev.entry or {}).get('title', ''), t, prev.t0, th, k_out=ko, rank=prev.rank)
                CD.meta_tag(c, fmt, (prev.entry or {}).get('place', ''), (prev.entry or {}).get('year', ''), t, prev.t0 + 1.70, th, k_out=ko)
            CD.number_card(c, fmt, rank, t, t0, th, total=total, k_out=1.0, variant=variant, word=self._card_word(), icon=self._card_icon(),
                           flight=(variant != 'A'), effects=not plan['respect'])
            entry = sc.entry or {}
            CD.title_plate(c, fmt, entry.get('title', ''), t, t0, th, rank=rank)
            if entry.get('place') or entry.get('year'):
                CD.meta_tag(c, fmt, entry.get('place', ''), entry.get('year', ''), t, t0 + 1.70, th)
            if look.get('progress', True):
                if rank == 1:
                    CD.progress(c, fmt, 1, total, t, th, t_fill=t0 + 0.58)
                elif prev is not None and prev.kind == 'entry':
                    CD.progress(c, fmt, prev.rank, total, t, th, t_fill=t0 + 0.58)
                else:
                    CD.progress(c, fmt, total + 1, total, t, th, t_fill=None)
        elif sc.kind == 'hook':
            if look.get('progress', True):
                CD.progress(c, fmt, total + 1, total, t, th, t_fill=None)
        else:
            if look.get('progress', True):
                CD.progress(c, fmt, 1, total, t, th, t_fill=None)
        if look.get('watermark', True):
            CD.watermark(c, fmt, cfg, th, alpha=0.62, t=t)
        if look.get('captions', True):
            CAP.draw(c, fmt, self.tl, t, th, cfg)
