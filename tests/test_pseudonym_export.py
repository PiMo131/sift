"""Fase 1.2: pseudonimisering en exportcontract. Exports worden inhoudelijk gecontroleerd, niet alleen op HTTP 200."""
from __future__ import annotations

import copy
import csv
import io
import json
import zipfile

import pytest

from sift import export
from sift.pseudonym import Pseudonymizer

MAP = {"Anna de Vries": "[persoon1]", "Anna": "[persoon1]", "Zwolle": "[plaats1]"}


# ---------- pseudonimiseren ----------
def test_word_boundaries_and_case():
    ps = Pseudonymizer({"Anna": "Bea"})
    # hoofdletterongevoelig zoeken; ALL CAPS wordt overgenomen, anders blijft de vervanging zoals ingevoerd
    assert ps.text("Anna, ANNA en anna; maar niet Annabel of Joanna.") == "Bea, BEA en Bea; maar niet Annabel of Joanna."
    assert Pseudonymizer({"de buurvrouw": "buurvrouw B"}).text("De buurvrouw zei") == "buurvrouw B zei"


def test_placeholder_keeps_brackets_and_apostrophe_boundary():
    ps = Pseudonymizer(MAP)
    assert ps.text("vlakbij ANNA's zus in Zwolle.") == "vlakbij [persoon1]'s zus in [plaats1]."


def test_single_pass_no_chaining():
    # 'Anna'→'Bea' mag NIET daarna door 'Bea'→'Cees' worden geraakt; en langste term eerst
    ps = Pseudonymizer([{"find": "Anna", "replace": "Bea"}, {"find": "Bea", "replace": "Cees"}, {"find": "Anna de Vries", "replace": "mevrouw X"}])
    assert ps.text("Anna en Bea en Anna de Vries") == "Bea en Cees en mevrouw X"


def test_transcript_copy_covers_all_user_fields(transcript):
    before = copy.deepcopy(transcript)
    ps = Pseudonymizer(MAP)
    t = ps.transcript(transcript)
    assert transcript == before, "origineel mag niet veranderen"
    assert t["speakers"]["S2"]["name"] == "[persoon1]"
    assert "[persoon1]" in t["segments"][1]["note"] and "Anna" not in t["segments"][1]["note"]
    assert t["segments"][1]["words"][6]["alts"]["large-v3-turbo"] == "[persoon1]'s"
    assert "Anna" not in json.dumps(t, ensure_ascii=False)
    assert t["pseudonymized"] is True


# ---------- contract per formaat ----------
@pytest.mark.parametrize("fmt", [f for f in export.CONTRACTS if f != "docx"])
def test_every_text_format_applies_pseudonymization_to_all_included_fields(fmt, transcript):
    out = export.FORMATS[fmt][2](transcript, {"pseudonymize": MAP, "notes": True, "speakers": True})
    assert "Anna" not in out and "Zwolle" not in out, f"{fmt} lekt een naam: {out[:300]}"
    assert "[persoon1]" in out


def test_docx_applies_pseudonymization_to_text_speakers_notes_and_title(transcript, meta):
    data = export.to_docx(transcript, {"pseudonymize": MAP, "notes": True, "title": "Interview Anna de Vries", "control_overview": True}, meta)
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert "Anna" not in xml and "Zwolle" not in xml
    assert "[persoon1]" in xml and "Controleoverzicht" in xml and "lnNumType" in zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")


def test_docx_default_title_is_neutral(transcript, meta):
    xml = zipfile.ZipFile(io.BytesIO(export.to_docx(transcript, {}, meta))).read("word/document.xml").decode("utf-8")
    assert ">Transcript<" in xml and "Interview Anna" not in xml


def test_filename_is_pseudonymized():
    assert export.filename("docx", "Interview Anna de Vries", {"pseudonymize": MAP}) == "Interview [persoon1].docx"
    assert export.filename("json", "Interview Anna de Vries", {}) == "Interview Anna de Vries.transcript.json"


@pytest.mark.parametrize("fmt", [f for f in export.CONTRACTS if "quotes_only" in export.CONTRACTS[f]["options"] or export.CONTRACTS[f].get("fixed", {}).get("quotes_only")])
def test_quotes_only_in_every_supported_format(fmt, transcript, meta):
    from sift.migrate import migrate_transcript
    t, _ = migrate_transcript(transcript)  # highlight → quote
    assert [s["quote"] for s in t["segments"]] == [False, True, False]
    opts = {"quotes_only": True}
    if fmt == "docx":
        out = zipfile.ZipFile(io.BytesIO(export.to_docx(t, opts, meta))).read("word/document.xml").decode("utf-8")
    else:
        out = export.FORMATS[fmt][2](t, opts)
    assert "Zwolle" in out, fmt
    assert "Goedemiddag" not in out and "Dank u wel" not in out, f"{fmt} bevat niet-gemarkeerde passages"


def test_legacy_highlights_only_option_still_works(transcript):
    from sift.migrate import migrate_transcript
    t, _ = migrate_transcript(transcript)
    out = export.to_srt(t, {"highlights_only": True})
    assert "Zwolle" in out and "Goedemiddag" not in out


def test_export_does_not_change_original(transcript):
    before = copy.deepcopy(transcript)
    for fmt in export.FORMATS:
        export.FORMATS[fmt][2](transcript, {"pseudonymize": MAP, "quotes_only": True, "style": "clean", "time_offset": 90})
    assert transcript == before


def test_unsupported_options_are_ignored_not_silently_applied_elsewhere(transcript):
    # csv_words ondersteunt geen 'style': woorden blijven letterlijk, ook met style=clean
    out = export.to_csv_words(transcript, {"style": "clean"})
    assert "Eh," in out
    assert "style" not in export._opt("csv_words", {"style": "clean"})
    # maxqda negeert timestamps=none: tijdcode blijft (vast in het contract)
    assert "[00:00:00]" in export.to_maxqda(transcript, {"timestamps": "none"})


def test_clean_style_uses_selected_fillers(transcript):
    out = export.to_txt(transcript, {"style": "clean", "fillers": ["eh"]})
    assert "Eh," not in out and "ik woon" in out
    out2 = export.to_txt(transcript, {"style": "clean", "fillers": ["uhm"]})
    assert "Eh," in out2


def test_time_offset_for_fragment(transcript):
    assert "[00:01:30]" in export.to_txt(transcript, {"time_offset": 90})
    srt = export.to_srt(transcript, {"time_offset": 90})
    assert "00:01:30,000 -->" in srt


def test_csv_segments_fields(transcript):
    from sift.migrate import migrate_transcript
    t, _ = migrate_transcript(transcript)
    rows = list(csv.reader(io.StringIO(export.to_csv_segments(t, {"pseudonymize": MAP})), delimiter=";"))
    assert rows[0] == ["start", "eind", "spreker", "tekst", "gem_modelscore", "onzekere_woorden", "nagekeken", "citaat", "later_luisteren", "opmerking"]
    assert rows[2][2] == "[persoon1]" and rows[2][7] == "1" and "[persoon1]" in rows[2][9]


def test_nvivo_and_maxqda_are_distinct(transcript):
    assert "[00:00:00] Goedemiddag" in export.to_maxqda(transcript, {})
    assert "00:00:00 Goedemiddag" in export.to_nvivo(transcript, {}) and "[00:00:00]" not in export.to_nvivo(transcript, {})
    assert "Niet getest" in export.CONTRACTS["maxqda"]["note"] and "Niet getest" in export.CONTRACTS["nvivo"]["note"]


def test_json_export_is_labelled_as_transcript_data_not_project(transcript):
    d = json.loads(export.to_json(transcript, {"pseudonymize": MAP}))
    assert d["export"]["kind"] == "transcriptgegevens" and d["export"]["pseudonymized"] is True
    assert "pseudonymize" not in json.dumps(d) or "Anna" not in json.dumps(d)
    assert export.CONTRACTS["json"]["label"] == "Transcriptgegevens (JSON)"


def test_preview_matches_export(transcript):
    assert export.preview("txt", transcript, {"pseudonymize": MAP}).startswith("[00:00:00] Interviewer: Goedemiddag [persoon1]")
    pv = export.preview("docx", transcript, {"line_numbers": True})
    assert pv.splitlines()[0] == "Transcript" and "  1  " in pv
