"""Start de server en open de browser:  python -m sift [--port 8765] [--no-browser]"""
from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from .config import APP_NAME, PROJECTS_DIR, find_ffmpeg, hardware_info


def main():
    ap = argparse.ArgumentParser(prog="sift")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    hw = hardware_info()
    print(f"{APP_NAME}: GPU={hw['gpu_name'] or 'geen (CPU)'}  ffmpeg={'ok' if find_ffmpeg() else 'NIET GEVONDEN'}  projecten={PROJECTS_DIR}")
    url = f"http://{a.host}:{a.port}"
    if not a.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("sift.server:app", host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
