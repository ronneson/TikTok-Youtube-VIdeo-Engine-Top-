"""Marke: Profilbild, freigestelltes Zeichen und Wasserzeichen-Kopf von Odd (STIL.md 8.2)."""
from __future__ import annotations
import os
from . import theme as TH
from . import fonts as F
from . import mascot


def draw_mark(c, x, y, size, theme=None, alpha=1.0, t=0.0):
    """Odd-Kopf als Zeichen, Kopfmitte (x, y), Durchmesser size."""
    th = theme or TH.get('curious')
    with c.layer(alpha=alpha):
        mascot.draw_head(c, x, y, size, t=t, expr='smile', look=(0.3, -0.2), theme=th, costume='default', rim=max(3.0, size * 0.09))


def profile(c, W, theme_name='curious', with_text=True):
    th = TH.get(theme_name)
    c.fill_shader(c.linear(0, 0, 0, W, [th['bg0'], th['bg1']]))
    c.circle(W / 2, W / 2, W * 0.46, th['bg2'], alpha=0.6)
    c.glow(W / 2, W * 0.42, W * 0.3, th['glow'], 0.35, sigma=W * 0.18)
    mascot.draw_head(c, W * 0.5, W * 0.46, W * 0.62, t=0.0, expr='smile', look=(0.35, -0.15), theme=th, costume='default', rim=W * 0.024)
    if with_text:
        f = F.font('mono', W * 0.06)
        c.text('ODD CABINET', W / 2, W * 0.88, f, th['ink'], 'center', 'middle', alpha=0.9, spacing=W * 0.008)


def write(out_dir: str, theme_name: str = 'curious') -> dict:
    from .canvas import Frame
    os.makedirs(out_dir, exist_ok=True)
    fr = Frame(1024, 1024)
    profile(fr.c, 1024, theme_name)
    p1 = os.path.join(out_dir, 'profilbild.png')
    fr.save_png(p1)
    fr2 = Frame(512, 512)
    fr2.canvas.clear(0x00000000)
    draw_mark(fr2.c, 256, 256, 300, TH.get(theme_name))
    from PIL import Image
    im = Image.fromarray(fr2.to_array().copy(), 'RGBA')
    p2 = os.path.join(out_dir, 'zeichen.png')
    im.save(p2)
    return {'profilbild': p1, 'zeichen': p2}
