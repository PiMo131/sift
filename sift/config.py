"""Paden, hardwaredetectie en standaardinstellingen."""
from __future__ import annotations

import glob
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "sift"
ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = Path(os.environ.get("SIFT_PROJECTS") or os.environ.get("sift_PROJECTS") or (ROOT / "projects"))
STATIC_DIR = Path(__file__).resolve().parent / "static"
HF_CACHE = Path(os.environ.get("HF_HUB_CACHE") or os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface") / "hub")

MODELS = {
    # id: engine (module in sift.engines), modelnaam voor die engine, geschatte snelheid (x realtime), downloadgrootte, opmerking
    "large-v3": {"label": "Whisper large-v3", "engine": "fasterwhisper", "fw": "large-v3", "hf_repo": "Systran/faster-whisper-large-v3", "size_gb": 3.1,
                 "xrt_gpu": 7, "xrt_cpu": 1.5, "note": "Beste kwaliteit, aanbevolen basis"},
    "large-v3-turbo": {"label": "Whisper large-v3-turbo", "engine": "fasterwhisper", "fw": "large-v3-turbo", "hf_repo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "size_gb": 1.6,
                       "xrt_gpu": 25, "xrt_cpu": 2.5, "note": "Snel, iets minder nauwkeurig"},
    "medium": {"label": "Whisper medium", "engine": "fasterwhisper", "fw": "medium", "hf_repo": "Systran/faster-whisper-medium", "size_gb": 1.5,
               "xrt_gpu": 12, "xrt_cpu": 3, "note": "Lichter, voor zwakke hardware"},
    "qwen3-asr": {"label": "Qwen3-ASR 1.7B", "engine": "qwen3", "fw": "Qwen/Qwen3-ASR-1.7B", "hf_repo": "Qwen/Qwen3-ASR-1.7B", "size_gb": 4.0,
                  "xrt_gpu": 5, "xrt_cpu": 0.2, "note": "Ander modelfamilie, extra stem; geen woordzekerheid; vereist pip install qwen-asr torch", "optional": True},
}

LANGUAGES = [("nl", "Nederlands"), ("en", "Engels"), ("de", "Duits"), ("fr", "Frans"), ("es", "Spaans"), ("it", "Italiaans"), ("tr", "Turks"), ("ar", "Arabisch"), ("pl", "Pools"), ("", "Automatisch herkennen")]

DEFAULT_SETTINGS = {
    "language": "nl",
    "models": ["large-v3", "large-v3-turbo"],
    "combine": "consensus",          # consensus | highest_p | base_plus_alts
    "device": "auto",                # auto | cuda | cpu
    "normalize": True,
    "target_lufs": -16,
    "compressor": True,
    "denoise": "off",                # off | light | strong
    "diarize": True,
    "num_speakers": 2,               # None = weet ik niet (Sift schat 2..5 op stemkenmerken)
    "hotwords": "Uhm, weet je, dit is, eh, zeker niet makkelijk.",
    "initial_prompt": "",            # eigen namen/termen van dit interview (de woordenlijst van het onderzoek komt daar bovenop)
    "beam_size": 5,
    "uncertain_threshold": 0.6,
    "start": None,                   # seconden; None = begin
    "end": None,
}


def find_ffmpeg() -> str | None:
    env = os.environ.get("SIFT_FFMPEG") or os.environ.get("sift_FFMPEG")
    if env and Path(env).exists():
        return env
    p = shutil.which("ffmpeg")
    if p:
        return p
    candidates = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates += glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "**", "ffmpeg.exe"), recursive=True)
        candidates += glob.glob(os.path.join(local, "Microsoft", "WinGet", "Links", "ffmpeg.exe"))
    candidates += glob.glob(r"C:\ffmpeg\bin\ffmpeg.exe")
    return candidates[0] if candidates else None


def cuda_available() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def resolve_device(setting: str) -> tuple[str, str]:
    """Geeft (device, compute_type)."""
    if setting == "cpu" or (setting == "auto" and not cuda_available()):
        return "cpu", "int8"
    return "cuda", "float16"


def model_downloaded(mid: str) -> bool:
    """Staat het model al in de Hugging Face-cache? (faster-whisper downloadt bij het eerste gebruik)"""
    repo = MODELS.get(mid, {}).get("hf_repo")
    if not repo:
        return False
    d = HF_CACHE / ("models--" + repo.replace("/", "--")) / "snapshots"
    if not d.exists():
        return False
    return any((snap / "model.bin").exists() or (snap / "model.safetensors").exists() or any(snap.glob("*.safetensors")) for snap in d.iterdir())


def engine_available(mid: str) -> bool:
    eng = MODELS.get(mid, {}).get("engine", "fasterwhisper")
    if eng == "qwen3":
        try:
            import qwen_asr  # noqa: F401
            return True
        except Exception:
            return False
    return True


def hardware_info() -> dict:
    info = {"cuda": cuda_available(), "gpu_name": None, "vram_gb": None, "cpu_threads": os.cpu_count(), "ffmpeg": find_ffmpeg(), "python": sys.version.split()[0]}
    if info["cuda"]:
        try:
            import torch
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["vram_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1)
        except Exception:
            info["gpu_name"] = "CUDA-GPU"
    try:
        import psutil  # optioneel
        info["ram_gb"] = round(psutil.virtual_memory().total / 2**30, 1)
    except Exception:
        info["ram_gb"] = None
    return info


def recommended_settings(hw: dict | None = None) -> dict:
    """Passende standaardconfiguratie op basis van de beschikbare computer. Geeft ook een uitleg in gewone taal."""
    hw = hw or hardware_info()
    if hw.get("cuda") and (hw.get("vram_gb") or 0) >= 6:
        models, why = ["large-v3", "large-v3-turbo"], f"GPU gevonden ({hw.get('gpu_name')}): twee modellen, het beste en een snelle tweede stem."
    elif hw.get("cuda"):
        models, why = ["large-v3-turbo"], f"GPU met weinig geheugen ({hw.get('vram_gb')} GB): één snel model."
    elif (hw.get("cpu_threads") or 4) >= 8:
        models, why = ["large-v3-turbo"], "Geen NVIDIA-GPU: één snel model op de processor (ongeveer 2,5× sneller dan realtime)."
    else:
        models, why = ["medium"], "Weinig rekenkracht: het lichte model medium."
    return {"models": models, "combine": "consensus", "device": "auto", "why": why}


def models_info() -> dict:
    """MODELS aangevuld met beschikbaarheid en downloadstatus, voor de interface."""
    out = {}
    for mid, m in MODELS.items():
        out[mid] = {**m, "available": engine_available(mid), "downloaded": model_downloaded(mid)}
    return out
