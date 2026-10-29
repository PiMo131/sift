"""Sprekerscheiding met pyannote (optioneel; vereist Hugging Face-token en geaccepteerde modelvoorwaarden).

Zonder token of pakket wordt None teruggegeven en krijgt alles 'Spreker 1'. Sprekertoewijzing per segment volgt de
noScribe-regel: de diarisatiebeurt met de grootste overlapfractie wint; boven 0,8 heeft een kortere beurt voorrang.
"""
from __future__ import annotations

from pathlib import Path

from .config import hf_token


def available() -> bool:
    try:
        import pyannote.audio  # noqa: F401
        return hf_token() is not None
    except Exception:
        return False


def run(wav: Path, num_speakers: int | None, device: str, log=print) -> list[dict] | None:
    if not available():
        return None
    import torch
    from pyannote.audio import Pipeline

    pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=hf_token())
    if device == "cuda" and torch.cuda.is_available():
        pipe.to(torch.device("cuda"))
    kw = {"num_speakers": num_speakers} if num_speakers else {}
    diar = pipe(str(wav), **kw)
    turns = [{"start": float(t.start), "end": float(t.end), "speaker": s} for t, _, s in diar.itertracks(yield_label=True)]
    turns.sort(key=lambda t: t["start"])
    return turns


def assign(segments: list[dict], turns: list[dict] | None, default: str = "S1") -> dict:
    """Zet speaker-ids op segmenten; geeft speakers-mapping terug."""
    if not turns:
        for s in segments:
            s["speaker"] = default
        return {default: {"name": "Spreker 1"}}
    labels = sorted({t["speaker"] for t in turns})
    ids = {lab: f"S{i+1}" for i, lab in enumerate(labels)}
    for s in segments:
        best, best_frac, best_len = None, 0.0, 0.0
        seg_len = max(s["end"] - s["start"], 1e-3)
        for t in turns:
            ov = max(0.0, min(s["end"], t["end"]) - max(s["start"], t["start"]))
            if ov <= 0:
                continue
            frac = ov / seg_len
            tlen = t["end"] - t["start"]
            if frac > best_frac or (best_frac >= 0.8 and frac >= 0.8 and tlen < best_len):
                best, best_frac, best_len = t, frac, tlen
        s["speaker"] = ids[best["speaker"]] if best else (segments[segments.index(s) - 1]["speaker"] if segments.index(s) > 0 else ids[labels[0]])
    return {sid: {"name": f"Spreker {i+1}"} for i, sid in enumerate(ids.values())}
