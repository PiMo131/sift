"""faster-whisper-adapter. Wordt als subproces gestart door engines.run_engine.

Argumenten: <audio.wav 16k mono> <uit.json> <opties-json>
Opties: model, hf_repo, device (cuda|cpu), compute_type, language, beam_size, hotwords, initial_prompt, vad (bool)
Schrijft voortgang als JSON-regels naar stdout. Bij een CUDA-fout één keer opnieuw op CPU.

Modeldownload: faster-whisper haalt een model bij het eerste gebruik van Hugging Face. Staat het model nog niet in de
cache, dan downloaden we het hier eerst expliciet (snapshot_download in een thread) en melden we de voortgang als
{"download": {"bytes", "total"}}, zodat de interface downloaden en herkennen apart kan tonen.
"""
from __future__ import annotations

import json
import os
import pathlib
import site
import sys
import threading
import time


def _enable_cuda_dlls():
    for sp in site.getsitepackages():
        for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin"):
            p = pathlib.Path(sp) / sub
            if p.is_dir():
                try:
                    os.add_dll_directory(str(p))
                except Exception:
                    pass
                os.environ["PATH"] = str(p) + os.pathsep + os.environ["PATH"]


def emit(**kw):
    print(json.dumps(kw, ensure_ascii=False), flush=True)


def _cache_dir(repo: str) -> pathlib.Path:
    from huggingface_hub import constants
    return pathlib.Path(constants.HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))


def _dir_size(p: pathlib.Path) -> int:
    total = 0
    for f in p.rglob("*"):
        try:
            if f.is_file() and not f.is_symlink():
                total += f.stat().st_size
        except OSError:
            pass
    return total


def ensure_downloaded(repo: str | None, est_total: int) -> None:
    """Download het model vooraf met zichtbare voortgang (alleen als het nog niet in de cache staat)."""
    if not repo:
        return
    d = _cache_dir(repo)
    if (d / "snapshots").exists() and any((s / "model.bin").exists() for s in (d / "snapshots").iterdir()):
        return
    from huggingface_hub import snapshot_download
    emit(download={"model": repo, "bytes": 0, "total": est_total, "status": "start"})
    err: list[Exception] = []

    def dl():
        try:
            snapshot_download(repo, allow_patterns=["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"])
        except Exception as e:  # noqa: BLE001
            err.append(e)
    th = threading.Thread(target=dl, daemon=True)
    th.start()
    while th.is_alive():
        time.sleep(1.0)
        emit(download={"model": repo, "bytes": _dir_size(d) if d.exists() else 0, "total": est_total, "status": "bezig"})
    if err:
        raise RuntimeError(f"modeldownload mislukt ({repo}): {err[0]}")
    emit(download={"model": repo, "bytes": _dir_size(d), "total": est_total, "status": "klaar"})


def transcribe(audio: str, opt: dict, device: str, compute: str) -> dict:
    import soundfile as sf
    from faster_whisper import WhisperModel

    wav, sr = sf.read(audio, dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != 16000:
        raise RuntimeError(f"verwacht 16 kHz, kreeg {sr}")
    duration = len(wav) / 16000.0

    t0 = time.time()
    cpu_threads = max(1, (os.cpu_count() or 4) // 2) if device == "cpu" else 0
    model = WhisperModel(opt["model"], device=device, compute_type=compute, cpu_threads=cpu_threads)
    load_s = time.time() - t0
    emit(progress=0.0, text=f"model geladen ({load_s:.0f}s)")

    kwargs = dict(language=opt.get("language") or None, beam_size=int(opt.get("beam_size", 5)), word_timestamps=True,
                  vad_filter=bool(opt.get("vad", True)), vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 50},
                  condition_on_previous_text=False, temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0], no_speech_threshold=0.5)
    if opt.get("hotwords"):
        kwargs["hotwords"] = opt["hotwords"]
    if opt.get("initial_prompt"):
        kwargs["initial_prompt"] = opt["initial_prompt"]

    t0 = time.time()
    segments, info = model.transcribe(wav, **kwargs)
    segs, words = [], []
    for s in segments:
        segs.append({"start": float(s.start), "end": float(s.end), "text": s.text.strip(),
                     "avg_logprob": float(s.avg_logprob), "no_speech_prob": float(s.no_speech_prob)})
        for w in (s.words or []):
            words.append({"start": float(w.start), "end": float(w.end), "word": w.word.strip(), "p": round(float(w.probability), 4)})
        emit(progress=min(0.99, float(s.end) / max(duration, 1e-6)), text=s.text.strip()[:80])
    run_s = time.time() - t0
    probs = [w["p"] for w in words]
    return {
        "stats": {"model": opt["model"], "device": device, "compute": compute, "load_s": round(load_s, 1), "run_s": round(run_s, 1),
                  "audio_s": round(duration, 1), "realtime_factor": round(duration / max(run_s, 1e-6), 1),
                  "n_segments": len(segs), "n_words": len(words), "mean_p": round(sum(probs) / max(len(probs), 1), 3),
                  "language": getattr(info, "language", None), "language_probability": round(float(getattr(info, "language_probability", 0) or 0), 3)},
        "segments": segs, "words": words,
    }


def main():
    audio, out_json, opt = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    device, compute = opt.get("device", "cpu"), opt.get("compute_type", "int8")
    if device == "cuda":
        _enable_cuda_dlls()
    try:
        ensure_downloaded(opt.get("hf_repo"), int(opt.get("size_bytes") or 0))
    except Exception as e:
        emit(error=str(e))
        raise
    try:
        result = transcribe(audio, opt, device, compute)
    except Exception as e:  # één keer terugvallen op CPU
        if device == "cuda":
            emit(progress=0.0, text=f"GPU-fout ({str(e)[:120]}), opnieuw op CPU")
            result = transcribe(audio, opt, "cpu", "int8")
        else:
            emit(error=str(e))
            raise
    pathlib.Path(out_json).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    emit(progress=1.0, text="klaar")


if __name__ == "__main__":
    main()
