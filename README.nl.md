🇬🇧 [English](README.md) · 🇳🇱 Nederlands

<p align="center"><img src="docs/logo.png" width="96" alt="Sift"></p>

# Sift

**Van interviewopname naar een gecontroleerd transcript, op je eigen computer, met hulp bij de passages die aandacht nodig hebben.**

Sift is voor studenten en onderzoekers die interviews afnemen (gezondheidswetenschappen, medische wetenschappen, ander
kwalitatief onderzoek) en een zorgvuldig nagekeken transcript nodig hebben volgens de afspraken van hun onderzoek.
Je hoeft niets van Python, modellen of audiotechniek te weten. De opname verlaat je computer niet.

Wat Sift doet:

1. Je kiest een opname en zegt welke taal er gesproken wordt en met hoeveel mensen.
2. Sift zet de opname om in tekst met tijdcodes, wijst sprekers toe en markeert wat aandacht nodig heeft.
3. Je kijkt het transcript na met de audio ernaast: klik op een woord en je hoort het fragment; Sift leidt je langs de aandachtspunten.
4. Je exporteert naar Word, MAXQDA, NVivo, een citatenlijst of een gegevensformaat, desgewenst met namen vervangen.

![Transcript nakijken](docs/screenshot_editor.png)

## Installeren zonder Python (Windows) en de Android-app

- **Windows-installer**: `Sift-Setup-<versie>.exe` op de [Releases-pagina](https://github.com/PiMo131/sift/releases). Bij de eerste start installeert hij zelf de juiste onderdelen (GPU of CPU) en downloadt Whisper bij de eerste transcriptie. Ook als offline-bundel. Uitleg, SmartScreen, vereisten en schijfruimte: [docs/INSTALL.md](docs/INSTALL.md).

  Sift opent in een eigen venster (Microsoft Edge WebView2, standaard aanwezig op Windows 11 en met Edge op Windows 10; de installer haalt het op als het ontbreekt). Het venster sluiten laat Sift doordraaien in het systeemvak, zodat een transcriptie doorgaat; het icoon daar biedt *Sift tonen*, *Openen in browser*, de projecten- en logboekmap en *Afsluiten*, dat de server stopt. Sift nogmaals starten haalt het bestaande venster naar voren. `Sift.exe --browser` geeft het oude gedrag (standaardbrowser, geen venster).
- **Android-app**: `Sift-<versie>.apk` op dezelfde pagina. Scan de QR-code uit Sift, stuur opnames (ook WhatsApp-audio) naar je pc en kijk na op je telefoon: [docs/ANDROID.md](docs/ANDROID.md).

Beide worden automatisch gebouwd door GitHub Actions bij een versietag (`v0.1.0`). De installer is niet digitaal ondertekend; Windows vraagt daarom eenmalig om "Toch uitvoeren".

## Starten vanuit de broncode

Zonder installer start je Sift vanuit de broncode (Windows, Linux, macOS):

1. Installeer [Python 3.10 of nieuwer](https://www.python.org/downloads/) en [ffmpeg](https://ffmpeg.org) (Windows: `winget install Gyan.FFmpeg`).
2. Download deze repository (groene knop *Code → Download ZIP*, of `git clone https://github.com/PiMo131/sift.git`) en pak uit.
3. Dubbelklik op `start.ps1` (Windows) of voer `./start.sh` uit (Linux/macOS). De eerste keer worden de onderdelen geïnstalleerd; dat duurt enkele minuten. Op Windows start `start-app.ps1` hetzelfde in het eigen venster van Sift (vereist de .NET 8 SDK).
4. Je browser opent `http://127.0.0.1:8765`.

Bij de eerste verwerking downloadt Sift eenmalig een spraakmodel (1,6 tot 3,1 GB; je ziet de voortgang). Daarna werkt
alles zonder internet. Vereisten, schijfruimte en modeldownloads staan in [docs/INSTALL.md](docs/INSTALL.md).

## Probeer het met het fictieve demo-interview

In `demo/` staat een volledig verzonnen interview van 2,5 minuut over het dagelijks leven met reuma, ingesproken met
synthetische stemmen (`demo/demo_interview.m4a`, script met tijdcodes in `demo/script.md`). Het bevat opzettelijk een
zachte passage, een stilte van vier seconden en een zin die zo zacht en snel is dat de spraakmodellen die overslaan.

1. Start Sift, klik op *+ Nieuw onderzoek* en geef het een naam.
2. Kies onder *Nieuw interview* het bestand `demo/demo_interview.m4a`, taal Nederlands, 2 sprekers, en klik *Transcript maken*.
3. Na een halve tot enkele minuten (afhankelijk van je computer) staat het transcript klaar. Gebruik *Volgend aandachtspunt* om de passages te bekijken die aandacht nodig hebben; bij ongeveer 1:29 staat *Mogelijk ontbrekende tekst — luister terug*: dat is de weggelaten zin uit het script.

![Demo: nakijken in Sift](docs/demo.gif)

Een demovideo van 2,5 minuut (startpagina, verwerking, nakijken, modellen vergelijken, exporteren, telefoon) staat in [docs/demo.mp4](docs/demo.mp4); hij is gemaakt met `demo/record_demo.py`.

Alle resultaten in deze README en in `docs/` zijn gemaakt met dit demo-interview; de screenshots zijn met
`docs/screenshots.py` gegenereerd. Er is geen echt interviewmateriaal gebruikt.

## De volledige flow

### 1. Onderzoek en interview aanmaken

Een **onderzoek** bundelt interviews met een gedeelde woordenlijst (namen, afkortingen, vaktermen),
transcriptieafspraken en exportvoorkeuren. Een **interview** is één opname met eigen transcript, sprekers,
opmerkingen, aandachtspunten, versies en controlestatus. Bij elk interview zie je de status en de volgende nuttige stap.

Voor een nieuw interview geef je op: de opname, een naam, de gesproken taal, het aantal sprekers (of *weet ik niet*:
Sift schat het dan op stemkenmerken, controleer het daarna) en optioneel namen en vaktermen. Sift kiest zelf een
passende configuratie voor jouw computer; specialistische instellingen staan onder *Geavanceerd*. Met *Probeer eerst
twee minuten* verwerk je eerst een fragment; daarna kun je met één klik de hele opname doen.

![Start](docs/screenshot_home.png)

### 2. Opname verwerken

De verwerking laat in gewone taal zien wat er gebeurt: opname voorbereiden, tekst herkennen (per model), sprekers
toewijzen, transcript voorbereiden. Een modeldownload wordt apart getoond, met grootte en voortgang. Zodra er genoeg
gegevens zijn, zie je een schatting van de resterende tijd met een marge. Bij een fout krijg je concrete vervolgstappen;
de technische melding en het logboek staan onder *Technische details*. Onderbreken bewaart wat al klaar is; hervatten
gaat verder waar het bleef.

![Opname verwerken](docs/screenshot_process.png)

### 3. Nakijken

Het transcript staat als gewone, rustige tekst. Aandachtspunten zijn gemarkeerd met een teken (ook zonder kleur):
`?` *aandacht nodig* (lage modelscore), `≠` *modellen geven verschillende woorden*, `⟲` *later opnieuw luisteren*,
`⚠` *mogelijk ontbrekende tekst*. Met *Vorig / Volgend aandachtspunt* (Alt+↑/↓) loop je ze langs en kies je per punt:
**Klopt zo**, **Aangepast** of **Later opnieuw luisteren**. Afgehandelde punten komen niet terug, tenzij je het woord
later toch verandert. Filters bepalen welke soorten je ziet.

*Interessant citaat* (Alt+C) en *Later opnieuw luisteren* (Alt+L) zijn aparte markeringen met eigen lijsten.
Bestaande highlights uit oudere projecten zijn bij de migratie overgenomen als *Interessant citaat*.

Klik op een woord om het fragment te horen (uit te zetten bij *Luisteropties*), typ gewoon over de tekst heen, kies
een alternatief van een ander model, wissel de spreker, splits of voeg samen, en maak alles ongedaan met Ctrl+Z.
Alles wordt automatisch opgeslagen; de status onderin zegt eerlijk *wijzigingen aanwezig*, *bezig met opslaan*,
*opgeslagen* of *opslaan mislukt* (met een knop om het opnieuw te proberen). Ctrl+S slaat direct op.

Aandachtspunten helpen prioriteren, maar vinden niet alle fouten. Een volledige luistercontrole blijft de norm; de
voortgang (segmenten nagekeken, aandachtspunten afgehandeld) is gebaseerd op jouw controle, niet op modelzekerheid.
*Gecontroleerd* is een status die alleen jij zet.

| Toets | Werking |
|---|---|
| Ctrl+Spatie | Afspelen / pauze (springt bij hervatten iets terug) |
| Ctrl+← / Ctrl+→ | 3 seconden terug / vooruit |
| Alt+↓ / Alt+↑ (J / K buiten de tekst) | Volgend / vorig aandachtspunt |
| Alt+K · Alt+L · Alt+C | Klopt zo · Later opnieuw luisteren · Interessant citaat |
| Alt+S | Spreker wisselen |
| Ctrl+Enter | Segment nagekeken, door naar het volgende |
| Ctrl+S · Ctrl+Z · Ctrl+Y | Opslaan · ongedaan maken · opnieuw |
| Ctrl+U · Ctrl+F | [onverstaanbaar hh:mm:ss] invoegen · zoek en vervang |
| Enter · Backspace aan het begin | Splitsen · samenvoegen |
| Tab / Shift+Tab | Gewone focusnavigatie langs knoppen en velden |

### 4. Transcriptieafspraken

Per onderzoek leg je vast hoe je omgaat met stopwoorden, herhalingen, afgebroken zinnen, pauzes, lachen,
onverstaanbare passages en overlap, met per keuze een voor/na-voorbeeld. Sift is precies over wat automatisch
gebeurt (alleen: geselecteerde stopwoorden weglaten bij een export in *clean verbatim*) en wat je zelf doet (de knoppen
in de werkbalk voegen de gekozen notatie in). *Verbatim* betekent: zoals herkend en door jou gecorrigeerd; een model
herkent niet elke aarzeling. Het tijdcodeformaat `#hh:mm:ss-t#` is alleen een notatie, geen volledige ondersteuning van
het protocol van Dresing & Pehl. De afspraken zijn als tekst te exporteren om met je begeleider af te stemmen; Sift
beoordeelt niet of ze methodologisch passend zijn.

![Onderzoek instellen](docs/screenshot_study.png)

### 5. Exporteren

Je begint met het doel: **Naar Word**, **Naar MAXQDA**, **Naar NVivo**, **Citaten exporteren**, **Ondertitels** of
**Geavanceerde gegevensformaten** (tekst, CSV per segment, CSV per woord, *Transcriptgegevens (JSON)*). Per formaat
zie je alleen de instellingen die ervoor gelden, wat er in het bestand terechtkomt en een voorbeeld. Instellingen
blijven bewaard bij wisselen.

*Namen en herkenbare gegevens vervangen* is een tabel (te vervangen tekst → vervanging) die geldt voor transcripttekst,
sprekernamen, opmerkingen, alternatieve woorden, titel en bestandsnaam; alle vervangingen gebeuren in één keer, met
woordgrenzen en hoofdletterbehoud. Dit is pseudonimiseren, geen gegarandeerde anonimisering: plaatsen, organisaties
en beschrijvingen kunnen iemand nog herkenbaar maken. Het transcript en de opname veranderen niet.

Word krijgt regelnummering, een neutrale titel en optioneel een controleoverzicht (nagekeken, open aandachtspunten,
afspraken). De MAXQDA- en NVivo-bestanden volgen de tekst-met-tijdstempels-opzet van aTrain; ze zijn **niet in MAXQDA
of NVivo zelf getest** en worden zo ook in de interface aangeduid.

![Exporteren](docs/screenshot_export.png)

### 6. Versies en back-up

*Versie bewaren* slaat de actuele tekst op, inclusief wat je nog aan het typen bent. Onder *Exporteren → Versies* zie
je datum, naam en een voorbeeld, en kun je herstellen; vóór herstel wordt de huidige toestand automatisch bewaard.
Een **volledige back-up** (zip) bevat de oorspronkelijke opname, transcript, sprekers, opmerkingen, versies,
modeluitvoer, instellingen en het onderzoek. Dat is dus géén gepseudonimiseerde export. Terugzetten maakt altijd een
nieuw interview aan en overschrijft nooit iets.

## Vanaf je telefoon

Een interview opnemen of versturen met je telefoon, zonder kabel of cloud:

1. Klik in Sift op **📱 Telefoon** (rechtsboven) en zet **Bereikbaar op het netwerk** aan, of start Sift met `.\start.ps1 --lan`. Dezelfde QR-code en code staan ook op de startpagina, onder *Nieuw interview*.
2. Scan de QR-code met de camera van je telefoon (zelfde wifi, geen gastennetwerk). De 4-cijferige code wordt meegestuurd; typ hem anders over.
3. Op de telefoon: **Tik om een opname te kiezen**, of neem direct op met **Opname starten**. Vink *direct transcriberen* aan als de verwerking meteen mag starten.
4. De opname verschijnt op de computer als interview (op de telefoon kun je het meteen aan een onderzoek koppelen; anders komt het onder *Zonder onderzoek*). Via **Open in Sift** kun je de voortgang en het transcript ook op je telefoon bekijken en nakijken (werkbalk met *Volgend aandachtspunt*; de panelen *Overzicht* en *Aandachtspunt* klap je in en uit met de knoppen in de werkbalk).

Verzoeken van andere apparaten worden alleen toegelaten met de code (5 foute pogingen = een minuut wachten); **Nieuwe code** maakt een andere. Windows Firewall vraagt bij de eerste verbinding mogelijk om toestemming: kies *Toegang toestaan* voor privénetwerken. Opnemen in de browser werkt alleen via https of localhost; via het wifi-adres blokkeren Android en iOS de microfoon, kies dan een opname uit de recorder-app (of gebruik de Sift-app voor Android, zie [docs/ANDROID.md](docs/ANDROID.md)). De pagina `http://<ip>:8765/drop` is als PWA aan het startscherm toe te voegen.

## Wat lokaal blijft en waarvoor internet nodig is

- Opnames, transcripten, opmerkingen, exports en back-ups blijven op je computer (map `projects/`, instelbaar met `SIFT_PROJECTS`). Niets wordt geüpload; er is geen account en geen analytics.
- Internet is alleen nodig voor het eenmalig downloaden van spraakmodellen van Hugging Face (en bij installatie vanuit broncode voor de Python-onderdelen). De interface laat downloads zien.
- Zet de projectmap bij voorkeur niet in een gesynchroniseerde map (OneDrive): synchronisatie houdt bestanden soms kort vast. Sift probeert het schrijven dan opnieuw en meldt het eerlijk als het mislukt.

## Ondersteuning en bekende beperkingen

- Modelscores zijn hints, geen gemeten kans dat een woord klopt. Aandachtspunten vinden niet alle fouten; een volledige luistercontrole blijft nodig.
- De controle *mogelijk ontbrekende tekst* gebruikt spraakdetectie en verschillen tussen modellen. Ze mist passages die álle modellen én de spraakdetectie overslaan, en kan afgaan op lachen, hoesten of achtergrondgeluid. Afwijzen kan met één klik.
- Sprekerscheiding werkt goed bij twee duidelijk verschillende stemmen; bij meer sprekers of gelijkende stemmen zijn correcties nodig. *Weet ik niet* is een schatting.
- Pseudonimisering vervangt alleen wat je in de tabel zet. Context kan iemand herkenbaar houden.
- MAXQDA- en NVivo-import is niet in die programma's getest.
- De Windows-installer is niet digitaal ondertekend (SmartScreen-melding bij de eerste start); starten vanuit broncode vereist Python en ffmpeg.
- Getest op Windows 11 met een NVIDIA RTX 2000 Ada (8 GB) en op de processor; Linux/macOS alleen via `start.sh`, niet uitgebreid getest.

Vragen of problemen: open een issue op GitHub met de tekst onder *Technische details* (zonder opname of transcript).
Een overzicht van de uitgevoerde controles staat in [docs/VERIFICATIE.md](docs/VERIFICATIE.md), de stand per
onderdeel in [docs/IMPLEMENTATIE.md](docs/IMPLEMENTATIE.md).

---

## Voor ontwikkelaars

### Installatie vanuit broncode en starten

```powershell
git clone https://github.com/PiMo131/sift.git
cd sift
.\start.ps1                       # maakt .venv, installeert requirements.txt, start op http://127.0.0.1:8765
.\.venv\Scripts\python -m sift --no-browser --port 8765
```

Linux/macOS: `./start.sh`. Omgevingsvariabelen: `SIFT_PROJECTS` (projectmap), `SIFT_FFMPEG` (pad naar ffmpeg).
GPU: een NVIDIA-kaart met recente driver; cuBLAS/cuDNN komen via pip mee, CUDA hoeft niet apart geïnstalleerd.

### Tests

```powershell
.\.venv\Scripts\python -m pip install pytest playwright && .\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python -m pytest tests            # backend (export, pseudonimisering, migratie, back-up, API) + browsertests
.\.venv\Scripts\python tests\walkthrough_demo.py  # de twaalf verificatiestappen met echte transcriptie van het demo-interview
.\.venv\Scripts\python demo\generate_demo.py      # demo-audio opnieuw genereren (edge-tts, internet nodig)
```

### Architectuur

Backend: FastAPI (`sift/server.py`) met faster-whisper (CTranslate2) in subprocessen (`sift/engines/`), SpeechBrain
ECAPA-embeddings met ward-clustering voor sprekers (`sift/diarize.py`), combineren van modeluitkomsten
(`sift/consensus.py`), controle op ontbrekende tekst met Silero VAD (`sift/gaps.py`), exports met een contract per
formaat (`sift/export.py`, `sift/pseudonym.py`), back-up (`sift/backup.py`), onderzoeken (`sift/studies.py`),
transcriptieafspraken (`sift/conventions.py`), controlestatus (`sift/review.py`) en versiebeheerde migraties
(`sift/migrate.py`). Frontend: vanilla JS zonder build-stap (`sift/static/app.js`, `process.js`, `editor.js`,
`export.js`).

```
projects/<interview>/
  project.json          instellingen, status, controlestatus, study_id      (schema_version 2)
  transcript.json       het bewerkbare transcript: segmenten, woorden, markeringen, gaps (schema_version 2)
  versions/             versies (+ .meta.json met naam en datum)
  runs/<model>.json     ruwe uitvoer per model (start, end, word, p)
  work/                 audio_16k.wav, audio_norm.wav, play.m4a, peaks.json, vad.json, diarization.json
projects/_studies/<id>.json   onderzoek: naam, woordenlijst, afspraken, exportvoorkeuren
```

Oude projecten (zonder `schema_version`) worden bij het laden in het geheugen gemigreerd en pas bij de volgende opslag
weggeschreven; `sift/migrate.py` bevat ook de omgekeerde stap. Het woordformaat per model is overal hetzelfde,
waardoor een nieuwe engine een adapter van één bestand is.

### Modellen en verwerking

| Model | Kwaliteit | GPU (RTX 2000 Ada) | CPU (i7-13700H, int8) |
|---|---|---|---|
| Whisper large-v3 | beste | ± 7–11× realtime | ± 1,5× realtime |
| Whisper large-v3-turbo | goed | ± 25–38× realtime | ± 2,5× realtime |
| Whisper medium | redelijk | ± 12× | ± 3× |
| Qwen3-ASR 1.7B (optioneel) | wisselend | ± 5× | te traag |

Snelheden gemeten op 29–30 oktober 2026 met faster-whisper 1.2.1 op de genoemde hardware (zie
`benchmark/BENCHMARK.md`). Audio wordt eerst genormaliseerd (highpass, compressor, loudnorm −16 LUFS); dat verlaagde
in een beperkte proef het aantal onzekere woorden met een kwart. Meerdere modellen worden per woord op tijd uitgelijnd
(met correctie voor verschoven woordtijden); strategieën: consensus, hoogste score, basismodel + alternatieven.
Modellen draaien na elkaar: twee modellen tegelijk op één GPU van 8 GB bleek tien tot dertig keer trager.

De benchmark in `benchmark/BENCHMARK.md` is een **beperkte proef zonder handmatig referentietranscript**: de cijfers
zijn gemiddelde modelscores en aantallen onzekere woorden op één opname, geen gemeten woordfoutpercentages. Voor
uitspraken over transcriptiekwaliteit is een onafhankelijk gecontroleerd referentietranscript nodig.

### Licenties van de onderdelen

| Onderdeel | Licentie |
|---|---|
| Sift | MIT |
| Whisper-modellen (OpenAI) via faster-whisper / CTranslate2 | MIT |
| SpeechBrain ECAPA spreker-embeddings | Apache 2.0 |
| Qwen3-ASR (optioneel) | Apache 2.0 |
| FastAPI, uvicorn, python-docx, soundfile, numpy, scipy | MIT / BSD |
| ffmpeg (extern programma) | LGPL/GPL |
| edge-tts (alleen voor het genereren van de demo) | GPL-3.0; niet meegeleverd in Sift |

### Dankwoord en bronnen

Ideeën overgenomen uit noScribe (sprekertoewijzing, pauzeweergave, subproces-architectuur), aTrain (MAXQDA-export,
faster-whisper-instellingen), f4 (terugspoelen bij hervatten, tekstbouwstenen), Sonix (zekerheidsmarkering als
schakelaar), MacWhisper (zoek en vervang, exportpresets) en Amberscript (pseudonimisering, Dresing & Pehl-notatie).
Het ontwerponderzoek staat in `ONDERZOEK.md`.

Licentie: MIT.
