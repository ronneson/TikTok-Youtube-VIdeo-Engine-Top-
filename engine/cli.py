"""Befehle: python3 -m engine <befehl> [...]. Ausgabe als JSON, damit sie sich lesen und prüfen lässt."""
from __future__ import annotations
import argparse
import json
import os
import sys
from . import ROOT


def _p(obj):
    print(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='engine', description='Top-Listen Video-Engine')
    ap.add_argument('--root', default=ROOT, help='Engine-Ordner (Standard: der Ordner dieser Datei)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('status', help='Umgebung prüfen'); 
    s = sub.add_parser('new', help='Projekt anlegen'); s.add_argument('slug'); s.add_argument('title'); s.add_argument('--format', default='portrait'); s.add_argument('--theme', default='curious'); s.add_argument('--series', default='')
    s = sub.add_parser('projects', help='Projekte auflisten')
    s = sub.add_parser('words', help='Zeiten der Zeilen und Wörter'); s.add_argument('project'); s.add_argument('--all', action='store_true')
    s = sub.add_parser('plan', help='Plan schreiben (Szenen, Töne, Warnungen) und Mischung erzeugen'); s.add_argument('project'); s.add_argument('--no-mix', action='store_true')
    s = sub.add_parser('tts', help='Stimme erzeugen (ElevenLabs oder espeak)'); s.add_argument('project'); s.add_argument('--provider', default=None)
    s = sub.add_parser('voices', help='ElevenLabs-Stimmen des Kontos')
    s = sub.add_parser('voice', help='Stimme aufbereiten -> voice.wav, words.json'); s.add_argument('project')
    s = sub.add_parser('mix', help='Musik, Töne, Mastering -> mix.wav'); s.add_argument('project'); s.add_argument('--music', default=None)
    s = sub.add_parser('render', help='Video rendern'); s.add_argument('project'); s.add_argument('--workers', type=int, default=None); s.add_argument('--budget', type=float, default=None); s.add_argument('--name', default=None); s.add_argument('--overwrite', action='store_true')
    s = sub.add_parser('stills', help='Standbilder zu Zeiten/Wörtern'); s.add_argument('project'); s.add_argument('times', nargs='+'); s.add_argument('--px', type=float, default=0.5); s.add_argument('--dir', default=None)
    s = sub.add_parser('sheet', help='Kontaktbogen'); s.add_argument('project'); s.add_argument('--n', type=int, default=12); s.add_argument('--cols', type=int, default=4); s.add_argument('--px', type=float, default=0.25); s.add_argument('--times', nargs='*', default=None); s.add_argument('--out', default=None)
    s = sub.add_parser('seq', help='Bildfolge um einen Zeitpunkt'); s.add_argument('project'); s.add_argument('time'); s.add_argument('--span', type=float, default=1.4); s.add_argument('--n', type=int, default=8); s.add_argument('--px', type=float, default=0.25)
    s = sub.add_parser('check', help='Sicherheitszonen, Kontrast, Telefonansicht'); s.add_argument('project'); s.add_argument('--times', nargs='*', default=None)
    s = sub.add_parser('phone', help='Bild so, wie das Telefon es zeigt'); s.add_argument('project'); s.add_argument('times', nargs='+')
    s = sub.add_parser('sounds', help='Alle Töne als WAV nach library/sfx rendern'); s.add_argument('--out', default=None)
    s = sub.add_parser('music', help='Musikbetten als WAV nach library/music rendern'); s.add_argument('--out', default=None); s.add_argument('--seconds', type=float, default=30.0)
    s = sub.add_parser('mascot', help='Posen-Bogen des Maskottchens'); s.add_argument('--out', default=None)
    s = sub.add_parser('props', help='Bogen aller Piktogramme'); s.add_argument('--out', default=None)
    s = sub.add_parser('palette', help='Farbbogen aller Themen'); s.add_argument('--out', default=None)
    s = sub.add_parser('brand', help='Profilbild und Zeichen schreiben'); s.add_argument('--out', default=None)
    s = sub.add_parser('sfxsheet', help='Töne auflisten')
    s = sub.add_parser('loudness', help='Lautheit einer Datei messen'); s.add_argument('file')

    a = ap.parse_args(argv)
    root = a.root
    from . import config as CFG, project as P
    cfg = CFG.load(root)

    if a.cmd == 'status':
        _p(P.status(root)); return
    if a.cmd == 'new':
        _p({'project': P.new(a.slug, a.title, root, a.format, a.theme, a.series)}); return
    if a.cmd == 'projects':
        _p(P.listing(root)); return
    if a.cmd == 'voices':
        from .audio import tts
        _p(tts.list_voices(root)); return
    if a.cmd == 'sounds':
        from .audio import sfx
        _p(sfx.render_all(a.out or os.path.join(root, 'library', 'sfx'))); return
    if a.cmd == 'sfxsheet':
        from .audio import sfx
        _p(sfx.catalog()); return
    if a.cmd == 'music':
        from .audio import music
        _p(music.render_all(a.out or os.path.join(root, 'library', 'music'), a.seconds)); return
    if a.cmd == 'mascot':
        from . import mascot
        _p({'sheet': mascot.sheet(a.out or os.path.join(root, 'library', 'sheets', 'mascot.png'))}); return
    if a.cmd == 'props':
        from . import props
        _p({'sheet': props.sheet(a.out or os.path.join(root, 'library', 'sheets', 'props.png'))}); return
    if a.cmd == 'palette':
        from . import theme
        _p({'sheet': theme.sheet(a.out or os.path.join(root, 'library', 'sheets', 'palette.png'))}); return
    if a.cmd == 'brand':
        from . import brand
        _p(brand.write(a.out or os.path.join(root, 'assets', 'brand'))); return
    if a.cmd == 'loudness':
        from .audio import wav
        _p(wav.measure_lufs(a.file)); return

    proj = P.find(a.project, root)
    if a.cmd == 'words':
        from . import compose
        comp = compose.load(proj, root)
        out = {'source': comp.tl.source, 'duration': round(comp.duration, 2), 'voice_end': round(comp.tl.voice_end(), 2), 'words': len(comp.tl.words),
               'scenes': [{'id': sc.id, 't0': round(sc.t0, 2), 't1': round(sc.t1, 2), 'dur': round(sc.dur, 2)} for sc in comp.scenes],
               'lines': [{'id': ln.id, 't0': round(ln.t0, 2), 't1': round(ln.t1, 2), 'text': ln.text if a.all else ln.text[:60]} for ln in comp.tl.lines],
               'warnings': comp.warnings()}
        if a.all:
            out['word_list'] = [{'w': w.w, 't0': round(w.t0, 2), 't1': round(w.t1, 2), 'line': w.line} for w in comp.tl.words]
        _p(out); return
    if a.cmd == 'plan':
        from . import compose
        comp = compose.load(proj, root)
        plan = compose.write_plan(proj, comp)
        out = {k: plan[k] for k in ('title', 'format', 'duration', 'voice_source', 'words', 'warnings')}
        out['scenes'] = plan['scenes']
        if not a.no_mix and os.path.exists(os.path.join(proj, 'voice.wav')):
            from .audio import mix
            out['mix'] = mix.build(proj, cfg, root)
        _p(out); return
    if a.cmd == 'tts':
        from .audio import tts
        _p(tts.synthesize(proj, cfg, root, a.provider)); return
    if a.cmd == 'voice':
        from .audio import voice
        _p(voice.process(proj, cfg)); return
    if a.cmd == 'mix':
        from .audio import mix
        _p(mix.build(proj, cfg, root, music=a.music)); return
    if a.cmd == 'render':
        from . import render
        _p(render.render(proj, root, a.workers, a.budget, a.name, overwrite=a.overwrite)); return
    if a.cmd == 'stills':
        from . import render
        _p(render.stills(proj, [_num(t) for t in a.times], a.dir, a.px, root)); return
    if a.cmd == 'sheet':
        from . import render
        _p({'sheet': render.sheet(proj, [_num(t) for t in a.times] if a.times else None, a.n, a.cols, a.px, a.out, root)}); return
    if a.cmd == 'seq':
        from . import render
        _p({'seq': render.seq(proj, _num(a.time), a.span, a.n, a.px, root=root)}); return
    if a.cmd == 'check':
        from . import check
        _p(check.run(proj, [_num(t) for t in a.times] if a.times else None, root)); return
    if a.cmd == 'phone':
        from . import check
        _p(check.phone(proj, [_num(t) for t in a.times], root)); return


def _num(s):
    try:
        return float(s)
    except ValueError:
        return s


if __name__ == '__main__':
    main()
