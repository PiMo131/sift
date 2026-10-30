"""Meerdere modeluitkomsten over elkaar leggen.

Het basismodel (eerste in de lijst, normaal large-v3) levert de ruggengraat: segmenten en woorden.
Voor elk basiswoord zoeken we in de andere runs het woord met de grootste tijdsoverlap en vergelijken de tekst.
Resultaat per woord: p (zekerheid basismodel), alts {model: woord}, agree (aantal modellen dat het eens is),
en bij strategie 'consensus' of 'highest_p' eventueel een vervangen tekst (origineel bewaard in 'base').
"""
from __future__ import annotations

import re
from collections import Counter


def _norm(w: str) -> str:
    return re.sub(r"[^\w']", "", w.lower())


def _overlap(a, b) -> float:
    return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


def _index(words):
    """Sorteer en geef een zoeker op tijd. Whisper-woordtijden verschuiven tussen modellen vaak een woord; daarom wordt
    eerst binnen een klein venster (±1 s rond het basiswoord) naar hetzelfde woord gezocht en pas daarna naar het woord
    met de grootste tijdsoverlap. Elk woord van het andere model wordt maar één keer gebruikt."""
    ws = sorted(words, key=lambda w: w["start"])
    starts = [w["start"] for w in ws]
    used: set[int] = set()
    import bisect

    def find(t0, t1, norm_word):
        i0 = bisect.bisect_left(starts, t0 - 1.5)
        best, best_ov, best_i = None, 0.0, None
        same = None
        i = i0
        while i < len(ws) and ws[i]["start"] < t1 + 1.5:
            if i not in used:
                ov = _overlap({"start": t0, "end": t1}, ws[i])
                if ov > best_ov:
                    best, best_ov, best_i = ws[i], ov, i
                if same is None and norm_word and _norm(ws[i]["word"]) == norm_word and ws[i]["end"] > t0 - 1.0 and ws[i]["start"] < t1 + 1.0:
                    same = i
            i += 1
        if same is not None:
            used.add(same)
            return ws[same]
        if best is not None and best_ov > 0:
            used.add(best_i)
            return best
        return None
    return find


def _glue_apostrophes(words: list[dict]) -> list[dict]:
    """Whisper splitst "zo'n" soms in "zo" + "'n". Plak een token dat met een apostrof begint aan het vorige woord."""
    out = []
    for w in words:
        if out and w["word"].startswith(("'", "’")) and len(w["word"]) <= 4:
            prev = out[-1]
            prev["word"] = prev["word"] + w["word"]
            prev["end"] = max(prev["end"], w["end"])
            if prev.get("p") is not None and w.get("p") is not None:
                prev["p"] = min(prev["p"], w["p"])
        else:
            out.append(dict(w))
    return out


def combine(runs: dict[str, dict], order: list[str], strategy: str = "consensus") -> dict:
    """runs: {model_id: engine-json}. order: modellen in volgorde van voorkeur (eerste = basis)."""
    order = [m for m in order if m in runs]
    if not order:
        raise ValueError("geen runs")
    runs = {m: {**r, "words": _glue_apostrophes(r["words"])} for m, r in runs.items()}
    base_id = order[0]
    base = runs[base_id]
    finders = {m: _index(runs[m]["words"]) for m in order[1:]}

    out_words = []
    for w in base["words"]:
        entry = {"start": w["start"], "end": w["end"], "word": w["word"], "p": w["p"], "base": w["word"], "alts": {}, "agree": 1, "n_models": len(order), "missing_in": []}
        votes = Counter({_norm(w["word"]): 1})
        best_p, best_word = w["p"], w["word"]
        for m in order[1:]:
            o = finders[m](w["start"], w["end"], _norm(w["word"]))
            if o is None:
                # het andere model heeft hier helemaal geen woord: dat is géén 'ander woord' maar een hiaat bij dat model
                entry["missing_in"].append(m)
                continue
            if _norm(o["word"]) == _norm(w["word"]):
                entry["agree"] += 1
            else:
                entry["alts"][m] = o["word"]
            votes[_norm(o["word"])] += 1
            if o.get("p") is not None and (best_p is None or o["p"] > best_p):
                best_p, best_word = o["p"], o["word"]
        if strategy == "consensus" and len(order) >= 3:
            top, n = votes.most_common(1)[0]
            if n > votes[_norm(w["word"])]:
                for m, alt in entry["alts"].items():
                    if _norm(alt) == top:
                        entry["word"] = alt
                        entry["p"] = runs[m]["stats"].get("mean_p") if runs[m]["stats"].get("mean_p") is not None else w["p"]
                        break
                entry["alts"][base_id] = w["word"]
        elif strategy == "highest_p" and best_word != w["word"]:
            entry["word"], entry["p"] = best_word, best_p
            entry["alts"][base_id] = w["word"]
        entry["disagree"] = any(a for a in entry["alts"].values())  # alleen als een model écht een ander woord geeft
        out_words.append(entry)

    # woorden aan basissegmenten koppelen
    segments = []
    wi = 0
    for si, s in enumerate(base["segments"]):
        seg_words = []
        while wi < len(out_words) and out_words[wi]["start"] < s["end"] - 1e-3:
            if out_words[wi]["end"] > s["start"] - 1e-3:
                seg_words.append(out_words[wi])
            wi += 1
        text = " ".join(w["word"] for w in seg_words) if seg_words else s["text"]
        # modellen die meer dan de helft van dit segment niet herkend hebben (informatief; geen aandachtspunt per woord)
        other_missing = [m for m in order[1:] if seg_words and sum(m in w.get("missing_in", []) for w in seg_words) * 2 > len(seg_words)]
        segments.append({"id": si, "start": s["start"], "end": s["end"], "text": text, "words": seg_words,
                         "speaker": None, "reviewed": False, "quote": False, "later": False, "note": "", "other_missing": other_missing})
    return {"base_model": base_id, "models": order, "strategy": strategy, "segments": segments}


def runs_summary(runs: dict[str, dict], threshold: float = 0.6) -> dict:
    out = {}
    for m, r in runs.items():
        ps = [w["p"] for w in r["words"] if w.get("p") is not None]
        out[m] = {**r["stats"], "uncertain": sum(p < threshold for p in ps) if ps else None}
    return out
