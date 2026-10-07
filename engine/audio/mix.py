"""Mischung und Mastering: Stimme + Musikbett (Ducking) + Töne -> mix.wav.

Ablauf von build():
 1. Komposition laden (Szenen, Wörter, Cues); voice.wav lesen, auf mix.voice_lufs bringen und auf die
    Videodauer (comp.duration = Stimme + tail) füllen.
 2. Musikbett aus engine.audio.music (fehlt das Modul: generierter Platzhalter-Pad), Pegel per Ducking an die
    Stimme koppeln: beim Sprechen mix.music_db unter dem Stimmpegel, ohne Stimme mix.music_solo_db.
 3. Töne aus engine.audio.sfx (fehlt Modul oder ID: Platzhalter-Blip) an die Cue-Zeiten setzen; liegt ein Ton
    auf einem Wort, bleibt er mindestens 6 dB unter dem Wortpegel (Maskierungsregel).
 4. Summe auf mix.master_lufs bringen, Lookahead-Limiter hält den True Peak unter mix.true_peak_db,
    Kontrollmessung.
 5. mix.wav schreiben (Stereo, 48 kHz, Länge exakt = Videodauer), optional stems/ (voice, music, sfx).

Alle Signale float32 bei SR = 48000, Stereo als (n, 2). Pegel in dB sind dBFS (RMS) bzw. LUFS.
Die Module music und sfx werden tolerant importiert, damit die Pipeline auch ohne sie läuft.
"""
from __future__ import annotations
import importlib
import os
import tempfile
import zlib
import numpy as np
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from scipy.signal import resample_poly, sosfilt
from . import SR, wav

HOP = 240               # Steuerraster des Duckings: 5 ms bei 48 kHz
RMS_WIN = 0.02          # Fenster der Stimm-Hüllkurve in s
MASK_DB = 6.0           # Ton auf einem Wort: höchstens so viele dB unter dem Wortpegel
MASK_WARN_DB = 8.0      # mask(): Wörter melden, deren Abstand zu einem Ton darunter liegt
TP_MARGIN_DB = 0.15     # Sicherheitsabstand des Limiters zur True-Peak-Grenze
GATE_DB = -40.0         # unter diesem RMS zählt die Stimme nicht zum Sprechpegel

_MIX_DEFAULTS = {
    'voice_lufs': -16.0, 'master_lufs': -14.0, 'true_peak_db': -1.0,
    'music_db': -14.0, 'music_solo_db': -6.0, 'sfx_db': -8.0,
    'duck_attack': 0.08, 'duck_release': 0.45, 'duck_lookahead': 0.05,
    'tail': 2.0, 'music': 'auto', 'stems': False,
}


# ----------------------------------------------------------------------------------------------------------------
# Öffentliche Einstiege
# ----------------------------------------------------------------------------------------------------------------

def build(project_dir: str, cfg: dict, root: str = None, music: str = None) -> dict:
    """Mischung eines Projekts erzeugen: voice.wav + Musik + Töne -> mix.wav. Gibt Messwerte zurück.

    music: Bett-ID, 'auto' (nach Thema) oder 'none'; None nimmt script.json bzw. cfg['mix']['music'].
    Rückgabe u. a.: duration, lufs, true_peak, music ('placeholder' ohne music-Modul), music_gain_db, cues,
    missing_sfx, masked, voice_lufs, master_gain_db, limiter_db, stems, warnings.
    """
    from .. import compose
    mcfg = _mix_cfg(cfg)
    comp = compose.load(project_dir, root)
    warnings = []
    n_total = max(1, int(round(comp.duration * SR)))

    # 1. Stimme: lesen, auf voice_lufs bringen, auf die Videodauer füllen
    voice_raw, voice_dur = _load_voice(project_dir)
    if voice_dur > comp.duration + 0.01:
        warnings.append(f"voice.wav ({voice_dur:.2f} s) ist länger als das Video ({comp.duration:.2f} s): wird abgeschnitten")
    voice_m = _lufs_measure(voice_raw, fast=True)
    voice_gain_db = _clamp(mcfg['voice_lufs'] - voice_m['lufs'], -24.0, 24.0) if _finite(voice_m['lufs']) else 0.0
    voice = _fit(voice_raw * wav.db(voice_gain_db), n_total)
    if len(voice_raw) > n_total:
        voice = _fade_edges(voice, 0.0, 0.01)       # harter Schnitt am Videoende: 10 ms ausblenden
    spans = [(w.t0, w.t1) for w in comp.tl.words]
    ref_db = voice_level_db(voice, spans)

    # 2. Musik: Bett holen, Ducking-Kurve anwenden
    sections = sections_from(comp)
    seed = _seed(comp)
    bed, music_name = _music_bed(comp, mcfg, music, comp.duration, seed, sections, warnings)
    bed = _fit(wav.to_stereo(bed), n_total)
    bed_db = wav.rms_db(bed) if np.any(bed) else None
    if bed_db is None or bed_db < -90:
        music_st = np.zeros((n_total, 2), np.float32)
        music_gain_db = None
        duck_db = None
    else:
        target = duck_curve(voice, mcfg, ref_db)
        gain_db = target - bed_db
        music_st = (bed * wav.db(gain_db)[:, None]).astype(np.float32)
        music_st = _fade_edges(music_st, 0.3, 0.5)
        music_gain_db = float(np.mean(gain_db))
        solo_db = ref_db + mcfg['music_solo_db']
        duck_db = float(solo_db - np.min(target))

    # 3. Töne: Cues planen (Pegel, Maskierung) und einrechnen
    placed, missing, skipped = _plan_cues(comp, mcfg, voice, ref_db, n_total)
    sfx_st = _render_cues(placed, n_total)
    for sk in skipped:
        warnings.append(f"Cue {sk['sfx']} bei {sk['t']:.2f} s liegt außerhalb des Videos (0..{comp.duration:.2f} s)")
    if missing:
        warnings.append("Platzhalter-Töne für: " + ', '.join(missing))
    if music_name == 'placeholder':
        warnings.append("Platzhalter-Musikbett (engine.audio.music fehlt oder scheiterte)")

    # 4. Mastering: Lautheit, Limiter, Kontrolle
    voice_st = wav.to_stereo(voice)
    total = (voice_st + music_st + sfx_st).astype(np.float32)
    mastered, m = master(total, mcfg['master_lufs'], mcfg['true_peak_db'])

    # 5. Schreiben
    out_path = os.path.join(project_dir, 'mix.wav')
    wav.write(out_path, mastered, SR)
    stems_dir = None
    if mcfg.get('stems'):
        stems_dir = os.path.join(project_dir, 'stems')
        os.makedirs(stems_dir, exist_ok=True)
        g = wav.db(m['master_gain_db'])
        wav.write(os.path.join(stems_dir, 'voice_stem.wav'), voice_st * g, SR)
        wav.write(os.path.join(stems_dir, 'music_stem.wav'), music_st * g, SR)
        wav.write(os.path.join(stems_dir, 'sfx_stem.wav'), sfx_st * g, SR)

    return {
        'file': out_path,
        'duration': round(n_total / SR, 3),
        'samples': n_total,
        'lufs': _r(m['lufs']),
        'true_peak': _r(m['true_peak']),
        'lufs_pre': _r(m['lufs_pre']),
        'master_gain_db': _r(m['master_gain_db']),
        'limiter_db': _r(m['limiter_db']),
        'measure': m['source'],
        'voice_lufs': _r(voice_m['lufs']),
        'voice_gain_db': _r(voice_gain_db),
        'voice_ref_db': _r(ref_db),
        'music': music_name,
        'music_gain_db': _r(music_gain_db),
        'music_duck_db': _r(duck_db),
        'cues': len(placed),
        'masked': sum(1 for c in placed if c['masked']),
        'missing_sfx': missing,
        'skipped_cues': len(skipped),
        'stems': stems_dir,
        'warnings': warnings,
    }


def mask(project_dir: str, cfg: dict, root: str = None, min_db: float = MASK_WARN_DB) -> list:
    """Wörter, bei denen ein Ton weniger als min_db (8 dB) unter dem Wortpegel liegt, für den Befehl 'mask'.

    Rechnet die Töne wie build() (Pegel, Maskierungsregel), schreibt aber nichts. Ein Ton zählt zu jedem Wort,
    dessen Spanne er mit seiner wirksamen Dauer überlappt. Ohne voice.wav gilt der Sprechpegel als Wortpegel.
    Rückgabe: [{'w', 'line', 't0', 't1', 'word_db', 'sfx', 't', 'sfx_db', 'distance_db', 'why'}], nach Zeit sortiert.
    """
    from .. import compose
    mcfg = _mix_cfg(cfg)
    comp = compose.load(project_dir, root)
    n_total = max(1, int(round(comp.duration * SR)))
    words = comp.tl.words
    voice = None
    ref_db = mcfg['voice_lufs'] - 2.0     # grobe Annahme: RMS beim Sprechen etwas über der Lautheit
    if os.path.exists(os.path.join(project_dir, 'voice.wav')):
        voice_raw, _ = _load_voice(project_dir)
        vm = _lufs_measure(voice_raw, fast=True)
        g = _clamp(mcfg['voice_lufs'] - vm['lufs'], -24.0, 24.0) if _finite(vm['lufs']) else 0.0
        voice = _fit(voice_raw * wav.db(g), n_total)
        ref_db = voice_level_db(voice, [(w.t0, w.t1) for w in words])
    placed, _, _ = _plan_cues(comp, mcfg, voice, ref_db, n_total)
    levels = _word_levels(voice, words, ref_db)
    out = []
    for c in placed:
        t0, t1 = c['t'], c['t'] + c['dur']
        for w, wdb in zip(words, levels):
            if w.t1 <= t0 or w.t0 >= t1:
                continue
            dist = wdb - c['target_db']
            if dist < min_db:
                out.append({'w': w.w, 'line': w.line, 't0': round(w.t0, 3), 't1': round(w.t1, 3), 'word_db': _r(wdb),
                            'sfx': c['sfx'], 't': round(c['t'], 3), 'sfx_db': _r(c['target_db']),
                            'distance_db': _r(dist), 'why': c['why']})
    return sorted(out, key=lambda d: (d['t0'], d['t']))


# ----------------------------------------------------------------------------------------------------------------
# Ducking
# ----------------------------------------------------------------------------------------------------------------

def duck_curve(voice: np.ndarray, mix_cfg: dict, ref_db: float = None, sr: int = SR) -> np.ndarray:
    """Zielpegel der Musik in dBFS (RMS) je Sample, aus der Stimme abgeleitet.

    Hüllkurve der Stimme: RMS über 20 ms, geglättet mit duck_attack/duck_release. Beim Sprechen liegt die Musik
    music_db unter dem (träge verfolgten) Stimmpegel, ohne Stimme music_solo_db unter dem Sprechpegel ref_db.
    Dazwischen blendet eine Sprach-Wahrscheinlichkeit weich (smoothstep über 12 dB), ein kleiner Vorlauf
    (duck_lookahead) senkt die Musik schon kurz vor dem ersten Wort. Die Kurve ist am Steuerraster (5 ms)
    gerechnet und linear auf Samples interpoliert, also frei von Sprüngen.
    """
    mcfg = _mix_cfg({'mix': mix_cfg})
    v = wav.to_mono(np.asarray(voice, np.float32))
    n = len(v)
    if n == 0:
        return np.zeros(0, np.float32)
    hop = max(1, int(round(HOP * sr / SR)))
    win = max(1, int(round(RMS_WIN * sr)))
    if ref_db is None:
        ref_db = voice_level_db(v, sr=sr)
    idx = np.arange(0, n, hop)
    env = _rms_at(v, idx, win)
    env = _ar_smooth(env, mcfg['duck_attack'], mcfg['duck_release'], hop, sr)
    env_db = 20.0 * np.log10(env + 1e-6)
    # Sprach-Wahrscheinlichkeit: 0 unter ref-18 dB, 1 über ref-9 dB, dazwischen smoothstep. Mit der
    # Release-Hüllkurve ergibt das: kurze Pausen halten die Absenkung, nach dem Sprechen ist die Musik in
    # etwa einer Sekunde wieder oben.
    lo, hi = ref_db - 18.0, ref_db - 9.0
    p = np.clip((env_db - lo) / (hi - lo), 0.0, 1.0)
    p = p * p * (3.0 - 2.0 * p)
    # Träger Stimmpegel für den Musikpegel beim Sprechen: folgt der Hüllkurve nur während der Sprache
    # (sonst gehalten), beginnt beim Sprechpegel und bleibt in einem engen Band darum (kein Pumpen)
    lvl_db = _ar_smooth(env_db, 0.25, 0.8, hop, sr, gate=p > 0.5, start=ref_db)
    lvl_db = np.clip(lvl_db, ref_db - 9.0, ref_db + 6.0)
    solo = ref_db + mcfg['music_solo_db']
    speak = np.minimum(lvl_db + mcfg['music_db'], solo)
    target = solo * (1.0 - p) + speak * p
    # Vorlauf: das Minimum der nächsten duck_lookahead Sekunden gilt schon jetzt
    la = int(round(mcfg['duck_lookahead'] * sr / hop))
    if la > 0 and len(target) > 1:
        ext = np.concatenate([target, np.full(la, target[-1])])
        target = np.lib.stride_tricks.sliding_window_view(ext, la + 1).min(axis=1)
    return np.interp(np.arange(n), idx, target).astype(np.float32)


def voice_level_db(voice: np.ndarray, spans: list = None, sr: int = SR) -> float:
    """Sprechpegel in dBFS (RMS): über die Wortspannen [(t0, t1), ...], sonst über alle 20-ms-Abschnitte über -40 dBFS."""
    v = wav.to_mono(np.asarray(voice, np.float32)).astype(np.float64)
    n = len(v)
    if n == 0:
        return -60.0
    if spans:
        sel = np.zeros(n, bool)
        for t0, t1 in spans:
            a, b = max(0, int(t0 * sr)), min(n, int(np.ceil(t1 * sr)))
            if b > a:
                sel[a:b] = True
        if sel.any():
            return float(10.0 * np.log10(np.mean(v[sel] ** 2) + 1e-12))
    win = max(1, int(round(RMS_WIN * sr)))
    m = n // win
    if m == 0:
        return float(10.0 * np.log10(np.mean(v ** 2) + 1e-12))
    blocks = np.mean(v[:m * win].reshape(m, win) ** 2, axis=1)
    loud = blocks[10.0 * np.log10(blocks + 1e-12) > GATE_DB]
    if len(loud) == 0:
        return float(10.0 * np.log10(blocks.max() + 1e-12))
    return float(10.0 * np.log10(loud.mean() + 1e-12))


def _rms_at(x: np.ndarray, idx: np.ndarray, win: int) -> np.ndarray:
    """RMS eines zentrierten Fensters der Länge win an den Positionen idx (über kumulierte Quadratsumme)."""
    n = len(x)
    cs = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    a = np.clip(idx - win // 2, 0, n)
    b = np.clip(idx + (win - win // 2), 0, n)
    return np.sqrt((cs[b] - cs[a]) / np.maximum(1, b - a))


def _ar_smooth(x: np.ndarray, attack: float, release: float, hop: int, sr: int, gate=None, start: float = None) -> np.ndarray:
    """Hüllkurvenfolger mit getrennten Zeitkonstanten für Anstieg (attack) und Abfall (release), am Steuerraster.

    gate: optionale Bool-Folge; wo sie False ist, wird der Wert gehalten. start: Anfangswert (sonst x[0]).
    """
    ca = float(np.exp(-hop / (max(1e-4, attack) * sr)))
    cr = float(np.exp(-hop / (max(1e-4, release) * sr)))
    out = np.empty(len(x), np.float64)
    e = float(start) if start is not None else (float(x[0]) if len(x) else 0.0)
    g = gate.tolist() if gate is not None else None
    for i, v in enumerate(x.tolist()):
        if g is None or g[i]:
            c = ca if v > e else cr
            e = c * e + (1.0 - c) * v
        out[i] = e
    return out


# ----------------------------------------------------------------------------------------------------------------
# Musik
# ----------------------------------------------------------------------------------------------------------------

def sections_from(comp) -> list:
    """Abschnitte für music.render aus den Szenen: [{'t0', 't1', 'kind', 'rank', 'energy'}].

    Energie: hook 0.6, Einträge von 0.5 (höchste Nummer) steigend bis 0.9 bei Nummer 1, outro 0.4.
    """
    ranks = [sc.rank for sc in comp.scenes if sc.kind == 'entry' and sc.rank]
    top = max(ranks) if ranks else 1
    out = []
    for sc in comp.scenes:
        if sc.kind == 'hook':
            e = 0.6
        elif sc.kind == 'entry':
            r = sc.rank or top
            e = 0.9 if r == 1 else 0.5 + 0.4 * (top - r) / max(1, top - 1)
        else:
            e = 0.4
        out.append({'t0': round(sc.t0, 3), 't1': round(sc.t1, 3), 'kind': sc.kind, 'rank': sc.rank, 'energy': round(e, 3)})
    return out


def placeholder_bed(duration: float, seed: int = 0, sr: int = SR, level_db: float = -30.0) -> np.ndarray:
    """Leises Platzhalterbett: weicher Sinus-Pad-Akkord aus drei Tönen mit langsamer Lautstärke-LFO.

    Stereo durch gegenläufige, langsame Phasenmodulation (bleibt monokompatibel: keine Auslöschung),
    auf level_db (RMS je Kanal) normiert, deterministisch aus seed. Die Teiltöne bleiben unter 600 Hz,
    darum wird bei sr/4 gerechnet und 4-fach hochgetastet (ein 90-s-Bett in deutlich unter einer Sekunde).
    """
    n = max(1, int(round(duration * sr)))
    up = 4
    n4 = -(-n // up)
    t = np.arange(n4, dtype=np.float64) * (up / sr)
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    root = float(rng.choice([98.0, 110.0, 123.47, 130.81]))     # G2, A2, H2, C3
    third = 1.2 if rng.random() < 0.5 else 1.25                 # kleine oder große Terz
    out = np.zeros((n4, 2), np.float64)
    for i, f in enumerate((root, root * third, root * 1.5)):
        ph = rng.random() * 2 * np.pi
        lfo = 0.65 + 0.35 * np.sin(2 * np.pi * (0.04 + 0.015 * i) * t + ph)
        wob = 0.6 * np.sin(2 * np.pi * (0.3 + 0.07 * i) * t + ph)     # ±0,6 rad: nie gegenphasig
        for ch, sign in ((0, 1.0), (1, -1.0)):
            sw = np.sin(2 * np.pi * f * t + sign * wob)
            cw = np.cos(2 * np.pi * f * t + sign * wob)
            # sin 2w = 2 sin w cos w, sin 3w = sin w (3 - 4 sin² w): zwei transzendente Aufrufe statt drei
            out[:, ch] += lfo * (sw + 0.5 * sw * cw + 0.08 * sw * (3.0 - 4.0 * sw * sw))
    out = resample_poly(out, up, 1, axis=0)[:n]
    fade = min(n, int(sr * 1.0))
    out[:fade] *= np.linspace(0.0, 1.0, fade)[:, None]
    rms = float(np.sqrt(np.mean(out ** 2)))
    out *= wav.db(level_db) / max(rms, 1e-9)
    return out.astype(np.float32)


def _music_bed(comp, mcfg: dict, music, duration: float, seed: int, sections: list, warnings: list) -> tuple:
    """Musikbett (stereo) und sein Name: aus engine.audio.music, sonst Platzhalter; 'none' ergibt Stille."""
    sel = music
    if sel is None:
        s = comp.script.get('music')
        sel = s if s not in (None, '', 'auto') else mcfg.get('music', 'auto')
    if str(sel).lower() in ('none', 'off', 'no', 'false', '0'):
        return np.zeros((1, 2), np.float32), 'none'
    mod = _optional('music')
    if mod is not None:
        try:
            bed_id = mod.pick(comp.theme_name) if str(sel) == 'auto' else str(sel)
            bed = np.asarray(mod.render(bed_id, duration, seed=seed, sections=sections), np.float32)
            if bed.size and np.isfinite(bed).all():
                return bed, bed_id
            warnings.append(f"music.render({bed_id!r}) lieferte kein brauchbares Signal")
        except Exception as e:  # Modul da, aber kaputt oder ID unbekannt: Pipeline darf nicht stehen bleiben
            warnings.append(f"music: {type(e).__name__}: {e}")
    return placeholder_bed(duration, seed), 'placeholder'


def _seed(comp) -> int:
    """Deterministischer Seed des Projekts: script['seed'] oder CRC des Slugs."""
    s = comp.script.get('seed')
    if s is not None:
        try:
            return int(s)
        except (TypeError, ValueError):
            return zlib.crc32(str(s).encode('utf-8')) & 0xFFFF
    return zlib.crc32(str(comp.script.get('slug', 'x')).encode('utf-8')) & 0xFFFF


# ----------------------------------------------------------------------------------------------------------------
# Töne
# ----------------------------------------------------------------------------------------------------------------

def placeholder_blip(sr: int = SR, freq: float = 1200.0, dur: float = 0.06, tau: float = 0.015) -> np.ndarray:
    """Platzhalterton: kurzer Sinus-Blip (60 ms, 1200 Hz) mit Exponentialhüllkurve, stereo."""
    n = max(8, int(round(dur * sr)))
    t = np.arange(n, dtype=np.float64) / sr
    x = 0.5 * np.sin(2 * np.pi * freq * t) * np.exp(-t / tau)
    x[:8] *= np.linspace(0.0, 1.0, 8)
    return wav.to_stereo(x.astype(np.float32))


def _sound(sfx_id: str, mod, cache: dict, missing: list) -> tuple:
    """Klang zu einer ID: (stereo, Pegel dB, wirksame Dauer s), aus sfx.render oder als Platzhalter."""
    if sfx_id in cache:
        return cache[sfx_id]
    snd = None
    if mod is not None:
        try:
            snd = np.asarray(mod.render(sfx_id), np.float32)
            if not snd.size or not np.isfinite(snd).all():
                snd = None
        except Exception:
            snd = None
    if snd is None:
        if sfx_id not in missing:
            missing.append(sfx_id)
        snd = placeholder_blip()
    snd = wav.to_stereo(snd)
    cache[sfx_id] = (snd, _level_db(snd), _active_dur(snd))
    return cache[sfx_id]


def _plan_cues(comp, mcfg: dict, voice, ref_db: float, n_total: int, sr: int = SR) -> tuple:
    """Cues aus comp.cues() mit Klang, Zielpegel und Maskierung versehen: (placed, missing, skipped).

    Zielpegel = Sprechpegel + sfx_db + cue['db']; liegt cue['t'] in einem Wort, höchstens Wortpegel - 6 dB.
    placed: [{'t', 'sfx', 'db', 'why', 'n0', 'sound', 'gain', 'level_db', 'target_db', 'word', 'masked', 'dur'}]
    """
    mod = _optional('sfx')
    words = comp.tl.words
    levels = _word_levels(voice, words, ref_db)
    cache, missing, placed, skipped = {}, [], [], []
    for cue in comp.cues():
        t = float(cue['t'])
        n0 = int(round(t * sr))
        if n0 < 0 or n0 >= n_total:
            skipped.append(cue)
            continue
        snd, lvl, dur = _sound(str(cue['sfx']), mod, cache, missing)
        target = ref_db + mcfg['sfx_db'] + float(cue.get('db', 0.0))
        wi = _word_at(words, t)
        masked = False
        if wi is not None and target > levels[wi] - MASK_DB:
            target = levels[wi] - MASK_DB
            masked = True
        placed.append({'t': t, 'sfx': str(cue['sfx']), 'db': cue.get('db', 0.0), 'why': cue.get('why', ''), 'n0': n0,
                       'sound': snd, 'gain': float(wav.db(target - lvl)), 'level_db': lvl, 'target_db': float(target),
                       'word': words[wi].w if wi is not None else None, 'masked': masked, 'dur': dur})
    return placed, missing, skipped


def _render_cues(placed: list, n_total: int, sr: int = SR) -> np.ndarray:
    """Alle geplanten Töne mit ihrem Gain in eine Stereospur summieren; was über das Videoende hinausragt,
    wird abgeschnitten und über die letzten 10 ms ausgeblendet (kein Knacken am Schluss)."""
    out = np.zeros((n_total, 2), np.float32)
    edge = max(1, int(round(0.01 * sr)))
    for c in placed:
        s, n0 = c['sound'], c['n0']
        n1 = min(n_total, n0 + len(s))
        if n1 <= n0:
            continue
        seg = s[:n1 - n0] * np.float32(c['gain'])
        if n1 - n0 < len(s):
            k = min(edge, len(seg))
            seg[-k:] *= np.linspace(1.0, 0.0, k, dtype=np.float32)[:, None]
        out[n0:n1] += seg
    return out


def _word_at(words: list, t: float):
    """Index des Wortes, in dessen Spanne t liegt, sonst None."""
    for i, w in enumerate(words):
        if w.t0 <= t <= w.t1:
            return i
    return None


def _word_levels(voice, words: list, ref_db: float, sr: int = SR) -> list:
    """RMS-Pegel (dBFS) der Stimme je Wortspanne; ohne Stimme oder leere Spanne der Sprechpegel ref_db."""
    if voice is None:
        return [ref_db] * len(words)
    v = wav.to_mono(np.asarray(voice, np.float32)).astype(np.float64)
    cs = np.concatenate([[0.0], np.cumsum(v ** 2)])
    out = []
    for w in words:
        a, b = max(0, int(w.t0 * sr)), min(len(v), int(np.ceil(w.t1 * sr)))
        if b <= a:
            out.append(ref_db)
        else:
            out.append(float(10.0 * np.log10((cs[b] - cs[a]) / (b - a) + 1e-12)))
    return out


def _level_db(x: np.ndarray, win: float = 0.05, sr: int = SR) -> float:
    """Pegel eines Tons: lautestes 50-ms-RMS-Fenster in dBFS (robust für Blips wie für Flächen)."""
    m = wav.to_mono(np.asarray(x, np.float32)).astype(np.float64)
    n = len(m)
    if n == 0:
        return -120.0
    w = max(1, min(n, int(round(win * sr))))
    cs = np.concatenate([[0.0], np.cumsum(m * m)])
    r = (cs[w:] - cs[:-w]) / w
    return float(10.0 * np.log10(float(r.max()) + 1e-12))


def _active_dur(x: np.ndarray, sr: int = SR) -> float:
    """Wirksame Dauer eines Tons in s: bis zum letzten Sample über 1 % der Spitze."""
    m = np.abs(wav.to_mono(np.asarray(x, np.float32)))
    pk = float(m.max()) if m.size else 0.0
    if pk <= 0:
        return 0.0
    idx = np.flatnonzero(m > pk * 0.01)
    return float((idx[-1] + 1) / sr)


# ----------------------------------------------------------------------------------------------------------------
# Mastering: Lautheit, True Peak, Limiter
# ----------------------------------------------------------------------------------------------------------------

def master(x: np.ndarray, target_lufs: float, true_peak_db_max: float, sr: int = SR) -> tuple:
    """Summe auf target_lufs bringen und den True Peak per Lookahead-Limiter unter true_peak_db_max halten.

    Misst vorher und nachher; drückt der Limiter die Lautheit um mehr als 0,3 LU, folgt eine Korrekturrunde
    (höchstens +2 dB). Gibt (Signal, Messwerte) zurück.
    """
    x = np.asarray(x, np.float32)
    m0 = _lufs_measure(x, fast=True)
    gain_db = _clamp(target_lufs - m0['lufs'], -30.0, 30.0) if _finite(m0['lufs']) else 0.0
    ceiling = true_peak_db_max - TP_MARGIN_DB
    y, red = limit(x * wav.db(gain_db), ceiling, sr=sr)
    m1 = _lufs_measure(y)
    if _finite(m1['lufs']) and abs(target_lufs - m1['lufs']) > 0.3:
        corr = _clamp(target_lufs - m1['lufs'], -2.0, 2.0)
        gain_db += corr
        y, red = limit(x * wav.db(gain_db), ceiling, sr=sr)
        m1 = _lufs_measure(y)
    return y, {'lufs_pre': m0['lufs'], 'master_gain_db': gain_db, 'limiter_db': red,
               'lufs': m1['lufs'], 'true_peak': m1['true_peak'], 'source': m1['source']}


def limit(x: np.ndarray, ceiling_db: float = -1.0, lookahead: float = 0.005, release: float = 0.12, sr: int = SR) -> tuple:
    """Lookahead-Peak-Limiter, blockweise mit numpy. Gibt (Signal, größte Absenkung in dB) zurück.

    Spitzen werden 4-fach überabgetastet erkannt (True Peak). Der nötige Gain wird über 2·lookahead gehalten
    (Minimum-Filter) und über lookahead linear angefahren (Mittelwert-Filter), so dass er am Peak exakt erreicht
    ist; danach kehrt er mit der Zeitkonstante release zurück (Steuerraster 1 ms). Unveränderte Stellen
    behalten Gain 1.
    """
    x = np.asarray(x, np.float32)
    n = len(x)
    if n == 0:
        return x, 0.0
    ceil = float(wav.db(ceiling_db))
    env = _tp_env(x)
    g_req = np.minimum(1.0, ceil / np.maximum(env, 1e-9))
    if g_req.min() >= 1.0 - 1e-6:
        return x, 0.0
    L = max(1, int(round(lookahead * sr)))
    held = minimum_filter1d(g_req, size=2 * L + 1, mode='nearest')
    ramp = uniform_filter1d(held, size=L + 1, mode='nearest')
    red = -20.0 * np.log10(np.maximum(ramp, 1e-6))
    # Rückkehr am Steuerraster: Absenkung fällt exponentiell, nie unter die geforderte
    hop = max(1, int(round(0.001 * sr)))
    m = -(-n // hop)
    blk = np.concatenate([red, np.zeros(m * hop - n)]).reshape(m, hop).max(axis=1)
    coef = float(np.exp(-hop / (max(1e-4, release) * sr)))
    rel = np.empty(m, np.float64)
    e = 0.0
    for i, v in enumerate(blk.tolist()):
        e = v if v > e else e * coef
        rel[i] = e
    centers = np.arange(m) * hop + hop / 2.0
    total = np.maximum(red, np.interp(np.arange(n), centers, rel))
    gain = (10.0 ** (-total / 20.0)).astype(np.float32)
    y = x * gain[:, None] if x.ndim == 2 else x * gain
    tp = true_peak_db(y)
    if tp > ceiling_db:     # Rest aus der Interpolation: global abfangen
        y = y * wav.db(ceiling_db - tp)
    return y.astype(np.float32), float(total.max())


def true_peak_db(x: np.ndarray, sr: int = SR) -> float:
    """True Peak in dBTP (4-fach überabgetastet, alle Kanäle)."""
    env = _tp_env(np.asarray(x, np.float32))
    return float(20.0 * np.log10(float(env.max()) + 1e-12)) if env.size else -120.0


def _tp_env(x: np.ndarray, oversample: int = 4, chunk: int = 1 << 17, pad: int = 256) -> np.ndarray:
    """Spitzenhüllkurve je Sample: Maximum über alle Kanäle des überabgetasteten Signals, blockweise gerechnet."""
    x2 = x if x.ndim == 2 else x[:, None]
    n = len(x2)
    out = np.empty(n, np.float64)
    for s in range(0, n, chunk):
        e = min(n, s + chunk)
        a, b = max(0, s - pad), min(n, e + pad)
        up = np.abs(resample_poly(x2[a:b].astype(np.float64), oversample, 1, axis=0))
        # Maximum über Phasen und Kanäle elementweise (schneller als Reduktionen über kurze Achsen)
        env = up[0::oversample].copy()
        for k in range(1, oversample):
            np.maximum(env, up[k::oversample], out=env)
        env1 = env[:, 0].copy()
        for ch in range(1, env.shape[1]):
            np.maximum(env1, env[:, ch], out=env1)
        out[s:e] = env1[s - a:s - a + (e - s)]
    direct = np.abs(x2[:, 0]).astype(np.float64)
    for ch in range(1, x2.shape[1]):
        np.maximum(direct, np.abs(x2[:, ch]), out=direct)
    return np.maximum(out, direct)


def lufs_numpy(x: np.ndarray, sr: int = SR) -> float:
    """Integrierte Lautheit nach ITU-R BS.1770-4 ohne ffmpeg: K-Filter, 400-ms-Blöcke (75 % Überlappung),
    absolute Schranke -70 LUFS und relative Schranke -10 LU. Stille ergibt -inf. Koeffizienten für 48 kHz."""
    d = np.asarray(x, np.float64)
    d = d[:, None] if d.ndim == 1 else d
    if sr != 48000:
        d = wav.resample(d, sr, 48000).astype(np.float64)
        sr = 48000
    # K-Filter (Kuhschwanz + Hochpass) als zwei Biquads; gerechnet auf (Kanäle, n), das ist in scipy um ein
    # Vielfaches schneller als entlang der ersten Achse eines (n, 2)-Arrays.
    sos = np.array([[1.53512485958697, -2.69169618940638, 1.19839281085285, 1.0, -1.69065929318241, 0.73248077421585],
                    [1.0, -2.0, 1.0, 1.0, -1.99004745483398, 0.99007225036621]])
    k = sosfilt(sos, np.ascontiguousarray(d.T), axis=-1)
    power = np.einsum('ij,ij->j', k, k)            # Summe der Kanalleistungen je Sample (L und R mit Gewicht 1)
    blk, hop = int(0.4 * sr), int(0.1 * sr)
    if len(power) < blk:
        power = np.concatenate([power, np.zeros(blk - len(power))])
    cs = np.concatenate([[0.0], np.cumsum(power)])
    starts = np.arange(0, len(power) - blk + 1, hop)
    z = (cs[starts + blk] - cs[starts]) / blk
    lk = -0.691 + 10.0 * np.log10(z + 1e-20)
    keep = lk > -70.0
    if not keep.any():
        return float('-inf')
    rel = -0.691 + 10.0 * np.log10(z[keep].mean()) - 10.0
    keep &= lk > rel
    if not keep.any():
        return float('-inf')
    return float(-0.691 + 10.0 * np.log10(z[keep].mean()))


def _lufs_measure(data: np.ndarray, sr: int = SR, fast: bool = False) -> dict:
    """Lautheit (LUFS) und True Peak: über eine temporäre WAV mit wav.measure_lufs (ffmpeg), ohne ffmpeg mit
    lufs_numpy/true_peak_db. Für die Messung wird das Signal sicher unter Vollaussteuerung skaliert.

    fast=True misst nur die Lautheit mit lufs_numpy (ohne ffmpeg, ohne True Peak; weicht um < 0,1 LU ab) für
    Zwischenschritte, deren Wert nur den Gain bestimmt; die Endkontrolle bleibt bei ffmpeg."""
    d = np.asarray(data, np.float32)
    if fast:
        return {'lufs': lufs_numpy(d, sr), 'true_peak': None, 'source': 'numpy'}
    pk = float(np.max(np.abs(d))) if d.size else 0.0
    scale = 1.0 if pk <= 0.5 else 0.5 / pk
    off = -20.0 * np.log10(scale)
    out = {'lufs': None, 'true_peak': None, 'source': 'ffmpeg'}
    if pk > 0:
        try:
            with tempfile.TemporaryDirectory() as td:
                p = os.path.join(td, 'measure.wav')
                wav.write(p, d * scale, sr)
                m = wav.measure_lufs(p)
            if m.get('lufs') is not None and m['lufs'] > -69.0:
                out['lufs'] = float(m['lufs']) + off
            if m.get('true_peak') is not None:
                out['true_peak'] = float(m['true_peak']) + off
        except Exception:
            pass
    if out['lufs'] is None:
        out['lufs'] = lufs_numpy(d, sr)
        out['source'] = 'numpy'
    if out['true_peak'] is None:
        out['true_peak'] = true_peak_db(d, sr)
    return out


# ----------------------------------------------------------------------------------------------------------------
# Hilfen
# ----------------------------------------------------------------------------------------------------------------

def _mix_cfg(cfg: dict) -> dict:
    """Mix-Einstellungen mit Standardwerten auffüllen (Zahlen als float)."""
    out = dict(_MIX_DEFAULTS)
    out.update((cfg or {}).get('mix', {}) or {})
    for k in ('voice_lufs', 'master_lufs', 'true_peak_db', 'music_db', 'music_solo_db', 'sfx_db',
              'duck_attack', 'duck_release', 'duck_lookahead', 'tail'):
        out[k] = float(out[k])
    return out


def _optional(name: str):
    """Modul engine.audio.<name> laden; None, wenn es fehlt oder beim Import scheitert."""
    try:
        return importlib.import_module(f'{__package__}.{name}')
    except Exception:
        return None


def _load_voice(project_dir: str) -> tuple:
    """voice.wav als Mono float32 bei 48 kHz lesen: (Signal, Dauer in s)."""
    p = os.path.join(project_dir, 'voice.wav')
    if not os.path.exists(p):
        raise FileNotFoundError("voice.wav fehlt: erst `tts` und `voice` ausführen")
    v, _ = wav.read(p, SR, mono=True)
    v = np.asarray(v, np.float32)
    return v, len(v) / SR


def _fit(x: np.ndarray, n: int) -> np.ndarray:
    """Signal auf genau n Samples bringen (mit Nullen füllen oder abschneiden)."""
    x = np.asarray(x, np.float32)
    if len(x) == n:
        return x
    if len(x) > n:
        return x[:n]
    pad = (n - len(x),) + x.shape[1:]
    return np.concatenate([x, np.zeros(pad, np.float32)], axis=0)


def _fade_edges(x: np.ndarray, fade_in: float, fade_out: float, sr: int = SR) -> np.ndarray:
    """Weiche Ränder: linear ein- und ausblenden (gegen Knacken am Anfang und am Videoende)."""
    n = len(x)
    a, b = min(n, int(fade_in * sr)), min(n, int(fade_out * sr))
    y = x.copy()
    shape = (-1,) + (1,) * (x.ndim - 1)
    if a > 1:
        y[:a] *= np.linspace(0.0, 1.0, a, dtype=np.float32).reshape(shape)
    if b > 1:
        y[n - b:] *= np.linspace(1.0, 0.0, b, dtype=np.float32).reshape(shape)
    return y


def _finite(v) -> bool:
    return v is not None and np.isfinite(v)


def _clamp(v: float, lo: float, hi: float) -> float:
    return float(min(hi, max(lo, v)))


def _r(v, nd: int = 2):
    """Runden für die Ausgabe; None und nicht endliche Werte bleiben None."""
    return round(float(v), nd) if _finite(v) else None
