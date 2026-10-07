#!/usr/bin/env bash
# Einrichtung auf dem Mac (oder Linux): Python-Pakete, ffmpeg, optional espeak-ng als Platzhalterstimme.
set -e
cd "$(dirname "$0")"
echo "== Python-Pakete"
python3 -m pip install --user -r requirements.txt || python3 -m pip install --break-system-packages -r requirements.txt
if ! command -v ffmpeg >/dev/null; then
  echo "== ffmpeg fehlt"; if command -v brew >/dev/null; then brew install ffmpeg; else echo "bitte ffmpeg installieren (https://ffmpeg.org)"; fi
fi
if ! command -v espeak-ng >/dev/null; then
  echo "== espeak-ng fehlt (nur für die Platzhalterstimme nötig)"; if command -v brew >/dev/null; then brew install espeak-ng || true; fi
fi
mkdir -p config/keys projects library/sheets
echo "== Status"; python3 -m engine status
echo
echo "ElevenLabs: Schlüssel in config/keys/elevenlabs.txt legen (eine Zeile) und voice_id in config/engine.json eintragen:"
echo '  python3 -c "from engine import config; config.save_value(\".\", \"voice.voice_id\", \"DEINE_VOICE_ID\")"'
