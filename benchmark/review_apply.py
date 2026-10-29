"""Past nakijkcorrecties toe op een Sift-transcript via de API en markeert segmenten als nagekeken.

Gebruik: python review_apply.py <project_id> <edits.json>
edits.json: {"global": [[regex, vervanging], ...], "text": {"<segment-index>": "nieuwe tekst"}, "speaker": {"<idx>": "S1"}, "note": {"<idx>": "..."}}
Woorden worden opnieuw uitgelijnd met een LCS-diff op genormaliseerde tokens (zelfde logica als de editor).
"""
import json, re, sys, urllib.request
from difflib import SequenceMatcher

pid, edits_path = sys.argv[1], sys.argv[2]
base = f"http://127.0.0.1:8765/api/projects/{pid}"
edits = json.loads(open(edits_path, encoding="utf-8").read())

def req(url, method="GET", data=None):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    r = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": "application/json; charset=utf-8"})
    return json.loads(urllib.request.urlopen(r).read().decode("utf-8"))

req(base + "/snapshot", "POST", {"label": "voor_nakijken"})
t = req(base + "/transcript")
norm = lambda w: re.sub(r"[^\w']", "", w.lower())

def realign(seg, new_text):
    tokens = new_text.split()
    old = seg.get("words") or []
    a = [norm(w["word"]) for w in old]; b = [norm(x) for x in tokens]
    sm = SequenceMatcher(a=a, b=b, autojunk=False)
    out, last_end = [], seg["start"]
    def interp(toks, next_start):
        span = max(0.05, next_start - last_end) / max(len(toks), 1)
        return [{"start": last_end + k * span, "end": last_end + (k + 1) * span, "word": tk, "p": None, "edited": True, "alts": {}, "agree": 1, "n_models": 1} for k, tk in enumerate(toks)]
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                w = dict(old[i]);
                if w["word"] != tokens[j]: w["word"] = tokens[j]; w["edited"] = True
                out.append(w); last_end = w["end"]
        elif tag == "replace":
            nxt = old[i2]["start"] if i2 < len(old) else seg["end"]
            ws = interp(tokens[j1:j2], nxt)
            # tijd van de oude woorden overnemen als aantallen gelijk zijn
            if i2 - i1 == j2 - j1:
                for k, i in enumerate(range(i1, i2)):
                    ws[k]["start"], ws[k]["end"] = old[i]["start"], old[i]["end"]
                    ws[k]["p"] = old[i].get("p")
            out += ws; last_end = out[-1]["end"] if out else last_end
        elif tag == "insert":
            nxt = old[i1]["start"] if i1 < len(old) else seg["end"]
            out += interp(tokens[j1:j2], nxt); last_end = out[-1]["end"]
        # delete: niets
    seg["words"] = out; seg["text"] = " ".join(tokens)

n_text = n_global = 0
for i, seg in enumerate(t["segments"]):
    txt = seg["text"]
    for pat, rep in edits.get("global", []):
        new = re.sub(pat, rep, txt)
        if new != txt: n_global += 1; txt = new
    if str(i) in edits.get("text", {}):
        txt = edits["text"][str(i)]; n_text += 1
    if txt != seg["text"]:
        realign(seg, txt)
    if str(i) in edits.get("speaker", {}):
        seg["speaker"] = edits["speaker"][str(i)]
    if str(i) in edits.get("note", {}):
        seg["note"] = edits["note"][str(i)]
    seg["reviewed"] = True
t["speakers"] = edits.get("speakers", t["speakers"])
r = req(base + "/transcript", "PUT", t)
print(f"tekstcorrecties: {n_text}, globale vervangingen: {n_global}, sprekers: {len(edits.get('speaker', {}))}, opgeslagen versie {r['version']}")
