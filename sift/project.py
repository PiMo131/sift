"""Projectmap: audio, caches, modelruns, transcript en versies.

projects/<naam>/
  project.json        metadata, instellingen, sprekers, status
  transcript.json     het bewerkbare transcript (autosave)
  versions/           eerdere versies van transcript.json
  work/               audio_16k.wav, audio_norm.wav, play.m4a, play_orig.m4a, peaks.json
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


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.U).strip("_")
    return s[:60] or "project"


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
    def create(cls, name: str, source: Path, settings: dict | None = None) -> "Project":
        slug = slugify(name)
        path = PROJECTS_DIR / slug
        i = 2
        while path.exists():
            path = PROJECTS_DIR / f"{slug}_{i}"
            i += 1
        p = cls(path)
        dst = p.path / ("source" + source.suffix.lower())
        shutil.copy2(source, dst)
        meta = {"name": name, "created": datetime.now().isoformat(timespec="seconds"), "source": dst.name,
                "settings": {**DEFAULT_SETTINGS, **(settings or {})}, "audio": {}, "status": "nieuw", "steps": {},
                "speakers": {}, "runs": {}, "error": None}
        p.save_meta(meta)
        return p

    @classmethod
    def load(cls, name: str) -> "Project":
        path = PROJECTS_DIR / name
        if not (path / "project.json").exists():
            raise FileNotFoundError(name)
        return cls(path)

    @classmethod
    def list(cls) -> list[dict]:
        out = []
        if not PROJECTS_DIR.exists():
            return out
        for d in sorted(PROJECTS_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if (d / "project.json").exists():
                m = json.loads((d / "project.json").read_text(encoding="utf-8"))
                out.append({"id": d.name, "name": m.get("name"), "created": m.get("created"), "status": m.get("status"),
                            "duration": m.get("audio", {}).get("duration"), "models": list(m.get("runs", {}).keys())})
        return out

    # ---------- meta ----------
    def meta(self) -> dict:
        return json.loads((self.path / "project.json").read_text(encoding="utf-8"))

    def save_meta(self, meta: dict) -> None:
        tmp = self.path / "project.json.tmp"
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path / "project.json")

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

    # ---------- transcript ----------
    @property
    def transcript_path(self) -> Path:
        return self.path / "transcript.json"

    def transcript(self) -> dict | None:
        if not self.transcript_path.exists():
            return None
        return json.loads(self.transcript_path.read_text(encoding="utf-8"))

    def save_transcript(self, data: dict, keep_version: bool = True) -> int:
        """Schrijft atomair; bewaart om de 25 versies of bij expliciete vraag een kopie. Geeft versienummer."""
        old = self.transcript()
        version = (old.get("version", 0) if old else 0) + 1
        data["version"] = version
        data["saved"] = datetime.now().isoformat(timespec="seconds")
        if old and keep_version and (version % 25 == 0 or old.get("version", 0) == 0):
            (self.versions / f"transcript_v{old.get('version', 0):05d}.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        tmp = self.path / "transcript.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        try:
            tmp.replace(self.transcript_path)
        except PermissionError:  # bestand in gebruik: wegschrijven onder unieke naam
            alt = self.path / f"transcript_rescue_{int(time.time())}.json"
            tmp.replace(alt)
            self.log(f"transcript.json geblokkeerd, opgeslagen als {alt.name}")
        return version

    def snapshot(self, label: str = "") -> Path:
        t = self.transcript()
        if not t:
            raise FileNotFoundError("geen transcript")
        name = f"transcript_v{t.get('version', 0):05d}{('_' + slugify(label)) if label else ''}.json"
        p = self.versions / name
        p.write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
        return p
