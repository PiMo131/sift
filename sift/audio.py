"""Audio inlezen, meten, normaliseren en voorbereiden voor afspelen. Alles via ffmpeg."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np

from .config import find_ffmpeg


class AudioError(RuntimeError):
    pass


def _ff() -> str:
    p = find_ffmpeg()
    if not p:
        raise AudioError("ffmpeg niet gevonden. Installeer met: winget install Gyan.FFmpeg")
    return p


def _run(args: list[str], capture=True) -> str:
    proc = subprocess.run(args, capture_output=capture, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise AudioError((proc.stderr or "")[-2000:])
    return (proc.stderr or "") + (proc.stdout or "")


def probe(path: Path) -> dict:
    ffprobe = str(Path(_ff()).with_name("ffprobe.exe" if _ff().endswith(".exe") else "ffprobe"))
    out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_name,sample_rate,channels",
                          "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise AudioError(f"Bestand niet leesbaar: {out.stderr.strip()[-500:]}")
    info = json.loads(out.stdout)
    streams = [s for s in info.get("streams", []) if s.get("codec_name")]
    return {"duration": float(info["format"].get("duration", 0)), "codec": streams[0].get("codec_name") if streams else None,
            "sample_rate": int(streams[0].get("sample_rate", 0)) if streams else None, "channels": streams[0].get("channels") if streams else None}


def to_wav16k(src: Path, dst: Path, start: float | None = None, end: float | None = None) -> None:
    args = [_ff(), "-hide_banner", "-loglevel", "error", "-y"]
    if start:
        args += ["-ss", str(start)]
    args += ["-i", str(src)]
    if end:
        args += ["-t", str(max(0.0, end - (start or 0)))]
    args += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)]
    _run(args)


def measure_loudness(wav: Path, target: float) -> dict:
    out = _run([_ff(), "-hide_banner", "-nostats", "-i", str(wav), "-af",
                f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", out, re.S)
    if not m:
        raise AudioError("Luidheidsmeting mislukt")
    d = json.loads(m.group(0))
    return {k: float(d[k]) for k in ("input_i", "input_tp", "input_lra", "input_thresh")}


def normalize(src16k: Path, dst: Path, target: float = -16, compressor: bool = True, denoise: str = "off") -> dict:
    """Highpass, optioneel ruisfilter, compressor en 2-pass loudnorm. Geeft meetwaarden voor/na."""
    before = measure_loudness(src16k, target)
    chain = ["highpass=f=80"]
    if denoise == "light":
        chain.append("afftdn=nf=-25:nt=w:om=o")
    elif denoise == "strong":
        chain.append("afftdn=nf=-20:nt=w:om=o:tr=1")
    if compressor:
        chain.append("acompressor=threshold=-30dB:ratio=3:attack=10:release=200:makeup=4")
    chain.append(f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={before['input_i']}:measured_TP={before['input_tp']}:"
                 f"measured_LRA={before['input_lra']}:measured_thresh={before['input_thresh']}:linear=true")
    _run([_ff(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src16k), "-af", ",".join(chain), "-ar", "16000", str(dst)])
    after = measure_loudness(dst, target)
    return {"before_lufs": before["input_i"], "before_lra": before["input_lra"], "after_lufs": after["input_i"], "after_lra": after["input_lra"]}


def to_playback(src: Path, dst_m4a: Path) -> None:
    """Compacte AAC voor de browser (seekbaar, klein)."""
    _run([_ff(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(dst_m4a)])


def waveform_peaks(wav: Path, bins: int = 3000) -> list[float]:
    import soundfile as sf
    data, sr = sf.read(str(wav), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    n = len(data)
    if n == 0:
        return []
    size = max(1, n // bins)
    trimmed = data[: size * (n // size)]
    chunks = np.abs(trimmed.reshape(-1, size))
    peaks = chunks.max(axis=1)
    mx = float(peaks.max()) or 1.0
    return [round(float(p) / mx, 3) for p in peaks]
