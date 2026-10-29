"""Exports: CSV (woorden en segmenten), TXT, SRT, DOCX, MAXQDA/NVivo-tekst, JSON.

Opties: style = verbatim | clean (fillers weg), timestamps = none | paragraph | minute, speakers = bool,
anonymize = {naam: plaatshouder}, highlights_only = bool, ts_format = brackets | dp  ([00:01:23] of #00:01:23-4#)
"""
from __future__ import annotations

import csv
import io
import json
import re

FILLERS = re.compile(r"\b(eh|ehm|uh|uhm|hm|hmm|mm|mhm)\b[,.]?\s*", re.I)


def _ts(sec: float, fmt: str = "brackets") -> str:
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    if fmt == "dp":
        tenth = int((sec - int(sec)) * 10)
        return f"#{h:02d}:{m:02d}:{s:02d}-{tenth}#"
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def _srt_ts(sec: float) -> str:
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _clean(text: str, style: str) -> str:
    if style == "clean":
        text = FILLERS.sub("", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _anon(text: str, mapping: dict | None) -> str:
    if not mapping:
        return text
    for name, placeholder in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        if name:
            text = re.sub(r"(?<!\w)" + re.escape(name) + r"(?!\w)", placeholder, text, flags=re.I)
    return text


def paragraphs(transcript: dict, opts: dict) -> list[dict]:
    """Voegt opeenvolgende segmenten van dezelfde spreker samen tot alinea's."""
    speakers = transcript.get("speakers", {})
    out = []
    for s in transcript["segments"]:
        if opts.get("highlights_only") and not s.get("highlight"):
            continue
        text = _anon(_clean(s["text"], opts.get("style", "verbatim")), opts.get("anonymize"))
        if not text.strip():
            continue
        name = speakers.get(s.get("speaker") or "", {}).get("name", s.get("speaker") or "")
        max_len = opts.get("max_paragraph_s", 40)
        if (out and out[-1]["speaker"] == name and (s["start"] - out[-1]["end"]) < 2.0 and not opts.get("highlights_only")
                and (s["end"] - out[-1]["start"]) <= max_len):
            out[-1]["text"] += " " + text
            out[-1]["end"] = s["end"]
        else:
            out.append({"speaker": name, "start": s["start"], "end": s["end"], "text": text})
    return out


def to_txt(transcript: dict, opts: dict) -> str:
    lines = []
    last_minute = -1
    for para in paragraphs(transcript, opts):
        prefix = ""
        if opts.get("timestamps", "paragraph") == "paragraph":
            prefix = _ts(para["start"], opts.get("ts_format", "brackets")) + " "
        elif opts.get("timestamps") == "minute" and int(para["start"] // 60) > last_minute:
            last_minute = int(para["start"] // 60)
            prefix = _ts(para["start"], opts.get("ts_format", "brackets")) + " "
        spk = f"{para['speaker']}: " if opts.get("speakers", True) and para["speaker"] else ""
        lines.append(f"{prefix}{spk}{para['text']}")
        lines.append("")
    return "\n".join(lines)


def to_maxqda(transcript: dict, opts: dict) -> str:
    """aTrain-stijl: [HH:MM:SS] aan het begin van elke alinea, sprekernaam op eigen regel bij wissel."""
    lines, last = [], None
    for para in paragraphs(transcript, {**opts, "timestamps": "paragraph"}):
        if para["speaker"] != last:
            lines.append(para["speaker"])
            last = para["speaker"]
        ts = _ts(para["start"], "brackets")
        if opts.get("nvivo_mac"):
            ts = ts.strip("[]")
        lines.append(f"{ts} {para['text']}")
        lines.append("")
    return "\n".join(lines)


def to_srt(transcript: dict, opts: dict) -> str:
    out = []
    n = 1
    speakers = transcript.get("speakers", {})
    for s in transcript["segments"]:
        text = _anon(_clean(s["text"], opts.get("style", "verbatim")), opts.get("anonymize"))
        if not text.strip():
            continue
        name = speakers.get(s.get("speaker") or "", {}).get("name", "")
        if opts.get("speakers", True) and name:
            text = f"{name}: {text}"
        out += [str(n), f"{_srt_ts(s['start'])} --> {_srt_ts(s['end'])}", text, ""]
        n += 1
    return "\n".join(out)


def to_csv_segments(transcript: dict, opts: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(["start", "eind", "spreker", "tekst", "gem_zekerheid", "onzekere_woorden", "nagekeken", "highlight", "opmerking"])
    speakers = transcript.get("speakers", {})
    thr = opts.get("threshold", 0.6)
    for s in transcript["segments"]:
        ps = [x["p"] for x in s.get("words", []) if x.get("p") is not None]
        w.writerow([f"{s['start']:.2f}", f"{s['end']:.2f}", speakers.get(s.get("speaker") or "", {}).get("name", ""),
                    _anon(_clean(s["text"], opts.get("style", "verbatim")), opts.get("anonymize")),
                    f"{sum(ps)/len(ps):.3f}" if ps else "", sum(p < thr for p in ps), int(bool(s.get("reviewed"))), int(bool(s.get("highlight"))), s.get("note", "")])
    return buf.getvalue()


def to_csv_words(transcript: dict, opts: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(["start", "eind", "spreker", "woord", "zekerheid", "modellen_eens", "alternatieven", "bewerkt"])
    speakers = transcript.get("speakers", {})
    for s in transcript["segments"]:
        name = speakers.get(s.get("speaker") or "", {}).get("name", "")
        for x in s.get("words", []):
            alts = "; ".join(f"{m}={a}" for m, a in (x.get("alts") or {}).items() if a)
            w.writerow([f"{x['start']:.2f}", f"{x['end']:.2f}", name, x["word"], "" if x.get("p") is None else f"{x['p']:.3f}",
                        x.get("agree", ""), alts, int(bool(x.get("edited")))])
    return buf.getvalue()


def to_docx(transcript: dict, opts: dict, meta: dict | None = None) -> bytes:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    title = (meta or {}).get("name") or "Transcript"
    doc.add_heading(title, level=1)
    if meta:
        info = [f"Duur: {int((meta.get('audio', {}).get('duration') or 0) // 60)} min",
                f"Modellen: {', '.join(meta.get('runs', {}).keys())}", f"Stijl: {opts.get('style', 'verbatim')}"]
        doc.add_paragraph(" · ".join(info)).runs[0].font.size = Pt(9)
    for para in paragraphs(transcript, opts):
        p = doc.add_paragraph()
        if opts.get("speakers", True) and para["speaker"]:
            r = p.add_run(para["speaker"] + ": ")
            r.bold = True
        p.add_run(para["text"])
        if opts.get("timestamps", "paragraph") != "none":
            r = p.add_run(" " + _ts(para["end"] if opts.get("ts_format") == "dp" else para["start"], opts.get("ts_format", "brackets")))
            r.font.size = Pt(8)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def to_json(transcript: dict, opts: dict) -> str:
    return json.dumps(transcript, ensure_ascii=False, indent=1)


FORMATS = {
    "txt": ("text/plain; charset=utf-8", "txt", to_txt),
    "maxqda": ("text/plain; charset=utf-8", "maxqda.txt", to_maxqda),
    "srt": ("text/plain; charset=utf-8", "srt", to_srt),
    "csv": ("text/csv; charset=utf-8", "segmenten.csv", to_csv_segments),
    "csv_words": ("text/csv; charset=utf-8", "woorden.csv", to_csv_words),
    "json": ("application/json", "json", to_json),
}
