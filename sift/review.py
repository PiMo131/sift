"""Controlevoortgang en aandachtspunten, los van modelzekerheid.

Drie eigenschappen per woord blijven gescheiden:
  p        de ruwe score van het model (wordt nooit aangepast door de gebruiker)
  edited   door een mens gewijzigd
  checked  door een mens bevestigd ('Klopt zo' of na aanpassing)

Een aandachtspunt is open zolang er geen menselijke beslissing over is genomen. Als het woord daarna verandert
(commitSegment in de editor zet `checked` dan terug), gaat het aandachtspunt opnieuw open.
"""
from __future__ import annotations


def attention_points(t: dict, threshold: float = 0.6) -> list[dict]:
    """Alle aandachtspunten (open én afgehandeld), in volgorde van tijd."""
    pts = []
    for si, s in enumerate(t.get("segments", [])):
        for wi, w in enumerate(s.get("words", []) or []):
            kinds = []
            if w.get("p") is not None and w["p"] < threshold and not w.get("edited"):
                kinds.append("uncertain")
            if w.get("disagree"):
                kinds.append("disagree")
            if w.get("later"):
                kinds.append("later")
            if kinds:
                pts.append({"id": f"w:{si}:{wi}", "kind": kinds, "start": w["start"], "end": w["end"], "si": si, "wi": wi,
                            "done": bool(w.get("checked")) and not w.get("later"), "text": w.get("word", "")})
        if s.get("later"):
            pts.append({"id": f"s:{si}", "kind": ["later"], "start": s["start"], "end": s["end"], "si": si, "wi": None, "done": False, "text": s.get("text", "")[:60]})
    for gi, g in enumerate(t.get("gaps", []) or []):
        pts.append({"id": f"g:{gi}", "kind": ["gap"], "start": g["start"], "end": g["end"], "si": None, "wi": None, "done": bool(g.get("dismissed")), "text": g.get("hint", "")})
    pts.sort(key=lambda p: (p["start"], p["si"] if p["si"] is not None else -1))
    return pts


def summary(t: dict | None, threshold: float = 0.6) -> dict:
    if not t:
        return {"segments": 0, "reviewed": 0, "attention_total": 0, "attention_open": 0, "quotes": 0, "later": 0, "gaps_open": 0, "progress": 0.0}
    segs = t.get("segments", [])
    pts = attention_points(t, threshold)
    open_pts = [p for p in pts if not p["done"]]
    reviewed = sum(1 for s in segs if s.get("reviewed"))
    n = len(segs) or 1
    return {"segments": len(segs), "reviewed": reviewed, "attention_total": len(pts), "attention_open": len(open_pts),
            "quotes": sum(1 for s in segs if s.get("quote")), "later": sum(1 for s in segs if s.get("later")),
            "gaps_open": sum(1 for p in open_pts if "gap" in p["kind"]), "progress": round(reviewed / n, 3)}


def next_action(meta: dict, t: dict | None, threshold: float = 0.6) -> str:
    """De volgende nuttige stap voor dit interview, in gewone taal."""
    st = meta.get("status")
    if st in (None, "nieuw"):
        return "Opname verwerken"
    if st == "bezig":
        return "Wachten op verwerking"
    if st in ("fout", "onderbroken"):
        return "Verwerking hervatten"
    if meta.get("review_status") == "checked":
        return "Exporteren"
    s = summary(t, threshold)
    if s["attention_open"]:
        return f"{s['attention_open']} aandachtspunten nakijken"
    if s["reviewed"] < s["segments"]:
        return "Nakijken afronden"
    return "Als gecontroleerd markeren"


def display_status(meta: dict, t: dict | None) -> str:
    st = meta.get("status")
    if st in (None, "nieuw"):
        return "Nog te verwerken"
    if st == "bezig":
        return "Bezig met verwerken"
    if st == "onderbroken":
        return "Verwerking onderbroken"
    if st == "fout":
        return "Verwerking mislukt"
    if meta.get("review_status") == "checked":
        return "Gecontroleerd"
    if meta.get("review_status") == "in_progress" or (t and (t.get("edited") or any(s.get("reviewed") for s in t.get("segments", [])))):
        return "Nakijken bezig"
    return "Transcript beschikbaar"
