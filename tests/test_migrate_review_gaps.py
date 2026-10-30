"""Schema-migratie (omkeerbaar), controlestatus en de controle op mogelijk ontbrekende tekst."""
from __future__ import annotations

import copy

from sift import gaps, review
from sift.migrate import downgrade_project, downgrade_transcript, migrate_project, migrate_transcript


def test_transcript_v1_to_v2_keeps_highlights_as_quotes(transcript):
    t, changed = migrate_transcript(transcript)
    assert changed and t["schema_version"] == 2
    assert [s["quote"] for s in t["segments"]] == [False, True, False]
    assert all("highlight" not in s and s["later"] is False for s in t["segments"])
    assert t["gaps"] == []
    t2, changed2 = migrate_transcript(t)
    assert not changed2 and t2 is t


def test_transcript_downgrade_roundtrip(transcript):
    t, _ = migrate_transcript(transcript)
    t["segments"][0]["words"][0]["checked"] = True
    back = downgrade_transcript(t)
    assert back["segments"][1]["highlight"] is True and "quote" not in back["segments"][1]
    assert "schema_version" not in back and "checked" not in back["segments"][0]["words"][0]
    orig = copy.deepcopy(transcript)
    assert [s["text"] for s in back["segments"]] == [s["text"] for s in orig["segments"]]


def test_project_v1_to_v2_and_back(meta):
    m, changed = migrate_project(meta)
    assert changed and m["schema_version"] == 2 and m["study_id"] is None and m["review_status"] == "none"
    assert meta.get("schema_version") is None, "origineel ongewijzigd"
    assert downgrade_project(m) == meta


def test_cancelled_v1_project_becomes_onderbroken(meta):
    m, _ = migrate_project({**meta, "status": "fout", "error": "geannuleerd"})
    assert m["status"] == "onderbroken"
    assert downgrade_project(m)["status"] == "fout"


# ---------- controlestatus ----------
def test_display_status_requires_explicit_checked(meta, transcript):
    assert review.display_status({**meta, "status": "nieuw"}, None) == "Nog te verwerken"
    assert review.display_status({**meta, "status": "bezig"}, None) == "Bezig met verwerken"
    assert review.display_status({**meta, "status": "onderbroken"}, None) == "Verwerking onderbroken"
    assert review.display_status({**meta, "status": "fout"}, None) == "Verwerking mislukt"
    fresh = {**transcript, "edited": False, "segments": [{**s, "reviewed": False} for s in transcript["segments"]]}
    assert review.display_status({**meta, "review_status": "none"}, fresh) == "Transcript beschikbaar"
    assert review.display_status({**meta, "review_status": "in_progress"}, transcript) == "Nakijken bezig"
    all_reviewed = {**transcript, "segments": [{**s, "reviewed": True} for s in transcript["segments"]]}
    assert review.display_status({**meta, "review_status": "in_progress"}, all_reviewed) == "Nakijken bezig", "alles nagekeken is nog niet 'Gecontroleerd'"
    assert review.display_status({**meta, "review_status": "checked"}, all_reviewed) == "Gecontroleerd"


def test_attention_points_and_summary(transcript):
    t, _ = migrate_transcript(transcript)
    pts = review.attention_points(t, 0.6)
    ids = [p["id"] for p in pts]
    assert ids == ["w:1:0", "w:1:4", "w:1:6"]  # Eh (onzeker), Zwolle (oneens), ANNA's (onzeker+oneens)
    assert review.summary(t)["attention_open"] == 3
    t["segments"][1]["words"][0]["checked"] = True   # 'Klopt zo'
    t["segments"][1]["words"][4]["later"] = True     # 'Later opnieuw luisteren' blijft open
    assert review.summary(t)["attention_open"] == 2
    assert review.next_action({"status": "klaar", "review_status": "in_progress"}, t) == "2 aandachtspunten nakijken"
    t["gaps"] = [{"start": 1, "end": 2, "kind": "vad", "dismissed": False}]
    assert review.summary(t)["gaps_open"] == 1
    t["gaps"][0]["dismissed"] = True
    assert review.summary(t)["gaps_open"] == 0


def test_model_score_is_never_changed_by_confirming(transcript):
    t, _ = migrate_transcript(transcript)
    w = t["segments"][1]["words"][0]
    w["checked"] = True
    assert w["p"] == 0.4 and not w.get("edited")


# ---------- mogelijk ontbrekende tekst ----------
def _words(spans):
    # lange woordvorm zodat een span van 1 s niet als 'uitgesmeerd' telt (zie gaps.stretched)
    return [{"start": a, "end": b, "word": f"woordenboek{i}"} for i, (a, b) in enumerate(spans)]


def test_gap_from_vad_speech_without_words_but_not_from_silence():
    vad = [{"start": 0.0, "end": 3.0}, {"start": 10.0, "end": 13.5}, {"start": 20.0, "end": 21.0}]
    words = _words([(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (20.0, 21.0)])  # 10–13.5 is spraak zonder tekst; 3–10 is stilte
    found = gaps.detect(vad, {}, words, "large-v3")
    assert len(found) == 1 and found[0]["kind"] == "vad"
    assert 9.9 <= found[0]["start"] <= 10.1 and 13.4 <= found[0]["end"] <= 13.6


def test_gap_from_coverage_difference_carries_hint_but_no_inserted_text():
    runs = {"large-v3": {"words": _words([(0, 1)])}, "large-v3-turbo": {"words": [{"start": 5.0, "end": 5.4, "word": "misselijk"}, {"start": 5.5, "end": 5.9, "word": "van"}]}}
    words = _words([(0, 1)])
    found = gaps.detect(None, runs, words, "large-v3")
    assert len(found) == 1 and found[0]["kind"] == "coverage" and found[0]["hint"] == "misselijk van" and found[0]["models"] == ["large-v3-turbo"]
    assert words == _words([(0, 1)]), "transcript blijft ongewijzigd"


def test_short_pauses_and_single_stray_words_are_ignored():
    vad = [{"start": 0.0, "end": 2.5}]
    words = _words([(0.0, 1.0), (1.9, 2.5)])  # 0.9 s gat, maar met marge < MIN_GAP_S
    assert gaps.detect(vad, {}, words, "x") == []
    runs = {"x": {"words": []}, "y": {"words": [{"start": 5.0, "end": 5.3, "word": "hm"}]}}  # één los woord telt niet
    assert gaps.detect(None, runs, [], "x") == []


def test_stretched_words_do_not_cover_unrecognised_speech():
    # Gebaseerd op het demo-interview: beide modellen slaan de zachte zin over, maar het basismodel smeert de eerste
    # woorden van de volgende vraag ('Zijn er dingen', waarbij 'dingen' 2,0 s duurt) terug over de niet-herkende spraak.
    vad = [{"start": 83.82, "end": 86.48}, {"start": 88.37, "end": 88.56}, {"start": 89.01, "end": 90.64}]
    words = [{"start": 83.9, "end": 84.1, "word": "de"}, {"start": 84.1, "end": 85.3, "word": "reumaverpleegkundige"}, {"start": 85.3, "end": 85.6, "word": "belt"},
             {"start": 85.6, "end": 86.3, "word": "tussendoor."}, {"start": 88.3, "end": 88.5, "word": "Zijn"}, {"start": 88.5, "end": 88.6, "word": "er"},
             {"start": 89.0, "end": 91.0, "word": "dingen"}, {"start": 91.0, "end": 91.2, "word": "die"}]
    assert gaps.stretched(words[6]) and not gaps.stretched(words[3]) and not gaps.stretched(words[1])
    found = gaps.detect(vad, {}, words, "large-v3")
    assert len(found) == 1 and 88.8 <= found[0]["start"] <= 89.1 and 90.5 <= found[0]["end"] <= 90.7


def test_dismissed_gaps_stay_dismissed_after_recompute():
    old = [{"start": 10.0, "end": 13.0, "dismissed": True}]
    new = [{"start": 10.2, "end": 13.1, "kind": "vad", "dismissed": False}, {"start": 30, "end": 32, "kind": "vad", "dismissed": False}]
    out = gaps.carry_dismissed(old, new)
    assert out[0]["dismissed"] is True and out[1]["dismissed"] is False
