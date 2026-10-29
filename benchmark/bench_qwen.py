"""Benchmark Qwen3-ASR op een audiofragment. Gebruik: python bench_qwen.py <audio.wav> <label>"""
import json, sys, time, pathlib
import torch

audio, label = sys.argv[1], sys.argv[2]
out_dir = pathlib.Path(audio).parent
model_id = "Qwen/Qwen3-ASR-1.7B"

t0 = time.time()
from qwen_asr import Qwen3ASRModel
model = Qwen3ASRModel.from_pretrained(model_id, dtype=torch.float16, device_map="cuda:0")
t_load = time.time() - t0

t0 = time.time()
results = model.transcribe(audio=audio, language="Dutch")
t_run = time.time() - t0

r = results[0] if isinstance(results, list) else results
text = getattr(r, "text", None) or (r.get("text") if isinstance(r, dict) else str(r))
ts = getattr(r, "time_stamps", None) or (r.get("time_stamps") if isinstance(r, dict) else None)
words = []
if ts:
    for w in ts:
        if isinstance(w, dict):
            words.append({"start": w.get("start_time"), "end": w.get("end_time"), "word": w.get("text"), "p": None})
        else:
            words.append({"start": getattr(w, "start_time", None), "end": getattr(w, "end_time", None), "word": getattr(w, "text", None), "p": None})

stats = {"model": model_id, "device": "cuda", "compute": "float16", "load_s": round(t_load, 1), "run_s": round(t_run, 1),
         "audio_s": 300.0, "realtime_factor": round(300.0 / t_run, 1), "n_words": len(text.split()), "n_timestamped_words": len(words),
         "mean_p": None, "words_below_0.6": None, "words_below_0.4": None}
(out_dir / f"{label}.json").write_text(json.dumps({"stats": stats, "text": text, "words": words}, ensure_ascii=False, indent=1), encoding="utf-8")
(out_dir / f"{label}.txt").write_text(text, encoding="utf-8")
print(json.dumps(stats, ensure_ascii=False))
