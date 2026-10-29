"""Genereert het fictieve demo-interview (demo/demo_interview.m4a) uit demo/script.json.

Gebruik:  python demo/generate_demo.py  [--out demo/demo_interview.m4a]

Vereist: edge-tts (pip install edge-tts, heeft internet nodig voor de synthetische stemmen) en ffmpeg.
Het script bevat opzettelijk: een zachte passage (gain_db), een stilte van 4 s (gap_after) en een zin die zo zacht en
snel is uitgesproken dat een spraakmodel die waarschijnlijk overslaat (weggelaten zin). Zo heeft de controle
"Mogelijk ontbrekende tekst" iets te vinden. Alles is fictief; er is geen echt interviewmateriaal gebruikt.
Naast de audio wordt demo/script.md geschreven: het referentiescript met tijdcodes per regel (de "grondwaarheid").
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sift.config import find_ffmpeg  # noqa: E402

SR = 16000


def ff(args: list[str]) -> None:
    subprocess.run([find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def duration(path: Path) -> float:
    import soundfile as sf
    info = sf.info(str(path))
    return info.frames / info.samplerate


async def synth(text: str, voice: str, rate: str, out_mp3: Path) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out_mp3))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default=str(HERE / "script.json"))
    ap.add_argument("--out", default=str(HERE / "demo_interview.m4a"))
    a = ap.parse_args()
    script = json.loads(Path(a.script).read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="sift_demo_"))
    parts: list[Path] = []
    timeline: list[dict] = []
    t = 0.8  # korte aanloop
    lead = tmp / "lead.wav"
    ff(["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono", "-t", str(t), lead])
    parts.append(lead)
    for i, line in enumerate(script["lines"]):
        sp = script["speakers"][line["spk"]]
        mp3 = tmp / f"{i:02d}.mp3"
        asyncio.run(synth(line["text"], sp["voice"], line.get("rate", "+0%"), mp3))
        wav = tmp / f"{i:02d}.wav"
        gain = line.get("gain_db", 0)
        ff(["-i", str(mp3), "-ac", "1", "-ar", str(SR), "-af", f"volume={gain}dB", str(wav)])
        d = duration(wav)
        timeline.append({"i": i, "speaker": sp["name"], "start": round(t, 2), "end": round(t + d, 2), "text": line["text"],
                         "gain_db": gain, "rate": line.get("rate", "+0%"), "comment": line.get("comment", "")})
        parts.append(wav)
        t += d
        gap = line.get("gap_after", 0.7)
        g = tmp / f"{i:02d}_gap.wav"
        ff(["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono", "-t", str(gap), str(g)])
        parts.append(g)
        t += gap
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    full = tmp / "full.wav"
    # heel licht ruisbed (-55 dB) zodat de stiltes niet digitaal nul zijn, zoals bij een echte opname
    ff(["-f", "concat", "-safe", "0", "-i", str(lst), "-f", "lavfi", "-i", f"anoisesrc=r={SR}:c=pink:a=0.002", "-filter_complex",
        "[1:a]atrim=0:%s[n];[0:a][n]amix=inputs=2:duration=first:normalize=0" % round(t + 1, 2), "-ac", "1", "-ar", str(SR), str(full)])
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ff(["-i", str(full), "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(out)])
    md = [f"# {script['title']}", "", script["note"], "", "Referentiescript met tijdcodes (grondwaarheid voor de demo). Gegenereerd door `demo/generate_demo.py`.", "",
          "| # | tijd | spreker | tekst | bijzonderheid |", "|---|---|---|---|---|"]
    for e in timeline:
        m0, s0 = divmod(int(e["start"]), 60)
        md.append(f"| {e['i'] + 1} | {m0:02d}:{s0:02d} | {e['speaker']} | {e['text']} | {e['comment']} |")
    (HERE / "script.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (HERE / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"klaar: {out} ({out.stat().st_size / 1e6:.2f} MB, {t:.0f} s)")


if __name__ == "__main__":
    main()
