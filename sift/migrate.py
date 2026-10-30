"""Versies van de JSON-bestanden en omkeerbare migraties.

project.json
  v1 (impliciet, geen schema_version): name, created, source, settings, audio, status, steps, speakers, runs, error
  v2: + schema_version, study_id (None = geen onderzoek), review_status (none | in_progress | checked), checked_at,
      export_prefs (laatst gebruikte exportinstellingen per doel)

transcript.json
  v1 (impliciet): segments[].highlight (één markering voor "citaat" én "later luisteren")
  v2: + schema_version; segments[].quote (= oude highlight: een bestaande highlight wordt een 'Interessant citaat'),
      segments[].later (nieuw, 'Later opnieuw luisteren'); words[].checked (door een mens bevestigd), words[].later;
      gaps[] (mogelijk ontbrekende tekst, met dismissed-vlag)

Migratie gebeurt in het geheugen bij het laden en wordt pas weggeschreven bij de volgende opslag. Bestaande v1-bestanden
blijven dus leesbaar zolang er niets wordt opgeslagen. `downgrade_*` zet een v2-bestand terug naar v1 (verlies: alleen de
nieuwe velden), zodat een oudere Sift-versie het bestand weer kan openen.
"""
from __future__ import annotations

import copy

PROJECT_SCHEMA = 2
TRANSCRIPT_SCHEMA = 2


def migrate_project(meta: dict) -> tuple[dict, bool]:
    """Geeft (meta, gewijzigd)."""
    v = int(meta.get("schema_version") or 1)
    if v >= PROJECT_SCHEMA:
        return meta, False
    m = copy.deepcopy(meta)
    if v < 2:
        m.setdefault("study_id", None)
        m.setdefault("review_status", "none")
        m.setdefault("checked_at", None)
        m.setdefault("export_prefs", {})
        if m.get("status") == "fout" and (m.get("error") or "") == "geannuleerd":
            m["status"] = "onderbroken"
    m["schema_version"] = PROJECT_SCHEMA
    return m, True


def downgrade_project(meta: dict) -> dict:
    m = copy.deepcopy(meta)
    for k in ("schema_version", "study_id", "review_status", "checked_at", "export_prefs"):
        m.pop(k, None)
    if m.get("status") == "onderbroken":
        m["status"] = "fout"
        m["error"] = m.get("error") or "geannuleerd"
    return m


def migrate_transcript(t: dict) -> tuple[dict, bool]:
    v = int(t.get("schema_version") or 1)
    if v >= TRANSCRIPT_SCHEMA:
        return t, False
    d = copy.deepcopy(t)
    if v < 2:
        for s in d.get("segments", []):
            if "quote" not in s:
                s["quote"] = bool(s.pop("highlight", False))
            else:
                s.pop("highlight", None)
            s.setdefault("later", False)
        d.setdefault("gaps", [])
        d["migration_note"] = "v1→v2: bestaande highlights zijn overgenomen als 'Interessant citaat'."
    d["schema_version"] = TRANSCRIPT_SCHEMA
    return d, True


def downgrade_transcript(t: dict) -> dict:
    d = copy.deepcopy(t)
    for s in d.get("segments", []):
        s["highlight"] = bool(s.pop("quote", False))
        s.pop("later", None)
        for w in s.get("words", []) or []:
            w.pop("checked", None)
            w.pop("later", None)
    for k in ("schema_version", "gaps", "migration_note"):
        d.pop(k, None)
    return d
