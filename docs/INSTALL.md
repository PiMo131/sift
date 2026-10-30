# Sift installeren op Windows

Sift draait volledig op je eigen computer. Er zijn twee manieren om het op Windows te installeren; beide staan bij elke
[release](https://github.com/PiMo131/sift/releases) als download.

| | Lichte installer | Offline-bundel |
|---|---|---|
| Bestand | `Sift-Setup-<versie>.exe` (ca. 70 MB) | `Sift-Offline-CPU-<versie>.zip` (ca. 1 GB) of `Sift-Offline-GPU-<versie>.zip.001` + `.002` (ca. 3,5 GB) |
| Internet nodig bij installeren | ja: de eerste start downloadt de Python-onderdelen (ca. 1 GB zonder, 3,5 GB met NVIDIA-GPU) | nee, alles zit erin |
| Internet nodig bij de eerste transcriptie | ja, voor de Whisper-modellen (large-v3: 3 GB) | ja, tenzij je de modellen kopieert (zie onder) |
| Kiest zelf CPU of GPU | ja, automatisch | nee: CPU- of GPU-bundel |

## Wat je nodig hebt

| | Minimaal | Aanbevolen |
|---|---|---|
| Windows | 10 (64-bit) | 11 |
| Processor | 4 kernen | 8 kernen of meer |
| Werkgeheugen | 8 GB | 16 GB |
| Grafische kaart | niet nodig (verwerking op de processor) | NVIDIA met 6 GB of meer videogeheugen en een recent stuurprogramma (CUDA zelf hoeft niet geïnstalleerd te worden) |
| Schijfruimte | 5 GB voor Sift en de Python-onderdelen, plus de spraakmodellen | 10 GB vrij |
| Internet | bij de installatie (lichte installer) en bij het eerste gebruik, voor het downloaden van de spraakmodellen | |

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

Zet de projectmap bij voorkeur **niet** in een OneDrive- of andere gesynchroniseerde map: synchronisatie houdt
bestanden soms kort vast. Sift probeert het schrijven dan opnieuw, maar het blijft trager en foutgevoeliger. De
projectmap is instelbaar via de omgevingsvariabele `SIFT_PROJECTS`; ffmpeg vindt Sift ook via `SIFT_FFMPEG`.

## Lichte installer

1. Download `Sift-Setup-<versie>.exe` en start het.
2. **SmartScreen.** Windows toont waarschijnlijk "Windows heeft uw pc beschermd", omdat de installer niet met een
   (duur) code-ondertekeningscertificaat is ondertekend. Klik op *Meer informatie* en dan op *Toch uitvoeren*. Je
   kunt het bestand controleren tegen de sha256 die bij de release staat.
3. De installer vraagt geen beheerdersrechten en zet Sift in `%LOCALAPPDATA%\Programs\Sift` (per gebruiker). Het
   enige keuzevak is een snelkoppeling op het bureaublad.
4. Bij de eerste start opent Sift een zwart console-venster: de **bootstrap**. Die installeert de resterende
   Python-onderdelen (torch, faster-whisper, speechbrain, ...) in de programmamap. Het venster toont de voortgang;
   met een NVIDIA-GPU wordt ongeveer 3,5 GB gedownload, zonder GPU ongeveer 1 GB. Dit gebeurt één keer, en opnieuw na
   een update van Sift. Daarna sluit het venster en opent Sift in je browser op `http://127.0.0.1:8765`.
5. Bij de eerste transcriptie worden de gekozen Whisper-modellen van Hugging Face gedownload (large-v3 is 3 GB,
   large-v3-turbo 1,6 GB). Ze komen in `%USERPROFILE%\.cache\huggingface\hub` en worden daarna hergebruikt.

### Wat de bootstrap precies doet

- Zoekt een NVIDIA-stuurprogramma (`nvcuda.dll` in `System32` of `nvidia-smi`). Gevonden: torch 2.7.1 voor CUDA 12.6
  plus cuBLAS en cuDNN via pip. Niet gevonden: torch voor de CPU.
- Installeert daarna `requirements.txt` in de ingebedde Python 3.12 (`python\Lib\site-packages` in de programmamap).
- Elke stap wordt bij een fout één keer herhaald. Het volledige logboek staat in `%LOCALAPPDATA%\Sift\bootstrap.log`.
- Afdwingen kan: `Sift.exe --cpu` of `Sift.exe --gpu` (bijvoorbeeld een laptop met NVIDIA-kaart die je toch op de
  CPU wilt laten werken). Combineer met `--repair` om een bestaande installatie om te zetten.

## Offline-bundel

Voor een computer zonder (snelle) internetverbinding, of om de download maar één keer te doen voor meerdere
computers.

1. Download de CPU-bundel of (met NVIDIA-kaart) de GPU-bundel. De GPU-bundel is groter dan 2 GB en daarom gesplitst
   in `Sift-Offline-GPU-<versie>.zip.001` en `.002`. Zet beide delen in dezelfde map en open `.001` met
   [7-Zip](https://7-zip.org); dat leest de delen achter elkaar. Zonder 7-Zip voeg je ze eerst samen in een
   opdrachtvenster:
   ```
   copy /b Sift-Offline-GPU-<versie>.zip.001 + Sift-Offline-GPU-<versie>.zip.002 Sift-Offline-GPU-<versie>.zip
   ```
   en pak je het resultaat uit met Verkenner.
2. In de uitgepakte map staan `Sift-Setup-<versie>.exe`, een map `wheels\` en `LEESMIJ.txt`. Laat ze bij elkaar en
   start de installer. Die ziet de map `wheels\` naast zich staan en kopieert die mee naar de programmamap.
3. De eerste start installeert alles uit `wheels\` zonder internet. De map blijft staan zodat *Sift herstellen* ook
   offline werkt; na een geslaagde installatie mag je `wheels\` in de programmamap verwijderen om schijfruimte terug
   te krijgen.
4. De Whisper-modellen zitten niet in de bundel. Zonder internet: kopieer de map `%USERPROFILE%\.cache\huggingface\hub`
   van een computer waar Sift die modellen al heeft gebruikt.

## Waar staat wat

| | |
|---|---|
| Programma | `%LOCALAPPDATA%\Programs\Sift` (Sift.exe, `app\sift`, `python\`, `ffmpeg\`) |
| Projecten (opnames, transcripten, exports) | `Documenten\Sift\projects` |
| Whisper- en SpeechBrain-modellen | `%USERPROFILE%\.cache\huggingface\hub` |
| Logboeken | `%LOCALAPPDATA%\Sift\bootstrap.log` (installatie) en `sift.log` (server) |

Sift luistert op poort 8765, ook op je lokale netwerk (voor de telefoon-koppeling; verzoeken van buiten deze computer
worden pas toegelaten na het inschakelen van *LAN* in de app, met een code). Windows vraagt daarom bij de eerste start
mogelijk om toegang door de firewall; kies *Particuliere netwerken*. De installer maakt zelf geen firewallregel aan
(dat vereist beheerdersrechten).

Ontwikkelaars: `Sift.exe --port 9000 --no-browser` werkt zoals `python -m sift`. Draait Sift al op de poort, dan
opent Sift.exe alleen de browser.

## Herstellen en verwijderen

- **Sift herstellen** (Startmenu) of `Sift.exe --repair` draait de bootstrap opnieuw: bij een mislukte of
  onderbroken eerste installatie, na een driverwissel (CPU ↔ GPU) of als een onderdeel kapot is. Projecten en
  modellen blijven staan.
- Een nieuwe versie installeer je gewoon over de oude heen; de bootstrap merkt dat en werkt de onderdelen bij.
- **Verwijderen** via *Apps en onderdelen* of het Startmenu. Dat verwijdert de programmamap (inclusief de
  geïnstalleerde Python-onderdelen en eventuele `wheels\`) en de logboeken. Projecten in `Documenten\Sift` en de
  modellen in `.cache\huggingface` blijven bewust staan; verwijder die zelf als je ze niet meer nodig hebt.

## Zelf bouwen

Alles staat in `installer\` en `.github\workflows\release.yml`; de release-workflow bouwt dezelfde bestanden bij elke
tag `v*` en hangt ze aan de GitHub Release (geen secrets nodig, alleen `GITHUB_TOKEN`). De versie komt uit
`sift/__init__.py`; de tag moet daarmee overeenkomen (`v0.1.0`).

Lokaal bouwen vereist: [.NET 8 SDK](https://dotnet.microsoft.com/download) (launcher),
[Inno Setup 6](https://jrsoftware.org/isinfo.php) (installer), Python 3 (alleen voor de offline-bundels en om het
icoon opnieuw te maken) en [7-Zip](https://7-zip.org) (alleen offline-bundels).

```powershell
.\installer\build.ps1                       # lichte installer -> installer\dist\Sift-Setup-<versie>.exe
.\installer\build.ps1 -Variant offline-cpu  # ook de CPU-bundel (downloadt ca. 1 GB aan wheels)
.\installer\build.ps1 -Variant all          # alles, ook de GPU-bundel (ca. 3,5 GB)
.\installer\build.ps1 -Variant all -DryRun  # alleen controleren of alle hulpmiddelen en scripts in orde zijn
```

Wat `build.ps1` doet:

1. Downloadt (met sha256-controle, gecachet in `installer\.build\dl`) de Python 3.12 embeddable (python.org), de
   ffmpeg "essentials"-build van gyan.dev en een pip-wheel.
2. Bouwt de launcher `Sift.exe` (`installer\launcher`, C#/.NET 8, self-contained, één bestand) met het icoon
   `installer\sift.ico` (gemaakt uit `sift/static/logo.svg` door `installer\make_icon.py`).
3. Zet de stage-map klaar: `Sift.exe`, `app\` (sift-pakket, `requirements.txt`, `bootstrap.py`, `VERSION`),
   `python\` (met aangepaste `python312._pth` zodat `import site`, pip en `..\app` werken), `ffmpeg\` (ffmpeg,
   ffprobe, LICENSE) en `tools\pip-*.whl`.
4. Compileert `installer\Sift.iss` met ISCC.
5. Voor een offline-bundel: `pip download` van alle wheels voor cp312/win_amd64 (torch van download.pytorch.org,
   CPU of cu126) naar `wheels\`, plus de setup-exe en `LEESMIJ.txt`, gezipt met 7-Zip en boven 1,9 GB gesplitst in
   `.zip.001/.002`.

Testen zonder iets te raken: installeer stil in een tijdelijke map en start op een vrije poort.

```powershell
.\installer\dist\Sift-Setup-0.1.0.exe /VERYSILENT /SUPPRESSMSGBOXES /DIR="$env:TEMP\SiftTest"
& "$env:TEMP\SiftTest\python\python.exe" "$env:TEMP\SiftTest\app\bootstrap.py" --cpu
& "$env:TEMP\SiftTest\Sift.exe" --port 8799 --no-browser --no-wait
Invoke-RestMethod http://127.0.0.1:8799/api/info | Select-Object version
& "$env:TEMP\SiftTest\unins000.exe" /VERYSILENT
```

Waarom Python 3.12 en niet 3.13: niet alle binaire afhankelijkheden (onder andere oudere PyAV-versies) hebben
wheels voor 3.13; faster-whisper, ctranslate2, torch en speechbrain hebben ze allemaal voor 3.12. Waarom een
gecompileerde launcher en geen `.cmd` of PowerShell-naar-exe: een echte exe krijgt een icoon in de taakbalk, en
ps2exe-bestanden worden vaak door virusscanners aangezien voor malware.

## Zonder installer: starten vanuit de broncode

Zie de README onder "Starten vanuit de broncode" en "Voor ontwikkelaars": `git clone`, `.\start.ps1` (maakt een
virtuele omgeving en installeert alles). Vereist Python 3.10 of nieuwer en ffmpeg.
