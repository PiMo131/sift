"""Combineren van modeluitkomsten: verschoven woordtijden mogen geen valse 'modellen verschillen' opleveren, en een
model dat een passage helemaal mist telt als hiaat (missing_in / other_missing), niet als ander woord."""
from __future__ import annotations

from sift import consensus


def _run(words, seg_text):
    ws = [{"start": s, "end": e, "word": w, "p": p} for s, e, w, p in words]
    return {"stats": {"mean_p": 0.9}, "segments": [{"start": ws[0]["start"], "end": ws[-1]["end"], "text": seg_text}], "words": ws}


def test_shifted_timestamps_still_agree():
    base = _run([(0.0, 0.4, "Goedemiddag", .9), (0.4, 0.8, "mevrouw", .9), (0.8, 1.2, "de", .9), (1.2, 1.6, "Vries,", .9), (1.6, 2.0, "fijn", .9)], "x")
    # zelfde woorden, maar alle tijden een woord later (typische Whisper-verschuiving)
    other = _run([(0.4, 0.8, "Goedemiddag", .9), (0.8, 1.2, "mevrouw", .9), (1.2, 1.6, "de", .9), (1.6, 2.0, "Vries,", .9), (2.0, 2.4, "fijn", .9)], "x")
    out = consensus.combine({"a": base, "b": other}, ["a", "b"], "consensus")
    assert all(not w["disagree"] for w in out["segments"][0]["words"])
    assert all(w["agree"] == 2 for w in out["segments"][0]["words"])


def test_real_difference_is_flagged_and_missing_passage_is_not_a_word_disagreement():
    base = _run([(0.0, 0.4, "Dat", .9), (0.4, 0.8, "is", .9), (0.8, 1.2, "twaalf", .7), (1.2, 1.6, "kilometer", .9), (5.0, 5.4, "misselijk", .9), (5.4, 5.8, "van", .9)], "x")
    other = _run([(0.0, 0.4, "Dat", .9), (0.4, 0.8, "is", .9), (0.8, 1.2, "12", .9), (1.2, 1.6, "kilometer", .9)], "x")
    out = consensus.combine({"a": base, "b": other}, ["a", "b"], "base_plus_alts")
    words = out["segments"][0]["words"]
    assert words[2]["disagree"] and words[2]["alts"] == {"b": "12"}
    assert not words[4]["disagree"] and words[4]["missing_in"] == ["b"] and words[4]["alts"] == {}
    assert not words[0]["disagree"]
