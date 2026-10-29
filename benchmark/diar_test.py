"""Experiment: clusterstrategieën voor sprekerscheiding op een bestaand project."""
import json, sys, pathlib
import numpy as np, soundfile as sf, torch
from scipy.cluster.hierarchy import fcluster, linkage
from speechbrain.inference.speaker import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy

proj = pathlib.Path(sys.argv[1])
segs = json.loads((proj / "runs" / "large-v3.json").read_text(encoding="utf-8"))["segments"]
data, sr = sf.read(str(proj / "work" / "audio_norm.wav"), dtype="float32")
enc = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", run_opts={"device": "cuda"}, local_strategy=LocalStrategy.COPY,
                                     savedir=str(pathlib.Path.home() / ".cache" / "sift" / "ecapa"))
embs, idx, lens = [], [], []
for i, s in enumerate(segs):
    a, b = s["start"], s["end"]
    L = b - a
    if L < 1.5:
        mid = (a + b) / 2; a, b = max(0, mid - 0.75), min(len(data) / sr, mid + 0.75)
    chunk = data[int(a * sr):int(b * sr)]
    with torch.no_grad():
        e = enc.encode_batch(torch.from_numpy(chunk).unsqueeze(0).to("cuda")).squeeze().cpu().numpy()
    embs.append(e / np.linalg.norm(e)); idx.append(i); lens.append(L)
X = np.stack(embs); lens = np.array(lens)
print("n", len(X))

def show(name, labels):
    u, c = np.unique(labels, return_counts=True)
    print(f"\n== {name}: verdeling {dict(zip(u.tolist(), c.tolist()))}")
    for k in range(0, 40):
        print(f"  {labels[k]} [{segs[idx[k]]['start']:5.1f}s] {segs[idx[k]]['text'][:70]}")

# 1) average cosine
show("average-cosine", fcluster(linkage(X, "average", "cosine"), 2, "maxclust"))
# 2) ward op genormaliseerde vectoren
show("ward", fcluster(linkage(X, "ward"), 2, "maxclust"))
# 3) alleen lange segmenten clusteren (>=1.5 s), rest naar dichtstbijzijnde centroid
long = lens >= 1.5
lab_long = fcluster(linkage(X[long], "ward"), 2, "maxclust")
cent = np.stack([X[long][lab_long == k].mean(0) for k in (1, 2)])
lab3 = np.array([int(np.argmax(cent @ x)) + 1 for x in X])
show("ward-lang+centroid", lab3)
# 4) spectral clustering (affiniteit = cosinus, genormaliseerd)
from scipy.sparse.csgraph import laplacian
A = X @ X.T; A = (A - A.min()) / (A.max() - A.min()); np.fill_diagonal(A, 0)
Lp = laplacian(A, normed=True)
w, v = np.linalg.eigh(Lp)
emb2 = v[:, :2]
lab4 = fcluster(linkage(emb2, "ward"), 2, "maxclust")
show("spectral", lab4)
# 5) kmeans op gecentreerde vectoren
Xc = X - X.mean(0); Xc /= np.linalg.norm(Xc, axis=1, keepdims=True)
show("ward-gecentreerd", fcluster(linkage(Xc, "ward"), 2, "maxclust"))
show("average-gecentreerd", fcluster(linkage(Xc, "average", "cosine"), 2, "maxclust"))
