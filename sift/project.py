"""Projectmap: audio, caches, modelruns, transcript en versies.

projects/<naam>/
  project.json        metadata, instellingen, sprekers, status, controlestatus, study_id (schema_version 2)
  transcript.json     het bewerkbare transcript (autosave; schema_version 2)
  versions/           eerdere versies van transcript.json (+ .meta.json met label/datum)
  work/               audio_16k.wav, audio_norm.wav, play.m4a, play_orig.m4a, peaks.json, vad.json
  runs/<model>.json   ruwe engine-uitvoer per model
  log.txt
"""
from __future__ import annotations

import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from .config import DEFAULT_SETTINGS, PROJECTS_DIR
from .migrate import PROJECT_SCHEMA, TRANSCRIPT_SCHEMA, migrate_project, migrate_transcript


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.U).strip("_")
    return s[:60] or "project"


def atomic_replace(tmp: Path, dst: Path, attempts: int = 8) -> bool:
    """os.replace met korte herhaling: OneDrive, virusscanners en indexering houden een bestand op Windows soms een
    fractie van een seconde vast (PermissionError / WinError 5). Geeft False als het na alle pogingen niet lukt."""
    for i in range(attempts):
        try:
            tmp.replace(dst)
            return True
        except PermissionError:
            if i == attempts - 1:
                return False
            time.sleep(0.15 * (i + 1))
    return False


class Project:
    def __init__(self, path: Path):
        self.path = path
        self.work = path / "work"
        self.runs_dir = path / "runs"
        self.versions = path / "versions"
        for d in (self.work, self.runs_dir, self.versions):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return self.path.name

    # ---------- aanmaken / laden ----------
    @classmethod
    def create(cls, name: str, source: Path, settings: dict | None = None, study_id: str | None = None) -> "Project":
        slug = slugify(name)
        path = PROJECTS_DIR / slug
        i = 2
        while path.exists():
            path = PROJECTS_DIR / f"{slug}_{i}"
            i += 1
        p = cls(path)
        dst = p.path / ("source" + source.suffix.lower())
        shutil.copy2(source, dst)
        meta = {"schema_version": PROJECT_SCHEMA, "name": name, "created": datetime.now().isoformat(timespec="seconds"), "source": dst.name,
                "settings": {**DEFAULT_SETTINGS, **(settings or {})}, "audio": {}, "status": "nieuw", "steps": {},
                "speakers": {}, "runs": {}, "error": None, "study_id": study_id, "review_status": "none", "checked_at": None, "export_prefs": {}}
        p.save_meta(meta)
        return p

    @classmethod
    def load(cls, name: str) -> "Project":
        if name.startswith("_") or "/" in name or "\\" in name or ".." in name:
            raise FileNotFoundError(name)
        path = PROJECTS_DIR / name
        if not (path / "project.json").exists():
            raise FileNotFoundError(name)
        return cls(path)

    @classmethod
    def list(cls) -> list[dict]:
        from . import review
        out = []
        if not PROJECTS_DIR.exists():
            return out
        for d in sorted(PROJECTS_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if d.name.startswith("_") or not (d / "project.json").exists():
                continue
            p = cls(d)
            m = p.meta()
            t = p.transcript() if m.get("status") == "klaar" else None
            thr = m.get("settings", {}).get("uncertain_threshold", 0.6)
            out.append({"id": d.name, "name": m.get("name"), "created": m.get("created"), "status": m.get("status"),
                        "status_label": review.display_status(m, t), "review_status": m.get("review_status", "none"),
                        "next_action": review.next_action(m, t, thr), "review": review.summary(t, thr) if t else None,
                        "study_id": m.get("study_id"), "duration": m.get("audio", {}).get("duration"), "models": list(m.get("runs", {}).keys()),
                        "fragment": {"start": m.get("settings", {}).get("start"), "end": m.get("settings", {}).get("end")}})
        return out

    # ---------- meta ----------
    def meta(self) -> dict:
        raw = json.loads((self.path / "project.json").read_text(encoding="utf-8"))
        m, _ = migrate_project(raw)
        return m

    def save_meta(self, meta: dict) -> None:
        meta.setdefault("schema_version", PROJECT_SCHEMA)
        tmp = self.path / "project.json.tmp"
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        if not atomic_replace(tmp, self.path / "project.json"):
            raise PermissionError(f"project.json is geblokkeerd (OneDrive/virusscanner?): {self.path}")

    def update_meta(self, **kw) -> dict:
        m = self.meta()
        m.update(kw)
        self.save_meta(m)
        return m

    def log(self, text: str) -> None:
        with open(self.path / "log.txt", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {text}\n")

    def read_log(self, n: int = 60) -> list[str]:
        f = self.path / "log.txt"
        if not f.exists():
            return []
        return f.read_text(encoding="utf-8").splitlines()[-n:]

    # ---------- runs ----------
    def run_path(self, model: str) -> Path:
        return self.runs_dir / f"{model}.json"

    def load_runs(self) -> dict:
        return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in self.runs_dir.glob("*.json")}

    def invalidate_audio_caches(self) -> None:
        """Andere bron/fragment: alle afgeleide bestanden en modelruns zijn ongeldig."""
        for name in ("audio_norm.wav", "play.m4a", "play_orig.m4a", "peaks.json", "diarization.json", "vad.json"):
            f = self.work / name
            if f.exists():
                f.unlink()
        for old in self.runs_dir.glob("*.json"):
            old.unlink()

    # ---------- transcript ----------
    @property
    def transcript_path(self) -> Path:
        return self.path / "transcript.json"

    def transcript(self) -> dict | None:
        if not self.transcript_path.exists():
            return None
        raw = json.loads(self.transcript_path.read_text(encoding="utf-8"))
        t, _ = migrate_transcript(raw)
        return t

    def save_transcript(self, data: dict, keep_version: bool = True) -> int:
        """Schrijft atomair; bewaart om de 25 versies of bij expliciete vraag een kopie. Geeft versienummer."""
        old = self.transcript()
        version = (old.get("version", 0) if old else 0) + 1
        data["version"] = version
        data["saved"] = datetime.now().isoformat(timespec="seconds")
        data.setdefault("schema_version", TRANSCRIPT_SCHEMA)
        if old and keep_version and (version % 25 == 0 or old.get("version", 0) == 0):
            self._write_version(old, "automatisch")
        tmp = self.path / "transcript.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if not atomic_replace(tmp, self.transcript_path):  # bestand in gebruik: wegschrijven onder unieke naam
            alt = self.path / f"transcript_rescue_{int(time.time())}.json"
            tmp.replace(alt)
            self.log(f"transcript.json geblokkeerd, opgeslagen als {alt.name}")
            raise PermissionError(f"transcript.json is geblokkeerd; reddingskopie {alt.name} geschreven")
        return version

    def _write_version(self, t: dict, label: str = "") -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"transcript_v{t.get('version', 0):05d}_{stamp}{('_' + slugify(label)) if label else ''}.json"
        p = self.versions / name
        p.write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
        (self.versions / (name[:-5] + ".meta.json")).write_text(json.dumps({"label": label, "created": datetime.now().isoformat(timespec="seconds"),
                                                                             "version": t.get("version", 0), "segments": len(t.get("segments", []))}, ensure_ascii=False), encoding="utf-8")
        return p

    def snapshot(self, label: str = "", data: dict | None = None) -> Path:
        """Versie bewaren. `data` = actuele toestand uit de editor (inclusief nog niet opgeslagen invoer); anders het opgeslagen bestand."""
        t = data if data is not None else self.transcript()
        if not t:
            raise FileNotFoundError("geen transcript")
        return self._write_version(t, label)

    def list_versions(self) -> list[dict]:
        out = []
        for f in sorted(self.versions.glob("transcript_v*.json"), reverse=True):
            if f.name.endswith(".meta.json"):
                continue
            meta_f = self.versions / (f.name[:-5] + ".meta.json")
            info = {"file": f.name, "label": "", "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"), "version": None, "segments": None}
            if meta_f.exists():
                try:
                    info.update(json.loads(meta_f.read_text(encoding="utf-8")))
                except Exception:
                    pass
            else:  # oude versiebestanden zonder meta: label uit de naam
                m = re.match(r"transcript_v(\d+)(?:_(.*))?\.json", f.name)
                if m:
                    info["version"] = int(m.group(1))
                    info["label"] = (m.group(2) or "").replace("_", " ")
            try:
                t = json.loads(f.read_text(encoding="utf-8"))
                segs = t.get("segments", [])
                info["segments"] = len(segs)
                info["preview"] = " ".join(s.get("text", "") for s in segs[:3])[:220]
                info["words"] = sum(len(s.get("words") or []) for s in segs)
            except Exception:
                info["preview"] = "(niet leesbaar)"
            out.append(info)
        return out

    def version_file(self, name: str) -> Path:
        if "/" in name or "\\" in name or ".." in name or not name.endswith(".json"):
            raise FileNotFoundError(name)
        f = self.versions / name
        if not f.exists():
            raise FileNotFoundError(name)
        return f
