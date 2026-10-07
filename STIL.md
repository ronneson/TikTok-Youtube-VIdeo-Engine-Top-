# STIL.md — ODD CABINET · „Peel & Pop“

Endgültiges Designsystem des Kanals (Jury-Finale, 2026-10-07). Gewinnerkonzept „Peel & Pop“ (Sticker-Wunderkammer der Elster **Odd**), ergänzt um die von der Jury empfohlenen Einzelideen der anderen Konzepte, soweit sie zum Sticker-Look passen. Alle Werte gelten für das Hochformat 1080 × 1920 bei 30 fps; Querformat-Werte stehen jeweils dabei (Schriftfaktor `fmt.scale` = 0.78). Alles ist aus Code zeichenbar (skia-python), alle Töne sind prozedural (numpy), alle Farben kommen aus `engine/theme.py`.

---

## 0. Entscheidungen des Creative Directors

**Übernommen aus den anderen Konzepten (Jury-Empfehlungen):**

| Idee | Herkunft | So kommt sie in „Peel & Pop“ |
|---|---|---|
| Stempel-Ritual („VERIFIED ODD“, „NEVER FOUND“, „FAKE“) | cabinet-of-curiosities | Stempel-Sticker in Koralle mit Multiply-Korn, Scale 1.6 → 1.0 in 120 ms, Ton `stamp`; für Pointen, max. 1 je Eintrag |
| Archivnummer je Video („EXHIBIT 0042“) | cabinet-of-curiosities | Serienetikett `CURIOUS HEISTS · 017`, DM Mono; die Nummer zählt kanalweit hoch (Kommentar-Haken „No. 017“) |
| Karteikarten-Flip ECHT/FAKE | cabinet-of-curiosities | Prop `flip_card`: Sticker klappt (Scale-X 1 → 0 → 1, 260 ms) von „APPROVED“ auf „FAKE“, Ton `page_flip` + `stamp` |
| Dreiton-Audiologo | cabinet-of-curiosities | Eigenes Motiv **„Odd-Ding“** = Stufen 1–5–8 der Rang-Leiter (kurz, kurz, lang), nur in `outro_chime` und `end_sting` |
| Rang-Leiter diatonisch statt chromatisch, auf die Tonart des Betts transponiert | flat-editorial, Jury 2 | Leiter 1–2–4–5–8 über dem Grundton des Musikbetts (modusfrei, in D: D5 E5 G5 A5 D6); `card_hit#5 … card_hit#1` |
| Energiestufen als additive Schichten | cabinet-of-curiosities | `sections.energy` 0.5 → 0.9 schaltet fünf Schichten je Bett zu (Schwellen 0.3 / 0.5 / 0.65 / 0.8 / 0.9) |
| Kostümregel „nie beide Augen bedecken, Schnabel immer sichtbar“ | cabinet-of-curiosities | Pflichtregel für alle Kostüme, Domino-Maske hat Augenschlitze |
| Zahl auf der Karte immer in `card_ink` | cabinet-of-curiosities | So bleibt es; nie Akzentfarbe als Ziffer |
| `mascot.sheet` in 120/240/420 px, Silhouetten-Test 120 px („vereinfachen, nicht verfeinern“) | flat-editorial, cabinet | Pflichttests vor jedem Merge (Abschnitt 11) |
| `theme.sheet` mit vier Pflicht-Kontrastpaaren und Messwert | cabinet-of-curiosities | `ink/bg0`, `accent/bg0`, `card_ink/card`, `caption_ink/caption_bg` je Thema |
| Kerzenmodus / respect_hush (Licht 60 %, 10 % wärmer, Musik −6 dB, 2 s Gag-Sperre) | flat-editorial, night-noir | In den Respekt-Modus eingebaut (Abschnitt 1.8) |
| Zählwerk-Rolle der Ziffer mit 12-ms-Ticks | flat-editorial | Karten-Variante B (#4, #2): Ziffer rollt in `clip_rect`, Ton `tick` −30 dB |
| „Plate wird dunkler, nie die Schrift kleiner“, Lesetempo ≤ 1 neues Element je 1.2 s, Schlagwort ≥ 1.5 s | flat-editorial | check.py-Regeln (Abschnitt 11) |
| Lichtinsel schwenkt mit dem Fokus | flat-editorial | Radiale Lichtinsel folgt dem Hero-Sticker, 400 ms `in_out_sine` |
| Fortschrittsleiste bleibt im Übergang sichtbar | night-noir | Album-Leiste liegt auf der UI-Ebene über dem Peel |
| Antizipation: Schatten 2 Frames vor dem Objekt | night-noir | Pop-In beginnt mit dem Schattenfleck (60 ms Vorlauf) |
| `keyword_slam` mit 20 ms Stille vor dem Schlag | night-noir | Töne `stamp` und `keyword_slam` |
| Helmlampe als echte Lichtquelle, die dem Blick folgt | night-noir, cabinet | Kostüm `miner`: Lichtkegel (additiv, alpha 0.25) folgt `look` |
| Vier-Augen-Prinzip (Zweitsignal für Mimik bei 140 px) | night-noir | Schwanzwinkel + Elfenbein-Brauen spiegeln jeden Ausdruck |
| Catchphrase als Sprechblase | night-noir | Odd sagt genau ein Wort: **„Odd.“** (max. 1× je Video, nie im Respekt-Modus) |
| Zwei-Pass-Weißrand statt Dilate-Filter | Jury 2 | Sticker-Rand als Union-Stroke (Abschnitt 1.2), Dilate nur Fallback |
| Kein Titelkarten-Bild zwischen Hook und #5 | Jury 3 | Hook → direkt #5; das Serienetikett erscheint im Hook (letzte 0.5 s) und bleibt |
| Hook-Headline ab Frame 1 lesbar | Jury 1 | Headline steht ohne Pop-In; nur Piktogramme und Odd poppen |
| Untertitel 60 px statt 56 px | Jury 3 | Outfit 700, 60 px |

**Aufgelöste Widersprüche:**

1. *Korn über alles vs. rein weißer Sticker-Rand* → Korn (0.045) liegt nur auf der Kulissenebene, Sticker- und UI-Ebene bleiben kornfrei; Vignette (0.28) zuletzt über alles.
2. *Eine Übergangsart je Video vs. Lieferung/Flip-Roll im Wechsel* → Der **Seitenwechsel ist immer Peel** (300 ms). Was wechselt, ist nur der **Einflug der Karte**: A „Elster-Lieferung“ (#5, #3, #1) / B „Zählwerk“ (#4, #2). Die Elster-Lieferung als Bildwechsel (Cut unter der Abdeckung) ist für `beats` innerhalb eines Eintrags reserviert. Hook → #5: Peel; Outro: Weichblende 400 ms; #1: Konfetti-Cut.
3. *Album-Leiste bei y 1520 kollidiert mit Untertiteln* → Album-Leiste wandert **nach oben rechts** (x 562–810, y 288–328) zwischen Serienetikett und Wasserzeichen; der Badge fliegt beim Wechsel nach oben in sein Fach (das war ohnehin die Bewegungsrichtung).
4. *Titel-Slot (y 660–880) vs. Maskottchen unten links* → Der Eintragstitel erscheint groß (72 px) nur in der Haltezeit unter der Karte und dockt dann als **einzeilige Kopfzeile** (52 px) bei y 668–744 an; Odd steht ab y 809.
5. *Zwei Ebenen vs. drei Ebenen mit Parallaxe* → Zwei Zeichenebenen (Kulisse in bg2-Silhouetten ohne Rand, Sticker mit Rand) plus Partikel; Parallaxe nur bei Push-In und Deck-Slide (Kulisse 0.3, Sticker 1.0, Partikel 1.3).
6. *Halbton-Punktraster* → gestrichen (Rechenzeit, Kompressionsartefakte).
7. *„Pica-Ding“* → heißt jetzt **Odd-Ding**; die Elster heißt endgültig Odd.
8. *Elfenbein auf Koralle* (2.8 : 1) ist verboten → Stempel-Text ist Koralle **mit weißem Rand** oder Tinte auf Koralle (5.4 : 1).

**Maskottchen-Name: Odd.** Vollständiges Etikett: „ODD · *Pica pica* · Exhibit No. 0“. **Kanalname-Favorit: ODD CABINET (@oddcabinet)**, Alternativen in Abschnitt 8 (der Nutzer entscheidet).

---

## 1. Animationsstil „Peel & Pop“

### 1.1 Grundbild und Prinzipien

Jede Szene ist eine Seite in einem edlen Sammelalbum. Alles Wichtige (Piktogramme, Odd, Nummernkarten, Schlagworte, Stempel) ist ein **Sticker**: dicke, abgerundete Flachform, weißer Rand, ein weicher Schatten, aufgeklebt auf einem ruhigen, leicht körnigen Hintergrund. Sticker **ploppen** auf, **kleben** und werden **abgezogen** (Peel). Energie entsteht aus Timing, nicht aus Bildlärm.

Sieben Regeln:
1. **Ein Gedanke pro Bild**: 1 Hero-Sticker + Odd + Badge + Untertitel (+ höchstens ein Schlagwort oder eine Stat-Plakette). Nie mehr als 6 Sticker je Frame.
2. **Ein Licht**: oben links, immer. Ein Schatten für alles: `dy 8, sigma 16, alpha 0.20`.
3. **Eine Radius-Skala**: 12 / 24 / 48 / 96 px. Absichtlich „gefährliche“ Formen (Zacken, Blitz, Stalaktit) dürfen 4 px.
4. **Keine Linien innen**: keine Outlines, keine Konturzeichnung; die einzige Linie ist der weiße Sticker-Rand außen.
5. **Nichts steht länger als 2 s still**, nichts zappelt: Atmen, Schweben, Funkeln als reine Funktionen von `t`.
6. **Regel der einen Bewegung**: höchstens eine große Bewegung je 0.5 s, alles andere ist Mikro.
7. **Zweit-Ton-Flat**: jede Fläche hat Grundfarbe, eine harte Schattenfläche (−12 %) und einen Glanzpunkt (+10 %); keine Verläufe in Stickern.

### 1.2 Formensprache und Sticker-Technik

- Primitive: Kreise, Ellipsen, Rechtecke mit Rundung, Bezier-Blobs (`c.blob`, `c.smooth_poly`), abgerundete Polygone (`rounded_poly_path`). Mindest-Strichstärke sichtbarer Elemente **14 px**, nichts Filigranes; Mindest-Primitivgröße 24 px.
- Silhouetten-Test: jedes Piktogramm muss als Einfarb-Silhouette bei **120 px** erkennbar sein. Fällt es durch, wird vereinfacht, nicht verfeinert.
- **Sticker-Rand** (Farbe `line` #FFFFFF): Piktogramme 10 px, Nummernkarte 12 px, Odd 14 px, Sticker-Text 8 px, Stempel 6 px, Mini-Badge (Album-Fach) 4 px. Im Querformat × 0.78, nie unter 4 px.
- **Zwei-Ton-Flat innerhalb eines Stickers**: Schattenfläche = Grundform, um 6 % der Objektgröße nach rechts unten versetzt und mit der Grundform geclippt, Farbe `color.darken(c, 0.12)`; Glanzpunkt = Ellipse 12 % × 7 % der Objektgröße oben links, `color.lighten(c, 0.10)`, Alpha 0.6–1.0 funkelnd bei 1.3 Hz. Keine Verläufe, kein Bevel.
- **Technik des Randes („Zwei-Pass-Weißrand“, Standard)**: jeder Sticker wird in drei Durchgängen gezeichnet, ohne Image-Filter:
  1. Schatten: `c.soft_shadow` der Hüllform (Rechteck/Ellipse, die das Prop meldet), dy 8, sigma 16, alpha 0.20.
  2. Rand: dieselbe Zeichenfunktion im Modus `rim` — jedes Primitiv wird in `line` gefüllt **und** mit Stroke 2·Rand gezeichnet (Union der Formen), Text mit `stroke` = 2·Rand in `line`.
  3. Farbe: die Zeichenfunktion normal.
  Dafür bekommen `props.draw`, `mascot.draw`, `cards.*` den Parameter `mode='color' | 'rim' | 'silhouette'` (silhouette = alles in einer Farbe, für Kulissen-Schatten und Album-Mini-Badges). Fallback für Blobs mit Shader: Offscreen-Layer + `skia.ImageFilters.Dilate(r, r)`.
- Sticker mit `alpha < 1` werden komplett in einem `c.layer(alpha)` gezeichnet (nicht Teil für Teil), sonst scheinen Ränder durch.
- Budget: ≤ 6 Sticker je Frame, ≤ 1 `layer` je Sticker, Kulisse ohne Layer.

### 1.3 Licht, Schatten, Texturen

- Hintergrund: vertikaler Verlauf `bg0` (oben) → `bg1` (unten), darüber eine **Lichtinsel** (`c.spotlight`, r 520, Farbe `glow`, alpha 0.10, add) auf dem Hero-Sticker; sie schwenkt beim Fokuswechsel in 400 ms (`in_out_sine`) mit.
- Kulissen-Elemente (Regale, Skyline, Stalaktiten) nur als Silhouetten in `bg2` (drei Helligkeitsstufen: `bg2`, `mix(bg2, bg1, 0.4)`, `mix(bg2, bg1, 0.7)`), **ohne Sticker-Rand** — so entsteht Tiefe mit zwei Ebenen.
- Korn: `c.grain(0.045)` nur auf der Kulissenebene (Luminanzrauschen, overlay). Vignette `0.28` zuletzt über alles.
- Glow nur additiv (`c.glow`, sigma 40–80, alpha ≤ 0.35): Lampen, Edelsteine, Album voll, #1.
- Kein Halbton, keine Scanlines, keine Stoff-/Holz-/Metalltexturen: Material entsteht aus Farbe (`wood`, `steel`).

### 1.4 Raster, Ebenen und Layout-Anker (Hochformat)

24-px-Raster, Außenrand 70 px (Text) / 60 px (Sticker). Nichts Wichtiges über y 260, unter y 1590, rechts von x 890 ab y 770 (`fmt.buttons`). Bühne `fmt.stage` = (60, 340, 960 × 1010).

Zeichenreihenfolge in `scenes.py`: Kulisse (+200 px Überhang, Push-In) → Korn → Lichtinsel → Sticker-Ebene (Hero, Begleiter, Odd, Schlagwort, Stat, Stempel; Push-In) → Partikel → Übergang → **UI-Ebene** (Badge, Album-Leiste, Kopfzeile, Meta-Pille, Serienetikett, Wasserzeichen, Untertitel; kein Push-In, kein Peel) → Vignette.

| Element | Anker (Bühnenanteile) | Pixel | Größe |
|---|---|---|---|
| Odd (Bodenmittelpunkt) | (0.28, 0.86) | (329, 1209) | size 400; Kopf oben 809, Schnabelspitze x 549, Schwanzspitze x 87 |
| Hero-Sticker | (0.69, 0.60) | (722, 946) | ≤ 300 px → x 572–872, y 796–1096 |
| Begleiter-Sticker | Hero-Ecke oben links, 25 % Überlappung | (600, 820) | ≤ 120 px |
| Sticker-Reihe (statt Hero) | im Hero-Feld x 560–884 | — | ≤ 2 × 150 px, Abstand 20 |
| Stat-Plakette | (0.76, 0.14) · zusammen mit Schlagwort (0.76, 0.10) | (790, 481) | ≤ 440 × 150 |
| Schlagwort-Sticker | (0.72, 0.22) · zusammen mit Stat (0.72, 0.26) | (751, 562) | ≤ 500 × 110 |
| Stempel | über dem Hero, −8° | (760, 880) | ≤ 420 × 110 |
| Große Nummernkarte (Haltezeit) | Bildmitte | (540, 860) | 560 × 560 |
| Titel in der Haltezeit | unter der Karte | y 1160 (oben) | 72 px, 1–2 Zeilen |
| Badge | `fmt.card` 70/350 300 × 300 | (220, 500) | 240 × 240 |
| Kopfzeile (Titel) + Meta-Pille | `fmt.title` → Rect(70, 664, 940, 84) | y 668–744 | Titel links ≤ 560 px, Pille rechtsbündig an x 1010, ≤ 360 px |
| Serienetikett | `fmt.label` 70/275 | (70, 310) | DM Mono 28, ≤ 22 Zeichen (≤ 480 px) |
| Album-Leiste | `fmt.progress` → Rect(560, 286, 250, 44) | Fächer x 562 / 614 / 666 / 718 / 770, y 288 | 5 × 40 px, Abstand 12 |
| Wasserzeichen | `fmt.watermark` → Rect(840, 275, 170, 90) | Kopf (925, 300), Handle y 352 | Kopf 44 px, DM Mono 24 |
| Untertitel | `fmt.caption` → Rect(90, 1356, 780, 180) | Mitte (480, 1446) | Plakette ≤ 780 × 174 |

Empfohlene Änderungen in `layout.py` (Hochformat): `title=Rect(70, 664, 940, 84)`, `progress=Rect(560, 286, 250, 44)`, `watermark=Rect(840, 275, 170, 90)`, `caption=Rect(90, 1356, 780, 180)`. Alle anderen Slots bleiben.

**Querformat** (1920 × 1080, Bühne 640/90 1200 × 820): Odd size 320 am Bodenpunkt (0.14, 0.92) → (808, 844); Hero (0.62, 0.56) → (1384, 549), ≤ 360 px; Stat/Schlagwort (0.84, 0.16) → (1648, 221); große Karte 460 × 460 in der Bühnenmitte (1240, 480); Badge 200 × 200 in `fmt.card` 100/140; Titel zweizeilig 56 px in `fmt.title` 100/420; Album-Leiste `progress` 100/1000 → 10 Fächer 32 px, Abstand 20 (Top 10); Untertitel Outfit 700 44 px, eine Zeile, Plakette ≤ 820 px bei y 880–1000.

### 1.5 Bewegung und Easing (Engine `anim.py`)

| Bewegung | Werte |
|---|---|
| **Pop-In** (jeder Sticker) | Scale 0 → 1.08 → 1.0, Rotation −6° → 0°, 320 ms, `out_back` s 1.70 = `anim.pop(t, t0, 0.32, overshoot=1.17)`; Odd s 2.2 = overshoot 1.22. **Antizipation**: der Schattenfleck erscheint 60 ms (2 Frames) vor der Form (alpha 0 → 0.20). Ton `pop_in` (max. 1 je 150 ms, sonst −6 dB gestapelt). |
| **Pop-Out** | Scale 1 → 0.9 → 0, Rotation +15°, 160 ms `in_cubic`; nie Fade. Ton `pop_out`. |
| **Landen / Squash** | beim Aufsetzen 90 ms `sy 0.92`, `sx = 1/sqrt(sy) = 1.04`, dann 160 ms Feder zurück: `anim.spring(t, t0, stiffness=324, damping=19.8)` (ω 18 rad/s, ζ 0.55). Ton `hop` (Odd) oder Squash-Teil von `card_hit`. |
| **Squash-&-Stretch-Grenzen** | Piktogramme ±12 %, Odd ±20 %, Nummernkarte ±8 %, Text 0 % (Text wird nur skaliert/gedreht, nie verzerrt). Volumenregel immer `sx = 1/sqrt(sy)`. |
| **Slide / Settle** | `out_quint`, 280–420 ms; UI-Mikrobewegungen 120–160 ms. |
| **Kamera** | Push-In 1.00 → 1.03 linear über die Eintragsdauer, Drehpunkt = Hero (Kulisse 0.3-fach, Sticker 1.0, Partikel 1.3); **Snap-Zoom** 1.00 → 1.06 in 90 ms bei Enthüllungen, Rückfederung 240 ms `out_cubic`. Nie kontinuierlich zoomen, nie rotieren. |
| **Stagger** | zusammengehörige Sticker 70 ms, Wörter 45 ms (`anim.stagger`), nie gleichzeitig. |
| **Smear** | schnelle Objekte (Odd im Flug, Karte beim Einwurf) werden 2 Frames um bis zu 1.4× entlang des Bewegungsvektors gestreckt (`c.tf(rot=Winkel, sx=1.4)`); kein Gauß-Motion-Blur. |
| **Idle-Loops** | Atmen Scale 1 ± 1.5 % bei 0.4 Hz; Schweben y ± 4 px bei 0.5 Hz; Funkeln Glanzpunkt-Alpha 0.6–1.0 bei 1.3 Hz; Wippen ± 3° bei 0.3 Hz. Jedes Prop genau **eine** Eigenbewegung. Phase aus `seed`. |
| **Shake** | nur Schock: 1× ≤ 200 ms, Amplitude ≤ 8 px (`anim.shake(t, t0, 0.2, 8)`). |
| **Zählwerk** | Stat-Werte zählen 0.8 s `out_quart` (`anim.count_value`), letzte Ziffer Pop 1.15 für 100 ms. |
| **Musikraster** | Schnitte und Pops liegen auf Achteln des Betts; v1 ohne Quantisierung, v2 `music.grid(bed, t)` verschiebt Pops um ≤ 130 ms auf das nächste Achtel. |
| **Lesetempo** | höchstens alle 1.2 s ein neues Bildelement; Schlagworte erscheinen auf dem gesprochenen Wort (`at`) und stehen ≥ 1.5 s. |

**Partikel** (`fx.py`): Konfetti nur aus 3 Formen (Kreis r 10–16, abgerundetes Quadrat 18–26, abgerundetes Dreieck 22), Farben nur `accent`, `accent2`, `glow`, `line`; 24 Stück bei der Nummernkarte, 60–80 bei #1 und Pointe; Gravitation 1800 px/s², Luftwiderstand 0.92/Frame, Drehung 90–360°/s, Verschwinden durch Scale → 0 in 200 ms (nie Fade). Konfetti ist ein Ereignis, nie Dauerzustand. Staub/Blasen/Sterne (`fx.particles`) dürfen dauerhaft laufen: ≤ 40 Teilchen, alpha ≤ 0.5.

### 1.6 Übergänge (`fx.transition`, alle ≤ 400 ms außer Respekt-Fade)

1. **Peel** (`kind='peel'`, Standard zwischen Einträgen, 300 ms, `in_out_cubic`): Die alte Seite (Kulisse + Sticker, ohne UI) hebt sich und wird nach oben abgezogen: `c.tf(y = −e·(H+300), rot = −4°·sin(π·e), px = W/2, py = 0)`; unter ihrer Unterkante ein Schattenband (Tinte, alpha 0.35·(1−e), sigma 30); die neue Seite liegt fertig darunter und hellt von 20 % Abdunklung auf. v2 mit Scherung (Skew-Erweiterung von `c.tf` über `skia.Matrix`), v1 ohne. Töne `card_whoosh` + `peel`.
2. **Sticker-Iris** (`kind='iris_sticker'`, 360 ms, `out_back` s 1.7): abgerundete Sticker-Maske (Radius 96, Rand 12 px in `line`) wächst aus dem Fokuspunkt; für Hook-Enthüllungen und Karten-Variante B.
3. **Elster-Lieferung** (Bildwechsel in `beats`, 420 ms = 13 Frames): Odd fliegt in Pose `fly` von links nach rechts (y 0.45 der Bühne, Smear ab Frame 4), die Szene dahinter wechselt per Cut in Frame 6. Ton `flap`.
4. **Deck-Slide** (`kind='deck'`, 320 ms, `out_quint`): neue Kulisse schiebt sich von unten unter die alte; die alte skaliert auf 0.96 und dunkelt 20 % ab. Für Ortswechsel innerhalb eines Eintrags ohne Odd.
5. **Konfetti-Cut** (#1 und Pointe): harter Schnitt + 40 Konfetti + `fx.flash(alpha 0.35, 120 ms)`. Töne `flash`, `confetti`.
6. **Respekt-Fade** (600 ms, `in_out_sine`): Weichblende, Partikel aus; nur bei Todesfällen.

Hook → #5: Peel. Outro: Weichblende 400 ms. Nie `zoom`, nie `blinds`, nie zwei Übergangsarten hintereinander.

### 1.7 Wie „clean“ entsteht

- Gleiche Lichtrichtung, gleicher Schatten, gleiche Randbreiten, gleiche Radius-Skala über alle Module: das ist 80 % des Edel-Eindrucks.
- Hintergrund immer ruhig: zwei Töne + Lichtinsel + Korn; Kulissen-Silhouetten nur in `bg2`-Stufen.
- Farben gedämpft (nie 100 % Sättigung), ≤ 5 Farbtöne je Bild; Freiraum um den Hero ≥ 60 px zu anderen Stickern, ≥ 120 px zu Text.
- Text nie gestreckt, nie mehr als zwei Schriftfamilien im Bild (Mono als Etikett zählt nicht), Versalien nur für Etiketten/Schlagworte/Stempel.
- Untertitel immer auf Plakette, links der Knopfleiste.
- 30 fps genügen mit Smear und Squash; 60 fps optional für Shorts.

### 1.8 Respekt-Modus (Todesfälle; Skript: `"respect": true` am Eintrag oder `beat`)

- Farben: `bg0/bg1/bg2` mit `color.saturate(c, 0.7)`, `accent` → Elfenbein, `accent2` → `ink_soft`, `glow` aus; Lichtinsel wird Kerzenlicht `candle` #FFD8A0, alpha 0.18, 10 % wärmer, Helligkeit der Insel auf 60 %.
- Kein Konfetti, kein Boing, kein Stempel, kein Snap-Zoom, keine Sprechblase; Übergang Respekt-Fade; Album-Fach füllt sich Elfenbein statt Gold, ohne Funkeln.
- Odd: Pose `bow` (Hut ab, im Flügel gehalten) ≥ 1.5 s ab der Nennung, danach `idle` mit `lid_top 0.3`; **Gag-Sperre 2 s** (keine Posen laugh/shock/wink).
- Props: `ghost_halo`, `candle`, `closed_label` („EXHIBIT CLOSED“-Sticker), leerer Stuhl; nie `skull_friendly`, nie Blut, nie Leichen. Text sagt „didn't make it“ statt Details.
- Ton: `respect_hush` (−18 dB), Musik duckt zusätzlich 6 dB für 2.5 s; Bett `parlour_waltz` in der Respekt-Variante (Energy 0.2, nur Spieluhr + Pad, Hall 1.4 s) oder das laufende Bett mit Schlagwerk stumm (`sections.energy 0.2`).
- Untertitel: aktives Wort Elfenbein, keine Scale-Pops. Humor liegt im Umstand, nie in der Person.

### 1.9 Negativliste — was wir nie tun

- Keine schwarzen Outlines, keine Doodle-/Handlinien, keine Verläufe oder Glanz-Verläufe innerhalb von Stickern, kein Bevel, keine 3D-Extrusion.
- Kein Fotorealismus, keine Bitmaps, keine KI-Bilder, kein Lens-Flare, keine Lichtstrahlen-Dauerschleife, kein Wackel-Kamera-Shake außer 1× ≤ 200 ms bei Schock.
- Kein Blut, keine Gore, keine Leichen; Tod immer abstrakt (Halo, Kerze, leerer Stuhl, „EXHIBIT CLOSED“).
- Kein Dauerkonfetti, keine Partikel ohne Anlass, kein Blinken schneller als 3 Hz, kein Stroboskop.
- Keine Verzerrung von Text, kein Fließtext in Versalien, keine Emojis, nie mehr als 2 Schriftfamilien pro Bild, kein Text unter 26 px, kein Text in den TikTok-Zonen.
- Keine Primärfarben in Vollsättigung, kein Regenbogen in einem Bild, nie mehr als 5 Farbtöne, kein reines Weiß als Fläche (Weiß gehört dem Rand).
- Keine Übergänge über 400 ms (außer Respekt-Fade), kein Zoom-Übergang, keine Blinds, keine sich drehenden Logos.
- Keine Begrüßung im Hook, kein „In diesem Video…“, keine Pfeile auf den Follow-Button, keine Titelkarte vor #5.
- Keine fremden Figuren, Marken, Flaggen; Länder nur als Kreis-Chip mit Kürzel (`country_chip`).
- Keine Meme-Sounds, kein Vine-Boom, keine Lachspur, kein Trap-808, kein Kino-Riser als Dauerzustand.

---

## 2. Maskottchen: Odd, die Elster

**Name:** Odd (endgültig). Etikett: „ODD · *Pica pica* · Exhibit No. 0“. **Rolle:** Kuratorin des Odd Cabinet, die alles Glänzende und Seltsame einsammelt und in Nummernkarten sortiert. **Code:** `mascot 'odd'`.

**Persönlichkeit:** neugierig bis zur Grenze des Anstands, hochintelligent, leicht diebisch, charmant-frech; staunt lieber, als zu urteilen. Makabrer Humor nur über Umstände, nie über Opfer: bei Todesfällen nimmt sie den Hut ab. Energie: schnell, zappelig, aber mit „Tuxedo-Haltung“, wie eine Museumsführerin, die nachts selbst ins Depot einbricht. Sie spricht nicht (die Stimme ist der Erzähler), sagt aber genau ein Wort als Sprechblase: **„Odd.“**

**Warum eine Elster für kuriose Top-Listen:** 1) Elstern sammeln Kuriositäten: Odd ist die Wunderkammer in Vogelform. 2) Smoking von Natur aus (schwarz/weiß): edel statt kindisch, farbneutral zu jeder Themenpalette; nur Kostüm und Flügelschimmer tragen Farbe. 3) Diebin und Problemlöserin: perfekt für Heists, Höhlen, Tiere (eines der klügsten Tiere), Geschichte (Zählreim „One for sorrow, two for joy…“, ein eingebauter Countdown). 4) Flug = kostenloser Übergang, Schnabel = Greifwerkzeug für Karten, Schwanz = Stimmungsnadel. 5) Keine bekannte Marke besetzt eine geometrische Elster; kein Bärtierchen, kein Glaskopffisch.

### 2.1 Konstruktion (24 Primitive, Einheit = Körperhöhe `size`; Boden = (0, 0), y nach oben negativ; Zeichenreihenfolge = Nummer; 3/4-Ansicht nach rechts, `flip` spiegelt)

| # | Teil | Form | Maße / Position | Farbe |
|---|---|---|---|---|
| 1 | Schwanz | rrect 0.40 × 0.10, r 0.05 | Drehpunkt (−0.26, −0.44), Winkel −30° Standard, Bereich −45° … +30° | `mascot_main` |
| 2 | Schwanzspitze | Ellipse 0.07 × 0.05 | am Schwanzende (lokal −0.36, 0) | `mascot_sheen` |
| 3 | Flügel fern | Tropfen 0.40 × 0.22 | Drehpunkt (−0.04, −0.60); nur in cheer / fly / run / shock sichtbar | `mascot_dark` |
| 4–5 | Beine | Rundlinien Breite 0.022 | (±0.09, −0.19) → (±0.10, 0); Länge × `leg_len` | `mascot_beak` |
| 6–7 | Füße | Polylinie „V“ (3 Zehen) | (±0.16, 0) – (±0.10, −0.03) – (±0.04, 0) | `mascot_beak` |
| 8 | Körper | Ellipse rx 0.31, ry 0.25, −10° | Mitte (0, −0.42); Squash-Träger | `mascot_main` |
| 9 | Bauch | Ellipse rx 0.20, ry 0.17 | Mitte (+0.06, −0.36), auf Körper geclippt | `mascot_light` |
| 10 | Kragen | Mondsichel (Kreis r 0.17 bei (0.10, −0.58) minus Kreis r 0.17 bei (0.16, −0.63)) | Smoking-Kragen, auf Körper geclippt | `mascot_light` |
| 11 | Flügel nah | Tropfen (`smooth_poly`, 5 Punkte) 0.42 × 0.24 | Drehpunkt (−0.06, −0.58), Winkel −10° Standard, −120° (hoch) … +25° (hängend); Spitze = Anker `hand` | `mascot_main` |
| 12 | Flügelband | rrect 0.22 × 0.07 | lokal (0.14, 0.02) auf dem Flügel, geclippt | `mascot_light` |
| 13 | Flügelschimmer | Ellipse 0.07 × 0.04 | lokal (0.26, −0.03), geclippt; funkelt 0.6–1.0 bei 1.3 Hz | `mascot_sheen` |
| 14 | Kopf | Kreis r 0.24 | Mitte (+0.14, −0.76); Scheitel bei −1.00; `head_tilt` ±15° um den Halspunkt (0.08, −0.56) | `mascot_main` |
| 15 | Wange | Ellipse 0.045 × 0.025 | (+0.26, −0.70), alpha 0 … 0.4 | `danger` |
| 16 | Schnabel unten | abgerundetes Dreieck (r 0.015), Länge 0.17, Höhe 0.05 | Drehpunkt (+0.35, −0.77), rotiert um `beak_open` 0 … 35° | `mascot_dark` |
| 17 | Zunge | Halbkreis r 0.035 | im Unterschnabel, sichtbar ab `beak_open` > 20° | `danger` |
| 18 | Schnabel oben | abgerundetes Dreieck (r 0.02), Länge 0.20, Höhe 0.065 | gleicher Drehpunkt, `beak_top_rot` −6° … 0° (Lächeln); Spitze = Anker `beak_tip` (0.55, −0.77) | `mascot_beak` |
| 19 | Augenweiß | Kreis r 0.07 | nahes Auge (+0.24, −0.80); fernes Auge (+0.07, −0.80), r 0.06, alpha = `head_turn` (0 = 3/4, 1 = frontal); `eye_scale` 1.0 … 1.15 | `line` |
| 20 | Pupille + Glanz | Kreis r 0.033 (× `pupil` 0.7 … 1.4), Glanzpunkt r 0.011 oben links | Versatz `look · 0.042` (60 % des Augenradius) | `mascot_dark` / `line` |
| 21 | Oberlid | Halbscheibe in Kopffarbe | `lid_top` 0 … 1 deckt von oben | `mascot_main` |
| 22 | Unterlid | Halbscheibe | `lid_bottom` 0 … 0.5 (fröhliches Kneifen) | `mascot_main` |
| 23 | Braue | rrect 0.12 × 0.03 | 0.11 über dem Auge, Winkel −25° … +25°, je Seite (`brow_l` nah, `brow_r` fern) | `mascot_light` (alpha 0.9) |
| 24 | Scheitelfedern | 3 abgerundete Dreiecke 0.06 | am Scheitel, nur in `shock` (Pop-In 200 ms, Pop-Out 300 ms) | `mascot_main` |

Dazu: Sticker-Rand 14 px um die Gesamtsilhouette (Kostüm eingeschlossen) und Schatten (dy 8, sigma 16, alpha 0.20); Bodenschatten `fx.floor_shadow` alpha 0.25. Die Brauen sind bewusst Elfenbein (auf dem dunklen Kopf wäre eine dunkle Braue unsichtbar); sie sind, mit dem Schwanz, das **Zweitsignal** der Mimik.

**Proportionen:** Kopf : Körper = 1 : 1.3; Auge = 29 % des Kopfdurchmessers; Schnabel = 83 % des Kopfradius; Schwanz = 65 % der Körperlänge; Beine 19 % der Gesamthöhe (hüpfend, nie stelzend). Körperneigung −25° … +25°, Kopfneigung ±15°, `head_turn` −1 … 1 verschiebt Schnabel und Augen um bis zu −0.12 in x und blendet das zweite Auge ein. Standardgröße 400 px (Hochformat), 320 px (Querformat), Minimum 140 px (ohne Glanzpunkt und Wange), Wasserzeichen 44 px (nur Kopf). Breite in Ruhe ≈ 1.16 × size (Schwanz −30° bis Schnabelspitze).

Anker für Kostüme: `hat` (0.14, −1.00), `face` (0.24, −0.80), `neck` (0.08, −0.56), `hand` (Flügelspitze), `back` (−0.20, −0.50), `beak_tip` (0.55, −0.77).

### 2.2 Augen-/Mund-System („Drei-Hebel-Mimik“ + Schwanz)

Jede Emotion ist ein Satz aus drei Hebeln: (a) Lider `lid_top` / `lid_bottom`, (b) Brauenwinkel `brow_l` / `brow_r`, (c) Schnabelöffnung `beak_open` 0 … 35° (plus `beak_top_rot` für das Lächeln). Vierte Nadel: Schwanzwinkel (oben = Freude/Erregung, unten = Trauer/Respekt). Blick `look = (dx, dy) ∈ [−1, 1]²`, Pupillengröße 0.7 (Schreck) … 1.4 (Staunen). Blinzeln: Schließen 120 ms, Öffnen 90 ms, Abstand 2.5 + 2.5·hash(seed, i) s, doppelt bei `think`/`worried`; Ton `blink` nur in Sprechpausen.

| Ausdruck | lid_top | lid_bottom | brow_l / brow_r | beak_open / top_rot | pupil | Extras |
|---|---|---|---|---|---|---|
| neutral | 0 | 0 | 0 / 0 | 0 / 0 | 1.0 | Schwanz −30° |
| smile | 0 | 0.15 | +8 / +8 | 4 / −6 | 1.1 | Wange 0.3, Schwanz −10° |
| smirk | 0.35 | 0 | +18 / −4 | 6 / −4 | 1.0 | Wange 0.2 |
| surprised | 0 | 0 | +25 / +25 | 30 / 0 | 0.8 | eye_scale 1.15, Schwanz +20° |
| worried | 0.2 | 0 | +20 / −12 | 8 / 0 | 1.0 | look (0.2, −0.5), Schwanz −40° |
| angry | 0.4 | 0 | −25 / −25 | 0 / 0 | 0.9 | Schwanz +10° |
| sleepy | 0.65 | 0.1 | 0 / 0 | 2 / 0 | 1.1 | Schwanz −40° |
| sly | 0.5 | 0 | −10 / −10 | 6 / −4 | 1.0 | look (0.8, 0), Wange 0.2 |

Mundformen: `closed`, `smile` (Oberschnabel −6°, Unterschnabel 4°, Wange an), `talk` (Öffnung folgt Sprachamplitude 0–18°, nur wenn Odd „spricht“), `gasp` (35°, Zunge), `grin` (12°, Unterlid 0.4), `smirk` (asymmetrisch).

### 2.3 Acht Posen (Engine-Namen; Zeitschleifen über `t`, kein Zustand)

1. **idle** — Neugier: Kopf 12° + `wobble(t, 0.3, 1.5°)`, Pupille 1.2, Schwanz −30° + 6°·`osc(t, 0.5)`, Atmen Scale 1 ± 1.5 % bei 0.4 Hz, Blick zum Hero (0.6, 0.1), jede dritte 1.8-s-Phase zur Kamera.
2. **point** — Präsentieren: Flügel −70° mit zwei Nachfedern (`spring(t, t0, 400, 12)`), Braue +15°, `smile`, Körper 6° zum Ziel, Gewicht auf einem Bein (`leg_len_r` 0.95), Blick zum Ziel.
3. **think** — Skeptisch: `brow_l` −12°, `brow_r` +18°, `lid_top` 0.45, Schnabel zu, Kopf −8°, Flügelspitze am Schnabel (−95°), Schwanz tickt 1 Hz (± 8°), Doppelblinzeln; optional `question`-Sticker über dem Kopf.
4. **shock** — Kinnlade: Schnabel 35°, Pupillen 0.7, `eye_scale` 1.15, Brauen +25°, Körper `sy` Keyframes [(0, 1.0), (0.06, 0.85), (0.18, 1.18), (0.34, 1.0)] `out_back`, Scheitelfedern ploppen ab, Schwanz +30°, Shake 8 px / 200 ms, Ton `gasp`.
5. **laugh** — Kichern: `lid_bottom` 0.4, Schnabel 10° + 4°·|`osc(t, 8)`|, Flügel vor dem Schnabel (−80°), Körper ± 2° bei 8 Hz, Wange 0.4, Schwanz +20°, Hüpfen 2 % bei 4 Hz, Ton `giggle`.
6. **sneak** — Dieb: Körper 20° nach vorn, `lid_top` 0.5, Beine 1.2× (Zehenspitzen), Schritt-Loop 1.6 Hz (Hub 3 %), Blick seitlich (0.9, 0), glänzendes Objekt an `beak_tip`, `sneak_trail` (gestrichelt, alpha 0.35), `hop` je Schritt (−14 dB).
7. **peek** — Hook-Auftritt: nur Kopf, Schnabel, Augen, Brauen und ein Flügel lugen vom unteren oder linken Bühnenrand herein (an der Kante geclippt), Pop-In s 2.2, Pupillen 1.4, Brauen +20°, Blick zur Kamera.
8. **bow** — Respekt: Flügel angelegt (+25°), Kopf −15°, `lid_top` 0.6, Schwanz −45°, Hut (falls Kostüm) im Flügel, nur Atmen 0.25 Hz, Haltezeit ≥ 1.5 s.

Weitere Presets: **cheer** (beide Flügel −120°, Hüpfen 5 % bei 2 Hz, Schnabel 12°, Konfetti erlaubt), **facepalm** (Flügel −100° über dem nahen Auge, Kopf −10°, `lid_top` 0.6, Ton `hmm`), **wink** (nahes Lid 1.0 für 300 ms, `smirk`, Kopf 8°), **fly/run** (Flügel −60° ± 50°·sin(2π·6t), Beine angelegt, Körper 15°, Smear, Ton `flap`), **hide** (hinter Prop/Karte, nur Augen, Brauen und Schwanzspitze sichtbar).

### 2.4 Kostüm-System

Jedes Kostüm ≤ 5 Primitive an den Ankern `hat` / `neck` / `hand` / `face`; Farben ≤ 2 Themenakzente + Elsterblau; **nie beide Augen bedecken, Schnabel immer sichtbar**; Kostüm kommt mit dem ersten Pop-In und wechselt nie innerhalb eines Eintrags; in `bow` wird der Hut abgenommen.

| Thema → Kostüm | Teile |
|---|---|
| curious → **default** | nur Smoking-Kragen; Serienfarbe im Flügelschimmer |
| heist → **thief** | Domino-Maske (zwei verschmolzene Ellipsen 0.14 × 0.08 an `face`, Tinte) mit Augenschlitzen; Beutel-Sticker 0.16 an `beak_tip` mit `gem` (accent). Gag: die Elster bräuchte keine Maske. |
| cave → **miner** | Helm (Halbscheibe r 0.20 + Krempe 0.44 × 0.04, accent) mit Lampe (Kreis r 0.04 + Lichtkegel-Dreieck alpha 0.25, glow, add; **Kegel folgt `look`**); Seilrolle (Ring 0.10 an `back`, wood) |
| animal → **explorer** | Tropenhelm (Ellipse 0.30 × 0.14 + Krempe 0.46 × 0.04, paper); Fernglas (zwei Kreise r 0.045 + Steg an `neck`) |
| space → **astronaut** | Glaskuppel (Kreis r 0.34 um den Kopf, `line` alpha 0.22 + Glanzbogen alpha 0.35); Antenne (Linie 0.10 + Kugel r 0.02, blinkt 1 Hz in accent2) |
| history → **historian** | Zylinder (rrect 0.26 × 0.22 + Krempe 0.40 × 0.04, Tinte, Band accent); Monokel (Ring r 0.08 am fernen Auge + Kettchen zu `neck`, accent) |
| ocean → **diver** | Taucherbrille (rrect 0.30 × 0.14, r 0.05, steel, Glas accent2 alpha 0.3); Schnorchel (Rundlinie 0.03 + Rohrende, accent) |
| medical → **doctor** | Stirnspiegel (Ring r 0.05 + Band, steel); Stethoskop (Rundlinie um `neck` + Scheibe r 0.04, steel); Kragen bleibt Elfenbein |
| crime → **detective** | Deerstalker (zwei Halbscheiben r 0.20, wood, Band accent); Lupe (Ring r 0.10 + Griff an `hand`); die Linse ist ein echter Clip mit Scale 1.3 |
| food → **chef** | Kochmütze (rrect 0.24 × 0.18 + drei Kreise r 0.07, light); Löffel (Linie 0.18 + Ellipse, steel) |

Die Zuordnung Thema → Kostüm ist eine Tabelle in `mascot.py` und im Skript überschreibbar (`"mascot": {"costume": "chef"}`).

### 2.5 Catchphrase, Zweitsignal, Tests

- **Sprechblase „Odd.“**: Sticker (Elfenbein, Rand 8 px, Schwanzpfeil), Unbounded 900 64 px in Tinte, Pop-In s 2.2, Ton `odd_say`. Höchstens 1× je Video, nur auf einer Pointe, nie im Respekt-Modus.
- **Vier-Augen-Prinzip**: Schwanzwinkel und Elfenbein-Brauen spiegeln jeden Ausdruck; Flügelschimmer leuchtet bei Staunen (alpha 1.0) und erlischt in `bow` (alpha 0.4). So bleibt die Mimik bei 140 px lesbar.
- **Tests**: `mascot.sheet` rendert Posen × Kostüme × Ausdrücke in 120, 240 und 420 px nach `library/sheets/mascot.png`; jede Pose muss als Silhouette bei 120 px Kopf, Schnabel, Schwanz und Flügel zeigen. Ohne Sticker-Rand ist `mascot_main` auf `bg0` 1.1 : 1 — der Rand ist lastentragend, nie Dekor.

---

## 3. Farbsystem

### 3.1 Basis-Palette (Markenkonstanten, in allen Themen gleich)

| Nr. | Name | HEX | Einsatz |
|---|---|---|---|
| 1 | Tinte | **#171A28** | Text auf hellen Flächen, Untertitel-Plakette (`caption_bg`), `card_ink` |
| 2 | Elfenbein | **#F7F1E6** | Hauptschrift (`ink`) auf dunklen Gründen, Bauch der Elster (`mascot_light`), Stat-Sticker, Titel-Sticker-Text |
| 3 | Sticker-Weiß | **#FFFFFF** | Sticker-Rand (`line`), Augenweiß, Glanzpunkte; sonst nie als Fläche |
| 4 | Wunder-Gold | **#F2B544** | Nummernkarte (`card`), Standard-Akzent, aktives Untertitelwort (`caption_hi`), #1-Momente, gefülltes Album-Fach |
| 5 | Koralle | **#F0634A** | Warn-/Gag-Akzent (`danger`), Stempel, Zunge, Wange, Stat-Pfeile |
| 6 | Elsterblau | **#2F9AA6** | Flügelschimmer und Schwanzspitze (`mascot_sheen`), Verweise |
| 7 | Pflaume | **#5B3F8F** | Grundton der Wunderkammer, Mystery-Schatten (Verwandter von `bg2` im Standardthema) |

Konstanten in jedem Thema: `ink` #F7F1E6, `ink_soft` #C9C2D6, `line` #FFFFFF, `card` #F2B544, `card_hi` #F7C96B (obere Zwei-Ton-Fläche der Karte), `card_ink` #171A28, `caption_bg` #171A28, `caption_ink` #F7F1E6, `caption_hi` #F2B544, `mascot_main` #1F2233, `mascot_dark` #12141F, `mascot_light` #F7F1E6, `mascot_sheen` #2F9AA6, `mascot_beak` #3A3F4F, `candle` #FFD8A0, `stamp` = `danger`. Naturfarben als Theme-Schlüssel (Props tragen keine eigenen HEX-Werte): `wood` #8E6F52, `steel` #9AA3B2, `skin` #E8C9A8, `paper` #EAD9B8, `chalk` #E9E4DA, `foam` #DDF3F5, `water` #5FD3F2.

### 3.2 Themenpaletten (`engine/theme.py`; `bg0` oben, `bg1` unten, `bg2` Silhouetten/Flächen)

| Thema | bg0 | bg1 | bg2 | accent | accent2 | glow | danger | ok | Bett | Kostüm |
|---|---|---|---|---|---|---|---|---|---|---|
| **curious** (Standard, Kabinett) | #1E1838 | #2E2250 | #41336C | #F2B544 | #5FD9B8 | #FFD98A | #F0634A | #5FD9B8 | cabinet_swing | default |
| **heist** (Raub) | #0F1A2C Nachtblau | #1A2740 | #27385A | #F2B544 Beute-Gold | #E8485C Sirenenrot | #FFE08A | #E8485C | #58E0C2 Laser-Mint | heist_tiptoe | thief |
| **cave** (Höhle) | #121420 | #232838 | #3B4254 Fels | #F2B544 Lampenlicht | #6FAE8F Moos | #FFD27A | #F0634A | #6FAE8F | cave_drip | miner |
| **animal** (Tiere) | #163A2C Dschungel | #1F5A3F | #2F7A52 | #F7A233 Papaya | #3FB7B0 Lagune | #FFD98A | #F0634A | #7CCB6B Blattgrün | safari_bounce | explorer |
| **space** (Weltraum) | #0B0D2A | #1B1D5A Tiefviolett | #2E2F80 | #FFD66B Sternengelb | #E86BB0 Nebelpink | #CFF4FF | #FF6B6B | #7FE3D2 | orbit_glow | astronaut |
| **history** (Geschichte) | #3A271C Sepia | #5A3C2A | #7A5A42 | #E2B55C Altgold | #B8402E Siegelrot | #FFE1A3 | #B8402E | #8FBF8F | parlour_waltz | historian |
| **ocean** (Ozean) | #0A2638 Abyss | #0F4A66 | #1C6F8C Lagune | #F0634A Koralle | #5FD9B8 | #A8FFE6 | #F0634A | #4FB38A Seegras | orbit_glow_ocean | diver |
| **medical** (Krankheit/Medizin) | #16343A Flaschengrün | #1F4A50 | #2C6168 | #F08CA8 Pillenrosa | #E9C45A Jodgelb | #CFF8EE Klinik-Mint | #F0634A | #8EF0D2 | cabinet_swing_pulse | doctor |
| **crime** (bizarre Geschichten/Gericht) | #2A1430 Aubergine | #3D1E3F | #55305A | #F2B544 | #F0634A | #FFD98A | #F0634A | #5FD9B8 | cabinet_swing | detective |
| **food** (Essen/Konsum, Alias) | #1E1838 | #2E2250 | #41336C | #F7A233 | #5FD9B8 | #FFD98A | #F0634A | #5FD9B8 | safari_bounce | chef |

Sonderakzente: cave `water` #5FD3F2; history `paper` #EAD9B8 (Schriftrollen, Tinte-Text); ocean `foam` #DDF3F5 (Blasen); crime `chalk` #E9E4DA (Tafel/Akten). Gold-Objekte (Münzen, Barren) bekommen **Altgold #E2B55C**, nie Wunder-Gold.

**Respekt-Variante** (automatisch über `theme.respect(th)`): `bg0/bg1/bg2` = `color.saturate(c, 0.7)` (z. B. heist → #131B28 / #20293A / #2F3B52, curious → #211D33 / #312949 / #453C63, history → #362821 / #533E31 / #725B4A), `accent` → #F7F1E6, `accent2` → #C9C2D6, `glow` aus, Lichtinsel `candle` #FFD8A0 alpha 0.18.

### 3.3 Regeln und gemessene Kontraste (`color.contrast`)

1. Pro Bild: `bg0/bg1` + `bg2` + maximal zwei Akzente + Elfenbein/Tinte. Konfetti und Props bedienen sich nur aus `accent`, `accent2`, `glow`, `line` (plus Naturfarben).
2. Schrift nur in zwei Kombinationen: **Elfenbein auf `bg0`/`bg1`/`caption_bg`** (Tinte 15.4 : 1, curious bg0 15.0, heist bg0 15.5, space bg0 16.9, history bg0 12.6, history bg1 8.8) oder **Tinte auf Gold/Pergament/Elfenbein** (Gold 9.4, hell-Gold 11.1, Altgold 9.1, Pergament 12.4, Elfenbein 15.4). Auf `bg2`-Flächen (hellste: history #7A5A42 → 5.5 : 1, animal #2F7A52 → 4.6 : 1) nur Text ≥ 40 px oder mit Plakette.
3. Farbiger Text (Schlagworte in `accent`/`accent2`, Stempel in Koralle) ausschließlich als **Sticker-Text**: Füllung + weißer Rand 8 px + Schatten; der Rand liefert den Kontrast, nie die Füllung. Koralle nie für Text unter 56 px (Koralle auf Tinte nur 5.4 : 1, Elfenbein auf Koralle 2.8 : 1 → verboten). Glow nie für Text.
4. **Gold ist reserviert**: Nummernkarte, aktives Untertitelwort, #1-Momente, gefülltes Album-Fach. Kein Gold für Props.
5. Untertitel: Elfenbein auf Tinte-Plakette alpha 0.92, aktives Wort Gold (9.4 : 1 auf Tinte). Nie Outline-Text ohne Plakette.
6. Alle Farben über `theme.get()`; Props dürfen keine eigenen HEX-Werte tragen.
7. `check.py`: Warnung < 4.5 : 1, Fehler < 3 : 1, Untertitel-Mindestkontrast 7 : 1 (gemessen gegen die tatsächliche Plakette); fällt ein Bild durch, wird die **Plakette dunkler, nie die Schrift kleiner**. `theme.sheet` zeigt je Thema die vier Pflichtpaare `ink/bg0`, `accent/bg0`, `card_ink/card`, `caption_ink/caption_bg` mit Messwert.
8. Akzent-Ziffern auf Karten: nie. Die Ziffer ist immer `card_ink`.

---

## 4. Typografie

### 4.1 Schriften (Google Fonts, OFL, in `assets/fonts`; Rollen aus `engine/fonts.py`)

- **number: Unbounded 900** — Ziffern der Nummernkarten, Stat-Werte, Jahreszahlen-Chips, Sprechblase „Odd.“. Breit, geometrisch, ikonisch; nie unter 48 px.
- **display: Bricolage Grotesque 800**, `opsz` 96, `wdth` 90 — Hook, Eintragstitel, Kopfzeile, Schlagworte, Stempel-Text (Versalien), CTA. Charaktervoll-editorial, aber sauber. Etikett-Zeilen in `wdth` 100, Gewicht 600.
- **body/caption: Outfit 700** (Untertitel), 500 (Erklärsätze im Querformat). Geometrisch, ruhig, lässt die Sticker rund sein, ohne kindlich zu werden. (Nunito 800 liegt als weichere Alternative bereit.)
- **mono: DM Mono Medium** — Serienetikett, „#“, Themenwort auf der Karte, Meta-Pille, Album-Ziffern, Stat-Label, Wasserzeichen-Handle, Quellenhinweise. Immer Versalien, Laufweite +0.14 em.
- **serif: Instrument Serif Italic** — nur im Thema history für Zitate (≤ 1 Zeile), sonst nie.
- `hand` (Caveat) wird **nicht** verwendet (keine Handlinien).

Regel: maximal zwei Familien pro Bild (Mono als Etikett zählt nicht); Zahlen im Fließtext bleiben Outfit, Zahlen als Sticker Unbounded. Kleinste Größe im Hochformat 26 px, im Querformat 22 px.

### 4.2 Größen Hochformat 1080 × 1920 (Querformat × 0.78, Nummern eigene Werte)

| Element | Schrift | Größe / Satz |
|---|---|---|
| Hook-Headline | Bricolage 800, wdth 90 | 104 px (fit_size bis 88), Zeilenhöhe 1.06, Laufweite −0.02 em, max. 3 Zeilen à ≤ 14 Zeichen, zentriert, Block um y 860 (700–1100); **Sticker-Text** Elfenbein, Rand 8 px, Schatten; das Schlüsselwort (`hook.keyword`) in Gold. **Steht ab Frame 1** (kein Pop-In). |
| Serienetikett + Archivnummer | DM Mono | 28 px, ≤ 22 Zeichen, Elfenbein alpha 0.8, x 70, y 310 (middle), z. B. `CURIOUS HEISTS · 017` |
| Nummernkarte groß | Unbounded 900 | Ziffer 420 px (#1: 500 px), „#“ DM Mono 48 px, Themenwort DM Mono 28 px |
| Badge | Unbounded 900 | Ziffer 150 px, „#“ DM Mono 24 px |
| Album-Fach | DM Mono | 22 px Ziffer in Tinte (Ausnahme vom 26-px-Minimum: reine Dekoration) |
| Eintragstitel (Haltezeit) | Bricolage 800 | 72 px (fit bis 60), max. 2 Zeilen, Zeilenhöhe 1.1, zentriert bei x 540, y 1160; Sticker-Text Elfenbein, Rand 8 px |
| Kopfzeile (gedockt) | Bricolage 800 | 52 px (fit bis 40), **eine Zeile**, ≤ 560 px, Tinte-Plakette alpha 0.92, Radius 24, Innenabstand 14 / 24, x 70, y 668–744. Skripttitel ≤ 24 Zeichen. |
| Meta-Pille (Ort · Jahr) | DM Mono | 26 px (fit bis 22), Versalien, `bg2`-Pille Höhe 48, Rand 6 px, rechtsbündig an x 1010, ≤ 360 px; Ort ≤ 12 Zeichen (`place` = Stadt) |
| Stat-Plakette | Unbounded 800 / DM Mono | Wert 96 px (fit bis 72 in 400 px), zählt hoch; Label 28 px Versalien, Tinte alpha 0.7; Elfenbein-Sticker, Rand 10 px, Radius 48 |
| Schlagwort-Sticker | Bricolage 800, wdth 90 | 80 px (fit bis 56), 1–2 Zeilen, ≤ 500 px, `accent`-Füllung + Rand 8 px, Rotation −4° … +4°, Pop-In, Ton `keyword_slam`; steht ≥ 1.5 s |
| Stempel | Bricolage 800 | 64 px Versalien, Koralle, Rahmen 6 px Koralle, Radius 24, Rand 6 px weiß, −8°, Multiply-Korn 0.08; Texte: VERIFIED ODD · FILED UNDER WHAT · NEVER FOUND · FAKE · NEVER PAID |
| Untertitel | Outfit 700 | 60 px, Zeilenhöhe 1.15, 1–2 Zeilen, ≤ 780 px, Plakette Tinte alpha 0.92, Radius 28, Innenabstand 18 / 28, Mitte x 480, y 1446 |
| Sprechblase „Odd.“ | Unbounded 900 | 64 px Tinte auf Elfenbein-Sticker |
| CTA im Outro | Bricolage 700 | 56 px, 2 Zeilen, zentriert, Sticker-Text Elfenbein |
| Wasserzeichen | DM Mono | 24 px Handle unter Odd-Kopf 44 px, alpha 0.62 |
| Zitat (nur history) | Instrument Serif Italic | 48 px, Elfenbein, auf `paper`-Schriftrolle Tinte |

Querformat: Hook 81 px, Titel 56 px (2 Zeilen in `fmt.title`), Kopfzeile 40 px, Untertitel 44 px (eine Zeile, Plakette ≤ 820 px), Karte 340 px (#1: 400 px), Badge 120 px, Mono 22–24 px, Schlagwort 62 px, Stat 76 px.

### 4.3 Untertitel-Stil („Sticker-Karaoke“)

Wortgruppen von 2–4 Wörtern bzw. ≤ 22 Zeichen (Zeitstempel aus ElevenLabs, `captions.chunks`), Satzzeichen bleiben, Groß-/Kleinschreibung wie gesprochen (nie Versalien-Sätze). Aktives Wort: Gold, Scale 1.06 mit 120 ms Pop (`out_back`) und 180 ms Rückfederung; gesprochene Wörter Elfenbein alpha 1.0; kommende Wörter Elfenbein alpha 0.55 (neuer Stil `caption_style = 'odd'`: Kombination aus `word` und `karaoke`). Zahlen und Eigennamen bekommen keine Sonderfarbe: Gold ist nur das aktive Wort. Die Plakette wächst/schrumpft mit der Gruppe (`out_quint`, 160 ms), bleibt horizontal auf x 480 zentriert und endet bei x ≤ 870. Während der Ansage („Number five.“, Zeile `E5.0`) und im Blackout der Karte gibt es keine Untertitel. Respekt-Modus: aktives Wort Elfenbein, keine Scale-Pops. Config: `caption_size 60`, `caption_max_words 4`, `caption_max_chars 22`, `caption_plate_alpha 0.92`, `caption_weight 700`.

---

## 5. Nummernkarten und Countdown

### 5.1 Die Sammelkarte

Abgerundetes Quadrat **560 × 560 px**, Radius 72, Füllung Wunder-Gold #F2B544, obere 46 % der Fläche in `card_hi` #F7C96B (Zwei-Ton-Flat, harte Kante um 4° schräg), weißer Sticker-Rand 12 px, Schatten dy 8 / sigma 16 / alpha 0.22. Inhalt: „#“ DM Mono 48 px Tinte oben links (Abstand 44 px), Ziffer Unbounded 900 **420 px** Tinte zentriert (Baseline optisch 20 px unter der Mitte), unten ein 72 px hoher Streifen in Tinte mit Themenwort (DM Mono 28 px Elfenbein, z. B. „HEIST“) und einem 44-px-Mini-Piktogramm des Themas (Mode `silhouette`, Elfenbein). Idle: Atmen 1 %.

**#1**: Scale 1.15 (644 px), Ziffer 500 px, Koralle-Eckband (Dreieck oben rechts) mit „TOP“ in DM Mono 24 px Elfenbein, Kronen-Sticker `crown` 120 px, der 200 ms nach der Landung aufploppt, 12 Funkel-Partikel in `glow`.

**Badge** (gedockt, `fmt.card` 70/350): 240 × 240, Radius 48, Rand 8 px, „#“ DM Mono 24, Ziffer 150 px, ohne Streifen, Atmen 1 %, bleibt die ganze Eintragsdauer.

### 5.2 Choreografie eines Nummernwechsels (relativ zu `sc.t0`, `trans_dur` 0.6 s)

| Zeit | Bild | Ton |
|---|---|---|
| t0 − 1.5 s (nur #1) | Riser; Lichtinsel pulsiert 1 Hz | `riser` (mit Trommelwirbel in den letzten 0.9 s) |
| t0 | **Peel** der alten Seite (300 ms); gleichzeitig Pop-Out des Badges (Scale 1 → 0.9, +15°, 160 ms), der als 40-px-Mini-Sticker in sein Album-Fach fliegt (`in_out_cubic` 420 ms, Landung mit 8 % Squash bei t0 + 0.58) | `card_whoosh`, `peel`; Landung `pop_in` −6 dB, Fach füllt sich Gold → `shiny` −12 dB |
| t0 … t0 + 0.33 | **Variante A „Elster-Lieferung“** (#5, #3): Odd fliegt in `fly` von oben rechts mit der Karte an `beak_tip` zu ihrem Bodenpunkt (330 ms, Smear), lässt sie bei t0 + 0.22 über der Bildmitte los; die Karte fällt 100 px mit −18° → 0° und landet bei **t0 + 0.33** auf (540, 860), Squash 90 ms, 24 Konfetti. Odd landet bei t0 + 0.40. | `flap`; **`card_hit#rank`** bei t0 + 0.33 (= `sc.t0 + 0.55 · trans_dur`, das Wort „Number“); `confetti` −12 dB; `hop` |
| t0 … t0 + 0.33 | **Variante B „Zählwerk“** (#4, #2): die Karte öffnet sich per Sticker-Iris in der Bildmitte (360 ms ab t0 − 0.03); in einem `clip_rect` rollt die alte Ziffer nach oben hinaus und die neue von unten herein (260 ms, 6 % Überschwingen, `out_back`), bei t0 + 0.33 blitzt die Goldfläche (`fx.flash` 0.25, 100 ms) | `tick` je Zwischenschritt (−30 dB), `card_hit#rank` bei t0 + 0.33 |
| t0 … t0 + 0.33 | **#1 „Konfetti-Cut“**: harter Schnitt statt Peel, Blitz 120 ms, 40 Konfetti; Odd in `cheer` wirft die Karte mit Krone aus ihrer Position, Flug 330 ms, Landung t0 + 0.33; Krone bei t0 + 0.53; Album-Fach 5 füllt sich bei t0 + 0.58 und die Leiste leuchtet 600 ms (`c.glow` sigma 30) mit 12 Funkeln: „Album voll“ | `flash`, `confetti` (80), `card_hit#1`, `number_one` bei t0 + 0.36 |
| t0 + 0.55 … 1.25 | Haltezeit; der Eintragstitel erscheint ab t0 + 0.55 per Wort-Stagger 45 ms unter der Karte (72 px, y 1160). Keine Untertitel. | `pop_in` je Wort −10 dB |
| t0 + 1.25 … 1.67 | Karte schrumpft (`in_out_cubic`, 420 ms) in den Badge-Slot oben links; der Titel gleitet zeitgleich in die Kopfzeile (72 → 52 px, Position nach x 70 / y 668); Meta-Pille tippt sich ab t0 + 1.70 ein (1 Zeichen je Frame, ≤ 12 Ticks) | `typewriter` ×n −16 dB |
| ≤ t0 + 1.8 | Hero-Sticker poppt (am Anker `at` oder spätestens hier); Odd nimmt die Skript-Pose ein; Lichtinsel schwenkt auf den Hero | `pop_in` |

Ansage-Sync: Landung auf dem Wort „Number“ (`sc.t0 + trans_dur · 0.55`), Titelzeile beginnt mit dem ersten Titelwort (`announce: number_title`) oder bei t0 + 0.55 (`announce: number`). Alles bleibt aus der Timeline ableitbar.

### 5.3 Album-Leiste (Fortschritt)

Fünf leere Sticker-Fächer oben rechts (`fmt.progress` → Rect(560, 286, 250, 44)): abgerundete Quadrate 40 × 40, Radius 12, gestrichelter Rand (`line` alpha 0.35, dash 6/6), Abstand 12 px, von links #5 bis rechts #1. Das **nächste** Fach pulsiert (Rand-Alpha 0.35 → 0.6 bei 0.8 Hz). Mit jedem Nummernwechsel fliegt der Badge als 40-px-Mini-Sticker (Mode `silhouette` in Tinte auf Gold, Rand 4 px) nach oben in sein Fach; das Fach ist danach Gold gefüllt und zeigt die Ziffer in DM Mono 22 px Tinte. Die Leiste liegt auf der UI-Ebene und bleibt in jedem Übergang sichtbar. Bei #1 füllt sich das letzte Fach, die Leiste leuchtet 600 ms in `glow` und 12 Funkel-Partikel steigen auf. Sie ersetzt jeden Balken; keine zweite Zeitanzeige. Respekt-Modus: Fach füllt sich Elfenbein, ohne Funkeln. Querformat / Top 10: eine Reihe mit 10 Fächern à 32 px, Abstand 20, in `fmt.progress` 100/1000; dazu, nur im Querformat, eine 2-px-Zeitlinie in `accent` unter der Kopfzeile, die sich über jeden 45–70-s-Eintrag füllt (Lesehilfe).

### 5.4 Stempel und Flip-Karte (Pointen-Werkzeuge)

- **Stempel** (`props.stamp(text)`): Koralle-Rahmen 6 px, Radius 24, Text Bricolage 800 64 px Versalien Koralle, weißer Sticker-Rand 6 px, Rotation −8°, Multiply-Korn 0.08 (Gummistempel). Einschlag: Scale 1.6 → 1.0 in 120 ms (`in_quart`), 2 Frames Shake 4 px, Ton `stamp` (20 ms Stille vorab). Max. 1 je Eintrag, nie im Respekt-Modus.
- **Flip-Karte** (`props.flip_card(front, back)`): Elfenbein-Karteikarte 300 × 200, Radius 24, Text DM Mono 30 px Tinte; klappt per Scale-X 1 → 0 → 1 (260 ms) und zeigt auf der Rückseite den Stempel („APPROVED“ → „FAKE“). Töne `page_flip` → `stamp`.
- **Sprechblase „Odd.“**: siehe 2.5.

---

## 6. Klangidentität „Holz, Glas und Papier“

Warm, trocken, nah: Marimba-/Kalimba-Mallets (Sinus + 3. und 4. Teilton, Decay 120–400 ms), gezupfte Saiten (`synth.pluck`, Karplus-Strong), Papier-Klicks und Pops (gefiltertes Rauschen 10–60 ms), Glasglöckchen (hohe Sinus-Cluster) für alles Glänzende. Kein Hall-Teppich außer im Respekt-Modus (`reverb` decay ≤ 1.6 s). Alles aus `audio/synth.py` (`sine, tri, saw, square, noise, sweep, fm, adsr, env_exp, lowpass/bandpass/highpass, svf, delay, reverb, chorus, drive, tremolo, pan, widen, pluck, bell, kick, click`), deterministisch über `seed`.

**Pegel** (`config.mix`): Stimme −16 LUFS, Musik −14 dB unter der Stimme beim Sprechen (Ducking Attack 80 ms, Release 450 ms), Musik solo −6 dB, Töne −8 dB (+ Cue-Offset), Master −14 LUFS, True Peak −1 dBTP, 48 kHz. Maskierung: Ton auf einem Wort höchstens 6 dB unter dem Wortpegel (`mix.MASK_DB`).

### 6.1 Rang-Leiter und Markenmotiv

- **Rang-Leiter**: Stufen **1 – 2 – 4 – 5 – 8** über dem Grundton des laufenden Betts (modusfrei, kein Terzton, passt zu Dur, Moll, Dorisch, Lydisch): #5 = Grundton, #4 = Sekunde, #3 = Quarte, #2 = Quinte, #1 = Oktave. Oktave 5 für Grundtöne bis F, sonst Oktave 4 (D: D5 E5 G5 A5 D6; E-Moll: E5 F#5 A5 B5 E6; A-Moll: A4 B4 D5 E5 A5; G: G4 A4 C5 D5 G5; F#: F#4 G#4 B4 C#5 F#5; B♭: B♭4 C5 E♭5 F5 B♭5). Top 10: #10 … #6 eine Oktave tiefer. API: `music.ladder(bed_id, total=5) -> [Noten]`, `sfx.set_key(root)` vor dem Rendern der Cues; `sfx.render('card_hit#4')` (ohne Suffix = Stufe #5).
- **Odd-Ding** (Signature `card_hit`): Stempel (Sinus 90 Hz 80 ms + Klick 15 ms) + Marimba-Dyade Grundton + Quinte (2 Anschläge 70 ms versetzt) + 4 Glas-Sinus 3–6 kHz 120 ms zufällig gepannt. Jeder Rang einen Leiterton höher; #1 bekommt zusätzlich `number_one` (Tonika-Dreiklang + Oktave als `bell()`, Shaker, Sub-Thump) nach dem Trommelwirbel des `riser`.
- **Markenmotiv „Odd-Ding“ (Audiologo)**: die Leiter komprimiert — Stufen **1 – 5 – 8** (= #5, #2, #1), Rhythmus kurz, kurz, lang (0.18 / 0.18 / 0.60 s). Als Kalimba in `outro_chime`, als Marimba + Glas + Flügelschlag in `end_sting`. Nirgends sonst.

### 6.2 Sound-Vorrat (`audio/sfx.py`; ID — Synthese — Einsatz; Pegel = Cue-dB relativ zu `sfx_db`)

**Pflicht-IDs der Engine**

1. `hook_hit` — Sub-Pop Sinus 180 → 55 Hz in 60 ms + Papierschlag (Rauschen bandpass 1.4–2.2 kHz, 25 ms) + Glas-Ping 2.4 kHz 300 ms — erster Frame des Hooks (−6).
2. `card_whoosh` — weißes Rauschen, Bandpass-Sweep 400 → 4000 Hz in 240 ms, Pan −0.8 → +0.8, leichtes Doppler — Peel (−8).
3. `card_hit#5 … #1` — Odd-Ding, siehe 6.1 — Karte landet (−5).
4. `number_one` — Glockenakkord Tonika + Oktave (`bell`, ratio 1.4, Decay 1.2 s, 3 Stimmen 40 ms versetzt) + Shaker 80 Impulse + Sub 55 Hz + Glas-Cluster — Karte #1 (−5).
5. `stat_pop` — Zählwerk: Holzblock-Klicks `click(0.012, 2200)` im Tempo der `count_value`-Kurve (12–26 Ticks), Abschluss-Pling Tri-Welle Quinte 90 ms — Stat-Plakette (−9).
6. `outro_chime` — Markenmotiv als Kalimba (`pluck`, bright 0.6, Chorus mix 0.3, Hall decay 0.9) — Outro-Beginn (−8).
7. `end_sting` — Markenmotiv Marimba (Decay 400 ms) + Glas-Cluster auf der Oktave + `flap` + Hall decay 1.2 s, Ausklang 1 s — letzter Frame (−7).

**Sticker und UI**

8. `pop_in` — Sinus-Sweep 600 → 1200 Hz 40 ms + Klick 8 ms — jeder Sticker-Auftritt, max. 1 je 150 ms (−12).
9. `pop_out` — Sweep 1200 → 500 Hz 50 ms, −4 dB gegenüber `pop_in` — Sticker verschwindet (−16).
10. `peel` — Rauschen highpass 3 kHz mit Amplituden-Knistern (Zufallsgates 2 ms), Attack 30 / Release 190 ms — Sticker abziehen, Seitenwechsel (−12).
11. `tick` — `click(0.012, 3000)` — Zählwerk-Rolle der Ziffer, optional Untertitel-Gruppenwechsel (−30).
12. `stamp` — 20 ms Stille, Sinus 90 Hz 80 ms + Rauschen lowpass 600 Hz 50 ms + Drive 0.3 — Stempel (−8).
13. `keyword_slam` — 20 ms Stille, Sub 50 Hz 140 ms + Rausch-Crack bandpass 1.2–1.8 kHz 25 ms + Glas-Ping 3.2 kHz — Schlagwort landet (−9).
14. `confetti` — Shaker: 24–80 Rauschimpulse 8 ms, bandpass 4–6 kHz, zufällig gepannt, Dichte fällt über 600 ms — Konfetti (−12).
15. `shiny` — Glasglöckchen-Cluster 5 Sinus 3.5–7 kHz, Decay 400 ms, 30 ms versetzt, Stereo-Spreizung — Edelstein, Beute, Album-Fach, Enthüllung (−12).
16. `riser` — Rauschen pink + Sinus-Sweep 200 → 2000 Hz über 1.5 s, exponentielle Lautstärke, Hochpass öffnet; in den letzten 900 ms Trommelwirbel (Rauschbursts bandpass 250–400 Hz, 8 → 24 Hz) — vor #1 (automatischer Cue bei `E1.t0 − 1.5`) oder Enthüllung (−12).
17. `record_stop` — aktueller Akkord als Tri-Dreiklang, Pitch → 0 über 400 ms + Lowpass zu — komisches Innehalten (−10).
18. `fail` — zwei Tri-Töne A4 → F4 je 180 ms mit Vibrato — gescheiterter Plan (−10).
19. `flash` — Rauschen highpass 6 kHz 60 ms + Sinus 4 kHz 40 ms — Blitz bei Konfetti-Cut (−14).

**Odd (Charakter)**

20. `flap` — zwei dumpfe Rauschstöße lowpass 500 Hz à 60 ms, Abstand 90 ms — Flügelschlag, Lieferung (−12).
21. `hop` — `pluck('G3', 0.12, bright 0.5)` — Hüpfen, Landung, Sneak-Schritt (−12 / −14).
22. `boing` — Sinus 220 Hz mit abklingendem Vibrato 8 Hz Tiefe 30 %, 350 ms — Squash-Gag (−10).
23. `blink` — Holztick 1.5 kHz 10 ms — Blinzeln in Pausen (−18).
24. `beak_click` — Doppelklick 2 × 8 ms Rauschen bandpass 2.5–3.5 kHz, Abstand 70 ms — Schnabel, Klopfen, Skepsis (−12).
25. `gasp` — Rauschen highpass 1 kHz, umgekehrte Hüllkurve (Attack 250 / Release 30 ms) + Formant-Bandpass 700/1200 Hz — Schock (−12).
26. `giggle` — drei Sinus-Blips 900/1100/1000 Hz à 50 ms, Pitch-Jitter ±4 % — Kichern (−12).
27. `hmm` — Sägezahn lowpass 800 Hz, E3 → C3 über 300 ms, Vibrato 5 Hz — Skepsis, Facepalm (−14).
28. `odd_say` — zwei Formant-Töne (Sinus durch Bandpass 600 + 1100 Hz) A4 → F4 über 180 ms + `beak_click` — Sprechblase „Odd.“ (−10).

**Themen-Props**

29. `drip` — Sinus 1800 → 900 Hz 25 ms + Delay 375 ms (3×) + Hall — Höhle, Wasser (−10).
30. `splash` — Rauschburst lowpass 1.2 kHz 120 ms + 6 Blasen-Chirps + Sinus 120 Hz Plop — Platschen (−9).
31. `bubble` — Sinus-Sweep 300 → 900 Hz 20 ms, Resonanz q 8 — Ozean (−14).
32. `coin` — Sinus 1.2 + 1.8 kHz 90 ms + Metallklick, Prell-Hüllkurve 3× (180/110/70 ms) — Geld, Beute (−12).
33. `page_flip` — Rauschen bandpass 0.9–1.5 kHz 120 ms, Doppelbuckel — Kalender, Akte, Flip-Karte (−12).
34. `typewriter` — `click(0.012, 4000)` im Zeichenrhythmus + Zeilenschlag 300 Hz — Meta-Pille, Etiketten, ≤ 12 Ticks (−16).
35. `heartbeat` — zwei Sinus-Thumps 60 Hz (90 / 70 ms), Abstand 180 ms — Medizin, Spannung (−10).
36. `alarm_blip` — Rechteck 1100 Hz 60 ms × 3 bei 8 Hz, lowpass 3 kHz — Laser, Alarm (−12).
37. `safe_click` — 5–9 Rasterklicks bei 12 Hz verlangsamend + „Clunk“ 90 Hz 150 ms — Tresor, Schloss (−10).
38. `rumble` — braunes Rauschen lowpass 90 Hz 1.5 s, Tremolo 6 Hz — Einsturz, Gefahr (−10).
39. `bat_flutter` — 6–8 Rausch-Puffs lowpass 1.2 kHz bei 18 Hz — Fledermaus (−16).
40. `whistle` — Sinus Portamento 1.8 → 2.4 kHz 120 ms, Vibrato 6 Hz — Tiere, Pointe (−14).

**Respekt**

41. `ghost_halo` — Sinus-Pad 3 Teiltöne auf A4, Attack 600 ms, Hall 1.6 s, luftiges Rauschen — Geist-Halo (−14).
42. `respect_hush` — Raumton (pinkes Rauschen lowpass 400 Hz, Schwell 800 ms) + einzelner Sinus G3 −18 dB, Hall 1.4 s; Musik duckt zusätzlich 6 dB für 2.5 s — jeder Todesfall (−18).

### 6.3 Musikbetten (`audio/music.py`; 8-Takt-Loops, `sections` aus `mix.sections_from`: hook 0.6, #5 0.5 … #1 0.9, outro 0.4; Schichten schalten bei Energy ≥ 0.3 / 0.5 / 0.65 / 0.8 / 0.9 zu)

1. **cabinet_swing** (curious, crime, Standard): 112 BPM, D-Dorisch, Swing 58 %. Schichten: Walking-Bass `pluck` Achtel lowpass 1.8 kHz → Marimba-Stabs (Sinus + 3./4. Teilton, Decay 260 ms) auf 2 und 4 → Besen-Hi-Hat (Rauschen highpass 7 kHz 30 ms) + Fingersnap (Klick bandpass 2.5 kHz) auf 2 und 4 → Kalimba-Gegenstimme eine Oktave höher → Glas-Glocke `bell` auf jeder 1. Nummernwechsel: Marimba-Lauf 4 Sechzehntel aufwärts, Schlagwerk pausiert 1 Beat.
2. **heist_tiptoe** (heist): 100 BPM, E-Moll, Swing 55 %. Pizzicato-Bass auf den Offbeats → Vibraphon-Akkorde (Sinus + Tremolo 5 Hz, Decay 1.2 s) → Holzblock-Pattern + Bongo-Pops (Sinus 180 → 90 Hz) → Melodie Dreieck lowpass 1.5 kHz mit kleiner Sexte (Spionage) → Laser-Mint-Arpeggio (square 1/16, lowpass 2 kHz) bei Alarm-Beats. Energy 0.3 beim Schleichen.
3. **cave_drip** (cave): 84 BPM, A-Moll. Pad `supersaw` 2 Stimmen ±7 Cent lowpass 300 Hz, Filter-LFO 0.1 Hz → Drip-Pings pentatonisch mit Delay 375 ms → Sub-Herzschlag alle 2 Takte → Marimba-Bass auf 1 und 3+ → Holzpuls je Takt. Hall 1.6 s. Nummernakzent: Lichtkegel-Sweep (Rauschen bandpass 300 → 4000 Hz). Staunen, kein Grusel.
4. **safari_bounce** (animal, food): 124 BPM, G-Dur. Kalimba (Tri + Sinus, Decay 250 ms) gebrochene Dreiklänge → Bass Sinus mit Pitch-Drop („bouncy“) → Shaker Sechzehntel → Holzblock-Clave 3-2 → Pfeif-Melodie (Sinus, Vibrato 6 Hz) alle 4 Takte.
5. **orbit_glow** (space; Variante **orbit_glow_ocean**: 88 BPM, Kick → Blasen-Perkussion, Sonar-Ping 1 kHz Delay 480 ms): 96 BPM, F#-Lydisch. Pad Sinus-Cluster + Chorus → Arpeggio square → lowpass mit ADSR, Delay 3/16 → weicher Sinus-Kick + Sidechain 6 dB → Sub 41 Hz → Glas-Sparkle.
6. **parlour_waltz** (history; Respekt-Modus aller Themen): 3/4, 72 BPM, B♭-Dur / g-Moll wechselnd. Spieluhr (Sinus + 3. und 5. Teilton, Decay 300 ms) → gestrichenes Pad (Sägezahn, Attack 400 ms, lowpass 1.2 kHz) → Pizzicato auf 1 → Cembalo-Imitation (square → Kammfilter) → weiche Pauke. Respekt: nur Spieluhr + Pad, Energy 0.2, Hall 1.4 s, kein Akzent.
7. **cabinet_swing_pulse** (medical): wie cabinet_swing bei 104 BPM, Fingersnap ersetzt durch `heartbeat` auf 1 und 3, Monitor-Piep (Sinus 1 kHz 40 ms) auf der 4.

Jedes Bett startet im Hook mit einem 2-Takt-Riser, setzt bei jedem Nummernwechsel einen Takt vorher einen Rausch-Swell, auf `sc.t0` Akkordwechsel + 1 Beat Schlagwerkpause + Akzentlauf, und kennt eine 2-taktige Dur-Auflösung für das Outro, gefolgt vom Markenmotiv. Kein Ritardando (v1). `music.pick(theme)` folgt der Tabelle in 3.2; `music.key(bed_id)` liefert den Grundton für die Leiter.

---

## 7. Bildrepertoire (Bauplan)

Reihenfolge = Baureihenfolge. Jedes Prop: flach, 2–4 Themenfarben, Zwei-Ton-Flat, Sticker-Rand 10 px, genau eine Eigenbewegung über `t`, Modi `color / rim / silhouette`, Hüllform für den Schatten, 120-px-Silhouettentest im `props.sheet`. Namen entsprechen den Props im Skript `script.json`.

**Woche 1 — Kulissen (`backdrops.py`, ganzflächig +200 px Überhang, Silhouetten in bg2-Stufen, ohne Rand)**
1. `spotlight` — leerer Boden, Lichtinsel, 24 Staubpartikel (Hook, Outro-Alternative).
2. `cabinet` — Wunderkammer-Regal: 3 Regalbretter, Gläser/Kuppeln als Ellipsen-Silhouetten, Lichtinsel Mitte (Standard, Outro).
3. `warehouse` — Regale mit Fässern/Kisten-Silhouetten, Deckenlampe mit Kegel alpha 0.15.
4. `museum` — Wand mit leeren Rahmen (Rechtecke, Radius 24), Sockel.
5. `vault` — Tresorwand: Reihen quadratischer Schließfächer, ein großes Tresorrad.
6. `night_city` — Flat-Skyline mit Fensterrastern, 3 Fenster blinken (≤ 1 Hz), Mond r 90.
7. `forest` — gestaffelte Blob-Baumkronen, Lichtflecken.
Woche 2: 8. `cave` (Stalaktiten/Stalagmiten aus abgerundeten Dreiecken, 3 bg2-Stufen, Tropfen), 9. `jungle` (Blattrahmen aus Ellipsen, Lichtflecken), 10. `savanna` (Horizont, Akazie als Blob + Stamm, Sonnenkreis), 11. `stars` (Sternfeld `fx.particles` + Ringplanet-Silhouette), 12. `seabed` (Algen-Bezier wiegen sich, Sandwellen, Blasen), 13. `clinic` (Fliesenraster, Fenster mit Jalousie), 14. `parchment` (Pergament `paper` mit Fleckenblobs und Siegel), 15. `courtroom` (Richterpult, Waage als Silhouette), 16. `street` (Straße, Laterne mit Kegel, Bordstein).

**Woche 1 — Universelle Piktogramme und Werkzeuge (`props.py`)**
17. `question` — Fragezeichen-Sticker, wippt. 18. `exclaim` — Ausrufezeichen, stretcht beim Pop. 19. `speech_bubble` / `thought_bubble` — mit Schwanzpfeil, parametrischer Text (auch „Odd.“). 20. `stamp` — Gummistempel mit Text (5.4). 21. `flip_card` — Karteikarte mit Vorder-/Rückseite (5.4). 22. `stat_chip` — Zahl + Label-Plakette, zählt hoch. 23. `keyword` — Schlagwort-Sticker. 24. `calendar` — Kalenderblatt mit Jahreszahl (Unbounded), blättert (`page_flip`). 25. `map_pin` — Pin auf Kreis-Karte, hüpft. 26. `country_chip` — Kreis mit 2–3-Buchstaben-Kürzel (keine Flaggen). 27. `arrow` — fetter Richtungspfeil, 4 Richtungen, pulsiert. 28. `magnifier` — Lupe, vergrößert Inhalt unter der Linse (Clip, Scale 1.3). 29. `clock` — Uhr mit drehenden Zeigern. 30. `newspaper` — „EXTRA“-Zeitung mit Balken-Text. 31. `money_bag` — Beutel mit Zugband, mit `gem` statt $. 32. `money` — Geldbündel mit Band, wippt. 33. `gem` / `diamond` — Edelstein aus Polygon, funkelt (`shiny`). 34. `coin` — Münze (Altgold), dreht (Scale-X oszilliert). 35. `crown` — Krone, 3 Zacken, für #1. 36. `ghost_halo` — Heiligenschein-Sticker (Ring + Glow, Respekt). 37. `candle` — Gedenkkerze mit Flammen-Blob (Respekt). 38. `closed_label` — „EXHIBIT CLOSED“-Schild (Respekt). 39. `skull_friendly` — runder, freundlicher Totenkopf (nur außerhalb des Respekt-Modus).

**Woche 1 — Heist-Set (erstes Video)**
40. `cheese_wheel` — Käselaib mit Keil, wippt. 41. `truck` — Flat-Lkw, Räder drehen, Slide mit Smear. 42. `painting` — Gemälde im Rahmen; Variante leerer Rahmen + Sticker, der sich abzieht (Peel). 43. `police` — Polizeimütze + Stern (als Sticker), gleitet. 44. `vault_door` — Tresortür mit Rad, öffnet um Scharnier; 10 Laserlinien in `ok`, die nacheinander aus-ploppen. 45. `sandwich` — angebissenes Sandwich mit DNA-Helix-Chip. 46. `motorcycle` — Flat-Motorrad, Räder drehen. 47. `car` — Flat-Auto (Seitenansicht), Smear-Linien. 48. `fire` — Flammen-Blob (Leuchtfackel), flackert 7 Hz. 49. `barrel` — Fass mit Reifen, Füllstand parametrisch (Sirup `accent` / Wasser `water`). 50. `syrup_bottle` — Flasche mit Ahornblatt-Etikett. 51. `water_drop` — Tropfen, fällt mit Squash. 52. `ladder` — Leiter, kippt. 53. `mask_domino`, 54. `handcuffs`, 55. `safe`, 56. `getaway_car`, 57. `bridge` (Segmente einzeln abziehbar), 58. `wheelbarrow`.

**Woche 2–3 — Themen-Sets**
59. Höhle: `helmet_lamp`, `rope`, `flashlight` (Kegel alpha 0.25), `bat`, `stalactite_set`, `narrow_passage` (Lücke parametrisch, „stuck“). 60. Tiere: `animal_kit` (parametrischer Säugetier-Baukasten: Rumpf-Ellipse, Kopf, Ohrform, Schwanz, Beinlänge, Fleckenmuster → Tapir, Ziege, Hund), `bird_kit`, `fish_kit`, `bug_kit` (Segmentzahl, Beinpaare), `paw`, `feather`, `egg`. 61. Weltraum: `rocket`, `planet_ring`, `satellite`, `space_helmet`. 62. Geschichte: `scroll` (Pergament, Zitat), `sword_shield`, `column`, `ship`, `quill`. 63. Ozean: `submarine`, `anchor`, `bubbles`, `jellyfish`, `treasure_chest`. 64. Medizin: `syringe` (Kolben bewegt sich), `heart_anatomy` (pulsiert, kein Blut), `microbe` (dreht), `pill`, `stethoscope`, `tooth`. 65. Gericht: `scales` (wippt), `gavel`, `file_folder`. 66. Essen: `food_kit` (Banane, Brot, Flasche, Pizza-Stück).

**Effekte (`fx.py`)**: 67. `confetti` (3 Formen, Gravitation), 68. `sparkle` (Glanzsterne), 69. `shock_lines` (Schock-/Tempolinien um ein Objekt, ≤ 300 ms), 70. `sweat_drop`, 71. `sneak_trail` (gestrichelte Spur), 72. `spot_cone` (Lichtkegel für Helm/Taschenlampe, folgt `look`), 73. `light_island` (schwenkbare Lichtinsel), Übergänge `peel`, `iris_sticker`, `deck`, `cut`, `fade`.

---

## 8. Kanal

### 8.1 Name — Favorit und Alternativen (Handles und Markenrecherche vor dem Start prüfen; „Cabinet of Curiosities“ als Serientitel wird vermieden)

**Favorit: ODD CABINET (@oddcabinet)** — „odd“ = kurios + Name des Maskottchens, „cabinet“ = Wunderkammer; Serien heißen „Odd Cabinet: Heists“, „Odd Cabinet: Caves“; Serienetikett `CURIOUS HEISTS · 017`; Odd ist „Exhibit No. 0“.

Alternativen (der Nutzer entscheidet):
1. **Hall of Huh** (@hallofhuh) — die Reaktion als Name, sehr TikTok, leicht zu sprechen.
2. **Curio Countdown** (@curiocountdown) — nennt das Format, alliteriert, gut für YouTube-Suche.
3. **The Magpie List** (@magpielist) — Maskottchen-bezogen, „list“ signalisiert Top-5/Top-10.
4. **Strangely Ranked** (@strangelyranked) — staunend-humorvoll, beschreibt das Countdown-Prinzip.
5. **Exhibit Zero** (@exhibitzero) — Odd als Exponat Nr. 0, Archivnummer je Video als Kommentar-Haken.
6. **Pica Picks** (@picapicks) — Latein-Name der Elster, „picks“ = Auswahl und Stehlen zugleich.

### 8.2 Profilbild, Banner, Wasserzeichen (`brand.py`, prozedural)

- **Profilbild** 1000 × 1000: Kreis in Wunder-Gold #F2B544 auf Tinte #171A28, darin Odds Kopf in 3/4-Ansicht, der von unten über den Kreisrand lugt (Pose `peek`), eine Braue hoch, Pupillen 1.4, Flügelschimmer in Elsterblau sichtbar; weißer Sticker-Rand 24 px um Kreis und Kopf, Schatten. Kein Text; bei 48 px bleiben Goldkreis, dunkler Kopf, zwei Augen, Elfenbein-Brauen und Schnabel lesbar.
- **Banner** (YouTube 2560 × 1440): Odd sitzt auf der #1-Karte und hält den Schnabel an eine Lupe, daneben fünf Album-Fächer, Kanalname in Bricolage 800.
- **Wasserzeichen** im Video: Odd-Kopf 44 px + Handle DM Mono 24 px, zweizeilig oben rechts in `fmt.watermark`, alpha 0.62.

---

## 9. Beispiel-Storyboard „Top 5 Curious Heists“ (Projekt `2026-10-07_curious-heists`, 82.8 s, Thema heist, Bett heist_tiptoe, Odd im Kostüm thief; Zeiten aus `plan.json`)

1. **Hook (0.0–2.6 s, Kulisse spotlight):** Ab Frame 1 steht die Sticker-Headline „Five real heists that SOUND MADE UP.“ (Schlüsselwort Gold), bei 0.12 s ploppen `money_bag`, `diamond` und `cheese_wheel` mit 70 ms Versatz als Sticker-Reihe auf, bei 0.4 s lugt Odd mit Domino-Maske von unten links herein (`peek`) und schielt auf den Käse; `hook_hit` bei 0.05 s, das Serienetikett „CURIOUS HEISTS · 017“ tippt sich in den letzten 0.5 s ein.
2. **#5 Einflug (2.6–4.3 s):** Peel der Hook-Seite, Odd fliegt von oben rechts mit der goldenen #5 im Schnabel ein und lässt sie auf die Bildmitte fallen (`card_hit#5` auf „Number“, 24 Konfetti), der Titel „The Great Cheese Robbery“ staggert darunter ein, die Karte dockt oben links an, die Meta-Pille „LONDON · 2024“ tippt sich ein.
3. **#5 Käse (4.3–18.7 s, Kulisse warehouse, Odd als `chef` in `think`):** Auf „cheddar“ fällt ein riesiger `cheese_wheel`-Sticker als Hero herunter (Squash, `boing`), auf „22“ zählt die Stat-Plakette „22 t OF CHEDDAR“ hoch, auf „300,000“ landet das Schlagwort „300,000 POUNDS“, auf „delivered“ schiebt sich ein `truck` mit Smear durch das Hero-Feld und verdrängt den Käse in den Begleiter-Slot, auf „money“ verblasst der `money`-Sticker zu einem Stempel „NEVER PAID“ und Odd macht `facepalm` (`hmm`).
4. **#4 Mona Lisa (18.7–32.6 s, Kulisse museum, Odd `thief` in `sneak`):** Peel, die Karte öffnet sich per Sticker-Iris und die Ziffer rollt als Zählwerk von 5 auf 4 (`tick`, `card_hit#4`), Titel „The Mona Lisa Walkout“, Meta „PARIS · 1911“; auf „Mona“ poppt das `painting` im Rahmen auf, Odd zieht es als Sticker ab (Peel) und schleicht mit dem Bild am Schnabel, auf „Nobody“ landet „NOBODY NOTICED“, auf „Police“ gleitet der `police`-Sticker herein, auf „Picasso“ `shock` mit abploppenden Scheitelfedern, auf „two“ zählt „2 years MISSING“ und ein `calendar` blättert zweimal.
5. **#3 Antwerpen (32.6–45.8 s, Kulisse vault):** Elster-Lieferung der #3 (`card_hit#3`), Titel „The Antwerp Sandwich“, Meta „ANTWERP · 2003“; auf „security“ öffnet sich die `vault_door`, zehn Laserlinien in Laser-Mint ploppen nacheinander aus (`shiny`, Stagger 70 ms), auf „diamonds“ regnen `diamond`-Sticker (Konfetti-Mechanik, 12 Stück), die Stat „$100M+ IN DIAMONDS“ zählt, Schlagwort „10 LAYERS“.
6. **#3 Beat „forest“ (ab 41 s):** Odd fliegt als Elster-Lieferung durchs Bild, hinter ihr wechselt die Kulisse per Cut zu `forest`; ein Müllsack-Sticker, daraus ploppt auf „sandwich“ das angebissene `sandwich` mit DNA-Helix-Chip, Stempel „FILED UNDER WHAT“ schlägt ein (`stamp`), Odd `facepalm`.
7. **#2 Tokio (45.8–60.7 s, Kulisse night_city, Odd `detective` in `point`):** Peel, Zählwerk 3 → 2 (`card_hit#2`), Titel „The Fake Cop of Tokyo“, Meta „TOKYO · 1968“; auf „motorcycle“ gleitet das `motorcycle` mit Smear ein, auf „car“ der Geldtransporter, auf „flare“ poppt `fire` als Begleiter und Odd hält die Lupe darüber (Clip vergrößert die Flamme 1.3×), auf „ran“ rennt Odd mit Smear aus dem Bild (`run`) und kommt zurück, auf „294“ zählt „¥294M GONE“, auf „Never“ landet das Schlagwort „NEVER CAUGHT“ in Koralle mit weißem Rand, dazu `record_stop`.
8. **#1 Ahornsirup (60.7–78.6 s, Kulisse warehouse, Odd `thief` in `cheer`):** Ab 59.2 s Riser mit Trommelwirbel, bei 60.7 s Konfetti-Cut (Blitz, 80 Konfetti), Odd wirft die #1 mit Krone ins Bild (`card_hit#1`, `number_one`), die Album-Leiste füllt das letzte Fach und leuchtet („Album voll“), Titel „The Maple Syrup Heist“, Meta „QUEBEC · 2012“; auf „barrels“ fällt eine Sticker-Reihe aus zwei `barrel` herunter, auf „maple“ poppt die `syrup_bottle` als Begleiter, auf „18“ zählt „$18M OF SYRUP“, auf „strategic“ landet „STRATEGIC RESERVE“ und Odd sagt in einer Sprechblase „Odd.“ (`odd_say`).
9. **#1 Beats „water“ und „climbed“ (ab 71 s):** Auf „water“ fällt ein `water_drop` ins Fass, dessen Füllstand von Sirup-Gold zu Wasserblau kippt (`drip`), Schlagwort „WATER“, Odd `shock`; auf „climbed“ kippt eine `ladder` an das Fass, Odd versteckt sich dahinter (`hide`, nur Augen und Schwanzspitze), auf „fell“ `splash` und ein `sweat_drop`, Odd taucht mit Tropfen auf dem Kopf wieder auf (`boing`).
10. **Outro (78.6–82.8 s, Kulisse cabinet):** Weichblende 400 ms, CTA „Which one would you have pulled off?“ als Sticker-Text 56 px, Odd `wink` mit Maske, `outro_chime` spielt das Odd-Ding als Kalimba, das Profilbild-Sticker-Logo ploppt neben den Kanalnamen, auf dem letzten Frame `end_sting` mit Flügelschlag; die volle Album-Leiste bleibt bis zum Schwarz.

---

## 10. Engine-Anpassungen (konkret, in dieser Reihenfolge)

1. `theme.py`: Paletten aus Abschnitt 3 (inkl. `card_hi`, `mascot_sheen`, `mascot_beak`, `candle`, `wood`, `steel`, `skin`, `paper`, `chalk`, `foam`, `water`), `theme.respect(th)`, `theme.sheet` mit vier Kontrastpaaren.
2. `layout.py` (Hochformat): `title=Rect(70, 664, 940, 84)`, `progress=Rect(560, 286, 250, 44)`, `watermark=Rect(840, 275, 170, 90)`, `caption=Rect(90, 1356, 780, 180)`.
3. `canvas.py`: Modus `rim` (Farb-/Stroke-Override für alle Primitive), optional Skew in `c.tf` (`kx`) für Peel v2.
4. `props.py` / `mascot.py` / `cards.py`: Parameter `mode='color'|'rim'|'silhouette'`; Hüllform je Prop für den Schatten; `sticker()`-Wrapper (Schatten → Rand → Farbe).
5. `fx.transition`: neue Arten `peel`, `iris_sticker`, `deck`; `confetti_burst` mit 3 Formen und Scale-Abgang.
6. `compose.cues`: `card_hit#<rank>` statt `card_hit`; zusätzliche automatische Cues `peel` (t0, −12), `confetti` (t0 + 0.33, −12), `shiny` (t0 + 0.58, −12), `hop` (t0 + 0.40, −12, Variante A), `flap` (t0, −12, Variante A), `riser` (E1.t0 − 1.5, −12), `typewriter` (t0 + 1.70 + i·0.033, ≤ 12), `pop_in` für Hero/Schlagwort/Stat an ihren Ankern, `keyword_slam` für Schlagworte, `stamp` für Stempel; `announce`-Zeilen ohne Untertitel.
7. `mix.py`: vor dem Rendern der Cues `sfx.set_key(music.key(bed_id))`; Respekt-Beats ducken die Musik zusätzlich 6 dB für 2.5 s.
8. `captions.py`: Stil `odd` (aktiv Gold + Pop, gesprochen Elfenbein, kommend alpha 0.55), Unterdrückung für `kind == 'announce'`.
9. `scenes.py`: Ebenenreihenfolge aus 1.4, Push-In 3 %, Lichtinsel, Respekt-Modus über `entry['respect']`/`beat['respect']`.
10. `script.py`: Warnungen für Titel > 24 Zeichen, Ort > 12 Zeichen, Serienetikett > 22 Zeichen, mehr als 1 Stempel oder 1 Sprechblase je Video.

---

## 11. Prüfregeln (`check.py`, Bögen)

- Sicherheitszonen: Text-Marken ≤ 2 % Überlappung mit `top`/`bottom`/`buttons`, Sticker ≤ 25 % (bestehend).
- Kontrast: Warnung < 4.5 : 1, Fehler < 3 : 1; Untertitel-Band ≥ 7 : 1 gegen die tatsächliche Plakette; bei Verstoß Plakette dunkler, nie Schrift kleiner.
- Lesetempo: ≤ 1 neues Bildelement je 1.2 s, Schlagwort ≥ 1.5 s sichtbar, ≤ 6 Sticker je Frame, ≤ 5 Farbtöne.
- Bewegung: höchstens eine große Bewegung je 0.5 s; kein Element steht > 2 s still; kein Blinken > 3 Hz; Shake ≤ 1× je Eintrag.
- Töne: `mix.mask` meldet Töne, die ein Wort um weniger als 8 dB unterschreiten; `pop_in` ≤ 1 je 150 ms.
- Bögen: `mascot.sheet` (120/240/420 px), `props.sheet` (120-px-Silhouettentest, Lichtrichtung oben links), `theme.sheet` (Kontrastpaare), `library/sfx` und `library/music` zum Anhören.
- Telefonansicht (`engine phone`) entscheidet, nicht der Monitor: Hook-Frame 1, Karten-Landung, Mitte jedes Eintrags, Outro.

## 12. Folgen bisher

| Nr. | Projekt | Thema | Dauer | Besonderheiten | Stand |
|---|---|---|---|---|---|
| 001 | `projects/2026-10-07_curious-heists` | heist, Bett `heist_tiptoe`, Odd als `thief` | 82.8 s | Hook „Five real heists that sound made up", 5 Einträge (Käse 2024, Mona Lisa 1911, Antwerpen 2003, Tokio 1968, Ahornsirup 2012), Stats, Schlagworte, Beats (Wasser, Leiter), Skript-Cues `drip`/`splash` | Testvideo mit espeak-Platzhalterstimme; Fakten in `quellen.md` |
