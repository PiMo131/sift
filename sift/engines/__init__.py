"""Engine-adapters. Elke engine draait in een eigen subproces en schrijft één gemeenschappelijk JSON-formaat:

{
  "stats": {"model", "device", "compute", "load_s", "run_s", "audio_s", "n_words", "mean_p"},
  "segments": [{"start", "end", "text", "avg_logprob", "no_speech_prob"}],
  "words": [{"start", "end", "word", "p"}]
}
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable


def run_engine(engine: str, audio: Path, out_json: Path, options: dict, on_progress: Callable[[float, str], None] | None = None) -> dict:
    """Start de engine als subproces en volg voortgang via JSON-regels op stdout."""
    cmd = [sys.executable, "-m", f"sift.engines.{engine}", str(audio), str(out_json), json.dumps(options)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=str(Path(__file__).resolve().parent.parent.parent))
    last_err = ""
    for line in proc.stdout:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "progress" in msg and on_progress:
            on_progress(float(msg["progress"]), msg.get("text", ""))
        if "error" in msg:
            last_err = msg["error"]
    stderr = proc.stderr.read()
    proc.wait()
    if proc.returncode != 0 or not out_json.exists():
        raise RuntimeError(last_err or stderr[-2000:] or f"engine {engine} faalde (exit {proc.returncode})")
    return json.loads(out_json.read_text(encoding="utf-8"))
