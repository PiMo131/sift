"""Maakt installer/sift.ico uit sift/static/logo.svg.

Gebruik (vanuit een tijdelijke venv met resvg-py en Pillow, zie build.ps1):
    python make_icon.py <logo.svg> <uit.ico>
"""
import io
import sys

import resvg_py
from PIL import Image

SIZES = [256, 128, 64, 48, 32, 24, 16]


def render(svg_text: str, size: int) -> Image.Image:
    png = resvg_py.svg_to_bytes(svg_string=svg_text, width=size, height=size)
    return Image.open(io.BytesIO(bytes(png))).convert("RGBA")


def main(svg_path: str, ico_path: str) -> None:
    svg = open(svg_path, encoding="utf-8").read()
    frames = [render(svg, s) for s in SIZES]
    # Pillow schrijft alle opgegeven formaten vanuit het grootste frame; we geven elk formaat expliciet mee.
    frames[0].save(ico_path, format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[1:])
    print(f"icoon geschreven: {ico_path} ({', '.join(str(s) for s in SIZES)} px)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
