"""Opname verwerken. Elke stap is gecached: bestaat de uitvoer al en zijn de instellingen gelijk, dan wordt de stap
overgeslagen. Modellen draaien NA ELKAAR (één GPU tegelijk) in een subproces.

Fasen (in gewone taal voor de interface):
  prepare     Opname voorbereiden   convert -> normalize -> playback -> peaks -> vad
  download    Model downloaden      (eenmalig, apart zichtbaar van het herkennen)
  transcribe  Tekst herkennen       per model
  diarize     Sprekers toewijzen
  combine     Transcript voorbereiden (combineren + controle op mogelijk ontbrekende tekst)

Onderbreken stopt het lopende subproces; afgeronde modelruns blijven bewaard, dus hervatten gaat verder waar het bleef.
Handmatige correcties in een bestaand transcript worden nooit overschreven (zie _combine_step).
"""
from __future__ import annotations

import json
import re
import threading
import time
import traceback
from pathlib import Path

from . import audio, consensus, diarize, gaps, studies
from .config import MODELS, model_downloaded, resolve_device
from .engines import run_engine
from .project import Project

_lock = threading.Lock()
_running: dict[str, "Job"] = {}

PHASES = {"prepare": "Opname voorbereiden", "download": "Model downloaden", "transcribe": "Tekst herkennen",
          "diarize": "Sprekers toewijzen", "combine": "Transcript voorbereiden", "done": "Klaar", "cancelled": "Onderbroken", "error": "Mislukt"}


class Cancelled(RuntimeError):
    pass


def friendly_error(msg: str) -> dict:
    """Technische fout → concrete vervolgstap. De ruwe tekst blijft beschikbaar in details."""
    m = (msg or "").lower()
    if "ffmpeg niet gevonden" in m or "ffmpeg" in m and "not found" in m:
        return {"title": "ffmpeg ontbreekt", "steps": ["Installeer ffmpeg (Windows: winget install Gyan.FFmpeg) en start Sift opnieuw.", "Of zet de omgevingsvariabele SIFT_FFMPEG naar ffmpeg.exe."]}
    if "out of memory" in m or "cuda_error_out_of_memory" in m or "cublas" in m and "alloc" in m:
        return {"title": "Te weinig GPU-geheugen", "steps": ["Kies onder Geavanceerd één model (bijvoorbeeld alleen large-v3-turbo).", "Of zet het apparaat op CPU; dat is trager maar werkt altijd."]}
    if "cudnn" in m or "cublas" in m or "cuda" in m and ("driver" in m or "library" in m or "dll" in m):
        return {"title": "GPU-onderdelen niet gevonden", "steps": ["Sift probeert automatisch opnieuw op de CPU.", "Blijft het misgaan: zet het apparaat onder Geavanceerd op CPU, of werk de NVIDIA-driver bij."]}
    if "bestand niet leesbaar" in m or "invalid data found" in m or "moov atom" in m:
        return {"title": "De opname kan niet worden gelezen", "steps": ["Controleer of het bestand compleet is en afspeelt in een mediaspeler.", "Zet het eventueel om naar mp3 of wav en maak een nieuw interview aan."]}
    if "geannuleerd" in m or "onderbroken" in m:
        return {"title": "Verwerking onderbroken", "steps": ["Klik op 'Hervatten' om verder te gaan; afgeronde stappen worden niet opnieuw gedaan."]}
    if "connection" in m or "huggingface" in m or "download" in m or "resolve" in m or "ssl" in m or "max retries" in m:
        return {"title": "Modeldownload mislukt", "steps": ["Voor het eenmalig downloaden van een spraakmodel is internet nodig.", "Controleer de verbinding en klik op 'Hervatten'."]}
    if "permission" in m or "access is denied" in m or "toegang geweigerd" in m:
        return {"title": "Een bestand was tijdelijk geblokkeerd", "steps": ["Vaak komt dit door OneDrive of een virusscanner die het bestand even vasthoudt.", "Klik op 'Hervatten'. Blijft het misgaan: zet de projectmap buiten een gesynchroniseerde map (SIFT_PROJECTS)."]}
    if "onbekend model" in m or "qwen" in m and "niet geïnstalleerd" in m:
        return {"title": "Dit model is niet beschikbaar", "steps": ["Kies onder Geavanceerd een ander model."]}
    return {"title": "Verwerking mislukt", "steps": ["Klik op 'Hervatten' om het opnieuw te proberen.", "Blijft het misgaan: open 'Technische details' en meld de foutmelding."]}


class Job:
    def __init__(self, project: Project, only_models: list[str] | None = None):
        self.project = project
        self.only_models = only_models
        self.cancel = False
        self.proc = None
        self.started = time.time()
        self.phase_started = time.time()
        self.state = {"phase": "prepare", "step": PHASES["prepare"], "progress": 0.0, "detail": "", "done": False, "error": None, "model": None,
                      "download": None, "eta": None, "models_total": 0, "models_done": 0}

    def set(self, **kw):
        if "phase" in kw and kw["phase"] != self.state.get("phase"):
            self.phase_started = time.time()
            kw.setdefault("step", PHASES.get(kw["phase"], kw["phase"]))
        self.state.update(kw)

    def check_cancel(self):
        if self.cancel:
            raise Cancelled("onderbroken")

    def run(self):
        p = self.project
        try:
            meta = p.meta()
            st = meta["settings"]
            meta["status"] = "bezig"
            meta["error"] = None
            meta["error_help"] = None
            p.save_meta(meta)
            self._audio_steps(p, meta, st)
            self.check_cancel()
            self._transcribe_steps(p, meta, st)
            self.check_cancel()
            self._diarize_step(p, meta, st)
            self.check_cancel()
            self._combine_step(p, meta, st)
            meta = p.meta()
            meta["status"] = "klaar"
            p.save_meta(meta)
            self.set(phase="done", progress=1.0, done=True, eta=None)
            p.log("verwerking klaar")
        except Cancelled:
            meta = p.meta()
            meta["status"] = "onderbroken"
            meta["error"] = "onderbroken door de gebruiker"
            meta["error_help"] = friendly_error("onderbroken")
            p.save_meta(meta)
            self.set(phase="cancelled", done=True, eta=None)
            p.log("verwerking onderbroken; afgeronde stappen blijven bewaard")
        except Exception as e:
            p.log("FOUT: " + "".join(traceback.format_exception_only(type(e), e)).strip())
            p.log(traceback.format_exc()[-1500:])
            meta = p.meta()
            meta["status"] = "fout"
            meta["error"] = str(e)
            meta["error_help"] = friendly_error(str(e))
            p.save_meta(meta)
            self.set(phase="error", error=str(e), done=True, eta=None)
        finally:
            with _lock:
                _running.pop(p.name, None)

    # ---------- audio ----------
    def _audio_steps(self, p: Project, meta: dict, st: dict):
        src = p.path / meta["source"]
        wav16 = p.work / "audio_16k.wav"
        key = {"start": st.get("start"), "end": st.get("end")}
        if not wav16.exists() or meta["steps"].get("convert") != key:
            self.set(phase="prepare", progress=0.02, detail="opname inlezen")
            info = audio.probe(src)
            audio.to_wav16k(src, wav16, st.get("start"), st.get("end"))
            p.invalidate_audio_caches()  # ander fragment: alles wat hiervan is afgeleid is ongeldig
            meta["audio"].update({"source_info": info, "duration": audio.probe(wav16)["duration"]})
            meta["steps"]["convert"] = key
            meta["runs"] = {}
            p.save_meta(meta)
            p.log(f"ingelezen: {info}")
        norm = p.work / "audio_norm.wav"
        key = {"normalize": st["normalize"], "target": st["target_lufs"], "compressor": st["compressor"], "denoise": st["denoise"]}
        if not norm.exists() or meta["steps"].get("normalize") != key:
            if st["normalize"]:
                self.set(phase="prepare", progress=0.06, detail="luidheid gelijktrekken, zodat zachte spraak beter hoorbaar is")
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
            meta["runs"] = {}
            p.save_meta(meta)
        if not (p.work / "play.m4a").exists():
            self.set(phase="prepare", progress=0.09, detail="afspeelbestanden maken")
            audio.to_playback(norm, p.work / "play.m4a")
            audio.to_playback(wav16, p.work / "play_orig.m4a")
        if not (p.work / "peaks.json").exists():
            (p.work / "peaks.json").write_text(json.dumps(audio.waveform_peaks(norm)), encoding="utf-8")
        if not (p.work / "vad.json").exists():
            self.set(phase="prepare", progress=0.11, detail="spraak en stilte in kaart brengen")
            try:
                (p.work / "vad.json").write_text(json.dumps(gaps.speech_regions(norm)), encoding="utf-8")
            except Exception as e:  # niet fataal: dan geen controle op ontbrekende tekst
                p.log(f"spraakdetectie overgeslagen: {e}")

    # ---------- transcriberen ----------
    def _transcribe_steps(self, p: Project, meta: dict, st: dict):
        device, compute = resolve_device(st["device"])
        models = self.only_models or st["models"]
        norm = p.work / "audio_norm.wav"
        study = studies.get(meta.get("study_id"))
        prompt = studies.effective_terms(study, st.get("initial_prompt", ""))
        self.set(models_total=len(models), models_done=0)
        for i, mid in enumerate(models):
            self.check_cancel()
            if mid not in MODELS:
                raise ValueError(f"onbekend model {mid}")
            out = p.run_path(mid)
            key = {"model": mid, "language": st["language"], "beam": st["beam_size"], "hotwords": st["hotwords"], "prompt": prompt}
            meta = p.meta()
            if out.exists() and meta["runs"].get(mid, {}).get("key") == key:
                p.log(f"{mid}: uit cache")
                self.set(models_done=i + 1)
                continue
            base = 0.12 + 0.7 * (i / len(models))
            span = 0.7 / len(models)
            label = MODELS[mid]["label"]
            if not model_downloaded(mid):
                self.set(phase="download", progress=base, model=mid, detail=f"{label} wordt eenmalig gedownload (± {MODELS[mid].get('size_gb', '?')} GB)",
                         download={"model": mid, "label": label, "bytes": 0, "total": int(MODELS[mid].get("size_gb", 0) * 1e9)})
            else:
                self.set(phase="transcribe", progress=base, model=mid, detail=f"{label} laden ({device})", download=None)
            p.log(f"{mid}: start op {device} ({compute})")
            t0 = time.time()

            def prog(frac, text, base=base, span=span, t0=t0, label=label):
                if isinstance(text, dict) and "download" in text:
                    d = text["download"]
                    self.set(phase="download", download=d, detail=f"{label} downloaden: {d.get('bytes', 0) / 1e9:.1f} van ± {d.get('total', 0) / 1e9:.1f} GB")
                    return
                if self.state["phase"] != "transcribe":
                    self.set(phase="transcribe", download=None)
                    t0 = time.time()
                self.set(progress=base + span * frac, detail=f"{label}: {text}" if text else label, eta=self._eta(frac, t0))

            opts = {"model": MODELS[mid]["fw"], "hf_repo": MODELS[mid].get("hf_repo"), "size_bytes": int(MODELS[mid].get("size_gb", 0) * 1e9), "device": device, "compute_type": compute, "language": st["language"],
                    "beam_size": st["beam_size"], "hotwords": st["hotwords"], "initial_prompt": prompt, "vad": True}
            try:
                result = run_engine(MODELS[mid].get("engine", "fasterwhisper"), norm, out, opts, prog, should_cancel=lambda: self.cancel)
            except RuntimeError:
                if self.cancel:
                    raise Cancelled("onderbroken")
                raise
            self.check_cancel()
            meta = p.meta()
            meta["runs"][mid] = {"key": key, "stats": result["stats"]}
            p.save_meta(meta)
            self.set(models_done=i + 1, eta=None)
            p.log(f"{mid}: klaar, {result['stats']}")

    def _eta(self, frac: float, t0: float) -> dict | None:
        """Resterende tijd met onzekerheidsmarge, pas als er genoeg gegevens zijn."""
        el = time.time() - t0
        if frac < 0.08 or el < 8:
            return None
        rem = el * (1 - frac) / frac
        return {"seconds": int(rem), "low": int(rem * 0.7), "high": int(rem * 1.4)}

    # ---------- diarisatie ----------
    def _diarize_step(self, p: Project, meta: dict, st: dict):
        turns_path = p.work / "diarization.json"
        if not st.get("diarize"):
            return
        key = {"n": st.get("num_speakers")}
        meta = p.meta()
        if turns_path.exists() and meta["steps"].get("diarize") == key:
            return
        if not diarize.available():
            p.log("sprekers toewijzen overgeslagen: speechbrain/torch ontbreekt")
            return
        runs = p.load_runs()
        base = next((m for m in st["models"] if m in runs), None)
        if not base:
            return
        self.set(phase="diarize", progress=0.86, detail="stemkenmerken per segment vergelijken" + ("" if st.get("num_speakers") else " en het aantal sprekers schatten"))
        device, _ = resolve_device(st["device"])
        turns = diarize.run(p.work / "audio_norm.wav", runs[base]["segments"], st.get("num_speakers") or None, device,
                            lambda t: self.set(detail=t))
        if turns is None:
            p.log("sprekers toewijzen mislukt")
            return
        turns_path.write_text(json.dumps(turns), encoding="utf-8")
        meta = p.meta()
        meta["diarization"] = {"method": "embeddings", "turns": len(turns), "speakers": len({t["speaker"] for t in turns}), "requested": st.get("num_speakers")}
        meta["steps"]["diarize"] = key
        p.save_meta(meta)
        p.log(f"sprekers (embeddings): {meta['diarization']['speakers']} gevonden, {len(turns)} beurten")

    # ---------- combineren ----------
    def _combine_step(self, p: Project, meta: dict, st: dict):
        self.set(phase="combine", progress=0.92, detail="uitkomsten van de modellen per woord naast elkaar leggen")
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
            for sid, sp in old["speakers"].items():  # sprekernamen bewaren bij opnieuw combineren
                if sid in speakers:
                    speakers[sid] = sp
        meta = p.meta()
        meta["speakers"] = speakers
        meta["summary"] = consensus.runs_summary(runs, st["uncertain_threshold"])
        p.save_meta(meta)
        vad = None
        if (p.work / "vad.json").exists():
            vad = json.loads((p.work / "vad.json").read_text(encoding="utf-8"))
        self.set(detail="controleren op mogelijk ontbrekende tekst")
        if old and old.get("edited"):
            # gebruiker heeft al bewerkt: tekst bewaren, alleen sprekers opnieuw toewijzen als er diarisatie is
            (p.path / "transcript_recombined.json").write_text(json.dumps({**combined, "speakers": speakers}, ensure_ascii=False), encoding="utf-8")
            if turns:
                p.snapshot("voor sprekers toewijzen")
                old_speakers = diarize.assign(old["segments"], turns)
                for sid, sp in (old.get("speakers") or {}).items():
                    if sid in old_speakers and not sp["name"].startswith("Spreker "):
                        old_speakers[sid] = sp
                old["speakers"] = old_speakers
            words = [w for s in old["segments"] for w in (s.get("words") or [])]
            old["gaps"] = gaps.carry_dismissed(old.get("gaps"), gaps.detect(vad, runs, words, combined["base_model"]))
            p.save_transcript(old)
            p.log("bewerkt transcript bewaard (tekst ongewijzigd); nieuwe combinatie apart in transcript_recombined.json")
        else:
            words = [w for s in combined["segments"] for w in s["words"]]
            found = gaps.detect(vad, runs, words, combined["base_model"])
            p.save_transcript({**combined, "speakers": speakers, "edited": False, "gaps": gaps.carry_dismissed(old.get("gaps") if old else None, found)}, keep_version=False)
            p.log(f"mogelijk ontbrekende tekst: {len(found)} interval(len)")


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
        return {"running": True, **job.state, "elapsed": int(time.time() - job.started)}
    m = project.meta()
    st = m.get("status")
    if st == "bezig":  # geen job meer maar status 'bezig': de server is herstart tijdens het verwerken
        m["status"] = st = "onderbroken"
        m["error"] = "verwerking onderbroken (Sift is tussendoor gestopt)"
        m["error_help"] = friendly_error("onderbroken")
        project.save_meta(m)
    phase = {"klaar": "done", "fout": "error", "onderbroken": "cancelled"}.get(st, "idle")
    return {"running": False, "phase": phase, "step": PHASES.get(phase, st), "progress": 1.0 if st == "klaar" else 0.0,
            "done": st in ("klaar", "fout", "onderbroken"), "error": m.get("error"), "error_help": m.get("error_help")}


def cancel(project: Project) -> bool:
    with _lock:
        job = _running.get(project.name)
    if job:
        job.cancel = True
        return True
    return False
