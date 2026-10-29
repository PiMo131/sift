#!/usr/bin/env bash
# Start Sift op Linux/macOS. Maakt bij de eerste keer een virtuele omgeving aan.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi
command -v ffmpeg >/dev/null || echo "ffmpeg niet gevonden: installeer met apt/brew install ffmpeg"
exec .venv/bin/python -m sift "$@"
