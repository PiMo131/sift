"""Transcriptieafspraken per onderzoek, met per keuze een concreet voor/na-voorbeeld.

Belangrijk onderscheid:
  automatic = True   Sift past dit zelf toe bij EXPORT (op een kopie; het transcript zelf verandert niet).
  automatic = False  Sift biedt alleen een knop of notatie; de onderzoeker beslist en controleert zelf per passage.

Een spraakmodel herkent niet alle aarzelingen, herhalingen of afgebroken zinnen. 'Verbatim' betekent hier: zoals herkend en
door jou gecorrigeerd, niet 'gegarandeerd woordelijk'. Een tijdcodeformaat voor Dresing & Pehl is géén volledige ondersteuning
van dat protocol. Sift herschrijft of interpreteert uitspraken nooit automatisch.
"""
from __future__ import annotations

CONVENTIONS = {
    "fillers": {
        "label": "Stopwoorden en aarzelingen (eh, uhm)",
        "automatic": "Alleen bij export in de stijl 'clean verbatim' worden de hier gekozen stopwoorden weggelaten. In de editor blijft alles staan.",
        "options": {
            "keep": {"label": "Behouden (verbatim)", "before": "Eh, ik… ik vond dat eigenlijk best moeilijk.", "after": "Eh, ik… ik vond dat eigenlijk best moeilijk."},
            "remove": {"label": "Geselecteerde stopwoorden weglaten bij export", "before": "Eh, ik… ik vond dat eigenlijk best moeilijk.", "after": "Ik… ik vond dat eigenlijk best moeilijk."},
        },
        "default": "keep",
        "extra": {"key": "filler_words", "label": "Welke stopwoorden", "default": "eh, ehm, uh, uhm, hm, hmm, mm, mhm"},
        "caveat": "Het model herkent niet elke aarzeling; wat niet in de tekst staat, kan ook niet worden weggelaten.",
    },
    "repetitions": {
        "label": "Herhalingen en valse starts",
        "automatic": "Niets automatisch. Je laat ze staan of verwijdert ze zelf tijdens het nakijken.",
        "options": {
            "keep": {"label": "Letterlijk laten staan", "before": "Ik ik ging toen naar, naar de huisarts.", "after": "Ik ik ging toen naar, naar de huisarts."},
            "manual_remove": {"label": "Zelf verwijderen bij nakijken", "before": "Ik ik ging toen naar, naar de huisarts.", "after": "Ik ging toen naar de huisarts."},
        },
        "default": "keep",
    },
    "broken": {
        "label": "Afgebroken zinnen",
        "automatic": "Niets automatisch. De knop 'Afgebroken' voegt het gekozen teken in.",
        "options": {
            "dash": {"label": "Afbreekstreepje", "before": "Toen wilde ik eigenlijk", "after": "Toen wilde ik eigenlijk –"},
            "ellipsis": {"label": "Beletselteken", "before": "Toen wilde ik eigenlijk", "after": "Toen wilde ik eigenlijk…"},
            "slash": {"label": "Schuine streep (Dresing & Pehl)", "before": "Toen wilde ik eigenlijk", "after": "Toen wilde ik eigenlijk/"},
        },
        "default": "ellipsis",
    },
    "pauses": {
        "label": "Pauzes",
        "automatic": "Niets automatisch. De knop '(pauze)' voegt de gekozen notatie in; de duur vul je zelf in of meet je in de golfvorm.",
        "options": {
            "dots": {"label": "(.) kort, (...) lang", "before": "Ja. Dat was wel", "after": "Ja. (...) Dat was wel"},
            "seconds": {"label": "(3) seconden tussen haken", "before": "Ja. Dat was wel", "after": "Ja. (3) Dat was wel"},
            "word": {"label": "(pauze)", "before": "Ja. Dat was wel", "after": "Ja. (pauze) Dat was wel"},
        },
        "default": "dots",
    },
    "laughter": {
        "label": "Lachen en non-verbaal",
        "automatic": "Niets automatisch. De knop 'Lachen' voegt de gekozen notatie in.",
        "options": {
            "parens": {"label": "(lacht)", "before": "Dat was me wat.", "after": "Dat was me wat. (lacht)"},
            "brackets": {"label": "[lacht]", "before": "Dat was me wat.", "after": "Dat was me wat. [lacht]"},
        },
        "default": "parens",
    },
    "unintelligible": {
        "label": "Onverstaanbare passages",
        "automatic": "Niets automatisch. De knop '[onverstaanbaar]' voegt de notatie met tijdcode in.",
        "options": {
            "timecode": {"label": "[onverstaanbaar hh:mm:ss]", "before": "en toen zei hij", "after": "en toen zei hij [onverstaanbaar 00:12:41]"},
            "unv": {"label": "(unv.) (Dresing & Pehl)", "before": "en toen zei hij", "after": "en toen zei hij (unv.)"},
            "guess": {"label": "(vermoedelijk woord?)", "before": "en toen zei hij", "after": "en toen zei hij (morfine?)"},
        },
        "default": "timecode",
    },
    "overlap": {
        "label": "Overlap tussen sprekers",
        "automatic": "Niets automatisch. De knop 'Overlap' voegt het teken in; splits zo nodig het segment.",
        "options": {
            "slashes": {"label": "// aan begin en einde", "before": "R: Ja precies. I: En toen?", "after": "R: Ja //precies//. I: //En toen?//"},
            "brackets": {"label": "[overlap]", "before": "R: Ja precies. I: En toen?", "after": "R: Ja precies. [overlap] I: En toen?"},
        },
        "default": "slashes",
    },
}

DEFAULT_CONVENTIONS = {k: v["default"] for k, v in CONVENTIONS.items()}
DEFAULT_CONVENTIONS["filler_words"] = CONVENTIONS["fillers"]["extra"]["default"]


def describe(chosen: dict | None) -> str:
    """Leesbare samenvatting (voor export en voor afstemming met een begeleider)."""
    chosen = {**DEFAULT_CONVENTIONS, **(chosen or {})}
    lines = ["Transcriptieafspraken", ""]
    for key, c in CONVENTIONS.items():
        o = c["options"].get(chosen.get(key), c["options"][c["default"]])
        lines.append(f"- {c['label']}: {o['label']}.")
        lines.append(f"  Voorbeeld: '{o['before']}' → '{o['after']}'")
        if key == "fillers" and chosen.get("fillers") == "remove":
            lines.append(f"  Stopwoorden: {chosen.get('filler_words', '')}")
        lines.append(f"  Automatisch: {c['automatic']}")
    lines += ["", "Deze afspraken zijn door de onderzoeker gekozen en met de begeleider af te stemmen. Sift beoordeelt niet of ze methodologisch passend zijn.",
              "Verbatim betekent: zoals door het spraakmodel herkend en door de onderzoeker gecorrigeerd. Een model herkent niet alle aarzelingen of herhalingen."]
    return "\n".join(lines)


def filler_list(chosen: dict | None) -> list[str]:
    raw = (chosen or {}).get("filler_words") or DEFAULT_CONVENTIONS["filler_words"]
    return [w.strip() for w in str(raw).replace(";", ",").split(",") if w.strip()]
