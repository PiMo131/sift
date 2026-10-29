"""Sprekerscheiding, volledig open source en zonder registratie.

Per Whisper-segment wordt een spreker-embedding berekend (SpeechBrain ECAPA-TDNN, Apache 2.0, getraind op VoxCeleb) en
die embeddings worden agglomeratief geclusterd (cosinusafstand). Met een opgegeven aantal sprekers wordt precies dat
aantal clusters gemaakt; anders bepaalt een afstandsdrempel het aantal. Een kort los segment tussen twee gelijke
sprekers ("ja", "hmm") krijgt de omliggende spreker.

Sprekertoewijzing per segment volgt de noScribe-regel: de beurt met de grootste overlapfractie wint; boven 0,8 heeft
een kortere beurt voorrang.
"""
from __future__ import annotations

from pathlib import Path

MODEL = "speechbrain/spkrec-ecapa-voxceleb"


def available() -> bool:
    try:
        import speechbrain  # noqa: F401
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def method() -> str | None:
    return "embeddings" if available() else None


def run(wav: Path, segments: list[dict], num_speakers: int | None, device: str, log=print) -> list[dict] | None:
    """segments: Whisper-segmenten (start, end). Geeft per segment een beurt met sprekerlabel, of None."""
    if not available():
        return None
    import numpy as np
    import soundfile as sf
    import torch
    from scipy.cluster.hierarchy import fcluster, linkage
    from speechbrain.inference.speaker import EncoderClassifier
    from speechbrain.utils.fetching import LocalStrategy

    data, sr = sf.read(str(wav), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    dev = "cuda" if device == "cuda" and torch.cuda.is_available() else "cpu"
    # COPY in plaats van symlinks: symlinks vereisen op Windows ontwikkelaarsmodus of beheerdersrechten
    enc = EncoderClassifier.from_hparams(source=MODEL, run_opts={"device": dev}, local_strategy=LocalStrategy.COPY,
                                         savedir=str(Path.home() / ".cache" / "sift" / "ecapa"))
    embs, idx = [], []
    min_len = 1.0
    for i, s in enumerate(segments):
        a, b = float(s["start"]), float(s["end"])
        if b - a < min_len:  # korte segmenten: venster verbreden rond het midden
            mid = (a + b) / 2
            a, b = max(0.0, mid - min_len / 2), min(len(data) / sr, mid + min_len / 2)
        chunk = data[int(a * sr):int(b * sr)]
        if len(chunk) < sr // 4:
            continue
        with torch.no_grad():
            e = enc.encode_batch(torch.from_numpy(chunk).unsqueeze(0).to(dev)).squeeze().cpu().numpy()
        embs.append(e / (np.linalg.norm(e) + 1e-9))
        idx.append(i)
        if i % 25 == 0:
            log(f"spreker-embeddings {i}/{len(segments)}")
    if len(embs) < 2:
        return [{"start": s["start"], "end": s["end"], "speaker": "SPEAKER_00"} for s in segments]
    X = np.stack(embs)
    # Ward op eenheidsvectoren geeft gebalanceerde clusters; average-linkage op cosinus isoleerde alleen uitschieters.
    Z = linkage(X, method="ward")
    if num_speakers and num_speakers >= 1:
        labels = fcluster(Z, t=min(num_speakers, len(embs)), criterion="maxclust")
    else:
        labels = _best_k(X, Z, log)
    order, seen = [], set()
    for lab in labels:
        if lab not in seen:
            seen.add(lab)
            order.append(lab)
    remap = {lab: f"SPEAKER_{k:02d}" for k, lab in enumerate(order)}
    lab_by_seg = {i: remap[labels[k]] for k, i in enumerate(idx)}
    turns, last = [], "SPEAKER_00"
    for i, s in enumerate(segments):
        last = lab_by_seg.get(i, last)
        turns.append({"start": float(s["start"]), "end": float(s["end"]), "speaker": last})
    for i in range(1, len(turns) - 1):
        if turns[i - 1]["speaker"] == turns[i + 1]["speaker"] != turns[i]["speaker"] and (turns[i]["end"] - turns[i]["start"]) < 1.0:
            turns[i]["speaker"] = turns[i - 1]["speaker"]
    return turns


def _best_k(X, Z, log=print):
    """Aantal sprekers kiezen (2..5) met een eenvoudige silhouettescore."""
    import numpy as np
    from scipy.cluster.hierarchy import fcluster
    from scipy.spatial.distance import cdist

    D = cdist(X, X)
    best, best_s, best_lab = 2, -1.0, None
    for k in range(2, min(5, len(X) - 1) + 1):
        lab = fcluster(Z, t=k, criterion="maxclust")
        s = []
        for i in range(len(X)):
            same = lab == lab[i]
            if same.sum() <= 1:
                s.append(0.0)
                continue
            a = D[i][same].sum() / (same.sum() - 1)
            b = min(D[i][lab == c].mean() for c in set(lab) if c != lab[i])
            s.append((b - a) / max(a, b, 1e-9))
        score = float(np.mean(s))
        log(f"k={k}: silhouette {score:.3f}")
        if score > best_s:
            best, best_s, best_lab = k, score, lab
    return best_lab


def assign(segments: list[dict], turns: list[dict] | None, default: str = "S1") -> dict:
    """Zet speaker-ids op segmenten; geeft speakers-mapping terug."""
    if not turns:
        for s in segments:
            s["speaker"] = default
        return {default: {"name": "Spreker 1"}}
    labels = sorted({t["speaker"] for t in turns})
    ids = {lab: f"S{i+1}" for i, lab in enumerate(labels)}
    prev = ids[labels[0]]
    for s in segments:
        best, best_frac, best_len = None, 0.0, 0.0
        seg_len = max(s["end"] - s["start"], 1e-3)
        for t in turns:
            ov = max(0.0, min(s["end"], t["end"]) - max(s["start"], t["start"]))
            if ov <= 0:
                continue
            frac = ov / seg_len
            tlen = t["end"] - t["start"]
            if frac > best_frac or (best_frac >= 0.8 and frac >= 0.8 and tlen < best_len):
                best, best_frac, best_len = t, frac, tlen
        s["speaker"] = ids[best["speaker"]] if best else prev
        prev = s["speaker"]
    return {sid: {"name": f"Spreker {i+1}"} for i, sid in enumerate(ids.values())}
