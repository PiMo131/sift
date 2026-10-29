"""Vergelijk benchmark-uitvoer: statistieken, onderlinge overeenstemming (WER tussen modellen) en zekerheidsverdeling.
Gebruik: python compare.py <label> [<label> ...]   (zonder argumenten: alle *.json in deze map)
"""
import json, re, sys, pathlib
from difflib import SequenceMatcher

here = pathlib.Path(__file__).parent
labels = sys.argv[1:] or sorted(p.stem for p in here.glob("*.json"))
runs = {}
for lb in labels:
    d = json.loads((here / f"{lb}.json").read_text(encoding="utf-8"))
    if "segments" in d:
        text = " ".join(s["text"] for s in d["segments"])
    else:
        text = d["text"]
    runs[lb] = {"stats": d["stats"], "text": text, "words": d.get("words", [])}

def norm(t):
    return re.findall(r"[\w']+", t.lower())

def wer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    sm = SequenceMatcher(a=r, b=h, autojunk=False)
    errs = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        errs += max(i2 - i1, j2 - j1)
    return errs / max(len(r), 1)

print(f"{'run':14} {'run_s':>6} {'xRT':>5} {'words':>6} {'mean_p':>7} {'<0.6':>5} {'<0.4':>5}")
for lb, r in runs.items():
    s = r["stats"]
    print(f"{lb:14} {s['run_s']:>6} {s['realtime_factor']:>5} {s['n_words']:>6} {str(s['mean_p']):>7} {str(s['words_below_0.6']):>5} {str(s['words_below_0.4']):>5}")

print("\nOnderlinge afwijking (woordfoutpercentage van rij t.o.v. kolom, lager = meer eens):")
names = list(runs)
print(" " * 14 + "".join(f"{n[:12]:>13}" for n in names))
for a in names:
    row = "".join(f"{wer(runs[b]['text'], runs[a]['text'])*100:>12.1f}%" for b in names)
    print(f"{a:14}{row}")

print("\nZekerheidsverdeling per run (aandeel woorden per bucket):")
for lb, r in runs.items():
    ps = [w["p"] for w in r["words"] if w.get("p") is not None]
    if not ps:
        continue
    b = [sum(p < 0.4 for p in ps), sum(0.4 <= p < 0.6 for p in ps), sum(0.6 <= p < 0.8 for p in ps), sum(p >= 0.8 for p in ps)]
    n = len(ps)
    print(f"{lb:14} <0.4 {b[0]/n:5.1%}  0.4-0.6 {b[1]/n:5.1%}  0.6-0.8 {b[2]/n:5.1%}  >=0.8 {b[3]/n:5.1%}")
