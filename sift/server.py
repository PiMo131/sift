"""FastAPI-server: projecten, pipeline, transcript (autosave), audio en exports. Alles lokaal."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, diarize, export, lan, pipeline
from .config import DEFAULT_SETTINGS, MODELS, PROJECTS_DIR, STATIC_DIR, hardware_info
from .project import Project

app = FastAPI(title="sift", version=__version__)
app.add_middleware(lan.CodeMiddleware)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

MAX_DROP_BYTES = 2 * 1024 ** 3


def _proj(pid: str) -> Project:
    try:
        return Project.load(pid)
    except FileNotFoundError:
        raise HTTPException(404, "project niet gevonden")


def _static_page(name: str, media_type: str = "text/html; charset=utf-8") -> Response:
    return Response((STATIC_DIR / name).read_bytes(), media_type=media_type, headers={"Cache-Control": "no-cache"})


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/drop")
def drop_page():
    return _static_page("drop.html")


@app.get("/manifest.webmanifest")
def manifest():
    return _static_page("manifest.webmanifest", "application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return _static_page("sw.js", "application/javascript")


@app.get("/api/ping")
def ping():
    return {"app": "sift", "version": __version__, "lan": lan.state.enabled}


# ---------- telefoon / LAN ----------
def _loopback_only(request: Request):
    if not lan.is_loopback(request.client.host if request.client else None):
        raise HTTPException(403, "alleen vanaf deze computer")


@app.get("/api/lan")
def lan_info(request: Request):
    _loopback_only(request)
    return lan.info()


@app.post("/api/lan/newcode")
def lan_newcode(request: Request):
    _loopback_only(request)
    lan.state.regenerate()
    return lan.info()


@app.post("/api/lan/enable")
async def lan_enable(request: Request, body: dict | None = None):
    _loopback_only(request)
    lan.state.enabled = bool((body or {}).get("enabled", True))
    return lan.info()


@app.get("/api/lan/qr.svg")
def lan_qr(request: Request):
    _loopback_only(request)
    return Response(lan.qr_svg(lan.url()), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


def _remux_if_needed(src: Path) -> Path:
    """Browser-opnames (MediaRecorder) missen duur en cues in de container; een remux zonder hercoderen herstelt dat."""
    if src.suffix not in (".webm", ".ogg", ".mkv"):
        return src
    from .config import find_ffmpeg
    ff = find_ffmpeg()
    if not ff:
        return src
    dst = src.with_name("remux" + src.suffix)
    try:
        r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-c", "copy", str(dst)],
                           capture_output=True, text=True, timeout=600)
        if r.returncode == 0 and dst.exists() and dst.stat().st_size > 0:
            return dst
    except Exception:
        pass
    return src


@app.post("/api/drop")
async def drop(request: Request, file: UploadFile = File(...), name: str = Form(""), autostart: str = Form("0")):
    """Opname van de telefoon: streamt naar schijf, maakt een project en start optioneel de pipeline."""
    length = request.headers.get("content-length")
    if length and int(length) > MAX_DROP_BYTES + 65536:
        raise HTTPException(413, "bestand te groot (max 2 GB)")
    fname = Path(file.filename or "opname").name or "opname"
    suffix = Path(fname).suffix.lower() or ".bin"
    tmpdir = Path(tempfile.mkdtemp(prefix="sift_drop_"))
    tmp = tmpdir / ("upload" + suffix)
    total = 0
    try:
        with open(tmp, "wb") as f:
            while True:
                chunk = await file.read(1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DROP_BYTES:
                    raise HTTPException(413, "bestand te groot (max 2 GB)")
                f.write(chunk)
        if total == 0:
            raise HTTPException(400, "leeg bestand")
        name = (name or "").strip() or f"{Path(fname).stem} {datetime.now():%Y-%m-%d %H:%M}"
        tmp = _remux_if_needed(tmp)
        p = Project.create(name, tmp, {})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if autostart in ("1", "true", "on", "yes"):
        pipeline.start(p)
    return {"id": p.name, "name": name, "bytes": total, "autostart": autostart in ("1", "true", "on", "yes")}


@app.get("/api/info")
def info():
    return {"version": __version__, "hardware": hardware_info(), "models": MODELS, "defaults": DEFAULT_SETTINGS,
            "projects_dir": str(PROJECTS_DIR), "diarize_available": diarize.available(), "diarize_method": diarize.method()}


# ---------- projecten ----------
@app.get("/api/projects")
def projects():
    return Project.list()


@app.post("/api/projects")
async def create_project(name: str = Form(...), settings: str = Form("{}"), file: UploadFile | None = File(None), path: str = Form("")):
    st = json.loads(settings or "{}")
    if file is not None:
        tmp = Path(tempfile.mkdtemp()) / (file.filename or "audio")
        with open(tmp, "wb") as f:
            shutil.copyfileobj(file.file, f)
        src = tmp
    elif path:
        src = Path(path)
        if not src.exists():
            raise HTTPException(400, "pad bestaat niet")
    else:
        raise HTTPException(400, "geen bestand")
    p = Project.create(name, src, st)
    if file is not None:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    return {"id": p.name}


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    p = _proj(pid)
    m = p.meta()
    return {**m, "id": p.name, "status_detail": pipeline.status(p), "log": p.read_log(40)}


@app.put("/api/projects/{pid}/settings")
async def put_settings(pid: str, settings: dict):
    p = _proj(pid)
    m = p.meta()
    m["settings"] = {**DEFAULT_SETTINGS, **m["settings"], **settings}
    p.save_meta(m)
    return m["settings"]


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    p = _proj(pid)
    if pipeline.status(p)["running"]:
        raise HTTPException(409, "pipeline draait nog")
    shutil.rmtree(p.path, ignore_errors=True)
    return {"ok": True}


# ---------- pipeline ----------
@app.post("/api/projects/{pid}/run")
async def run(pid: str, body: dict | None = None):
    p = _proj(pid)
    only = (body or {}).get("models")
    pipeline.start(p, only)
    return pipeline.status(p)


@app.get("/api/projects/{pid}/status")
def status(pid: str):
    p = _proj(pid)
    return {**pipeline.status(p), "log": p.read_log(12)}


@app.post("/api/projects/{pid}/cancel")
def cancel(pid: str):
    return {"cancelled": pipeline.cancel(_proj(pid))}


@app.post("/api/projects/{pid}/recombine")
async def recombine(pid: str, body: dict | None = None):
    """Opnieuw combineren met een andere strategie/volgorde, zonder modellen opnieuw te draaien."""
    p = _proj(pid)
    m = p.meta()
    if body:
        m["settings"].update({k: v for k, v in body.items() if k in ("combine", "models")})
        p.save_meta(m)
    job = pipeline.Job(p)
    job._combine_step(p, m, m["settings"])
    return {"ok": True}


# ---------- transcript ----------
@app.get("/api/projects/{pid}/transcript")
def get_transcript(pid: str):
    p = _proj(pid)
    t = p.transcript()
    if not t:
        raise HTTPException(404, "nog geen transcript")
    return t


@app.put("/api/projects/{pid}/transcript")
async def put_transcript(pid: str, data: dict):
    p = _proj(pid)
    data["edited"] = True
    v = p.save_transcript(data)
    m = p.meta()
    if data.get("speakers"):
        m["speakers"] = data["speakers"]
        p.save_meta(m)
    return {"version": v, "saved": data["saved"]}


@app.post("/api/projects/{pid}/snapshot")
async def snapshot(pid: str, body: dict | None = None):
    p = _proj(pid)
    path = p.snapshot((body or {}).get("label", ""))
    return {"file": path.name}


@app.get("/api/projects/{pid}/versions")
def versions(pid: str):
    p = _proj(pid)
    return sorted(x.name for x in p.versions.glob("*.json"))


@app.post("/api/projects/{pid}/versions/{name}/restore")
def restore(pid: str, name: str):
    p = _proj(pid)
    f = p.versions / name
    if not f.exists():
        raise HTTPException(404)
    p.snapshot("voor_herstel")
    data = json.loads(f.read_text(encoding="utf-8"))
    p.save_transcript(data)
    return {"ok": True}


@app.get("/api/projects/{pid}/runs")
def runs(pid: str):
    p = _proj(pid)
    return p.load_runs()


# ---------- audio ----------
@app.get("/api/projects/{pid}/audio")
def audio_file(pid: str, original: int = 0):
    p = _proj(pid)
    f = p.work / ("play_orig.m4a" if original else "play.m4a")
    if not f.exists():
        raise HTTPException(404, "audio nog niet verwerkt")
    return FileResponse(str(f), media_type="audio/mp4")


@app.get("/api/projects/{pid}/peaks")
def peaks(pid: str):
    p = _proj(pid)
    f = p.work / "peaks.json"
    if not f.exists():
        return []
    return Response(f.read_text(encoding="utf-8"), media_type="application/json")


# ---------- export ----------
@app.post("/api/projects/{pid}/export/{fmt}")
async def do_export(pid: str, fmt: str, opts: dict | None = None):
    p = _proj(pid)
    t = p.transcript()
    if not t:
        raise HTTPException(404, "geen transcript")
    opts = opts or {}
    base = p.meta().get("name") or p.name
    if fmt == "docx":
        data = export.to_docx(t, opts, p.meta())
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="{base}.docx"'})
    if fmt not in export.FORMATS:
        raise HTTPException(400, "onbekend formaat")
    mime, ext, fn = export.FORMATS[fmt]
    text = fn(t, opts)
    return Response(text.encode("utf-8-sig") if fmt.startswith("csv") else text, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{base}.{ext}"'})


@app.get("/api/projects/{pid}/export/{fmt}")
async def do_export_get(pid: str, fmt: str, style: str = "verbatim", timestamps: str = "paragraph", speakers: int = 1, ts_format: str = "brackets", highlights_only: int = 0):
    return await do_export(pid, fmt, {"style": style, "timestamps": timestamps, "speakers": bool(speakers), "ts_format": ts_format, "highlights_only": bool(highlights_only)})
