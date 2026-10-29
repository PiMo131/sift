"""Eerste-keer-installatie van de Python-afhankelijkheden van Sift (Windows).

Wordt door Sift.exe gestart in een console-venster (eerste start, na een update, of via 'Sift herstellen').
Kan ook met de hand:  python\\python.exe app\\bootstrap.py [--cpu|--gpu] [--online]

Stappen:
  1. pip beschikbaar maken in de ingebedde Python (uit tools\\pip-*.whl, geen internet nodig)
  2. GPU-detectie (nvcuda.dll in System32 of nvidia-smi) -> torch cu126, anders torch cpu
  3. torch/torchaudio installeren (download.pytorch.org), bij GPU ook cuBLAS/cuDNN via pip
  4. overige afhankelijkheden uit requirements.txt
  5. importcontrole en stempel .bootstrap-ok schrijven
Als er een map wheels\\ naast de app staat (offline-bundel), wordt alles daaruit geinstalleerd (--no-index).
Elke pip-stap wordt bij een fout een keer herhaald. Logboek: %LOCALAPPDATA%\\Sift\\bootstrap.log
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent          # {app}\app
ROOT = APP_DIR.parent                              # {app}
PYTHON = Path(sys.executable)
WHEELS = ROOT / "wheels"
TOOLS = ROOT / "tools"
MARKER = ROOT / ".bootstrap-ok"
REQUIREMENTS = APP_DIR / "requirements.txt"
VERSION = (APP_DIR / "VERSION").read_text(encoding="utf-8").strip() if (APP_DIR / "VERSION").exists() else "0"

TORCH_VERSION = "2.7.1"
TORCH_INDEX = {"gpu": "https://download.pytorch.org/whl/cu126", "cpu": "https://download.pytorch.org/whl/cpu"}
TORCH_SUFFIX = {"gpu": "+cu126", "cpu": "+cpu"}
CUDA_PIP = ["nvidia-cublas-cu12", "nvidia-cudnn-cu12"]

LOG_DIR = Path(os.environ.get("SIFT_LOG_DIR") or Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Sift")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = LOG_DIR / "bootstrap.log"
_log = open(LOG, "a", encoding="utf-8")


def say(msg: str = "") -> None:
    print(msg, flush=True)
    _log.write(msg + "\n")
    _log.flush()


def step(n: int, total: int, title: str) -> None:
    say("")
    say(f"[{n}/{total}] {title}")
    say("-" * 60)


def run(cmd: list[str], *, cwd: Path | None = None, retries: int = 1) -> int:
    """Voert een commando uit, toont de uitvoer live en schrijft die naar het logboek. Herhaalt bij een fout."""
    rc = 1
    for attempt in range(retries + 1):
        if attempt:
            say(f"... mislukt, nog een poging over 5 s (poging {attempt + 1}/{retries + 1})")
            time.sleep(5)
        say("> " + " ".join(cmd))
        proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1)
        assert proc.stdout is not None
        for line in proc.stdout:
            say(line.rstrip("\n"))
        rc = proc.wait()
        if rc == 0:
            return 0
        say(f"exitcode {rc}")
    return rc


def pip(*args: str, offline: bool, index: str | None = None, retries: int = 1) -> int:
    cmd = [str(PYTHON), "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location", "--no-input"]
    if offline:
        cmd += ["--no-index", "--find-links", str(WHEELS)]
    elif index:
        cmd += ["--index-url", index]
    cmd += list(args)
    return run(cmd, retries=retries)


def ensure_pip() -> bool:
    if subprocess.run([str(PYTHON), "-m", "pip", "--version"], capture_output=True).returncode == 0:
        say("pip is aanwezig")
        return True
    wheels = sorted(TOOLS.glob("pip-*.whl"))
    if not wheels:
        say(f"FOUT: geen pip-wheel gevonden in {TOOLS}")
        return False
    whl = wheels[-1]
    # Een pip-wheel is puur Python: uitpakken in Lib\site-packages is dezelfde installatie als pip zelf zou doen
    # (pip weigert zichzelf te installeren vanuit een wheel: "To modify pip, please run ...").
    site_packages = PYTHON.parent / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    say(f"pip {whl.name} uitpakken in {site_packages}")
    import zipfile
    with zipfile.ZipFile(whl) as z:
        z.extractall(site_packages)
    return run([str(PYTHON), "-m", "pip", "--version"], retries=0) == 0


def detect_gpu() -> tuple[bool, str]:
    sysroot = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    if (sysroot / "System32" / "nvcuda.dll").exists():
        return True, "nvcuda.dll gevonden in System32"
    if shutil.which("nvidia-smi") or (sysroot / "System32" / "nvidia-smi.exe").exists():
        return True, "nvidia-smi gevonden"
    try:
        ctypes.WinDLL("nvcuda.dll")
        return True, "nvcuda.dll laadbaar"
    except OSError:
        pass
    return False, "geen NVIDIA-stuurprogramma gevonden"


def filtered_requirements() -> Path:
    """requirements.txt zonder torch/torchaudio/nvidia-* (die gaan apart)."""
    keep = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        s = line.strip().lower()
        if not s or s.startswith("#"):
            continue
        name = s.split(";")[0].split("=")[0].split(">")[0].split("<")[0].split("[")[0].strip()
        if name in ("torch", "torchaudio") or name.startswith("nvidia-"):
            continue
        keep.append(line)
    out = Path(tempfile.gettempdir()) / "sift-requirements.txt"
    out.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return out


def stamp() -> str:
    return f"{VERSION} {hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()}"


def fail(msg: str) -> int:
    say("")
    say(f"MISLUKT: {msg}")
    say(f"Zie {LOG}. Controleer de internetverbinding en start Sift opnieuw, of kies 'Sift herstellen' in het Startmenu.")
    if sys.stdin and sys.stdin.isatty():
        try:
            input("Druk op Enter om dit venster te sluiten...")
        except EOFError:
            pass
    return 1


def main(argv: list[str]) -> int:
    t0 = time.time()
    force = "--gpu" if "--gpu" in argv else "--cpu" if "--cpu" in argv else None
    offline = WHEELS.is_dir() and any(WHEELS.glob("*.whl"))
    if "--online" in argv:
        offline = False
    total = 5
    try:
        os.system(f"title Sift {VERSION} - onderdelen installeren")
    except Exception:
        pass
    say("=" * 60)
    say(f"Sift {VERSION}: onderdelen installeren   {time.strftime('%Y-%m-%d %H:%M:%S')}")
    say(f"Python: {PYTHON}   logboek: {LOG}")
    say("Dit gebeurt een keer (en na een update). Het kan enkele minuten duren;")
    say("met een NVIDIA-GPU wordt ongeveer 3,5 GB gedownload, zonder GPU ongeveer 1 GB.")
    say("=" * 60)
    if MARKER.exists():
        try:
            MARKER.unlink()
        except OSError:
            pass

    step(1, total, "pip gereedmaken")
    if not ensure_pip():
        return fail("pip kon niet worden geinstalleerd")

    step(2, total, "hardware bepalen")
    if offline:
        v = (WHEELS / "VARIANT").read_text(encoding="utf-8").strip().lower() if (WHEELS / "VARIANT").exists() else "cpu"
        variant = "gpu" if v == "gpu" else "cpu"
        say(f"offline-bundel gevonden in {WHEELS} (variant: {variant}); er wordt niets gedownload")
        if force and force.lstrip("-") != variant:
            say(f"let op: {force} genegeerd, de bundel bevat alleen de {variant}-variant")
    else:
        has_gpu, why = detect_gpu()
        variant = force.lstrip("-") if force else ("gpu" if has_gpu else "cpu")
        say(f"GPU-detectie: {why} -> torch-variant: {variant}" + (" (afgedwongen)" if force else ""))

    step(3, total, f"torch {TORCH_VERSION} ({variant}) installeren")
    suffix = TORCH_SUFFIX[variant]
    if pip(f"torch=={TORCH_VERSION}{suffix}", f"torchaudio=={TORCH_VERSION}{suffix}", offline=offline, index=TORCH_INDEX[variant]):
        return fail("torch kon niet worden geinstalleerd")
    if variant == "gpu":
        say("cuBLAS en cuDNN (voor faster-whisper op de GPU)")
        if pip(*CUDA_PIP, offline=offline):
            return fail("cuBLAS/cuDNN konden niet worden geinstalleerd")

    step(4, total, "overige onderdelen installeren (faster-whisper, speechbrain, fastapi, ...)")
    if pip("-r", str(filtered_requirements()), offline=offline):
        return fail("afhankelijkheden konden niet worden geinstalleerd")

    step(5, total, "controle")
    check = ("import faster_whisper, ctranslate2, torch, torchaudio, speechbrain, fastapi, uvicorn, soundfile, docx, sift;"
             "print('faster-whisper', faster_whisper.__version__, '| ctranslate2', ctranslate2.__version__, '| torch', torch.__version__,"
             "'| cuda', torch.cuda.is_available(), '| sift', sift.__version__)")
    if run([str(PYTHON), "-c", check], cwd=APP_DIR, retries=0):
        return fail("importcontrole mislukt")
    MARKER.write_text(stamp() + "\n", encoding="utf-8")
    say("")
    say(f"Klaar in {time.time() - t0:.0f} s. Sift start nu.")
    say("Bij de eerste transcriptie worden de Whisper-modellen gedownload (large-v3 is 3 GB).")
    time.sleep(2)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
