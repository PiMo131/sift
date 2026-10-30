"""Onderzoek: een verzameling interviews met gedeelde instellingen.

projects/_studies/<id>.json
  id, name, created, language, num_speakers, terms (gedeelde woordenlijst: namen, afkortingen, vaktermen),
  conventions (transcriptieafspraken, zie conventions.py), export_prefs (standaard exportinstellingen), note

Een interview (bestaand project) hoort bij een onderzoek via project.json → study_id. Interviews zonder study_id blijven
gewoon werken ("zonder onderzoek"). Gedeelde instellingen worden bij het verwerken expliciet samengevoegd
(effective_terms): de woordenlijst van het onderzoek plus de eigen termen van het interview. Een wijziging in de
woordenlijst start geen verwerking en verandert geen bestaande correcties; ze geldt pas bij de volgende verwerking.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .config import PROJECTS_DIR
from .conventions import DEFAULT_CONVENTIONS


def _dir() -> Path:
    d = PROJECTS_DIR / "_studies"
    d.mkdir(parents=True, exist_ok=True)
    return d


def slug(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.U).strip("_")
    return s[:50] or "onderzoek"


def _path(sid: str) -> Path:
    return _dir() / f"{sid}.json"


def list_all() -> list[dict]:
    out = []
    for f in sorted(_dir().glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    out.sort(key=lambda s: s.get("created", ""), reverse=True)
    return out


def get(sid: str | None) -> dict | None:
    if not sid:
        return None
    f = _path(sid)
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def save(study: dict) -> dict:
    study["updated"] = datetime.now().isoformat(timespec="seconds")
    from .project import atomic_replace
    tmp = _path(study["id"] + ".tmp")
    tmp.write_text(json.dumps(study, ensure_ascii=False, indent=1), encoding="utf-8")
    if not atomic_replace(tmp, _path(study["id"])):
        raise PermissionError(f"onderzoeksbestand geblokkeerd: {_path(study['id'])}")
    return study


def create(name: str, **fields) -> dict:
    base = slug(name)
    sid, i = base, 2
    while _path(sid).exists():
        sid = f"{base}_{i}"
        i += 1
    study = {"id": sid, "name": name.strip() or sid, "created": datetime.now().isoformat(timespec="seconds"), "language": "nl",
             "num_speakers": 2, "terms": "", "conventions": dict(DEFAULT_CONVENTIONS), "export_prefs": {}, "note": ""}
    study.update({k: v for k, v in fields.items() if k in study and k not in ("id", "created")})
    return save(study)


def update(sid: str, fields: dict) -> dict:
    s = get(sid)
    if not s:
        raise FileNotFoundError(sid)
    for k, v in fields.items():
        if k in ("name", "language", "num_speakers", "terms", "conventions", "export_prefs", "note"):
            s[k] = v
    return save(s)


def delete(sid: str) -> None:
    f = _path(sid)
    if f.exists():
        f.unlink()


def restore(study: dict) -> dict:
    """Bij herstel uit een back-up: bestaat het onderzoek al, laat het staan; anders aanmaken met dezelfde id (of met achtervoegsel)."""
    sid = study.get("id") or slug(study.get("name", "onderzoek"))
    if _path(sid).exists():
        return {"id": sid, "action": "bestaand onderzoek gebruikt"}
    s = dict(study)
    s["id"] = sid
    save(s)
    return {"id": sid, "action": "onderzoek hersteld"}


def effective_terms(study: dict | None, own_terms: str) -> str:
    parts = [(study or {}).get("terms", "").strip(), (own_terms or "").strip()]
    return ", ".join(p for p in parts if p)
