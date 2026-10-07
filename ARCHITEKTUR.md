# Architektur und Schnittstellen der Engine

Python 3.10+, Zeichnen mit `skia-python`, Ton mit `numpy`/`scipy`, Ausgabe mit `ffmpeg`. Keine Bitmaps, keine Stock-Clips: alles entsteht aus Code.
Jede Szene ist eine **reine Funktion der Zeit** `draw(c, t)`: kein Zustand zwischen Bildern, damit Segmente parallel und wiederholbar gerechnet werden.

## Ordner

```
engine/            Paket (python3 -m engine <befehl>)
  canvas.py        Zeichenfläche C (circle, rect, path, text, Verläufe, layer, tf, clip, grain, vignette)   FERTIG
  anim.py          Easing, tween, appear, pop, spring, Keyframes, shake, count_value                        FERTIG
  color.py         Hex/Tupel/Color4f, mix, lighten, contrast                                               FERTIG
  fonts.py         font(role, size, weight=...) mit variablen Google Fonts, wrap, fit_size                  FERTIG
  layout.py        Format (portrait 1080x1920 / landscape 1920x1080), Sicherheitszonen, Slots              FERTIG
  config.py        DEFAULTS + config/engine.json, get_key('elevenlabs')                                    FERTIG
  script.py        script.json laden/prüfen, Zeilen mit IDs (H1, E5.0 Ansage, E5.1.., O1), tokens        FERTIG
  timeline.py      Wörter/Zeilen mit Zeiten, at('wort$+0.2'), Schätzung ohne Stimme                       FERTIG
  compose.py       Szenenfolge (hook, E5..E1, outro), Plan, Töne-Cues, Warnungen, Composition.draw        FERTIG
  render.py        Segmente parallel -> ffmpeg, stills, sheet, seq                                         FERTIG
  project.py       Projekte anlegen/finden                                                                 FERTIG
  cli.py           Befehle                                                                                 FERTIG
  theme.py         Farbthemen aus STIL.md                                                                  BAUEN
  mascot.py        Maskottchen, parametrisch (Posen, Ausdruck, Kostüme)                                    BAUEN
  props.py         Piktogramm-Repertoire                                                                   BAUEN
  backdrops.py     Kulissen (ganzflächig)                                                                  BAUEN
  cards.py         Nummernkarten, Titel, Stat, Ortsmarke, Serienetikett, Fortschritt, Wasserzeichen        BAUEN
  captions.py      Untertitel Wort für Wort                                                                BAUEN
  fx.py            Partikel, Lichtstrahlen, Übergänge, Blitz, Schockwelle                                  BAUEN
  scenes.py        SceneRenderer: Vorlagen hook/entry/outro, Übergänge, Aufbau eines Bildes                BAUEN (Platzhalter vorhanden)
  check.py         Sicherheitszonen, Kontrast, Telefonansicht                                              BAUEN
  brand.py         Profilbild und Zeichen                                                                  BAUEN
  audio/
    wav.py         lesen/schreiben/resample, measure_lufs                                                  FERTIG
    tts.py         ElevenLabs (with-timestamps) + espeak-Platzhalter -> raw_voice.wav, words_raw.json      FERTIG
    voice.py       Pausen straffen, Tempo, Klang -> voice.wav, words.json                                  FERTIG
    synth.py       Oszillatoren, Hüllkurven, Filter, Delay, Hall                                           BAUEN
    sfx.py         Tonvorrat (prozedural)                                                                  BAUEN
    music.py       Musikbetten (generativ, szenenbewusst)                                                  BAUEN
    mix.py         Stimme + Musik (Ducking) + Töne, Mastering -14 LUFS -> mix.wav                          BAUEN
assets/fonts/      Google Fonts (OFL)
config/engine.json Einstellungen; config/keys/ Schlüssel (nie committen)
projects/<datum>_<slug>/  script.json, words.json, voice.wav, mix.wav, plan.json, <slug>.mp4, check/
library/sheets/    Übersichtsbögen (Maskottchen, Piktogramme, Farben), library/sfx, library/music (Audition)
tests/             pytest
```

## Koordinaten und Format

- `fmt = layout.get_format('portrait')`: `fmt.W, fmt.H, fmt.fps, fmt.cx, fmt.cy`, Slots `fmt.stage, fmt.title, fmt.card, fmt.caption, fmt.progress, fmt.label, fmt.watermark` (je `Rect` mit x, y, w, h, cx, cy, x1, y1), `fmt.buttons` (TikTok-Knopfleiste, None im Querformat), `fmt.scale` (Schriftfaktor: 1.0 Hochformat, 0.78 Querformat), `fmt.portrait`.
- Hochformat: nichts Wichtiges über y=260 (Suchleiste), unter y=1590 (Kanalname), rechts in `fmt.buttons` (x>890, y>770). Text zwischen x=70 und 1010.
- Alles, was ganzflächig ist (Kulissen), mindestens 200 px über jeden Rand hinaus zeichnen (Übergänge skalieren/schieben).

## Zeichnen (canvas.C)

```python
c.fill(color); c.gradient_bg(top, bottom, mid=None); c.fill_shader(shader, alpha, blend)
c.circle(x, y, r, color, alpha=1, blur=0, stroke=None, blend=None, shader=None)
c.ellipse(x, y, rx, ry, color, ..., rot=0); c.rect(x, y, w, h, color, r=0, ..., rot=0); c.rect_c(cx, cy, w, h, color, r)
c.line(x0, y0, x1, y1, color, width, alpha, cap, dash=[on, off]); c.polyline(pts, ...); c.poly(pts, color, stroke=None)
c.path(skia.Path, ...); c.arc(x, y, r, a0, a1, color, width); c.pie(...); c.ring(...); c.star(...); c.regular(x, y, r, n)
c.blob(x, y, r, color, t=t, seed=k); c.smooth_poly(pts, color, tension=0.5, closed=True)
c.glow(x, y, r, color, alpha, sigma); c.soft_shadow(x, y, w, h, r, alpha, sigma, dy)
c.text(s, x, y, font, color, align='left|center|right', baseline='alphabetic|middle|top|cap|bottom', alpha, spacing, stroke)
c.text_lines(lines, x, y, font, color, align, leading); c.text_fit(s, x, y, role, size, max_width, ...); c.text_width(s, font)
c.linear(x0, y0, x1, y1, [(pos, color), ...]) / c.radial(x, y, r, stops) / c.sweep(...) / c.noise(freq, octaves, seed)  -> shader
with c.layer(alpha, blend, blur): ...     # Gruppen (teuer, sparsam)
with c.tf(x, y, rot, sx, sy, px, py): ... # Verschieben/Drehen/Skalieren um (px, py)
with c.clip_rect(x, y, w, h, r): ... / c.clip_circle / c.clip_path / c.clip_poly
c.grain(amount); c.vignette(strength); c.spotlight(x, y, r, color, alpha)
```
Farben: `'#RRGGBB'`, `'#RRGGBBAA'`, `(r, g, b[, a])` 0..1. Blend: `'add' | 'screen' | 'multiply' | 'overlay' | 'soft' | 'lighten' | 'darken'`.
Schriften: `fonts.font('display'|'number'|'body'|'caption'|'mono'|'serif'|'hand', size, weight=200..800)`; `fonts.wrap(text, role, size, max_w)`.
Bewegung: `anim.tween(t, t0, dur, 'out_cubic')`, `anim.appear(t, t_in, t_out)`, `anim.pop(t, t0)`, `anim.spring(t, t0)`, `anim.osc(t, f)`, `anim.wobble(t, f, amp, seed)`, `anim.shake(t, t0)`, `anim.count_value(t, t0, dur, a, b)`, `anim.Keyframes([(t, v), ...]).at(t)`, `anim.stagger(i, n, t, t0)`.

## Timeline

`comp.tl`: `tl.lines` (Line: id, text, kind, rank, words, t0, t1, gap_after, meta), `tl.words` (Word: w, t0, t1, line, clean), `tl.at('syrup')`, `tl.at('syrup$+0.1')`, `tl.at('E5.1:18')`, `tl.find(anchor)`, `tl.lines_of(kind, rank)`, `tl.entry_span(rank)`, `tl.span('hook')`, `tl.voice_end()`.
`comp.scenes`: Scene(id 'hook'|'E5'|...|'outro', kind, t0, t1, rank, entry (Skript-Eintrag), visual (dict), trans_in, trans_dur, lines). Übergang in eine Szene beginnt bei `sc.t0` und dauert `sc.trans_dur`; das erste Wort der Szene fällt etwa auf `sc.t0 + trans_dur/2`.

## Themen (theme.py)  — zu bauen

```python
THEMES = {'curious': {...}, 'heist': {...}, 'cave': {...}, 'animal': {...}, 'history': {...}, 'space': {...}, 'ocean': {...}, 'medical': {...}, ...}
class Theme(dict):  # Schlüssel: bg0, bg1 (Verlauf oben/unten), bg2 (Akzentfläche), ink, ink_soft, accent, accent2, glow, card, card_ink, danger, ok, line, caption_bg, caption_ink, caption_hi
def get(name) -> Theme        # unbekannt -> 'curious'
def names() -> list
def sheet(out_path) -> str    # Farbbogen
```

## Maskottchen (mascot.py)  — zu bauen

```python
POSES = ['idle', 'point', 'think', 'shock', 'sneak', 'laugh', 'wink', 'facepalm', 'cheer', 'peek', 'run', 'hide', ...]
EXPRS = ['neutral', 'smile', 'smirk', 'surprised', 'worried', 'angry', 'sleepy', 'sly']
COSTUMES = ['default', 'thief', 'miner', 'explorer', 'doctor', 'astronaut', 'diver', 'historian', 'detective', 'chef', ...]
def draw(c, x, y, size, t=0.0, pose='idle', expr=None, costume='default', look=(0.0, 0.0), flip=False, theme=None, alpha=1.0, rot=0.0, k=1.0, **kw)
    # (x, y) = Bodenmittelpunkt, size = Körperhöhe in px. look = Blickrichtung (-1..1, -1..1). k = Einblendung 0..1 (für Pop).
    # t treibt Atmen, Blinzeln, Schwanzwedeln, Pose-Loops. Posen sind Zeit-Schleifen, kein Zustand.
def sheet(out_path) -> str   # Posen x Kostüme Bogen
```

## Piktogramme (props.py)  — zu bauen

```python
def draw(c, name, x, y, size, t=0.0, theme=None, alpha=1.0, rot=0.0, k=1.0, **kw)   # (x, y) Mitte, size = größte Ausdehnung
def names() -> list; def has(name) -> bool; def sheet(out_path) -> str
```
Jedes Piktogramm flach, 2–4 Farben aus dem Thema (theme['accent'], ['ink'], ['bg2'], ...), mit kleiner Eigenbewegung über t (schweben, funkeln, drehen).

## Kulissen (backdrops.py)  — zu bauen

```python
def draw(c, name, fmt, t=0.0, theme=None, **kw)   # ganzflächig, 200 px über die Ränder hinaus
def names() -> list
```

## Karten (cards.py)  — zu bauen

```python
def number_card(c, fmt, rank, t, t0, theme, total=5, k_out=1.0)   # Countdown-Karte mit Einflug ab t0
def title_plate(c, fmt, title, t, t0, theme, k_out=1.0)
def stat_plate(c, fmt, value, label, t, t0, theme, count=True)    # Zahl zählt hoch, wenn count
def meta_tag(c, fmt, place, year, t, t0, theme)
def series_label(c, fmt, text, theme, alpha=1.0)
def progress(c, fmt, rank, total, t, theme)
def watermark(c, fmt, cfg, theme, alpha=0.62)
def hook_title(c, fmt, text, t, t0, theme)
def keyword(c, fmt, text, t, t0, t1, theme, y=None)
```

## Untertitel (captions.py)  — zu bauen

```python
def draw(c, fmt, tl, t, theme, cfg=None)   # aktuelle Wortgruppe (3–5 Wörter), aktives Wort hervorgehoben, Plakette, nie unter y=1590
```

## Effekte (fx.py)  — zu bauen

```python
def particles(c, fmt, t, kind='dust', theme=None, seed=0, n=40, alpha=0.6, area=None)   # dust, confetti, sparks, bubbles, snow, embers, stars
def light_rays(c, x, y, t, theme, n=7, length=900, alpha=0.18)
def speed_lines(c, fmt, t, k, theme)
def shockwave(c, x, y, t, t0, theme, r_max=600)
def flash(c, fmt, t, t0, color='#FFFFFF', dur=0.25)
def transition(c, fmt, kind, k, theme, draw_old, draw_new)   # kind: wipe, slide, iris, zoom, flip, fade, cut; k 0..1; draw_* sind Callbacks(c)
```

## Szenen (scenes.py)  — zu bauen (Platzhalter vorhanden)

`SceneRenderer(comp).draw(c, t)`: Kulisse (nach Thema/visual.backdrop) -> Szene nach `kind` -> Übergang zur Vorszene -> Karten -> Untertitel -> Wasserzeichen -> Korn/Vignette.
`visual` im Skript (hook/entry/outro):
```json
{"backdrop": "vault", "transition": "wipe",
 "props": ["barrel", {"name": "money", "x": 0.72, "y": 0.55, "size": 240, "at": "18", "anim": "pop"}],
 "mascot": {"pose": "sneak", "costume": "thief", "expr": "sly", "x": 0.3, "y": 0.78, "size": 420, "at": 0.4},
 "keywords": [{"text": "$18 MILLION", "at": "18"}],
 "beats": [{"at": "water", "props": ["water_drop"], "mascot": {"pose": "shock"}}]}
```
x, y als Anteile der Bühne (`fmt.stage`), `at` = Anker (Wort oder Sekunden ab Szenenbeginn). Fehlt eine Angabe, wählt die Vorlage einen sinnvollen Platz (Maskottchen unten links, Piktogramme rechts oben, nie in `fmt.buttons`).

## Ton

- `audio/synth.py`: `sine, saw, square, tri, noise(kind)`, `adsr`, `lowpass/highpass/bandpass`, `delay`, `reverb`, `chorus`, `drive`, `pan`, `mix`, `normalize`, `fade`, `db`. Alle Signale float32, SR=48000, Mono (n,) oder Stereo (n, 2).
- `audio/sfx.py`: `SOUNDS = {id: fn}`; `render(id) -> stereo`, `catalog() -> [{'id', 'use', 'dur'}]`, `render_all(out_dir)`. Pflicht-IDs (compose.cues): `hook_hit, card_whoosh, card_hit, number_one, stat_pop, outro_chime, end_sting`, dazu der Vorrat aus STIL.md.
- `audio/music.py`: `BEDS = {id: {...}}`; `pick(theme) -> id`; `render(bed_id, duration, seed=0, sections=None) -> stereo`; `render_all(out_dir, seconds)`. `sections` = Liste `[{'t0', 't1', 'kind', 'energy'}]` aus den Szenen: beim Nummernwechsel ein Akzent, im Outro Auflösung.
- `audio/mix.py`: `build(project_dir, cfg, root, music=None) -> dict` liest voice.wav, plan.json (cues) und Szenen, legt Musik (Ducking unter der Stimme, `mix.music_db`), Töne (`db` je Cue), mastert auf `mix.master_lufs`, True Peak < `mix.true_peak_db`, schreibt `mix.wav` (Länge = Videodauer) und gibt Messwerte zurück. Maskierung: Töne auf Wörtern höchstens -6 dB.

## Befehle (cli.py)

`status, new, projects, words, plan, tts, voices, voice, mix, render, stills, sheet, seq, check, phone, sounds, music, mascot, props, palette, brand, loudness`.

## Regeln für alle Module

- Python 3.10-kompatibel (kein `match`, keine `tomllib`), nur numpy/scipy/skia/PIL/cv2/requests.
- Zeichnen ohne Nebenwirkungen; teure Vorberechnungen (Noise-Texturen, Partikelpositionen) deterministisch aus `seed` beim ersten Aufruf cachen (modulweit, read-only).
- Keine Figur, kein Logo, keine Marke kopieren. Keine Bitmaps im Repo außer den generierten Bögen.
- Jede Funktion mit Docstring auf Deutsch; Bezeichner Englisch.
- Tests: `tests/test_<modul>.py` mit pytest, schnell (< 10 s je Datei), rendern kleine Bilder.
