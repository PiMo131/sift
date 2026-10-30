"""FastAPI-server: onderzoeken, interviews (projecten), verwerking, transcript (autosave), versies, back-up, audio en exports.
Alles lokaal; er wordt niets naar buiten gestuurd (modeldownloads uitgezonderd, zie engines/fasterwhisper.py)."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, backup, conventions, diarize, export, gaps, lan, pipeline, review, studies
from .config import DEFAULT_SETTINGS, LANGUAGES, PROJECTS_DIR, STATIC_DIR, hardware_info, models_info, recommended_settings
from .project import Project

app = FastAPI(title="sift", version=__version__)
app.add_middleware(lan.CodeMiddleware)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

MAX_DROP_BYTES = 2 * 1024 ** 3


def _proj(pid: str) -> Project:
    try:
        return Project.load(pid)
    except FileNotFoundError:
        raise HTTPException(404, "interview niet gevonden")


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


def _static_page(name: str, media_type: str = "text/html; charset=utf-8") -> Response:
    return Response((STATIC_DIR / name).read_bytes(), media_type=media_type, headers={"Cache-Control": "no-cache"})


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
async def drop(request: Request, file: UploadFile = File(...), name: str = Form(""), autostart: str = Form("0"), study_id: str = Form("")):
    """Opname van de telefoon: streamt naar schijf, maakt een interview (zonder onderzoek, tenzij study_id meegegeven) en start optioneel de verwerking."""
    length = request.headers.get("content-length")
    if length and int(length) > MAX_DROP_BYTES + 65536:
        raise HTTPException(413, "bestand te groot (max 2 GB)")
    study = studies.get(study_id) if study_id else None
    if study_id and not study:
        raise HTTPException(400, "onderzoek niet gevonden")
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
        st: dict = {}
        if study:
            st["language"] = study.get("language", "nl")
            st["num_speakers"] = study.get("num_speakers")
        p = Project.create(name, tmp, st, study["id"] if study else None)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    auto = autostart in ("1", "true", "on", "yes")
    if auto:
        pipeline.start(p)
    return {"id": p.name, "name": name, "bytes": total, "autostart": auto, "study_id": study["id"] if study else None}


@app.get("/api/info")
def info():
    hw = hardware_info()
    return {"version": __version__, "hardware": hw, "models": models_info(), "defaults": DEFAULT_SETTINGS, "recommended": recommended_settings(hw),
            "languages": LANGUAGES, "projects_dir": str(PROJECTS_DIR), "diarize_available": diarize.available(), "diarize_method": diarize.method(),
            "conventions": conventions.CONVENTIONS, "conventions_default": conventions.DEFAULT_CONVENTIONS, "export_contracts": export.CONTRACTS}


# ---------- onderzoeken ----------
@app.get("/api/studies")
def list_studies():
    projects = Project.list()
    out = []
    for s in studies.list_all():
        ivs = [p for p in projects if p.get("study_id") == s["id"]]
        out.append({**s, "interviews": len(ivs), "checked": sum(1 for p in ivs if p.get("review_status") == "checked")})
    return out


@app.post("/api/studies")
async def create_study(body: dict):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "naam ontbreekt")
    return studies.create(name, **{k: v for k, v in body.items() if k != "name"})


@app.get("/api/studies/{sid}")
def get_study(sid: str):
    s = studies.get(sid)
    if not s:
        raise HTTPException(404, "onderzoek niet gevonden")
    return s


@app.put("/api/studies/{sid}")
async def put_study(sid: str, body: dict):
    try:
        return studies.update(sid, body)
    except FileNotFoundError:
        raise HTTPException(404, "onderzoek niet gevonden")


@app.delete("/api/studies/{sid}")
def delete_study(sid: str):
    if any(p.get("study_id") == sid for p in Project.list()):
        raise HTTPException(409, "dit onderzoek bevat nog interviews; koppel die eerst los")
    studies.delete(sid)
    return {"ok": True}


@app.get("/api/studies/{sid}/conventions.txt")
def study_conventions_txt(sid: str):
    s = studies.get(sid)
    if not s:
        raise HTTPException(404)
    text = f"Onderzoek: {s['name']}\n\n" + conventions.describe(s.get("conventions"))
    return Response(text, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{sid}_transcriptieafspraken.txt"'})


@app.get("/api/conventions")
def get_conventions():
    return {"catalog": conventions.CONVENTIONS, "default": conventions.DEFAULT_CONVENTIONS}


@app.post("/api/conventions/describe")
async def describe_conventions(body: dict):
    return {"text": conventions.describe(body.get("conventions"))}


# ---------- interviews (projecten) ----------
@app.get("/api/projects")
def projects():
    return Project.list()


@app.post("/api/projects")
async def create_project(name: str = Form(...), settings: str = Form("{}"), file: UploadFile | None = File(None), path: str = Form(""), study_id: str = Form("")):
    st = json.loads(settings or "{}")
    if study_id and not studies.get(study_id):
        raise HTTPException(400, "onderzoek niet gevonden")
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
    study = studies.get(study_id) if study_id else None
    if study:
        st.setdefault("language", study.get("language", "nl"))
        if "num_speakers" not in st:
            st["num_speakers"] = study.get("num_speakers")
    p = Project.create(name, src, st, study_id or None)
    if file is not None:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    return {"id": p.name}


def _project_payload(p: Project) -> dict:
    m = p.meta()
    t = p.transcript() if m.get("status") == "klaar" else None
    thr = m.get("settings", {}).get("uncertain_threshold", 0.6)
    study = studies.get(m.get("study_id"))
    return {**m, "id": p.name, "status_detail": pipeline.status(p), "log": p.read_log(40), "status_label": review.display_status(m, t),
            "next_action": review.next_action(m, t, thr), "review": review.summary(t, thr) if t else None,
            "study": {"id": study["id"], "name": study["name"], "terms": study.get("terms", ""), "conventions": study.get("conventions"), "export_prefs": study.get("export_prefs", {})} if study else None,
            "effective_terms": studies.effective_terms(study, m.get("settings", {}).get("initial_prompt", ""))}


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return _project_payload(_proj(pid))


@app.put("/api/projects/{pid}/settings")
async def put_settings(pid: str, settings: dict):
    p = _proj(pid)
    m = p.meta()
    m["settings"] = {**DEFAULT_SETTINGS, **m["settings"], **settings}
    p.save_meta(m)
    return m["settings"]


@app.put("/api/projects/{pid}/study")
async def put_project_study(pid: str, body: dict):
    p = _proj(pid)
    sid = body.get("study_id") or None
    if sid and not studies.get(sid):
        raise HTTPException(404, "onderzoek niet gevonden")
    p.update_meta(study_id=sid)
    return {"study_id": sid}


@app.put("/api/projects/{pid}/review_status")
async def put_review_status(pid: str, body: dict):
    """'Gecontroleerd' is een expliciete gebruikershandeling; de computer zet dit nooit zelf."""
    p = _proj(pid)
    st = body.get("status")
    if st not in ("none", "in_progress", "checked"):
        raise HTTPException(400, "onbekende status")
    p.update_meta(review_status=st, checked_at=datetime.now().isoformat(timespec="seconds") if st == "checked" else None)
    return {"review_status": st}


@app.put("/api/projects/{pid}/name")
async def put_name(pid: str, body: dict):
    p = _proj(pid)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "naam ontbreekt")
    p.update_meta(name=name)
    return {"name": name}


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    p = _proj(pid)
    if pipeline.status(p)["running"]:
        raise HTTPException(409, "verwerking loopt nog")
    shutil.rmtree(p.path, ignore_errors=True)
    return {"ok": True}


# ---------- verwerking ----------
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


def _save_transcript(p: Project, data: dict) -> dict:
    if not isinstance(data.get("segments"), list):
        raise HTTPException(400, "ongeldig transcript (geen segmenten)")
    token = data.pop("client_token", None)
    data["edited"] = True
    try:
        v = p.save_transcript(data)
    except PermissionError as e:
        raise HTTPException(503, str(e))
    m = p.meta()
    changed = False
    if data.get("speakers"):
        m["speakers"] = data["speakers"]
        changed = True
    if m.get("review_status") == "none":
        m["review_status"] = "in_progress"
        changed = True
    if changed:
        p.save_meta(m)
    return {"version": v, "saved": data["saved"], "client_token": token, "project": p.name}


@app.put("/api/projects/{pid}/transcript")
async def put_transcript(pid: str, data: dict):
    return _save_transcript(_proj(pid), data)


@app.post("/api/projects/{pid}/transcript/beacon")
async def beacon_transcript(pid: str, request: Request):
    """Voor navigator.sendBeacon bij sluiten/verversen van de pagina (alleen POST mogelijk)."""
    data = json.loads((await request.body()).decode("utf-8") or "{}")
    return _save_transcript(_proj(pid), data)


@app.post("/api/projects/{pid}/snapshot")
async def snapshot(pid: str, body: dict | None = None):
    """Versie bewaren. Met body.transcript wordt de actuele toestand uit de editor bewaard (inclusief nog niet opgeslagen invoer)."""
    p = _proj(pid)
    body = body or {}
    data = body.get("transcript")
    if data is not None:
        if not isinstance(data.get("segments"), list):
            raise HTTPException(400, "ongeldig transcript")
        data.pop("client_token", None)
    path = p.snapshot(body.get("label", ""), data)
    return {"file": path.name}


@app.get("/api/projects/{pid}/versions")
def versions(pid: str):
    return _proj(pid).list_versions()


@app.get("/api/projects/{pid}/versions/{name}")
def version_content(pid: str, name: str):
    p = _proj(pid)
    try:
        return json.loads(p.version_file(name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(404)


@app.post("/api/projects/{pid}/versions/{name}/restore")
async def restore(pid: str, name: str, body: dict | None = None):
    """Herstelt een versie; bewaart eerst automatisch de huidige toestand (body.transcript = actuele editorinhoud)."""
    p = _proj(pid)
    try:
        f = p.version_file(name)
    except FileNotFoundError:
        raise HTTPException(404)
    current = (body or {}).get("transcript")
    if current is not None and isinstance(current.get("segments"), list):
        current.pop("client_token", None)
        p.snapshot("voor herstel", current)
    else:
        p.snapshot("voor herstel")
    data = json.loads(f.read_text(encoding="utf-8"))
    from .migrate import migrate_transcript
    data, _ = migrate_transcript(data)
    v = p.save_transcript(data)
    return {"ok": True, "version": v}


@app.get("/api/projects/{pid}/runs")
def runs(pid: str):
    return _proj(pid).load_runs()


@app.post("/api/projects/{pid}/gaps/recompute")
async def recompute_gaps(pid: str, body: dict | None = None):
    """Controle op mogelijk ontbrekende tekst opnieuw uitvoeren op de actuele tekst (body.transcript) of het opgeslagen transcript."""
    p = _proj(pid)
    t = (body or {}).get("transcript") or p.transcript()
    if not t:
        raise HTTPException(404, "geen transcript")
    vad = None
    if (p.work / "vad.json").exists():
        vad = json.loads((p.work / "vad.json").read_text(encoding="utf-8"))
    words = [w for s in t.get("segments", []) for w in (s.get("words") or [])]
    found = gaps.detect(vad, p.load_runs(), words, t.get("base_model"))
    return {"gaps": gaps.carry_dismissed(t.get("gaps"), found), "vad_available": vad is not None}


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
@app.get("/api/export/contracts")
def export_contracts():
    return export.CONTRACTS


def _export_opts(p: Project, opts: dict | None) -> dict:
    """Vult de stopwoordenlijst uit de afspraken van het onderzoek aan als de export die nodig heeft."""
    opts = dict(opts or {})
    m = p.meta()
    study = studies.get(m.get("study_id"))
    conv = (study or {}).get("conventions") or {}
    if "fillers" not in opts:
        opts["fillers"] = conventions.filler_list(conv)
    if opts.get("control_overview") and "conventions" not in opts and study:
        opts["conventions"] = conventions.describe(conv)
    if opts.get("time_offset") is None and opts.get("source_timecodes"):
        opts["time_offset"] = m.get("settings", {}).get("start") or 0
    return opts


@app.post("/api/projects/{pid}/export/{fmt}")
async def do_export(pid: str, fmt: str, opts: dict | None = None):
    p = _proj(pid)
    t = p.transcript()
    if not t:
        raise HTTPException(404, "geen transcript")
    if fmt not in export.CONTRACTS:
        raise HTTPException(400, "onbekend formaat")
    opts = _export_opts(p, opts)
    base = p.meta().get("name") or p.name
    fn = export.filename(fmt, base, opts)
    if fmt == "docx":
        data = export.to_docx(t, opts, p.meta())
        return Response(data, media_type=export.CONTRACTS["docx"]["mime"], headers={"Content-Disposition": f'attachment; filename="{fn}"'})
    mime, ext, func = export.FORMATS[fmt]
    text = func(t, opts)
    return Response(text.encode("utf-8-sig") if fmt.startswith("csv") else text, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@app.post("/api/projects/{pid}/export/{fmt}/preview")
async def export_preview(pid: str, fmt: str, opts: dict | None = None):
    p = _proj(pid)
    t = p.transcript()
    if not t:
        raise HTTPException(404, "geen transcript")
    if fmt not in export.CONTRACTS:
        raise HTTPException(400, "onbekend formaat")
    opts = _export_opts(p, opts)
    base = p.meta().get("name") or p.name
    from .pseudonym import Pseudonymizer
    ps = Pseudonymizer(opts.get("pseudonymize") if "pseudonymize" in export.CONTRACTS[fmt]["options"] else None)
    ps.transcript(t)
    ps.text(base)
    return {"preview": export.preview(fmt, t, opts, p.meta()), "filename": export.filename(fmt, base, opts), "contract": export.CONTRACTS[fmt],
            "replacements": ps.hits, "applied_options": export._opt(fmt, opts)}


@app.get("/api/projects/{pid}/export/{fmt}")
async def do_export_get(pid: str, fmt: str, style: str = "verbatim", timestamps: str = "paragraph", speakers: int = 1, ts_format: str = "brackets", quotes_only: int = 0):
    return await do_export(pid, fmt, {"style": style, "timestamps": timestamps, "speakers": bool(speakers), "ts_format": ts_format, "quotes_only": bool(quotes_only)})


@app.put("/api/projects/{pid}/export_prefs")
async def put_export_prefs(pid: str, body: dict):
    p = _proj(pid)
    m = p.meta()
    m["export_prefs"] = {**m.get("export_prefs", {}), **body}
    p.save_meta(m)
    return m["export_prefs"]


# ---------- back-up ----------
@app.get("/api/projects/{pid}/backup")
def project_backup(pid: str):
    p = _proj(pid)
    m = p.meta()
    data = backup.create(p, studies.get(m.get("study_id")))
    fn = f"sift_backup_{p.name}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@app.post("/api/backups/inspect")
async def backup_inspect(file: UploadFile = File(...)):
    try:
        return backup.inspect(await file.read())
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/backups/restore")
async def backup_restore(file: UploadFile = File(...), new_id: str = Form("")):
    try:
        return backup.restore(await file.read(), new_id or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
