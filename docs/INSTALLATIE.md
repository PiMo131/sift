# Sift op Windows installeren

> **Status:** deze branch bevat geen installer. De Windows-installer (Inno Setup + bootstrap) en de Android-app
> worden in een andere branch ontwikkeld en staan na samenvoegen in `installer/` en `android/` op `main`.
> Onderstaande tekst is de gebruikersdocumentatie en de eisen waaraan die installer moet voldoen. Er is in deze
> branch **geen** Windows-build gemaakt, getest, ondertekend of gepubliceerd.

## Wat je nodig hebt

| | Minimaal | Aanbevolen |
|---|---|---|
| Windows | 10 (64-bit) | 11 |
| Processor | 4 kernen | 8 kernen of meer |
| Werkgeheugen | 8 GB | 16 GB |
| Grafische kaart | niet nodig (verwerking op de processor) | NVIDIA met 6 GB of meer videogeheugen en een recente driver |
| Schijfruimte | 3 GB voor Sift en Python-onderdelen, plus de spraakmodellen | 10 GB vrij |
| Internet | alleen bij het eerste gebruik, voor het downloaden van de spraakmodellen | |

Spraakmodellen worden bij het eerste gebruik eenmalig gedownload van Hugging Face en daarna lokaal bewaard
(`%USERPROFILE%\.cache\huggingface\hub`):

| Model | Download |
|---|---|
| Whisper large-v3 (beste kwaliteit) | ± 3,1 GB |
| Whisper large-v3-turbo (snel) | ± 1,6 GB |
| Whisper medium (licht) | ± 1,5 GB |
| SpeechBrain ECAPA (sprekers) | ± 0,1 GB |

Sift kiest zelf een passende standaard voor je computer: met een NVIDIA-GPU large-v3 + turbo, zonder GPU alleen turbo.
Op de processor duurt een uur opname ongeveer 25 tot 40 minuten (turbo) of 40 tot 60 minuten (large-v3); met een GPU
enkele minuten. De interface laat zien wanneer er gedownload wordt en wanneer er herkend wordt.

## Eisen aan de installer (voor `installer/` op main)

- Geen terminalcommando's in de gewone gebruikersflow: dubbelklikken op het installatieprogramma, daarna een
  snelkoppeling "Sift" in het Startmenu en op het bureaublad.
- Starten opent de browser op `http://127.0.0.1:8765`; afsluiten via het pictogram in het systeemvak of door het
  venster te sluiten (de server stopt dan ook; een lopende verwerking wordt netjes onderbroken en kan hervat worden).
- Onderzoeksgegevens staan **buiten** de installatiemap, in `%LOCALAPPDATA%\Sift\projects` (instelbaar via de
  omgevingsvariabele `SIFT_PROJECTS`). Een update of deïnstallatie raakt die map niet aan; bij deïnstallatie wordt dat
  expliciet gemeld met het pad.
- Zet de projectmap bij voorkeur **niet** in een OneDrive- of andere gesynchroniseerde map: synchronisatie houdt
  bestanden soms kort vast. Sift probeert het schrijven dan opnieuw, maar het blijft trager en foutgevoeliger.
- ffmpeg wordt meegeleverd of door de installer opgehaald (`winget install Gyan.FFmpeg`); Sift vindt ffmpeg ook via
  de omgevingsvariabele `SIFT_FFMPEG`.
- Zware modellen worden niet meegeleverd maar bij het eerste gebruik gedownload (zie boven), zodat de installer
  klein blijft.
- Distributievoorwaarden van meegeleverde onderdelen: Sift (MIT), faster-whisper/CTranslate2 (MIT), Whisper-modellen
  (MIT), SpeechBrain (Apache 2.0), FastAPI/uvicorn/python-docx/soundfile/numpy/scipy (MIT/BSD), PyTorch (BSD),
  NVIDIA cuBLAS/cuDNN via pip (NVIDIA-licentie; herdistributie binnen de voorwaarden van de "NVIDIA Software License
  Agreement" controleren vóór publicatie), ffmpeg (LGPL/GPL: de gebruikte build en de bronverwijzing vermelden).
- Een reproduceerbare build (script in `installer/`) en een testverslag op een schone Windows-machine horen bij de
  release. Zonder dat verslag mag de README geen Windows-validatie claimen.

## Zonder installer: starten vanuit de broncode

Zie de README onder "Voor ontwikkelaars": `git clone`, `.\start.ps1` (maakt een virtuele omgeving en installeert
alles). Vereist Python 3.10 of nieuwer.
