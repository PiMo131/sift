"""Volledige projectback-up (zip) en herstel.

Inhoud van een back-up (backup.json beschrijft het):
  backup.json          formaat, Sift-versie, datum, project-id, onderzoek-id, bestandslijst
  project.json         instellingen, sprekers, status, controlestatus
  transcript.json      het bewerkbare transcript (tekst, woorden, sprekers, opmerkingen, markeringen, controlevlaggen)
  source.<ext>         de BRONOPNAME (ongewijzigd). Een back-up is dus GEEN gepseudonimiseerde export.
  versions/*.json      versiegeschiedenis
  runs/*.json          ruwe modeluitvoer (klein; nodig voor 'Modellen vergelijken' en de controle op ontbrekende tekst)
  work/vad.json        spraakregio's (klein)
  study.json           het onderzoek waar het interview bij hoort (naam, woordenlijst, afspraken, exportvoorkeuren)
  log.txt

NIET meegenomen (worden bij de volgende verwerking opnieuw gemaakt uit de bronopname): work/audio_16k.wav,
work/audio_norm.wav, work/play*.m4a, work/peaks.json, work/diarization.json.

Herstel maakt altijd een NIEUW project aan (bij een bestaande id met een achtervoegsel) en overschrijft nooit stilzwijgend.
Paden in de zip worden gecontroleerd: geen absolute paden, geen '..', alleen bekende mappen.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import PROJECTS_DIR
from .project import Project

BACKUP_FORMAT = 1
_ALLOWED_DIRS = ("versions/", "runs/")
_ALLOWED_FILES = ("backup.json", "project.json", "transcript.json", "log.txt", "study.json", "work/vad.json", "transcript_recombined.json")
_SAFE = re.compile(r"^[\w\-. ]+$")


def create(p: Project, study: dict | None = None) -> bytes:
    meta = p.meta()
    buf = io.BytesIO()
    files: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def add(path: Path, arc: str, compress=zipfile.ZIP_DEFLATED):
            z.write(path, arc, compress_type=compress)
            files.append(arc)
        add(p.path / "project.json", "project.json")
        if p.transcript_path.exists():
            add(p.transcript_path, "transcript.json")
        src = p.path / meta["source"]
        if src.exists():
            add(src, meta["source"], zipfile.ZIP_STORED)
        for f in sorted(p.versions.glob("*.json")):
            add(f, f"versions/{f.name}")
        for f in sorted(p.runs_dir.glob("*.json")):
            add(f, f"runs/{f.name}")
        for name in ("log.txt", "transcript_recombined.json"):
            if (p.path / name).exists():
                add(p.path / name, name)
        if (p.work / "vad.json").exists():
            add(p.work / "vad.json", "work/vad.json")
        if study:
            z.writestr("study.json", json.dumps(study, ensure_ascii=False, indent=1))
            files.append("study.json")
        manifest = {"format": "sift-backup", "backup_format": BACKUP_FORMAT, "sift_version": __version__,
                    "created": datetime.now().isoformat(timespec="seconds"), "project_id": p.name, "name": meta.get("name"),
                    "study_id": meta.get("study_id"), "contains_source_audio": src.exists(), "pseudonymized": False,
                    "caches_included": False, "files": files,
                    "note": "Bevat de oorspronkelijke opname en alle tekst. Dit is een volledige back-up, geen gepseudonimiseerde export."}
        z.writestr("backup.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    return buf.getvalue()


def inspect(data: bytes) -> dict:
    """Valideert de structuur en geeft de manifest + wat er gebeurt bij herstel."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("Dit is geen zip-bestand.")
    names = z.namelist()
    if "backup.json" not in names or "project.json" not in names:
        raise ValueError("Geen Sift-back-up: backup.json of project.json ontbreekt.")
    manifest = json.loads(z.read("backup.json"))
    if manifest.get("format") != "sift-backup":
        raise ValueError("Geen Sift-back-up (onbekend formaat).")
    if int(manifest.get("backup_format", 0)) > BACKUP_FORMAT:
        raise ValueError(f"Back-upformaat {manifest.get('backup_format')} is nieuwer dan deze Sift-versie ondersteunt.")
    meta = json.loads(z.read("project.json"))
    source = meta.get("source", "")
    for n in names:
        _check_path(n, source)
    pid = manifest.get("project_id") or meta.get("name") or "herstel"
    exists = (PROJECTS_DIR / pid / "project.json").exists()
    study = json.loads(z.read("study.json")) if "study.json" in names else None
    return {"manifest": manifest, "name": meta.get("name"), "project_id": pid, "exists": exists, "has_audio": source in names,
            "has_transcript": "transcript.json" in names, "versions": sum(n.startswith("versions/") for n in names),
            "study": {"id": study.get("id"), "name": study.get("name")} if study else None}


def _check_path(n: str, source: str) -> None:
    if n.startswith(("/", "\\")) or ".." in n.split("/") or ":" in n:
        raise ValueError(f"Onveilig pad in back-up: {n}")
    if n in _ALLOWED_FILES or n == source:
        return
    if any(n.startswith(d) and _SAFE.match(n[len(d):] or "") and n.endswith(".json") for d in _ALLOWED_DIRS):
        return
    raise ValueError(f"Onverwacht bestand in back-up: {n}")


def restore(data: bytes, new_id: str | None = None) -> dict:
    """Herstelt als NIEUW project. Bestaat de id al, dan krijgt het project een achtervoegsel. Geeft {id, renamed, study}."""
    from .project import slugify
    from . import studies

    info = inspect(data)
    z = zipfile.ZipFile(io.BytesIO(data))
    pid = slugify(new_id or info["project_id"])
    path, i, renamed = PROJECTS_DIR / pid, 2, False
    while path.exists():
        path = PROJECTS_DIR / f"{pid}_{i}"
        i += 1
        renamed = True
    path.mkdir(parents=True)
    for n in z.namelist():
        if n == "backup.json" or n == "study.json" or n.endswith("/"):
            continue
        dst = path / n
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(z.read(n))
    study_result = None
    if "study.json" in z.namelist():
        study = json.loads(z.read("study.json"))
        study_result = studies.restore(study)  # bestaand onderzoek blijft onaangeroerd
        meta = json.loads((path / "project.json").read_text(encoding="utf-8"))
        meta["study_id"] = study_result["id"]
        (path / "project.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    p = Project(path)
    p.log(f"hersteld uit back-up ({info['manifest'].get('created')}), oorspronkelijke id {info['project_id']}")
    return {"id": p.name, "renamed": renamed, "original_id": info["project_id"], "study": study_result}
