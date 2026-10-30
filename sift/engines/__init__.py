"""Engine-adapters. Elke engine draait in een eigen subproces en schrijft één gemeenschappelijk JSON-formaat:

{
  "stats": {"model", "device", "compute", "load_s", "run_s", "audio_s", "n_words", "mean_p"},
  "segments": [{"start", "end", "text", "avg_logprob", "no_speech_prob"}],
  "words": [{"start", "end", "word", "p"}]
}

Voortgang komt als JSON-regels op stdout: {"progress": 0..1, "text": "..."} of {"download": {"bytes", "total", ...}}.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable


def run_engine(engine: str, audio: Path, out_json: Path, options: dict, on_progress: Callable[[float, object], None] | None = None,
               should_cancel: Callable[[], bool] | None = None) -> dict:
    """Start de engine als subproces en volg voortgang via JSON-regels op stdout. should_cancel() → subproces wordt gestopt."""
    cmd = [sys.executable, "-m", f"sift.engines.{engine}", str(audio), str(out_json), json.dumps(options)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=str(Path(__file__).resolve().parent.parent.parent))
    last_err = ""
    cancelled = False

    def watch():
        nonlocal cancelled
        while proc.poll() is None:
            if should_cancel and should_cancel():
                cancelled = True
                proc.kill()
                return
            time.sleep(0.5)
    if should_cancel:
        threading.Thread(target=watch, daemon=True).start()
    for line in proc.stdout:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "download" in msg and on_progress:
            on_progress(0.0, {"download": msg["download"]})
        elif "progress" in msg and on_progress:
            on_progress(float(msg["progress"]), msg.get("text", ""))
        if "error" in msg:
            last_err = msg["error"]
    stderr = proc.stderr.read()
    proc.wait()
    if cancelled:
        raise RuntimeError("onderbroken")
    if proc.returncode != 0 or not out_json.exists():
        raise RuntimeError(last_err or stderr[-2000:] or f"engine {engine} faalde (exit {proc.returncode})")
    return json.loads(out_json.read_text(encoding="utf-8"))
