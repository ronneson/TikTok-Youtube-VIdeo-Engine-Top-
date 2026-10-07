# Top-Listen Video-Engine

Eine Engine, die aus einem Skript (`script.json`) ein fertiges Countdown-Video baut: Stimme (ElevenLabs), Wort-für-Wort-Untertitel, animierte Szenen mit Maskottchen und Piktogrammen, Nummernkarten, prozedurale Töne und Musik, Mastering auf −14 LUFS, Rendern mit ffmpeg. Hochformat 1080×1920 (TikTok, Shorts, Reels: 60–90 s) und Querformat 1920×1080 (YouTube: 8–12 min).

Alles entsteht aus Code: keine Stock-Clips, keine KI-Bilder. Gestaltung siehe `STIL.md`, Aufbau siehe `ARCHITEKTUR.md`.

## Einrichten

```bash
./install.sh                      # Pakete, ffmpeg, espeak-ng (Platzhalterstimme)
python3 -m engine status          # zeigt, was fehlt
```

ElevenLabs: den API-Schlüssel als **eine Zeile** in `config/keys/elevenlabs.txt` legen (oder Umgebungsvariable `ELEVENLABS_API_KEY`) und die Stimme eintragen:

```bash
python3 -m engine voices          # Stimmen des Kontos mit voice_id
python3 - <<'EOF2'
from engine import config
config.save_value('.', 'voice.voice_id', 'DEINE_VOICE_ID')
EOF2
```

`config/engine.json` überschreibt die Standardwerte aus `engine/config.py` (Stimme, Mischung, Look, Rendern). Nur eintragen, was abweichen soll.

## Ein Video bauen

```bash
python3 -m engine new curious-heists "Top 5 Curious Heists" --theme heist --series "CURIOUS HEISTS"
#  -> projects/<datum>_curious-heists/script.json  (Vorlage; Skript schreiben, siehe unten)
python3 -m engine words  curious-heists     # geschätzte Zeiten, Warnungen (kostet nichts)
python3 -m engine sheet  curious-heists     # Kontaktbogen check/sheet.jpg (geschätzte Zeiten)
python3 -m engine tts    curious-heists     # Stimme (ElevenLabs: kostet Credits; espeak: Platzhalter)
python3 -m engine voice  curious-heists     # Pausen straffen, Tempo, Klang -> voice.wav, words.json
python3 -m engine plan   curious-heists     # plan.json (Szenen, Töne) + mix.wav (Musik, Töne, Mastering)
python3 -m engine check  curious-heists     # Sicherheitszonen, Untertitel-Kontrast
python3 -m engine phone  curious-heists 3.0 20.5 "E3.1:money"   # Telefonansicht (check/phone_*.png)
python3 -m engine render curious-heists --workers 4   # -> projects/.../curious-heists.mp4
```

- `render --scale 0.5` rendert eine kleine Vorschau (`<slug>_preview.mp4`) in Sekunden.
- `render --budget 150` hört nach 150 s auf, neue Segmente zu beginnen; der nächste Aufruf macht weiter (fertige Segmente bleiben).
- `stills <projekt> 1.5 "E5.1:syrup" 40` Standbilder nach Sekunden oder Wort; `seq <projekt> "E4.0" --span 1.4` Bildfolge um einen Übergang.
- `loudness <datei>` misst LUFS und True Peak. `mask <projekt>` prüft, ob ein Ton die Stimme verdeckt.
- `sounds`, `music`, `mascot`, `props`, `palette` rendern Übersichten nach `library/` (Töne/Musik als WAV zum Anhören).

Ein geänderter **Text** braucht `tts` + `voice` neu (Credits). Geänderte **Bilder, Töne, Musik** brauchen nur `plan` + `render`.

## script.json

```json
{
 "title": "Top 5 Curious Heists", "slug": "curious-heists",
 "format": "portrait", "lang": "en", "theme": "heist", "series": "CURIOUS HEISTS",
 "caption": "Five heists too strange to be fiction. #heist #history", "hashtags": ["#curious", "#top5"],
 "tempo": 1.0, "tail": 2.0, "music": "auto", "announce": "number_title",
 "hook":    {"lines": ["These five heists were too dumb to be fake."], "keyword": "TOO DUMB TO BE FAKE",
             "visual": {"backdrop": "spotlight", "mascot": {"pose": "peek"}}},
 "entries": [
   {"rank": 5, "title": "The Maple Syrup Heist", "place": "Quebec, Canada", "year": 2012,
    "lines": ["In 2012, thieves drained 18 million dollars of maple syrup from Canada's strategic reserve.",
              {"text": "They refilled the barrels with water.", "gap_after": 0.4}],
    "stat": {"value": "$18M", "label": "OF SYRUP", "at": "18"},
    "visual": {"backdrop": "warehouse", "props": ["barrel", {"name": "water_drop", "at": "water", "anim": "pop"}],
               "mascot": {"pose": "sneak", "costume": "thief"}, "keywords": [{"text": "18 MILLION", "at": "18"}]},
    "cues": [["water", "drip", -10]]}
 ],
 "outro": {"lines": ["Which one would you have pulled off?"], "visual": {"mascot": {"pose": "wink"}}},
 "sources": [{"claim": "18 million dollars", "url": "https://..."}]
}
```

- **Zeilen** (`lines`): ein Gedanke je Zeile (ein bis drei kurze Sätze). `gap_after` setzt eine bewusste Pause in Sekunden.
- **IDs:** Hook `H1, H2…`, Eintrag `E5.0` (Ansage „Number five. Titel."), `E5.1…`, Outro `O1…`. Anker für Zeiten: `"syrup"`, `"syrup$"` (Wortende), `"syrup+0.2"`, `"E5.1:18"`, `"again#2"`.
- **announce**: `number_title` (Standard), `number`, `none`; je Eintrag überschreibbar mit `"announce": "Number five."`.
- **visual**: Kulisse (`backdrop`), Piktogramme (`props`: Name oder `{name, x, y, size, at, anim}`), Maskottchen (`mascot`: `pose, costume, expr, x, y, size, at`), Schlagworte (`keywords`), Bildwechsel innerhalb des Eintrags (`beats`: `[{at, props, mascot, backdrop}]`), Übergang (`transition`: wipe, slide, iris, zoom, flip, blinds, fade). `x, y` als Anteile der Bühne.
- **stat**: Zahl, die beim Anker `at` hochzählt. **cues**: eigene Töne `[anker, ton, dB]`.
- Länge: Hochformat 60–90 s ≈ 165–200 Wörter (ElevenLabs ≈ 150 Wörter/min). Querformat 8–12 min ≈ 1.300–1.800 Wörter, Top 10 mit 2–4 `beats` je Eintrag.
- Mehr Kontrolle: eine `scenes.py` im Projektordner darf eigene Zeichenfunktionen liefern (siehe `ARCHITEKTUR.md`).

## Ordner

`engine/` Code · `assets/fonts/` Schriften · `config/` Einstellungen und Schlüssel (`keys/` nie teilen) · `projects/` Videos · `library/` Töne, Musik, Übersichten · `tests/` Tests (`python3 -m pytest tests/ -q`).

## Grenzen und Hinweise

- Die espeak-Stimme ist nur ein Platzhalter für Timing und Vorschau; das echte Video entsteht mit ElevenLabs.
- Fakten werden nicht von der Engine geprüft: Quellen in `sources` eintragen, Behauptungen vor dem Vertonen prüfen.
- Rendern: etwa 4–6 s Video pro Sekunde Rechenzeit mit 4 Prozessen (Hochformat, volle Größe).
