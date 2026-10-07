"""Formate und Sicherheitszonen.

Hochformat 1080x1920 (TikTok, Shorts, Reels) und Querformat 1920x1080 (YouTube).
Alle Zonen in Pixeln. Die Bühne (stage) ist der Bereich für die Szene, darunter die Untertitel.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self): return self.x + self.w / 2
    @property
    def cy(self): return self.y + self.h / 2
    @property
    def x1(self): return self.x + self.w
    @property
    def y1(self): return self.y + self.h

    def inset(self, d):
        return Rect(self.x + d, self.y + d, self.w - 2 * d, self.h - 2 * d)

    def contains(self, x, y):
        return self.x <= x <= self.x1 and self.y <= y <= self.y1


@dataclass
class Format:
    name: str
    W: int
    H: int
    fps: int = 30
    # Sicherheitszonen (dort steht nichts Wichtiges)
    safe_top: float = 0        # Suchleiste / "For You"
    safe_bottom: float = 0     # Kanalname, Caption, Fortschrittsbalken
    safe_left: float = 0
    safe_right: float = 0
    buttons: Rect = None       # rechte Knopfleiste (TikTok), None im Querformat
    # Slots
    stage: Rect = None         # Hauptbühne für die Szene
    title: Rect = None         # Titel-/Schlagwortzeile
    card: Rect = None          # Nummernkarte (Countdown)
    progress: Rect = None      # Fortschrittsanzeige (Punkte/Balken)
    caption: Rect = None       # Untertitel-Band
    watermark: Rect = None     # Kanalzeichen
    label: Rect = None         # Serien-/Themenetikett oben
    scale: float = 1.0         # Schriftgrößen-Faktor relativ zum Hochformat

    @property
    def cx(self): return self.W / 2
    @property
    def cy(self): return self.H / 2
    @property
    def portrait(self): return self.H > self.W
    @property
    def content(self):
        return Rect(self.safe_left, self.safe_top, self.W - self.safe_left - self.safe_right, self.H - self.safe_top - self.safe_bottom)


def portrait() -> Format:
    W, H = 1080, 1920
    return Format(
        name='portrait', W=W, H=H, fps=30,
        safe_top=260, safe_bottom=330, safe_left=60, safe_right=60,
        buttons=Rect(890, 770, 190, 820),
        label=Rect(70, 275, 560, 60),
        card=Rect(70, 350, 300, 300),
        title=Rect(70, 664, 940, 84),
        stage=Rect(60, 340, 960, 1010),
        progress=Rect(560, 286, 250, 44),
        caption=Rect(90, 1356, 780, 180),
        watermark=Rect(840, 275, 170, 90),
        scale=1.0,
    )


def landscape() -> Format:
    W, H = 1920, 1080
    return Format(
        name='landscape', W=W, H=H, fps=30,
        safe_top=60, safe_bottom=90, safe_left=80, safe_right=80,
        buttons=None,
        label=Rect(100, 70, 600, 50),
        card=Rect(100, 140, 260, 260),
        title=Rect(100, 420, 760, 200),
        stage=Rect(640, 90, 1200, 820),
        progress=Rect(100, 1000, 540, 32),
        caption=Rect(550, 880, 820, 120),
        watermark=Rect(1700, 70, 140, 80),
        scale=0.78,
    )


FORMATS = {'portrait': portrait, 'landscape': landscape, 'tiktok': portrait, 'youtube': landscape, '9:16': portrait, '16:9': landscape}


def get_format(name: str = 'portrait') -> Format:
    return FORMATS[name]()
