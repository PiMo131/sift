"""Maakt een nakijklijst van een Sift-transcript: per segment de tekst, met onzekere woorden en modelvarianten gemarkeerd.

Gebruik: python review_extract.py <project_id> <uit.txt> [drempel]
Markering: ⟨woord|alt⟩ = onzeker (p < drempel) en/of modellen oneens; alt = variant(en) van de andere modellen.
"""
import json, sys, pathlib, urllib.request

pid, out = sys.argv[1], sys.argv[2]
thr = float(sys.argv[3]) if len(sys.argv) > 3 else 0.6
t = json.loads(urllib.request.urlopen(f"http://127.0.0.1:8765/api/projects/{pid}/transcript").read().decode("utf-8"))
sp = {k: v["name"] for k, v in t["speakers"].items()}
lines, n_unc = [], 0
for i, s in enumerate(t["segments"]):
    parts = []
    for w in s.get("words", []):
        alts = [a for a in (w.get("alts") or {}).values() if a and a.strip().lower() != w["word"].strip().lower()]
        unc = (w.get("p") is not None and w["p"] < thr)
        if unc or alts:
            n_unc += 1
            parts.append("⟨" + w["word"] + ("|" + "/".join(alts) if alts else "") + ("" if unc else "=") + "⟩")
        else:
            parts.append(w["word"])
    m, sec = divmod(int(s["start"]), 60)
    lines.append(f"#{i} [{m:02d}:{sec:02d}] {sp.get(s['speaker'], s['speaker'])}: {' '.join(parts)}")
pathlib.Path(out).write_text("\n".join(lines), encoding="utf-8")
print(f"{len(t['segments'])} segmenten, {n_unc} gemarkeerde woorden -> {out}")
