"""Testomgeving: een lege, tijdelijke projectmap (nooit de echte projects/). Alle gegevens zijn fictief."""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="sift_tests_"))
os.environ["SIFT_PROJECTS"] = str(_TMP / "projects")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fictional_transcript() -> dict:
    """Transcript in schemaversie 1 (zoals een bestaand project op schijf) met een fictieve naam in tekst, sprekerlabel,
    opmerking en alternatief. 'Anna de Vries' en 'Zwolle' zijn verzonnen."""
    def w(start, word, p=0.95, **kw):
        return {"start": start, "end": start + 0.4, "word": word, "p": p, "base": word, "alts": {}, "agree": 2, "n_models": 2, "disagree": False, **kw}
    return {
        "version": 3, "edited": True, "base_model": "large-v3", "models": ["large-v3", "large-v3-turbo"], "strategy": "consensus",
        "speakers": {"S1": {"name": "Interviewer"}, "S2": {"name": "Anna de Vries"}},
        "segments": [
            {"id": 0, "start": 0.0, "end": 3.0, "speaker": "S1", "reviewed": True, "highlight": False, "note": "",
             "text": "Goedemiddag Anna, fijn dat u meedoet.",
             "words": [w(0.0, "Goedemiddag"), w(0.5, "Anna,"), w(1.0, "fijn"), w(1.5, "dat"), w(2.0, "u"), w(2.5, "meedoet.")]},
            {"id": 1, "start": 3.5, "end": 7.0, "speaker": "S2", "reviewed": False, "highlight": True, "note": "Anna aarzelt hier; later navragen.",
             "text": "Eh, ik woon in Zwolle, vlakbij ANNA's zus.",
             "words": [w(3.5, "Eh,", 0.4), w(4.0, "ik"), w(4.4, "woon"), w(4.8, "in"), w(5.2, "Zwolle,", 0.5, alts={"large-v3-turbo": "Zwolle"}, disagree=True),
                       w(5.7, "vlakbij"), w(6.2, "ANNA's", 0.55, alts={"large-v3-turbo": "Anna's"}, disagree=True), w(6.6, "zus.")]},
            {"id": 2, "start": 7.5, "end": 9.0, "speaker": "S1", "reviewed": False, "highlight": False, "note": "",
             "text": "Dank u wel, mevrouw De Vries.",
             "words": [w(7.5, "Dank"), w(7.8, "u"), w(8.1, "wel,"), w(8.4, "mevrouw"), w(8.7, "De"), w(8.9, "Vries.")]},
        ],
    }


@pytest.fixture
def transcript() -> dict:
    return fictional_transcript()


@pytest.fixture
def meta() -> dict:
    return {"name": "Interview Anna de Vries", "created": "2026-10-30T10:00:00", "source": "source.m4a",
            "settings": {"uncertain_threshold": 0.6, "start": None, "end": None}, "audio": {"duration": 9.0}, "status": "klaar",
            "steps": {}, "speakers": {}, "runs": {"large-v3": {"stats": {}}, "large-v3-turbo": {"stats": {}}}, "error": None}


@pytest.fixture
def projects_dir() -> Path:
    d = Path(os.environ["SIFT_PROJECTS"])
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from sift.server import app
    # een loopback-adres: verzoeken van elders worden door de telefoon-middleware (sift.lan) pas met code toegelaten
    return TestClient(app, client=("127.0.0.1", 50000))


def make_project(projects_dir: Path, pid: str = "demo_iv", transcript: dict | None = None, meta_extra: dict | None = None, audio_bytes: bytes = b"RIFFfake") -> Path:
    """Maakt een projectmap zoals een oude Sift (schema v1) die zou achterlaten."""
    p = projects_dir / pid
    for sub in ("work", "runs", "versions"):
        (p / sub).mkdir(parents=True, exist_ok=True)
    (p / "source.m4a").write_bytes(audio_bytes)
    m = {"name": "Interview Anna de Vries", "created": "2026-10-30T10:00:00", "source": "source.m4a",
         "settings": {"language": "nl", "models": ["large-v3"], "uncertain_threshold": 0.6, "start": None, "end": None, "initial_prompt": ""},
         "audio": {"duration": 9.0}, "status": "klaar", "steps": {}, "speakers": {}, "runs": {"large-v3": {"key": {}, "stats": {"mean_p": 0.9}}}, "error": None}
    m.update(meta_extra or {})
    (p / "project.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    t = copy.deepcopy(transcript) if transcript is not None else fictional_transcript()
    (p / "transcript.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    (p / "runs" / "large-v3.json").write_text(json.dumps({"stats": {"mean_p": 0.9}, "segments": [], "words": []}), encoding="utf-8")
    return p
