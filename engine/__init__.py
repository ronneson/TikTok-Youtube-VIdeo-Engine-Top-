"""Top-Listen Video-Engine: zeichnet, vertont und rendert Countdown-Videos komplett aus Code.

Python 3.10+. Zeichnen mit skia-python, Ton mit numpy, Ausgabe mit ffmpeg.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_REV = 1
