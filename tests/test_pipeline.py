"""Durchlauf: Projekt -> espeak-Stimme -> Plan -> Standbild -> Prüfung (kein Video-Encoding, damit der Test schnell bleibt)."""
import os, sys, json, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import config, compose, render, check
from engine.audio import tts, voice

SCRIPT = {"title": "Top 2 Test", "slug": "t2", "format": "portrait", "theme": "heist",
          "hook": {"lines": ["Two tiny tests."]},
          "entries": [{"rank": 2, "title": "Second", "lines": ["It is second."]}, {"rank": 1, "title": "First", "lines": ["It is first."]}],
          "outro": {"lines": ["Done."]}}


def test_pipeline(tmp_path):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proj = tmp_path / 'p'
    proj.mkdir()
    with open(proj / 'script.json', 'w') as fh:
        json.dump(SCRIPT, fh)
    cfg = config.load(root)
    if shutil.which('espeak-ng'):
        tts.synthesize(str(proj), cfg, root, force_provider='espeak')
        voice.process(str(proj), cfg)
        assert (proj / 'words.json').exists()
    comp = compose.load(str(proj), root)
    plan = compose.write_plan(str(proj), comp)
    assert [s['id'] for s in plan['scenes']] == ['hook', 'E2', 'E1', 'outro']
    assert plan['duration'] > 3
    im = render.frame_at(comp, plan['scenes'][1]['t0'] + 1.0, 0.25)
    assert im.size == (270, 480)
    res = check.run(str(proj), [plan['scenes'][1]['t0'] + 1.0], root)
    assert 'problems' in res
