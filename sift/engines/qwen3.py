"""Qwen3-ASR-adapter (optioneel). Vereist: pip install qwen-asr torch  (GPU sterk aanbevolen).

Geeft geen woordzekerheid (p = null); woordtijdstempels via Qwen3-ForcedAligner. In de consensus telt dit model mee
als extra stem, in de heatmap blijft de zekerheid van het Whisper-basismodel leidend.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time


def emit(**kw):
    print(json.dumps(kw, ensure_ascii=False), flush=True)


LANG = {"nl": "Dutch", "en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian"}


def main():
    audio, out_json, opt = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    try:
        import soundfile as sf
        import torch
        from qwen_asr import Qwen3ASRModel
    except ImportError as e:
        emit(error=f"Qwen3-ASR niet geïnstalleerd ({e}). Installeer met: pip install qwen-asr torch")
        sys.exit(1)
    device = "cuda:0" if opt.get("device") == "cuda" and torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device != "cpu" else torch.float32
    t0 = time.time()
    try:
        model = Qwen3ASRModel.from_pretrained(opt.get("model", "Qwen/Qwen3-ASR-1.7B"), dtype=dtype, device_map=device,
                                              forced_aligner="Qwen/Qwen3-ForcedAligner-0.6B", forced_aligner_kwargs={"dtype": dtype, "device_map": device})
        aligner = True
    except Exception:
        model = Qwen3ASRModel.from_pretrained(opt.get("model", "Qwen/Qwen3-ASR-1.7B"), dtype=dtype, device_map=device)
        aligner = False
    load_s = time.time() - t0
    emit(progress=0.02, text=f"model geladen ({load_s:.0f}s), aligner={'ja' if aligner else 'nee'}")

    info = sf.info(audio)
    duration = info.frames / info.samplerate
    # in blokken van 60 s zodat er voortgang is en lange bestanden niet in één keer door het model hoeven
    data, sr = sf.read(audio, dtype="float32")
    block = 60 * sr
    segs, words = [], []
    t0 = time.time()
    lang = LANG.get(opt.get("language", "nl"), None)
    for i in range(0, len(data), block):
        chunk = data[i:i + block]
        offset = i / sr
        res = model.transcribe(audio=(chunk, sr), language=lang, return_time_stamps=aligner)
        r = res[0] if isinstance(res, list) else res
        text = (getattr(r, "text", None) or (r.get("text") if isinstance(r, dict) else "")).strip()
        ts = getattr(r, "time_stamps", None) or (r.get("time_stamps") if isinstance(r, dict) else None)
        if text:
            segs.append({"start": offset, "end": offset + len(chunk) / sr, "text": text, "avg_logprob": None, "no_speech_prob": None})
        if ts:
            for w in ts:
                g = (lambda k: w.get(k)) if isinstance(w, dict) else (lambda k: getattr(w, k, None))
                words.append({"start": offset + float(g("start_time") or 0), "end": offset + float(g("end_time") or 0), "word": str(g("text") or "").strip(), "p": None})
        else:
            # geen aligner: woorden gelijkmatig over het blok verdelen (grof, maar bruikbaar voor de vergelijking)
            toks = text.split()
            span = (len(chunk) / sr) / max(len(toks), 1)
            for k, t in enumerate(toks):
                words.append({"start": offset + k * span, "end": offset + (k + 1) * span, "word": t, "p": None})
        emit(progress=min(0.99, (i + len(chunk)) / len(data)), text=text[:80])
    run_s = time.time() - t0
    result = {"stats": {"model": opt.get("model", "Qwen/Qwen3-ASR-1.7B"), "device": device, "compute": str(dtype).split(".")[-1], "load_s": round(load_s, 1),
                        "run_s": round(run_s, 1), "audio_s": round(duration, 1), "realtime_factor": round(duration / max(run_s, 1e-6), 1),
                        "n_segments": len(segs), "n_words": len(words), "mean_p": None, "aligner": aligner},
              "segments": segs, "words": words}
    pathlib.Path(out_json).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    emit(progress=1.0, text="klaar")


if __name__ == "__main__":
    main()
