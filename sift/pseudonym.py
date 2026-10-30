"""Namen en herkenbare gegevens vervangen (pseudonimiseren) bij export.

Eén tabel: te vervangen tekst → vervanging. Alle vervangingen worden in ÉÉN regex-doorgang toegepast, zodat een
vervanging nooit een volgende vervanging kan activeren (geen kettingreacties). Langere zoektermen gaan vóór kortere.
Er wordt op woordgrenzen gezocht en hoofdletterongevoelig; de vervanging wordt precies zo ingevuld als ingevoerd
(alleen een match in HOOFDLETTERS wordt in hoofdletters vervangen; plaatshouders zoals [persoon1] blijven altijd gelijk).

Dit is pseudonimisering, geen gegarandeerde anonimisering: plaatsen, organisaties, functies en beschrijvingen in de tekst
kunnen iemand nog steeds herkenbaar maken, en de oorspronkelijke opname verandert niet.
"""
from __future__ import annotations

import re
from typing import Iterable


def normalize_mapping(mapping) -> list[tuple[str, str]]:
    """Accepteert {naam: vervanging} of [{find, replace}] of [[find, replace]]; geeft gesorteerde lijst (langste eerst)."""
    pairs: list[tuple[str, str]] = []
    if not mapping:
        return pairs
    items: Iterable
    if isinstance(mapping, dict):
        items = mapping.items()
    else:
        items = []
        for row in mapping:
            if isinstance(row, dict):
                items.append((row.get("find", ""), row.get("replace", "")))
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                items.append((row[0], row[1]))
    seen = set()
    for find, repl in items:
        find = (find or "").strip()
        if not find or find.lower() in seen:
            continue
        seen.add(find.lower())
        pairs.append((find, (repl or "").strip()))
    pairs.sort(key=lambda kv: -len(kv[0]))
    return pairs


class Pseudonymizer:
    def __init__(self, mapping):
        self.pairs = normalize_mapping(mapping)
        self.lookup = {f.lower(): r for f, r in self.pairs}
        self.hits: dict[str, int] = {f: 0 for f, _ in self.pairs}
        if self.pairs:
            alts = "|".join(re.escape(f) for f, _ in self.pairs)
            # (?<!\w) / (?!\w) in plaats van \b zodat ook namen met punt/apostrof aan de rand goed gaan
            self.re = re.compile(r"(?<!\w)(?:" + alts + r")(?!\w)", re.IGNORECASE | re.UNICODE)
        else:
            self.re = None

    def __bool__(self) -> bool:
        return bool(self.pairs)

    def _sub(self, m: re.Match) -> str:
        found = m.group(0)
        repl = self.lookup[found.lower()]
        for f in self.hits:
            if f.lower() == found.lower():
                self.hits[f] += 1
                break
        if repl.startswith(("[", "(", "<", "{")):
            return repl
        if found.isupper() and len(found) > 1:
            return repl.upper()
        return repl  # verder precies zoals ingevoerd: voorspelbaar voor namen én omschrijvingen

    def text(self, s: str | None) -> str:
        if not s or not self.re:
            return s or ""
        return self.re.sub(self._sub, s)

    def transcript(self, t: dict) -> dict:
        """Geeft een gepseudonimiseerde KOPIE: tekst, woorden, alternatieven, basiswoord, opmerkingen, sprekernamen."""
        import copy
        d = copy.deepcopy(t)
        if not self.re:
            return d
        for sid, sp in (d.get("speakers") or {}).items():
            sp["name"] = self.text(sp.get("name", ""))
        for s in d.get("segments", []):
            s["text"] = self.text(s.get("text", ""))
            if s.get("note"):
                s["note"] = self.text(s["note"])
            for w in s.get("words", []) or []:
                w["word"] = self.text(w.get("word", ""))
                if w.get("base"):
                    w["base"] = self.text(w["base"])
                if w.get("alts"):
                    w["alts"] = {m: self.text(a) for m, a in w["alts"].items()}
        for g in d.get("gaps", []) or []:
            if g.get("hint"):
                g["hint"] = self.text(g["hint"])
        d["pseudonymized"] = True
        return d
