"""Zeichenfläche: dünner, bequemer Mantel um skia.Canvas.

Alle Koordinaten in Pixeln des Zielformats. Farben als Hex, Tupel oder skia.Color4f (siehe color.py).
Zeichnen ist zustandslos: jede Szene ist eine reine Funktion der Zeit, die auf ein C-Objekt malt.
"""
from __future__ import annotations
import contextlib
import math
import numpy as np
import skia
from .color import c4f, parse
from . import fonts as F


class Frame:
    """Ein Bildpuffer (RGBA, premultiplied) mit Canvas. to_array() liefert numpy (H, W, 4) uint8."""

    def __init__(self, W: int, H: int):
        self.W, self.H = int(W), int(H)
        self.arr = np.zeros((self.H, self.W, 4), np.uint8)
        info = skia.ImageInfo.Make(self.W, self.H, skia.ColorType.kRGBA_8888_ColorType, skia.AlphaType.kPremul_AlphaType)
        self.surface = skia.Surface.MakeRasterDirect(info, self.arr, self.W * 4)
        self.canvas = self.surface.getCanvas()
        self.c = C(self.canvas, self.W, self.H)

    def flush(self):
        self.surface.flushAndSubmit()

    def to_array(self) -> np.ndarray:
        self.flush()
        return self.arr

    def to_rgb(self) -> np.ndarray:
        return self.to_array()[..., :3].copy()

    def snapshot(self) -> skia.Image:
        self.flush()
        return self.surface.makeImageSnapshot()

    def save_png(self, path: str, scale: float = 1.0):
        from PIL import Image
        im = Image.fromarray(self.to_rgb())
        if scale != 1.0:
            im = im.resize((max(1, int(self.W * scale)), max(1, int(self.H * scale))), Image.LANCZOS)
        im.save(path)


def _stroke_paint(p: skia.Paint, width: float, cap='round', join='round'):
    p.setStyle(skia.Paint.kStroke_Style)
    p.setStrokeWidth(float(width))
    p.setStrokeCap({'round': skia.Paint.kRound_Cap, 'butt': skia.Paint.kButt_Cap, 'square': skia.Paint.kSquare_Cap}[cap])
    p.setStrokeJoin({'round': skia.Paint.kRound_Join, 'miter': skia.Paint.kMiter_Join, 'bevel': skia.Paint.kBevel_Join}[join])


BLEND = {
    None: None, 'normal': skia.BlendMode.kSrcOver, 'screen': skia.BlendMode.kScreen, 'add': skia.BlendMode.kPlus,
    'multiply': skia.BlendMode.kMultiply, 'overlay': skia.BlendMode.kOverlay, 'soft': skia.BlendMode.kSoftLight,
    'lighten': skia.BlendMode.kLighten, 'darken': skia.BlendMode.kDarken, 'difference': skia.BlendMode.kDifference,
    'hue': skia.BlendMode.kHue, 'color': skia.BlendMode.kColor, 'luminosity': skia.BlendMode.kLuminosity,
    'src': skia.BlendMode.kSrc, 'dst_in': skia.BlendMode.kDstIn, 'dst_out': skia.BlendMode.kDstOut, 'src_in': skia.BlendMode.kSrcIn,
}


class C:
    """Zeichenbefehle. x, y sind Mittelpunkte bei circle/ellipse, linke obere Ecke bei rect."""

    def __init__(self, canvas: skia.Canvas, W: int, H: int):
        self.k = canvas
        self.W, self.H = W, H
        self.CX, self.CY = W / 2.0, H / 2.0
        self.marks = None   # Liste für wichtige Flächen (check.py setzt sie), sonst None

    def mark(self, x, y, w, h, label='', kind='text'):
        """Wichtige Fläche anmelden (Text, Karte, Figur), damit check.py sie gegen die Sicherheitszonen prüfen kann.
        Koordinaten im Bild; bei aktiver Transformation wird die Fläche über die Canvas-Matrix umgerechnet."""
        if self.marks is None:
            return
        try:
            m = self.k.getTotalMatrix()
            r = m.mapRect(skia.Rect.MakeXYWH(float(x), float(y), float(w), float(h)))
            self.marks.append({'x': r.left(), 'y': r.top(), 'w': r.width(), 'h': r.height(), 'label': label, 'kind': kind})
        except Exception:
            self.marks.append({'x': float(x), 'y': float(y), 'w': float(w), 'h': float(h), 'label': label, 'kind': kind})

    # ---------- Paints ----------
    def paint(self, color=None, alpha=1.0, blur=0.0, stroke=None, cap='round', join='round', blend=None, shader=None, dither=False) -> skia.Paint:
        p = skia.Paint(AntiAlias=True)
        if color is not None:
            p.setColor4f(c4f(color, alpha))
        elif shader is None:
            p.setColor4f(skia.Color4f(0, 0, 0, alpha))
        if shader is not None:
            p.setShader(shader)
            if color is None:
                p.setAlphaf(float(alpha))
        if blur and blur > 0:
            p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, float(blur)))
        if stroke is not None:
            _stroke_paint(p, stroke, cap, join)
        if blend:
            p.setBlendMode(BLEND[blend])
        if dither:
            p.setDither(True)
        return p

    def linear(self, x0, y0, x1, y1, stops, alpha=1.0):
        """Linearer Verlauf; stops = [(pos, color), ...] oder [color, color, ...]."""
        cols, poss = _stops(stops, alpha)
        return skia.GradientShader.MakeLinear(points=[(float(x0), float(y0)), (float(x1), float(y1))], colors=cols, positions=poss)

    def radial(self, x, y, r, stops, alpha=1.0):
        cols, poss = _stops(stops, alpha)
        return skia.GradientShader.MakeRadial(center=(float(x), float(y)), radius=float(r), colors=cols, positions=poss)

    def sweep(self, x, y, stops, alpha=1.0, start=0.0, end=360.0):
        cols, poss = _stops(stops, alpha)
        return skia.GradientShader.MakeSweep(cx=float(x), cy=float(y), colors=cols, positions=poss, startAngle=float(start), endAngle=float(end))

    def noise(self, freq=0.02, octaves=3, seed=0, turbulence=False):
        f = float(freq)
        if turbulence:
            return skia.PerlinNoiseShader.MakeTurbulence(f, f, int(octaves), float(seed))
        return skia.PerlinNoiseShader.MakeFractalNoise(f, f, int(octaves), float(seed))

    # ---------- Primitive ----------
    def fill(self, color, alpha=1.0):
        self.k.drawRect(skia.Rect.MakeXYWH(-10, -10, self.W + 20, self.H + 20), self.paint(color, alpha))

    def fill_shader(self, shader, alpha=1.0, blend=None):
        self.k.drawRect(skia.Rect.MakeXYWH(-10, -10, self.W + 20, self.H + 20), self.paint(shader=shader, alpha=alpha, blend=blend))

    def circle(self, x, y, r, color=None, alpha=1.0, blur=0.0, stroke=None, blend=None, shader=None):
        if r <= 0:
            return
        self.k.drawCircle(float(x), float(y), float(r), self.paint(color, alpha, blur, stroke, blend=blend, shader=shader))

    def ellipse(self, x, y, rx, ry, color=None, alpha=1.0, blur=0.0, stroke=None, blend=None, shader=None, rot=0.0):
        if rx <= 0 or ry <= 0:
            return
        p = self.paint(color, alpha, blur, stroke, blend=blend, shader=shader)
        if rot:
            with self.tf(rot=rot, px=x, py=y):
                self.k.drawOval(skia.Rect.MakeLTRB(x - rx, y - ry, x + rx, y + ry), p)
        else:
            self.k.drawOval(skia.Rect.MakeLTRB(x - rx, y - ry, x + rx, y + ry), p)

    def rect(self, x, y, w, h, color=None, r=0.0, alpha=1.0, blur=0.0, stroke=None, blend=None, shader=None, rot=0.0):
        if w <= 0 or h <= 0:
            return
        p = self.paint(color, alpha, blur, stroke, blend=blend, shader=shader)
        rr = skia.Rect.MakeXYWH(float(x), float(y), float(w), float(h))
        with self.tf(rot=rot, px=x + w / 2, py=y + h / 2) if rot else contextlib.nullcontext():
            if r:
                self.k.drawRoundRect(rr, float(r), float(r), p)
            else:
                self.k.drawRect(rr, p)

    def rect_c(self, cx, cy, w, h, color=None, r=0.0, **kw):
        """Rechteck um seinen Mittelpunkt."""
        self.rect(cx - w / 2, cy - h / 2, w, h, color, r, **kw)

    def rrect_mixed(self, x, y, w, h, radii, color=None, alpha=1.0, stroke=None, blur=0.0, shader=None, blend=None):
        """Rundung je Ecke: radii = (tl, tr, br, bl)."""
        rr = skia.RRect()
        tl, tr, br, bl = radii
        rr.setRectRadii(skia.Rect.MakeXYWH(x, y, w, h), [(tl, tl), (tr, tr), (br, br), (bl, bl)])
        self.k.drawRRect(rr, self.paint(color, alpha, blur, stroke, blend=blend, shader=shader))

    def line(self, x0, y0, x1, y1, color, width=4.0, alpha=1.0, cap='round', blur=0.0, blend=None, dash=None):
        p = self.paint(color, alpha, blur, width, cap, blend=blend)
        if dash:
            p.setPathEffect(skia.DashPathEffect.Make([float(d) for d in dash], 0.0))
        self.k.drawLine(float(x0), float(y0), float(x1), float(y1), p)

    def polyline(self, pts, color, width=4.0, alpha=1.0, cap='round', join='round', closed=False, blur=0.0, dash=None, blend=None):
        if len(pts) < 2:
            return
        path = skia.Path()
        path.moveTo(float(pts[0][0]), float(pts[0][1]))
        for x, y in pts[1:]:
            path.lineTo(float(x), float(y))
        if closed:
            path.close()
        p = self.paint(color, alpha, blur, width, cap, join, blend=blend)
        if dash:
            p.setPathEffect(skia.DashPathEffect.Make([float(d) for d in dash], 0.0))
        self.k.drawPath(path, p)

    def poly(self, pts, color=None, alpha=1.0, stroke=None, blur=0.0, blend=None, shader=None, join='round'):
        if len(pts) < 3:
            return
        path = skia.Path()
        path.moveTo(float(pts[0][0]), float(pts[0][1]))
        for x, y in pts[1:]:
            path.lineTo(float(x), float(y))
        path.close()
        self.k.drawPath(path, self.paint(color, alpha, blur, stroke, join=join, blend=blend, shader=shader))

    def path(self, path: skia.Path, color=None, alpha=1.0, stroke=None, blur=0.0, blend=None, shader=None, cap='round', join='round'):
        self.k.drawPath(path, self.paint(color, alpha, blur, stroke, cap, join, blend=blend, shader=shader))

    def arc(self, x, y, r, a0, a1, color, width=6.0, alpha=1.0, cap='round', blur=0.0, blend=None):
        """Kreisbogen von Winkel a0 bis a1 (Grad, 0 = rechts, im Uhrzeigersinn)."""
        if a1 == a0:
            return
        rect = skia.Rect.MakeLTRB(x - r, y - r, x + r, y + r)
        path = skia.Path()
        path.addArc(rect, float(a0), float(a1 - a0))
        self.k.drawPath(path, self.paint(color, alpha, blur, width, cap, blend=blend))

    def pie(self, x, y, r, a0, a1, color, alpha=1.0, blend=None, shader=None):
        rect = skia.Rect.MakeLTRB(x - r, y - r, x + r, y + r)
        path = skia.Path()
        path.moveTo(x, y)
        path.arcTo(rect, float(a0), float(a1 - a0), False)
        path.close()
        self.k.drawPath(path, self.paint(color, alpha, blend=blend, shader=shader))

    def ring(self, x, y, r, width, color, alpha=1.0, blur=0.0, blend=None):
        self.circle(x, y, r, color, alpha, blur, stroke=width, blend=blend)

    def star(self, x, y, r_outer, r_inner, n=5, color=None, alpha=1.0, rot=-90.0, stroke=None, blend=None):
        pts = []
        for i in range(n * 2):
            rr = r_outer if i % 2 == 0 else r_inner
            a = math.radians(rot + i * 180.0 / n)
            pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
        self.poly(pts, color, alpha, stroke, blend=blend)

    def regular(self, x, y, r, n=6, color=None, alpha=1.0, rot=0.0, stroke=None, blend=None, shader=None):
        pts = [(x + r * math.cos(math.radians(rot + i * 360.0 / n)), y + r * math.sin(math.radians(rot + i * 360.0 / n))) for i in range(n)]
        self.poly(pts, color, alpha, stroke, blend=blend, shader=shader)

    def blob(self, x, y, r, color=None, alpha=1.0, n=7, wob=0.12, seed=0.0, t=0.0, speed=0.3, stroke=None, blend=None, shader=None):
        """Organische, weich wabernde Form (geschlossene Catmull-Rom-ähnliche Kurve)."""
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n
            rr = r * (1 + wob * math.sin(seed * 3.1 + i * 2.3 + t * speed * 2 * math.pi) + wob * 0.5 * math.cos(seed * 1.7 + i * 4.1 - t * speed * 1.3 * 2 * math.pi))
            pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
        self.smooth_poly(pts, color, alpha, stroke=stroke, blend=blend, shader=shader)

    def smooth_poly(self, pts, color=None, alpha=1.0, stroke=None, tension=0.5, closed=True, blur=0.0, blend=None, shader=None):
        """Glatte Kurve durch Punkte (Catmull-Rom -> Bezier)."""
        path = smooth_path(pts, tension, closed)
        self.k.drawPath(path, self.paint(color, alpha, blur, stroke, blend=blend, shader=shader))

    def glow(self, x, y, r, color, alpha=0.6, sigma=None, blend='add'):
        """Weicher Lichtfleck."""
        s = sigma if sigma is not None else r * 0.6
        self.circle(x, y, r, color, alpha, blur=s, blend=blend)

    def soft_shadow(self, x, y, w, h, r=0.0, color='#000000', alpha=0.35, sigma=18.0, dy=14.0, dx=0.0):
        """Weicher Schatten unter einem Rechteck (vor dem Objekt zeichnen)."""
        self.rect(x + dx, y + dy, w, h, color, r, alpha, blur=sigma)

    def ellipse_shadow(self, x, y, rx, ry, color='#000000', alpha=0.3, sigma=16.0):
        self.ellipse(x, y, rx, ry, color, alpha, blur=sigma)

    # ---------- Text ----------
    def text(self, s, x, y, f: skia.Font, color='#FFFFFF', align='left', baseline='alphabetic', alpha=1.0, spacing=0.0, blur=0.0, stroke=None, blend=None, shader=None):
        """Text zeichnen. align: left/center/right. baseline: alphabetic/middle/top/cap/bottom. spacing in px je Zeichen."""
        if not s:
            return 0.0
        w = self.text_width(s, f, spacing)
        if align == 'center':
            x = x - w / 2
        elif align == 'right':
            x = x - w
        asc, desc, cap, xh = F.metrics(f)
        if baseline == 'middle':
            y = y + cap / 2
        elif baseline == 'top':
            y = y - asc
        elif baseline == 'cap':
            y = y + cap
        elif baseline == 'bottom':
            y = y - desc
        p = self.paint(color, alpha, blur, stroke, blend=blend, shader=shader)
        if spacing:
            cx = x
            for ch in s:
                self.k.drawString(ch, float(cx), float(y), f, p)
                cx += f.measureText(ch) + spacing
        else:
            self.k.drawString(s, float(x), float(y), f, p)
        return w

    def text_width(self, s, f: skia.Font, spacing=0.0) -> float:
        if not s:
            return 0.0
        if spacing:
            return sum(f.measureText(ch) for ch in s) + spacing * (len(s) - 1)
        return f.measureText(s)

    def text_lines(self, lines, x, y, f: skia.Font, color='#FFFFFF', align='center', leading=1.15, alpha=1.0, spacing=0.0, baseline='top', **kw):
        """Mehrere Zeilen untereinander; gibt die Unterkante zurück."""
        asc, desc, cap, xh = F.metrics(f)
        lh = f.getSize() * leading
        yy = y
        for ln in lines:
            self.text(ln, x, yy, f, color, align, baseline, alpha, spacing, **kw)
            yy += lh
        return yy - lh + (desc if baseline == 'top' else 0)

    def text_fit(self, s, x, y, role, size, max_width, color='#FFFFFF', align='center', baseline='middle', weight=None, alpha=1.0, min_size=14, **kw):
        """Text, der notfalls kleiner gesetzt wird, bis er in max_width passt."""
        sz = F.fit_size(s, role, max_width, size, min_size, weight=weight)
        f = F.font(role, sz, weight=weight)
        self.text(s, x, y, f, color, align, baseline, alpha, **kw)
        return sz

    # ---------- Bilder ----------
    def image(self, img, x, y, w=None, h=None, alpha=1.0, blend=None):
        """img: skia.Image oder numpy RGBA (H, W, 4)."""
        if isinstance(img, np.ndarray):
            img = skia.Image.fromarray(np.ascontiguousarray(img), skia.ColorType.kRGBA_8888_ColorType)
        w = img.width() if w is None else w
        h = img.height() if h is None else h
        p = skia.Paint(AntiAlias=True)
        p.setAlphaf(float(alpha))
        if blend:
            p.setBlendMode(BLEND[blend])
        self.k.drawImageRect(img, skia.Rect.MakeXYWH(float(x), float(y), float(w), float(h)), skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear), p)

    # ---------- Gruppen, Transformationen, Clipping ----------
    @contextlib.contextmanager
    def layer(self, alpha=1.0, blend=None, blur=0.0):
        """Gruppe mit gemeinsamer Deckkraft/Blendmodus/Weichzeichnung (teuer: sparsam einsetzen)."""
        p = skia.Paint()
        p.setAlphaf(float(max(0.0, min(1.0, alpha))))
        if blend:
            p.setBlendMode(BLEND[blend])
        if blur and blur > 0:
            p.setImageFilter(skia.ImageFilters.Blur(float(blur), float(blur)))
        self.k.saveLayer(None, p)
        try:
            yield self
        finally:
            self.k.restore()

    @contextlib.contextmanager
    def tf(self, x=0.0, y=0.0, rot=0.0, sx=1.0, sy=None, px=None, py=None):
        """Verschieben, drehen (Grad) und skalieren um den Drehpunkt (px, py)."""
        self.k.save()
        try:
            if x or y:
                self.k.translate(float(x), float(y))
            if rot or sx != 1.0 or (sy is not None and sy != 1.0):
                cx = 0.0 if px is None else float(px)
                cy = 0.0 if py is None else float(py)
                self.k.translate(cx, cy)
                if rot:
                    self.k.rotate(float(rot))
                if sx != 1.0 or (sy is not None and sy != 1.0):
                    self.k.scale(float(sx), float(sx if sy is None else sy))
                self.k.translate(-cx, -cy)
            yield self
        finally:
            self.k.restore()

    @contextlib.contextmanager
    def clip_rect(self, x, y, w, h, r=0.0):
        self.k.save()
        try:
            if r:
                self.k.clipRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), r, r), True)
            else:
                self.k.clipRect(skia.Rect.MakeXYWH(x, y, w, h), True)
            yield self
        finally:
            self.k.restore()

    @contextlib.contextmanager
    def clip_circle(self, x, y, r):
        self.k.save()
        try:
            path = skia.Path()
            path.addCircle(float(x), float(y), float(r))
            self.k.clipPath(path, True)
            yield self
        finally:
            self.k.restore()

    @contextlib.contextmanager
    def clip_path(self, path: skia.Path, inverse=False):
        self.k.save()
        try:
            self.k.clipPath(path, skia.ClipOp.kDifference if inverse else skia.ClipOp.kIntersect, True)
            yield self
        finally:
            self.k.restore()

    @contextlib.contextmanager
    def clip_poly(self, pts):
        path = skia.Path()
        path.moveTo(float(pts[0][0]), float(pts[0][1]))
        for x, y in pts[1:]:
            path.lineTo(float(x), float(y))
        path.close()
        with self.clip_path(path):
            yield self

    # ---------- Fertige Flächen ----------
    def grain(self, amount=0.06, scale=1.0, seed=3, blend='overlay'):
        """Feines Korn über das ganze Bild (Papier-/Druckgefühl)."""
        if amount <= 0:
            return
        sh = skia.PerlinNoiseShader.MakeTurbulence(0.9 / scale, 0.9 / scale, 1, float(seed))
        self.fill_shader(sh, alpha=amount, blend=blend)

    def vignette(self, strength=0.35, color='#000000', inner=0.55):
        if strength <= 0:
            return
        r = math.hypot(self.W, self.H) * 0.55
        sh = self.radial(self.CX, self.CY, r, [(0.0, (0, 0, 0, 0)), (inner, (0, 0, 0, 0)), (1.0, parse(color))])
        self.fill_shader(sh, alpha=strength)

    def spotlight(self, x, y, r, color='#FFFFFF', alpha=0.25, blend='add'):
        sh = self.radial(x, y, r, [(0.0, parse(color)), (1.0, (0, 0, 0, 0))])
        self.fill_shader(sh, alpha=alpha, blend=blend)

    def gradient_bg(self, top, bottom, mid=None):
        stops = [top, bottom] if mid is None else [(0.0, top), (0.5, mid), (1.0, bottom)]
        self.fill_shader(self.linear(0, 0, 0, self.H, stops))


def _stops(stops, alpha=1.0):
    if stops and not isinstance(stops[0], (tuple, list)) or (stops and isinstance(stops[0], (tuple, list)) and len(stops[0]) in (3, 4) and not isinstance(stops[0][1], (tuple, list, str))):
        # Liste reiner Farben
        n = len(stops)
        cols = [c4f(s, alpha) for s in stops]
        poss = [i / (n - 1) if n > 1 else 0.0 for i in range(n)]
        return cols, poss
    cols = [c4f(s[1], alpha) for s in stops]
    poss = [float(s[0]) for s in stops]
    return cols, poss


def smooth_path(pts, tension=0.5, closed=True) -> skia.Path:
    """Catmull-Rom-Spline durch pts als kubische Bezier-Segmente."""
    n = len(pts)
    path = skia.Path()
    if n < 2:
        return path
    def P(i):
        if closed:
            return pts[i % n]
        return pts[max(0, min(n - 1, i))]
    path.moveTo(float(pts[0][0]), float(pts[0][1]))
    segs = n if closed else n - 1
    for i in range(segs):
        p0, p1, p2, p3 = P(i - 1), P(i), P(i + 1), P(i + 2)
        c1 = (p1[0] + (p2[0] - p0[0]) * tension / 3, p1[1] + (p2[1] - p0[1]) * tension / 3)
        c2 = (p2[0] - (p3[0] - p1[0]) * tension / 3, p2[1] - (p3[1] - p1[1]) * tension / 3)
        path.cubicTo(c1[0], c1[1], c2[0], c2[1], float(p2[0]), float(p2[1]))
    if closed:
        path.close()
    return path


def rounded_poly_path(pts, radius) -> skia.Path:
    """Polygon mit abgerundeten Ecken."""
    n = len(pts)
    path = skia.Path()
    if n < 3:
        return path
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        v0 = (p0[0] - p1[0], p0[1] - p1[1]); v2 = (p2[0] - p1[0], p2[1] - p1[1])
        l0 = math.hypot(*v0) or 1; l2 = math.hypot(*v2) or 1
        r = min(radius, l0 / 2, l2 / 2)
        a = (p1[0] + v0[0] / l0 * r, p1[1] + v0[1] / l0 * r)
        b = (p1[0] + v2[0] / l2 * r, p1[1] + v2[1] / l2 * r)
        if i == 0:
            path.moveTo(*a)
        else:
            path.lineTo(*a)
        path.quadTo(p1[0], p1[1], b[0], b[1])
    path.close()
    return path
