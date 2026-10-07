"""Szenenvorlagen: Hook, Eintrag (Countdown), Outro, Übergänge. PLATZHALTER – wird durch das Designsystem ersetzt.

SceneRenderer.draw(c, t) zeichnet: Hintergrund -> Szene (mit Übergang) -> Karten/Etiketten -> Untertitel -> Korn/Vignette.
"""
from __future__ import annotations
from . import anim as A
from . import fonts as F
from .color import mix


class SceneRenderer:
    def __init__(self, comp):
        self.comp = comp
        self.fmt = comp.fmt
        self.cfg = comp.cfg

    def draw(self, c, t):
        comp, fmt = self.comp, self.fmt
        sc = comp.scene_at(t)
        c.gradient_bg('#121826', '#2B1E3C')
        # Szene mit einfacher Blende
        k_in = A.tween(t, sc.t0, sc.trans_dur, 'out_cubic')
        with c.layer(alpha=k_in):
            self._scene(c, t, sc)
        prev = [s for s in comp.scenes if s.t1 == sc.t0]
        if prev and t < sc.t0 + sc.trans_dur:
            with c.layer(alpha=1 - k_in):
                self._scene(c, t, prev[0])
        self._captions(c, t)
        c.grain(self.cfg['look'].get('grain', 0.04))
        c.vignette(self.cfg['look'].get('vignette', 0.25))

    def _scene(self, c, t, sc):
        fmt = self.fmt
        lt = t - sc.t0
        if sc.kind == 'entry':
            y = fmt.card.cy
            s = A.pop(t, sc.t0 + 0.1, 0.5)
            with c.tf(sx=s, px=fmt.card.cx, py=y):
                c.circle(fmt.card.cx, y, 110, '#FFC14A')
                c.text(str(sc.rank), fmt.card.cx, y, F.font('number', 150, weight=800), '#1A1020', 'center', 'middle')
            title = (sc.entry or {}).get('title', '')
            lines = F.wrap(title, 'display', 76, fmt.title.w, weight=800)
            a = A.appear(t, sc.t0 + 0.35)
            c.text_lines(lines, fmt.cx, fmt.title.y, F.font('display', 76, weight=800), '#FFFFFF', 'center', 1.08, alpha=a)
            c.circle(fmt.cx, fmt.stage.cy + 150, 160 + 10 * A.osc(lt, 0.4), '#5FF2C2', alpha=0.25)
        elif sc.kind == 'hook':
            kw = self.comp.script.get('hook', {}).get('keyword') or self.comp.script['title']
            lines = F.wrap(kw.upper(), 'display', 110, fmt.stage.w - 80, weight=800)
            c.text_lines(lines, fmt.cx, fmt.stage.cy - 60 * len(lines), F.font('display', 110, weight=800), '#FFFFFF', 'center', 1.0, alpha=A.appear(t, sc.t0 + 0.1))
        else:
            c.text(self.comp.script['title'], fmt.cx, fmt.stage.cy, F.font('display', 70, weight=700), '#FFFFFF', 'center', 'middle', alpha=A.appear(t, sc.t0 + 0.2))

    def _captions(self, c, t):
        tl, fmt = self.comp.tl, self.fmt
        cur = [w for w in tl.words if w.t0 - 0.05 <= t <= w.t1 + 0.35]
        if not cur:
            return
        w = cur[-1]
        ln = tl.line(w.line)
        idx = ln.words.index(w)
        grp = ln.words[max(0, idx - 2): idx + 3]
        f = F.font('caption', 52, weight=700)
        text = ' '.join(x.w for x in grp)
        c.rect_c(fmt.cx, fmt.caption.cy, c.text_width(text, f) + 60, 90, '#000000', r=24, alpha=0.55)
        x = fmt.cx - c.text_width(text, f) / 2
        for x_w in grp:
            col = '#FFC14A' if x_w is w else '#FFFFFF'
            x += c.text(x_w.w + ' ', x, fmt.caption.cy, f, col, 'left', 'middle')
