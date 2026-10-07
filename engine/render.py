"""Rendern: Bilder in Abschnitten (Segmente) über mehrere Prozesse, Zusammensetzen mit ffmpeg, Ton anlegen.

Fertige Segmente bleiben liegen: ein abgebrochener Lauf wird beim nächsten Aufruf fortgesetzt.
"""
from __future__ import annotations
import glob
import json
import math
import multiprocessing as mp
import os
import shutil
import subprocess
import time
from .canvas import Frame

SEG_FRAMES = 150   # 5 s bei 30 fps


def _segments_dir(project_dir: str) -> str:
    return os.path.join(project_dir, '.render', 'segments')


def _encode_cmd(path: str, W: int, H: int, fps: int, crf: int, preset: str, tune: str) -> list:
    return ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}', '-r', str(fps), '-i', '-',
            '-an', '-c:v', 'libx264', '-preset', preset, '-crf', str(crf), '-tune', tune, '-pix_fmt', 'yuv420p', '-g', str(fps * 2), path]


def _render_segment(args):
    project_dir, seg_index, f0, f1, out_path, root = args
    from . import compose
    comp = compose.load(project_dir, root)
    fmt = comp.fmt
    rc = comp.cfg['render']
    tmp = out_path + '.part.mp4'
    frame = Frame(fmt.W, fmt.H)
    proc = subprocess.Popen(_encode_cmd(tmp, fmt.W, fmt.H, fmt.fps, rc.get('crf', 17), rc.get('preset', 'medium'), rc.get('tune', 'animation')), stdin=subprocess.PIPE)
    t_start = time.time()
    try:
        for fi in range(f0, f1):
            t = fi / fmt.fps
            frame.canvas.clear(0xFF000000)
            comp.draw(frame.c, t)
            proc.stdin.write(frame.to_array().tobytes())
        proc.stdin.close()
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg Segment {seg_index} fehlgeschlagen")
        os.replace(tmp, out_path)
    except Exception:
        proc.kill()
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return seg_index, f1 - f0, time.time() - t_start


def render(project_dir: str, root: str = None, workers: int = None, budget: float = None, name: str = None, audio: str = None, overwrite: bool = False) -> dict:
    """Rendert das Video. budget: Sekunden, nach denen keine neuen Segmente mehr begonnen werden (Fortsetzung beim nächsten Aufruf)."""
    from . import compose, ROOT
    root = root or ROOT
    comp = compose.load(project_dir, root)
    fmt = comp.fmt
    rc = comp.cfg['render']
    workers = workers or rc.get('workers', 4)
    n_frames = int(math.ceil(comp.duration * fmt.fps))
    segdir = _segments_dir(project_dir)
    os.makedirs(segdir, exist_ok=True)
    # Signatur: ändert sich Plan oder Engine, werden alte Segmente verworfen
    sig = _signature(project_dir, comp)
    sig_p = os.path.join(segdir, 'signature.txt')
    old = open(sig_p).read() if os.path.exists(sig_p) else None
    if old != sig or overwrite:
        for f in glob.glob(os.path.join(segdir, 'seg_*.mp4')):
            os.unlink(f)
        with open(sig_p, 'w') as fh:
            fh.write(sig)
    n_seg = int(math.ceil(n_frames / SEG_FRAMES))
    jobs = []
    for i in range(n_seg):
        p = os.path.join(segdir, f'seg_{i:04d}.mp4')
        if not os.path.exists(p):
            jobs.append((project_dir, i, i * SEG_FRAMES, min(n_frames, (i + 1) * SEG_FRAMES), p, root))
    t0 = time.time()
    done = 0
    if jobs:
        ctx = mp.get_context('fork') if hasattr(os, 'fork') else mp.get_context('spawn')
        with ctx.Pool(processes=max(1, workers)) as pool:
            pending = []
            it = iter(jobs)
            # Budget: nur so lange neue Aufträge nachlegen, wie Zeit bleibt
            for job in it:
                pending.append(pool.apply_async(_render_segment, (job,)))
                if len(pending) >= workers * 2:
                    r = pending.pop(0).get()
                    done += 1
                    if budget and time.time() - t0 > budget:
                        break
            for r in pending:
                r.get()
                done += 1
    remaining = len([i for i in range(n_seg) if not os.path.exists(os.path.join(segdir, f'seg_{i:04d}.mp4'))])
    result = {'frames': n_frames, 'segments': n_seg, 'rendered_now': done, 'remaining': remaining, 'seconds': round(time.time() - t0, 1), 'duration': round(comp.duration, 2)}
    if remaining:
        result['status'] = 'partial'
        return result
    out = _assemble(project_dir, comp, name, audio)
    result.update({'status': 'done', 'video': out})
    return result


def _signature(project_dir: str, comp) -> str:
    from . import ENGINE_REV
    parts = [str(ENGINE_REV), json.dumps(comp.plan()['scenes'], sort_keys=True), str(comp.fmt.W), str(comp.fmt.H), str(comp.duration)]
    for fn in ('script.json', 'words.json', 'scenes.py'):
        p = os.path.join(project_dir, fn)
        if os.path.exists(p):
            parts.append(str(os.path.getmtime(p)))
    import hashlib
    return hashlib.md5('|'.join(parts).encode()).hexdigest()


def _assemble(project_dir: str, comp, name: str = None, audio: str = None) -> str:
    segdir = _segments_dir(project_dir)
    lst = os.path.join(segdir, 'list.txt')
    segs = sorted(glob.glob(os.path.join(segdir, 'seg_*.mp4')))
    with open(lst, 'w') as fh:
        for s in segs:
            fh.write(f"file '{os.path.abspath(s)}'\n")
    slug = name or comp.script['slug']
    out = os.path.join(project_dir, f'{slug}.mp4')
    k = 2
    while os.path.exists(out):
        out = os.path.join(project_dir, f'{slug}_v{k}.mp4')
        k += 1
    audio = audio or next((p for p in (os.path.join(project_dir, 'mix.wav'), os.path.join(project_dir, 'voice.wav')) if os.path.exists(p)), None)
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst]
    if audio:
        cmd += ['-i', audio, '-map', '0:v', '-map', '1:a', '-af', 'apad', '-c:a', 'aac', '-b:a', '192k']
    cmd += ['-c:v', 'copy', '-movflags', '+faststart', '-t', f'{comp.duration:.3f}', out]
    subprocess.run(cmd, check=True)
    return out


# ---------- Standbilder ----------

def frame_at(comp, t: float, scale: float = 1.0):
    """PIL-Bild zur Zeit t."""
    from PIL import Image
    fr = Frame(comp.fmt.W, comp.fmt.H)
    fr.canvas.clear(0xFF000000)
    comp.draw(fr.c, t)
    im = Image.fromarray(fr.to_rgb())
    if scale != 1.0:
        im = im.resize((max(1, int(comp.fmt.W * scale)), max(1, int(comp.fmt.H * scale))), Image.LANCZOS)
    return im


def stills(project_dir: str, times: list, out_dir: str = None, scale: float = 0.5, root: str = None) -> list:
    from . import compose
    comp = compose.load(project_dir, root)
    out_dir = out_dir or os.path.join(project_dir, 'check')
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for t in times:
        tt = comp.tl.at(t) if isinstance(t, str) else float(t)
        im = frame_at(comp, tt, scale)
        p = os.path.join(out_dir, f'still_{tt:07.2f}.png')
        im.save(p)
        paths.append(p)
    return paths


def sheet(project_dir: str, times: list = None, n: int = 12, cols: int = 4, scale: float = 0.25, out: str = None, root: str = None, label: bool = True) -> str:
    """Kontaktbogen: n gleichmäßig verteilte Bilder oder die angegebenen Zeiten."""
    from PIL import Image, ImageDraw
    from . import compose
    comp = compose.load(project_dir, root)
    if not times:
        times = [comp.duration * (i + 0.5) / n for i in range(n)]
    else:
        times = [comp.tl.at(t) if isinstance(t, str) else float(t) for t in times]
    ims = [frame_at(comp, t, scale) for t in times]
    w, h = ims[0].size
    rows = int(math.ceil(len(ims) / cols))
    sheet_im = Image.new('RGB', (cols * w, rows * h), (20, 20, 20))
    d = ImageDraw.Draw(sheet_im)
    for i, (im, t) in enumerate(zip(ims, times)):
        x, y = (i % cols) * w, (i // cols) * h
        sheet_im.paste(im, (x, y))
        if label:
            d.rectangle([x, y, x + 90, y + 22], fill=(0, 0, 0))
            d.text((x + 4, y + 4), f'{t:6.2f}s', fill=(255, 255, 255))
    out = out or os.path.join(project_dir, 'check', 'sheet.jpg')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet_im.save(out, quality=88)
    return out


def seq(project_dir: str, t: float, span: float = 1.4, n: int = 8, scale: float = 0.25, out: str = None, root: str = None) -> str:
    from . import compose
    comp = compose.load(project_dir, root)
    tt = comp.tl.at(t) if isinstance(t, str) else float(t)
    times = [tt + span * (i / (n - 1) - 0.5) for i in range(n)]
    return sheet(project_dir, times, cols=n, scale=scale, out=out or os.path.join(project_dir, 'check', f'seq_{tt:06.2f}.jpg'), root=root)
