"""Start de server en open de browser:  python -m sift [--port 8765] [--no-browser] [--lan]"""
from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from . import lan
from .config import APP_NAME, PROJECTS_DIR, find_ffmpeg, hardware_info


def main():
    ap = argparse.ArgumentParser(prog="sift")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="0.0.0.0", help="standaard 0.0.0.0; verzoeken van buiten deze computer worden pas toegelaten met --lan (of de schakelaar in de app) plus de code")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--lan", action="store_true", help="meteen bereikbaar maken voor telefoons op hetzelfde wifi (met 4-cijferige code)")
    a = ap.parse_args()
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    hw = hardware_info()
    print(f"{APP_NAME}: GPU={hw['gpu_name'] or 'geen (CPU)'}  ffmpeg={'ok' if find_ffmpeg() else 'NIET GEVONDEN'}  projecten={PROJECTS_DIR}")
    lan.state.port = a.port
    lan.state.enabled = a.lan
    if a.lan:
        print(f"{APP_NAME}: bereikbaar op het netwerk via {lan.url()}  (code {lan.state.code})")
    url = f"http://127.0.0.1:{a.port}"
    if not a.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("sift.server:app", host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
