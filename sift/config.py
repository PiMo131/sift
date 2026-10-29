"""Paden, hardwaredetectie en standaardinstellingen."""
from __future__ import annotations

import glob
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "sift"
ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = Path(os.environ.get("SIFT_PROJECTS") or os.environ.get("STEMSPOOR_PROJECTS") or (ROOT / "projects"))
STATIC_DIR = Path(__file__).resolve().parent / "static"

MODELS = {
    # id: engine (module in sift.engines), modelnaam voor die engine, geschatte snelheid (x realtime), opmerking
    "large-v3": {"label": "Whisper large-v3", "engine": "fasterwhisper", "fw": "large-v3", "xrt_gpu": 7, "xrt_cpu": 1.5, "note": "Beste kwaliteit, aanbevolen basis"},
    "large-v3-turbo": {"label": "Whisper large-v3-turbo", "engine": "fasterwhisper", "fw": "large-v3-turbo", "xrt_gpu": 25, "xrt_cpu": 2.5, "note": "Snel, iets minder nauwkeurig"},
    "medium": {"label": "Whisper medium", "engine": "fasterwhisper", "fw": "medium", "xrt_gpu": 12, "xrt_cpu": 3, "note": "Lichter, voor zwakke hardware"},
    "qwen3-asr": {"label": "Qwen3-ASR 1.7B", "engine": "qwen3", "fw": "Qwen/Qwen3-ASR-1.7B", "xrt_gpu": 5, "xrt_cpu": 0.2, "note": "Ander modelfamilie, extra stem; geen woordzekerheid; vereist pip install qwen-asr torch", "optional": True},
}

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
    "num_speakers": 2,
    "hotwords": "Uhm, weet je, dit is, eh, zeker niet makkelijk.",
    "initial_prompt": "",
    "beam_size": 5,
    "uncertain_threshold": 0.6,
    "start": None,                   # seconden; None = begin
    "end": None,
}


def find_ffmpeg() -> str | None:
    env = os.environ.get("SIFT_FFMPEG")
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


def hardware_info() -> dict:
    info = {"cuda": cuda_available(), "gpu_name": None, "cpu_threads": os.cpu_count(), "ffmpeg": find_ffmpeg(), "python": sys.version.split()[0]}
    if info["cuda"]:
        try:
            import torch
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["vram_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1)
        except Exception:
            info["gpu_name"] = "CUDA-GPU"
    return info
