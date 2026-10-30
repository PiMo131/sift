"""Mogelijk ontbrekende tekst.

De combinatielogica gebruikt de woorden van het basismodel als ruggengraat; een passage die het basismodel helemaal
overslaat krijgt daardoor vanzelf geen aandachtspunt. Deze lichte controle zoekt twee signalen:

  1. vad      Spraak volgens de spraakdetectie (Silero VAD, zelfde als in faster-whisper) zonder enig woord in het
              transcript in dat interval (minimaal MIN_GAP_S).
  2. coverage Een ander model heeft in een interval twee of meer woorden waar het transcript er geen heeft.
              De tekst van dat model wordt als HINT getoond ("ander model hoorde: …"), nooit automatisch ingevoegd.

Beperkingen (zie ook docs): de VAD reageert ook op lachen, hoesten, muziek of een deur; zeer zachte spraak kan de VAD
juist missen; en als álle modellen een passage overslaan en de VAD ook, vindt deze controle niets. Echte stilte (geen
VAD-spraak) wordt niet gemeld. Afwijzen ('Dit is geen ontbrekende tekst') zet dismissed=True en blijft bewaard.
"""
from __future__ import annotations

import re

MIN_GAP_S = 0.8


def stretched(w: dict) -> bool:
    """Een woord dat veel langer duurt dan zijn lengte rechtvaardigt (bijv. 'dingen' van 2,0 s) wijst erop dat Whisper
    de woordtijden heeft uitgesmeerd over spraak die het niet herkend heeft. Zulke woorden 'dekken' het interval niet."""
    dur = (w.get("end") or 0) - (w.get("start") or 0)
    n = len(re.sub(r"[^\w]", "", str(w.get("word", ""))))
    return dur > max(0.8, 0.1 * n)


def speech_regions(wav_path, min_silence_ms: int = 500) -> list[dict]:
    import soundfile as sf
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    wav, sr = sf.read(str(wav_path), dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    ts = get_speech_timestamps(wav, VadOptions(min_silence_duration_ms=min_silence_ms, speech_pad_ms=50))
    return [{"start": round(t["start"] / sr, 2), "end": round(t["end"] / sr, 2)} for t in ts]


def _uncovered(a: float, b: float, words: list[dict], pad: float = 0.25) -> list[tuple[float, float]]:
    """Deelintervallen van [a,b] zonder woorden (met wat marge rond elk woord)."""
    out, cur = [], a
    for w in sorted(words, key=lambda w: w["start"]):
        if stretched(w):
            continue
        ws, we = w["start"] - pad, w["end"] + pad
        if we <= cur or ws >= b:
            continue
        if ws > cur:
            out.append((cur, ws))
        cur = max(cur, we)
    if cur < b:
        out.append((cur, b))
    return [(x, y) for x, y in out if y - x >= MIN_GAP_S]


def detect(vad: list[dict] | None, runs: dict, transcript_words: list[dict], base_model: str | None = None) -> list[dict]:
    gaps: list[dict] = []
    words = [w for w in transcript_words if w.get("start") is not None]
    if vad:
        for r in vad:
            for a, b in _uncovered(r["start"], r["end"], words):
                gaps.append({"start": round(a, 2), "end": round(b, 2), "kind": "vad", "hint": "", "models": [], "dismissed": False})
    for mid, run in (runs or {}).items():
        if mid == base_model:
            continue
        other = run.get("words", [])
        # vind intervallen waar dit model >= 2 woorden heeft maar het transcript geen woorden
        for a, b in _merge_spans([(w["start"], w["end"]) for w in other], gap=0.6):
            for x, y in _uncovered(a, b, words):
                inside = [w for w in other if w["start"] >= x - 0.1 and w["end"] <= y + 0.1]
                if len(inside) >= 2:
                    gaps.append({"start": round(x, 2), "end": round(y, 2), "kind": "coverage", "hint": " ".join(w["word"] for w in inside), "models": [mid], "dismissed": False})
    return _merge_gaps(gaps)


def _merge_spans(spans: list[tuple[float, float]], gap: float) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for s, e in sorted(spans):
        if out and s - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(a, b) for a, b in out]


def _merge_gaps(gaps: list[dict]) -> list[dict]:
    gaps.sort(key=lambda g: g["start"])
    out: list[dict] = []
    for g in gaps:
        if out and g["start"] <= out[-1]["end"] + 0.3:
            m = out[-1]
            m["end"] = max(m["end"], g["end"])
            m["kind"] = "both" if m["kind"] != g["kind"] else m["kind"]
            if g["hint"] and not m["hint"]:
                m["hint"] = g["hint"]
            m["models"] = sorted(set(m["models"]) | set(g["models"]))
        else:
            out.append(dict(g))
    return out


def carry_dismissed(old: list[dict] | None, new: list[dict]) -> list[dict]:
    """Afgewezen intervallen blijven afgewezen als ze (grotendeels) overlappen met een nieuw gevonden interval."""
    for g in new:
        for o in old or []:
            if o.get("dismissed") and min(g["end"], o["end"]) - max(g["start"], o["start"]) > 0.5 * (g["end"] - g["start"]):
                g["dismissed"] = True
    return new
