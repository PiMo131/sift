"""Benchmark faster-whisper modellen op een audiofragment.

Gebruik: python bench_whisper.py <audio.wav> <model> <label> [device]
Schrijft <label>.json en <label>.txt naast de audio, met per woord tijd + zekerheid.
"""
import json, os, sys, time, site, pathlib

# cuDNN / cuBLAS uit de pip-packages vindbaar maken voor CTranslate2
for sp in site.getsitepackages():
    for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin"):
        p = pathlib.Path(sp) / sub
        if p.is_dir():
            os.add_dll_directory(str(p))
            os.environ["PATH"] = str(p) + os.pathsep + os.environ["PATH"]

from faster_whisper import WhisperModel

audio, model_name, label = sys.argv[1], sys.argv[2], sys.argv[3]
device = sys.argv[4] if len(sys.argv) > 4 else "cuda"
compute = "float16" if device == "cuda" else "int8"
out_dir = pathlib.Path(audio).parent

t0 = time.time()
model = WhisperModel(model_name, device=device, compute_type=compute)
t_load = time.time() - t0

import soundfile as sf
wav, sr = sf.read(audio, dtype="float32")
assert sr == 16000, f"verwacht 16 kHz, kreeg {sr}"
if wav.ndim > 1:
    wav = wav.mean(axis=1)

t0 = time.time()
segments, info = model.transcribe(
    wav,
    language="nl",
    beam_size=5,
    word_timestamps=True,
    vad_filter=True,
    vad_parameters={"min_silence_duration_ms": 500},
    condition_on_previous_text=False,
)
words, segs = [], []
for s in segments:
    segs.append({"start": float(s.start), "end": float(s.end), "text": s.text.strip(), "avg_logprob": float(s.avg_logprob),
                 "no_speech_prob": float(s.no_speech_prob)})
    for w in (s.words or []):
        words.append({"start": float(w.start), "end": float(w.end), "word": w.word.strip(), "p": float(w.probability)})
t_run = time.time() - t0

probs = [w["p"] for w in words]
stats = {
    "model": model_name, "device": device, "compute": compute,
    "load_s": round(t_load, 1), "run_s": round(t_run, 1),
    "audio_s": round(info.duration, 1), "realtime_factor": round(info.duration / t_run, 1),
    "n_segments": len(segs), "n_words": len(words),
    "mean_p": round(sum(probs) / max(len(probs), 1), 3),
    "words_below_0.6": int(sum(p < 0.6 for p in probs)),
    "words_below_0.4": int(sum(p < 0.4 for p in probs)),
}
(out_dir / f"{label}.json").write_text(json.dumps({"stats": stats, "segments": segs, "words": words}, ensure_ascii=False, indent=1), encoding="utf-8")
with open(out_dir / f"{label}.txt", "w", encoding="utf-8") as f:
    for s in segs:
        m, sec = divmod(int(s["start"]), 60)
        f.write(f"[{m:02d}:{sec:02d}] {s['text']}\n")
print(json.dumps(stats, ensure_ascii=False))
