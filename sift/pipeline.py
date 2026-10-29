"""Verwerkingspipeline per project. Elke stap is gecached: bestaat de uitvoer al en zijn de instellingen gelijk, dan wordt
de stap overgeslagen. Modellen draaien NA ELKAAR (één GPU tegelijk) in een subproces.

Stappen: convert -> normalize -> playback -> peaks -> transcribe[model...] -> diarize -> combine
"""
from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path

from . import audio, consensus, diarize
from .config import MODELS, resolve_device
from .engines import run_engine
from .project import Project

_lock = threading.Lock()
_running: dict[str, "Job"] = {}


class Job:
    def __init__(self, project: Project, only_models: list[str] | None = None):
        self.project = project
        self.only_models = only_models
        self.cancel = False
        self.state = {"step": "wacht", "progress": 0.0, "detail": "", "done": False, "error": None, "model": None}

    def set(self, **kw):
        self.state.update(kw)

    def run(self):
        p = self.project
        try:
            meta = p.meta()
            st = meta["settings"]
            meta["status"] = "bezig"
            meta["error"] = None
            p.save_meta(meta)
            self._audio_steps(p, meta, st)
            self._transcribe_steps(p, meta, st)
            self._diarize_step(p, meta, st)
            self._combine_step(p, meta, st)
            meta = p.meta()
            meta["status"] = "klaar"
            p.save_meta(meta)
            self.set(step="klaar", progress=1.0, done=True)
            p.log("pipeline klaar")
        except Exception as e:
            p.log("FOUT: " + "".join(traceback.format_exception_only(type(e), e)).strip())
            p.log(traceback.format_exc()[-1500:])
            meta = p.meta()
            meta["status"] = "fout"
            meta["error"] = str(e)
            p.save_meta(meta)
            self.set(step="fout", error=str(e), done=True)
        finally:
            with _lock:
                _running.pop(p.name, None)

    # ---------- audio ----------
    def _audio_steps(self, p: Project, meta: dict, st: dict):
        src = p.path / meta["source"]
        wav16 = p.work / "audio_16k.wav"
        key = {"start": st.get("start"), "end": st.get("end")}
        if not wav16.exists() or meta["steps"].get("convert") != key:
            self.set(step="Audio inlezen", progress=0.02, detail="ffmpeg → 16 kHz mono")
            info = audio.probe(src)
            audio.to_wav16k(src, wav16, st.get("start"), st.get("end"))
            meta["audio"].update({"source_info": info, "duration": audio.probe(wav16)["duration"]})
            meta["steps"]["convert"] = key
            p.save_meta(meta)
            p.log(f"ingelezen: {info}")
        norm = p.work / "audio_norm.wav"
        key = {"normalize": st["normalize"], "target": st["target_lufs"], "compressor": st["compressor"], "denoise": st["denoise"]}
        if not norm.exists() or meta["steps"].get("normalize") != key:
            if st["normalize"]:
                self.set(step="Luidheid normaliseren", progress=0.06, detail=f"loudnorm naar {st['target_lufs']} LUFS")
                m = audio.normalize(wav16, norm, st["target_lufs"], st["compressor"], st["denoise"])
                meta["audio"]["loudness"] = m
                p.log(f"normalisatie: {m}")
            else:
                import shutil
                shutil.copy2(wav16, norm)
                meta["audio"]["loudness"] = None
            meta["steps"]["normalize"] = key
            for old in p.runs_dir.glob("*.json"):  # andere audio → runs ongeldig
                old.unlink()
            p.save_meta(meta)
        if not (p.work / "play.m4a").exists():
            self.set(step="Afspeelbestanden maken", progress=0.1)
            audio.to_playback(norm, p.work / "play.m4a")
            audio.to_playback(wav16, p.work / "play_orig.m4a")
        if not (p.work / "peaks.json").exists():
            (p.work / "peaks.json").write_text(json.dumps(audio.waveform_peaks(norm)), encoding="utf-8")

    # ---------- transcriberen ----------
    def _transcribe_steps(self, p: Project, meta: dict, st: dict):
        device, compute = resolve_device(st["device"])
        models = self.only_models or st["models"]
        norm = p.work / "audio_norm.wav"
        for i, mid in enumerate(models):
            if self.cancel:
                raise RuntimeError("geannuleerd")
            if mid not in MODELS:
                raise ValueError(f"onbekend model {mid}")
            out = p.run_path(mid)
            key = {"model": mid, "language": st["language"], "beam": st["beam_size"], "hotwords": st["hotwords"], "prompt": st["initial_prompt"]}
            meta = p.meta()
            if out.exists() and meta["runs"].get(mid, {}).get("key") == key:
                p.log(f"{mid}: uit cache")
                continue
            base = 0.12 + 0.7 * (i / len(models))
            span = 0.7 / len(models)
            self.set(step=f"Transcriberen {MODELS[mid]['label']}", progress=base, model=mid, detail=f"{device} {compute}, model laden…")
            p.log(f"{mid}: start op {device} ({compute})")

            def prog(frac, text, base=base, span=span):
                self.set(progress=base + span * frac, detail=text)

            opts = {"model": MODELS[mid]["fw"], "device": device, "compute_type": compute, "language": st["language"],
                    "beam_size": st["beam_size"], "hotwords": st["hotwords"], "initial_prompt": st["initial_prompt"], "vad": True}
            result = run_engine(MODELS[mid].get("engine", "fasterwhisper"), norm, out, opts, prog)
            meta = p.meta()
            meta["runs"][mid] = {"key": key, "stats": result["stats"]}
            p.save_meta(meta)
            p.log(f"{mid}: klaar, {result['stats']}")

    # ---------- diarisatie ----------
    def _diarize_step(self, p: Project, meta: dict, st: dict):
        turns_path = p.work / "diarization.json"
        if not st.get("diarize"):
            return
        if turns_path.exists():
            return
        if not diarize.available():
            p.log("diarisatie overgeslagen: installeer speechbrain en torch (pip install -r requirements.txt)")
            return
        runs = p.load_runs()
        base = next((m for m in st["models"] if m in runs), None)
        if not base:
            return
        self.set(step="Sprekers scheiden", progress=0.86, detail=diarize.method() or "")
        device, _ = resolve_device(st["device"])
        turns = diarize.run(p.work / "audio_norm.wav", runs[base]["segments"], st.get("num_speakers") or None, device,
                            lambda t: self.set(detail=t))
        if turns is None:
            p.log("diarisatie mislukt")
            return
        turns_path.write_text(json.dumps(turns), encoding="utf-8")
        meta = p.meta()
        used = "embeddings"
        meta["diarization"] = {"method": used, "turns": len(turns), "speakers": len({t["speaker"] for t in turns})}
        p.save_meta(meta)
        p.log(f"diarisatie ({used}): {meta['diarization']['speakers']} sprekers, {len(turns)} beurten")

    # ---------- combineren ----------
    def _combine_step(self, p: Project, meta: dict, st: dict):
        self.set(step="Combineren", progress=0.92, detail="woorden uitlijnen")
        runs = p.load_runs()
        order = [m for m in st["models"] if m in runs] + [m for m in runs if m not in st["models"]]
        combined = consensus.combine(runs, order, st["combine"])
        turns = None
        tp = p.work / "diarization.json"
        if tp.exists():
            turns = json.loads(tp.read_text(encoding="utf-8"))
        old = p.transcript()
        speakers = diarize.assign(combined["segments"], turns)
        if old and old.get("speakers"):
            # sprekernamen bewaren bij opnieuw combineren
            for sid, sp in old["speakers"].items():
                if sid in speakers:
                    speakers[sid] = sp
        meta = p.meta()
        meta["speakers"] = speakers
        meta["summary"] = consensus.runs_summary(runs, st["uncertain_threshold"])
        p.save_meta(meta)
        if old and old.get("edited"):
            # gebruiker heeft al bewerkt: tekst bewaren, alleen sprekers opnieuw toewijzen als er diarisatie is
            (p.path / "transcript_recombined.json").write_text(json.dumps({**combined, "speakers": speakers}, ensure_ascii=False), encoding="utf-8")
            if turns:
                p.snapshot("voor_diarisatie")
                old_speakers = diarize.assign(old["segments"], turns)
                for sid, sp in (old.get("speakers") or {}).items():
                    if sid in old_speakers and not sp["name"].startswith("Spreker "):
                        old_speakers[sid] = sp
                old["speakers"] = old_speakers
                p.save_transcript(old)
                p.log("sprekers toegewezen aan bewerkt transcript (tekst ongewijzigd); nieuwe combinatie apart in transcript_recombined.json")
            else:
                p.log("transcript was al bewerkt; nieuwe combinatie opgeslagen als transcript_recombined.json")
        else:
            p.save_transcript({**combined, "speakers": speakers, "edited": False}, keep_version=False)


def start(project: Project, only_models: list[str] | None = None) -> Job:
    with _lock:
        if project.name in _running:
            return _running[project.name]
        job = Job(project, only_models)
        _running[project.name] = job
    threading.Thread(target=job.run, daemon=True, name=f"job-{project.name}").start()
    return job


def status(project: Project) -> dict:
    with _lock:
        job = _running.get(project.name)
    if job:
        return {"running": True, **job.state}
    m = project.meta()
    return {"running": False, "step": m.get("status"), "progress": 1.0 if m.get("status") == "klaar" else 0.0, "done": m.get("status") in ("klaar", "fout"), "error": m.get("error")}


def cancel(project: Project) -> bool:
    with _lock:
        job = _running.get(project.name)
    if job:
        job.cancel = True
        return True
    return False
