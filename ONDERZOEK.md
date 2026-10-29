# Onderzoek: lokale transcriptietool voor interviews (zachte, weinig gearticuleerde spraak)

Datum: 29 oktober 2026

## 1. Jouw machine

| Onderdeel | Waarde | Gevolg |
|---|---|---|
| GPU | NVIDIA RTX 2000 Ada Laptop (8 GB VRAM) | Whisper large-v3 in float16 past; 47 min audio in ~3-5 min |
| CPU | i7-13700H, 32 GB RAM | CPU-fallback (int8) werkt, maar ~5-10x trager |
| Python | 3.13 | Ok voor torch / faster-whisper |
| ffmpeg | niet geïnstalleerd | Nodig; `winget install ffmpeg` |
| Playwright, Pillow | al aanwezig | Handig voor tests |

## 2. Haalbaarheid per onderdeel

| Wens | Haalbaar? | Hoe |
|---|---|---|
| Audio normaliseren | Ja, triviaal | ffmpeg `loudnorm` (EBU R128) naar -16 LUFS + lichte compressor. Zachte spreker komt omhoog zonder clippen. |
| Achtergrondruis wegfilteren | Ja, met mate | DeepFilterNet (lokaal, GPU/CPU) op stand "licht". Bronnen waarschuwen: agressief filteren wist spraakdetail en verslechtert ASR. Demucs (stem isoleren) als optie bij muziek/geroezemoes. |
| Lokaal Whisper, CPU/GPU | Ja | faster-whisper (CTranslate2): cuda float16 op de RTX, int8 op CPU. Een schakelaar in de UI. |
| Google Coral | Nee | Edge TPU compileert Whisper niet (dynamische tensors, te weinig geheugen); community-pogingen zijn gestrand en de Edge TPU is feitelijk EOL. De nieuwe Coral-board (2026, Synaptics) is ander hardware zonder Whisper-ondersteuning. Advies: laat Coral uit de scope, bouw een device-abstractie (cpu / cuda) zodat ONNX/DirectML later kan. |
| "Zekerheid" per woord | Ja | faster-whisper geeft per woord `probability` (0-1) bij `word_timestamps=True`, plus `avg_logprob` per segment. Precies de data voor de heatmap. Let op: het is een token-kans, geen gekalibreerde maat; drempels (bijv. <0,6 oranje, <0,4 rood) moet je proefondervindelijk afstellen. |
| Klik in tekst → afspelen x s ervoor/erna | Ja | Woordtijdstempels zitten in dezelfde output. Instelbare pre/post-roll, loop en lagere snelheid (0,75x) helpen bij onduidelijke spraak. |
| Editor met autosave | Ja | Browser-UI (lokale webapp) met debounce-autosave naar JSON + versiehistorie. CSV-export is een afgeleide. |
| CSV-uitvoer | Ja | Kolommen: start, eind, spreker, woord/zin, zekerheid, status (nagekeken ja/nee). |

## 3. Beter dan Whisper?

- **Whisper large-v3** (niet turbo): beste Whisper voor Nederlands; turbo is sneller maar iets minder nauwkeurig en bij deze audio telt elke procent.
- **CrisperWhisper** (nyrahealth): Whisper-variant getraind op *verbatim* uitvoer: houdt "eh", herhalingen, valse starts en pauzes vast. Precies wat "woord voor woord" voor een universiteitsopdracht vraagt. Nadeel: licentie CC-BY-NC (niet-commercieel, voor studie prima), meertalig maar Nederlands nog te testen.
- **Qwen3-ASR-1.7B** scoort op de Open ASR Leaderboard beter dan Whisper (WER 5,4 vs 7,2), ondersteunt Nederlands. Waard om te benchmarken, maar minder tooling voor woord-tijdstempels.
- **Dysartrische spraak**: literatuur laat zien dat Whisper zonder fine-tuning sterk terugvalt bij matige/ernstige dysartrie, en dat per-spreker fine-tuning (LoRA) de WER halveert. Dat is een vervolgstap: na 1-2 handmatig gecorrigeerde interviews heb je trainingsdata voor een LoRA op precies deze spreker.
- **Hallucinaties**: Whisper verzint tekst bij stilte/zachte passages. Silero VAD vooraf is verplicht in de pipeline.

Advies: bouw de tool model-agnostisch (een `Transcriber`-interface) en benchmark large-v3, CrisperWhisper en Qwen3-ASR op 5 minuten van dit interview. Beslis dan.

## 4. Amberscript: wat zij hebben en wat jij nog miste

Functies van Amberscript (uit productpagina en reviews):

| Functie | In jouw plan? | Advies |
|---|---|---|
| Automatische sprekerherkenning + labels | Nee | Toevoegen: pyannote diarisatie (lokaal, HF-token nodig). Voor een interview met 2 sprekers werkt dit goed. |
| Klik op woord springt naar audio | Ja | Jij gaat verder (pre/post-roll, loop). |
| Timestamps invoegen/herijken | Deels | Forced alignment (WhisperX / wav2vec2 nl) geeft strakkere woordgrenzen dan Whisper zelf. |
| Verbatim / Clean verbatim / Clean read | Nee | Opnemen als exportstijl. Verbatim = CrisperWhisper-modus; clean verbatim = fillers wegfilteren bij export. |
| Dresing & Pehl transcriptieregels | Nee | Duits/NL-academische conventie (pauzes als (.) (2), [onverstaanbaar], nadruk). Een exportprofiel "academisch" met die notatie is goud voor de universiteit. |
| Highlight-tekst en export van alleen highlights | Nee | Nuttig voor coderen in een later stadium; laagdrempelig te bouwen. |
| Zoek & vervang | Nee | Toevoegen (namen anonimiseren!). |
| Sneltoetsen (play/pauze, terugspringen) | Nee | Essentieel voor tempo: Ctrl+Space, Ctrl+pijl, Tab naar volgend onzeker woord. |
| Export DOCX, JSON, SRT, VTT, TXT | Alleen CSV | Voeg DOCX en SRT/JSON toe (python-docx; triviaal). |
| Woordenboek / custom vocabulary | Nee | Whisper `initial_prompt` met namen en vaktermen verbetert herkenning merkbaar. |
| Human-made transcriptie (uitbesteden) | n.v.t. | |
| Cloud, GDPR, ISO 27001 | n.v.t. | Jouw tool is volledig lokaal: sterker privacy-argument voor medische interviewdata. |

Functies die Amberscript níet heeft en jij wel krijgt:

- Zekerheidsheatmap per woord en "spring naar volgend onzeker woord".
- Alternatieve hypotheses per woord (uit beam search) als klikbare chips.
- Audio-voorbewerking afgestemd op zachte spreker (gain, compressie, ruis).
- Volledig offline, geen minutenprijs.
- Status "nagekeken" per segment, met voortgangspercentage.

## 4b. Meerdere modellen over elkaar leggen (ensemble)

De gebruiker kiest één model, een selectie, of "Allemaal". Bij meer dan één model:

1. Elk model draait apart (gecached per model, dus later een model toevoegen kost geen herberekening van de rest).
2. Woorden worden op tijd uitgelijnd (woordtijdstempels, met forced alignment als fallback), zodat "half negen" van model A naast "half tien" van model B komt te staan.
3. Combineerstrategie, instelbaar:
   - **Consensus**: meerderheid per woord wint; bij gelijkspel wordt het woord rood gemarkeerd en kiest de gebruiker.
   - **Hoogste zekerheid wint**: per woord de variant met de hoogste modelkans.
   - **Basismodel + alternatieven**: één model is leidend, de andere leveren alleen klikbare alternatieven.
4. In de editor krijgt een woord een klein blauw cijfer als modellen het oneens zijn. Shift+Tab springt naar het volgende meningsverschil. Het rechterpaneel toont per model de variant en de zekerheid.
5. Het tabblad "Modellen vergelijken" toont de modellen als rijen onder elkaar, een consensusrij, en een tijdlijn van het hele interview waar rood/oranje aangeeft waar de modellen het oneens zijn. Daar zit de nakijktijd.

Verwachting: modellen zijn het over 80-90% van de woorden eens; die hoef je nauwelijks na te kijken. De 5-10% waar ze afwijken is precies waar de spreker onduidelijk is. Dit verkleint de nakijktijd van een uur audio van ruwweg 4 uur naar ongeveer 1 uur. Rekentijd op jouw GPU: ongeveer 3-5 minuten per model per 47 minuten audio.

## 4c. Alle Amberscript-functies, verwerkt in de UI

Sprekerlabels (toevoegen, samenvoegen, wisselen met Ctrl+S), klik-op-woord-afspelen, tijdcode invoegen, verbatim / clean verbatim / clean read, Dresing & Pehl-notatie, highlights en export van alleen highlights, zoek & vervang, undo/redo, sneltoetsenpaneel, opmerkingen bij segment, woordenlijst (initial prompt), markering [onverstaanbaar] en (pauze), alle audio- en videoformaten als invoer, export naar DOCX, SRT, VTT, JSON, TXT en CSV, versiehistorie bij autosave.

## 4d. Lessen uit vergelijkbare tools (onderzoek 29 oktober 2026)

Bekeken: noScribe, Subtitle Workbench, Buzz, Scriberr, aTrain, MacWhisper, Sonix, f4, Amberscript.

### Wat niemand goed doet (jouw voorsprong)

- **Zekerheid per woord tonen.** noScribe streamt de woordkans wel door maar gebruikt hem niet, Scriberr slaat hem op maar toont hem niet, Buzz en aTrain hebben hem niet. Alleen Sonix (cloud, betaald) kleurt woorden op zekerheid, en Subtitle Workbench (alleen Engels) markeert woorden onder 0,55.
- **Audio voorbewerken vóór de spraakherkenning.** Geen enkele open-source tool normaliseert of ontruist vóór Whisper. Subtitle Workbench heeft een complete "mastering"-keten (brom weg, denoise, leveler, compressor, loudnorm, limiter) maar past die alleen ná de transcriptie toe voor de export.
- **Meerdere modellen combineren.** Doet niemand.

### Concreet overnemen

Pipeline en instellingen
- faster-whisper-defaults uit noScribe en aTrain: `beam_size=5`, `word_timestamps=True`, `vad_filter=True` met `min_silence_duration_ms=500`, `speech_pad_ms=50`, `condition_on_previous_text=False` tegen herhaallussen, `no_speech_threshold` iets lager (0,4 à 0,6) zodat zachte spraak niet wegvalt, temperatuur-fallbacklijst.
- Stopwoorden ("eh", "uhm") sturen via `hotwords` met een Nederlandse zin, niet via `initial_prompt` (noScribe). Woordenlijst met namen en jargon wél via `initial_prompt`.
- Elk model en de diarisatie in een **apart subproces** dat JSON-regels streamt; bij een CUDA-fout één keer automatisch op CPU opnieuw (noScribe, aTrain, Buzz). Zo overleeft de app een hangende GPU.
- Segmentranden eerst naar de VAD-stilte snappen en dan pas pauzes meten; pauze weergeven als `(..)` met één punt per seconde (noScribe).
- Sprekertoewijzing: diarisatiebeurt met de hoogste overlapfractie, bij ≥0,8 de kortere beurt verkiezen; overlappende spraak markeren met `//` (noScribe). Ruwe diarisatie bewaren om overlap te kunnen tekenen (Subtitle Workbench).
- Laat de gebruiker een start/stop-fragment transcriberen om instellingen af te stellen vóór het hele interview draait (noScribe).

Editor
- Zekerheidsheatmap als **schakelaar**, met teller "N onzekere woorden" en sneltoets naar het volgende onzekere woord (Sonix). Drempel instelbaar (standaard 0,55) en een "gezien"-status die de markering weghaalt (Subtitle Workbench). Toon in de UI: licht gekleurd betekent niet per se fout.
- **Terugspoelen bij hervatten** (f4 "Spulintervall"): na elke pauze springt het afspelen een instelbaar aantal seconden terug, zodat je de laatste woorden opnieuw hoort. Dit is het bewezen tempo-trucje van professionele transcribenten.
- **Auto-pauze bij typen** (Sonix): audio pauzeert bij de eerste toetsaanslag en hervat ~2 s na de laatste.
- Golfvorm met sleep-om-te-loopen (f4) en A/B-schakelaar origineel vs. bewerkte audio (Subtitle Workbench).
- Snelheid 0,5 tot 1,5× met behoud van toonhoogte, plus volumeboost. f4 adviseert 75% voor uittypen en 150% voor nalezen.
- Enter splitst alinea, Backspace voegt samen; automatisch afwisselende sprekers bij een tweegesprek (f4, Amberscript). "Selectie aan spreker toewijzen" als belangrijkste reparatiegebaar (MacWhisper). "Speel voorbeeld" per gedetecteerde spreker vóór je een naam geeft (Buzz).
- Tekstbouwstenen met sneltoets en plaatshouder voor tijd (f4): `(unv.)`, `(woord?)`, `(...)`, `[onverstaanbaar hh:mm:ss]`; presets voor Dresing & Pehl en Amberscript clean verbatim.
- Synchromodus voor nalezen: tekst scrollt mee en de huidige regel licht op (f4).
- "Tijdcodes herijken" na zwaar bewerken via forced alignment in plaats van handmatig schuiven (Amberscript, Sonix).
- Zoek en vervang over het hele transcript, inclusief sprekernamen (MacWhisper, noScribe).
- Autosave elke paar seconden met zichtbare status; bij een geblokkeerd bestand (open in Word) wegschrijven naar een unieke bestandsnaam (noScribe).

Export en academisch gebruik
- **MAXQDA/NVivo/ATLAS.ti-export** zoals aTrain: tijdcode `[HH:MM:SS]` aan het begin van elke alinea, sprekernaam op een eigen regel alleen bij een sprekerwissel; variant zonder haken voor NVivo op de Mac. f4 en Amberscript gebruiken het Dresing & Pehl-formaat `#hh:mm:ss-m#` aan het einde van de alinea. Maak het tijdcodeformaat instelbaar.
- RTF/DOCX met één alinea per spreker, zodat analysesoftware de audio kan koppelen (f4).
- Anonimisering bij export met genummerde plaatshouders `[persoon1]`, `[locatie1]`, consistent per entiteit, met bewerkbare entiteitenlijst (Amberscript).
- Exportpresets (MacWhisper): met/zonder sprekers, tijdcodes, milliseconden, alleen highlights, clean text.
- Per project een YAML/JSON met metadata: model(len), device, compute type, duur, verwerkingstijd, instellingen (aTrain). Dat is ook je methodesectie voor het verslag.
- Projectbestand bevat tekst, timing per woord, spreker en pad naar de audio in één bestand (noScribe, MacWhisper), zodat de editor zelfstandig werkt.

Architectuur
- Eén engine-adapterinterface met een gemeenschappelijk JSON-resultaat (`segments`, `words` met start, end, word, score, speaker) zoals Scriberr. Het combineren van modellen is dan alleen uitlijnen van adapter-uitvoer op tijd.
- Houd het bij één Python-toolkit voor app én editor. noScribe splitste in customtkinter plus een losse PyQt6-editor en verloor daardoor vertaling en autosave-pariteit. Scriberr's Go/React-stack kostte de meeste complexiteit. Advies: FastAPI + lokale webpagina in een pywebview-venster (zoals aTrain met NiceGUI), of volledig PyQt6.
- Opmerkingen uit de issues: herhaallussen en hallucinaties komen overal terug (Buzz, noScribe). Hoe lang bestand, hoe meer kans; transcribeer in overlappende blokken en meld herhaling automatisch.

Licenties: noScribe GPL-3.0, aTrain AGPL-3.0, Buzz en Scriberr MIT, Subtitle Workbench zonder licentie (niet overnemen), MacWhisper gesloten (€64 eenmalig), Sonix ~$10 per uur, f4 licentie €149 per half jaar (studenten €25 per 3 maanden), Amberscript ~€10 per uur.

## 4e. Benchmark op het echte interview (29 oktober 2026)

Volledig verslag in `benchmark/BENCHMARK.md`. Kern:

- Normaliseren (highpass, compressor, loudnorm −16 LUFS) verlaagt het aantal onzekere woorden met een kwart. Ruisonderdrukking voegt niets toe en staat standaard uit.
- large-v3 is het beste model (gem. zekerheid 0,905), turbo een goede snelle tweede. Qwen3-ASR en de faster-whisper-versie van CrisperWhisper vallen af.
- GPU: turbo 26× realtime, large-v3 7×. CPU int8: turbo 2,5×, large-v3 1,5×. CPU-only is dus werkbaar.
- Modellen nooit tegelijk op één GPU: dat kost een factor 10 tot 30. Na elkaar draaien en cachen.
- Combineren: large-v3 + turbo verschillen 15% van de woorden; dat zijn de passages om na te luisteren.

## 5. Voorgestelde architectuur

```
audio.wav
  └─ ffmpeg: 16 kHz mono            (cache: work/audio_16k.wav)
  └─ loudnorm + compressor          (cache: work/audio_norm.wav)
  └─ DeepFilterNet (optioneel)      (cache: work/audio_clean.wav)
  └─ Silero VAD → spraakregio's
  └─ Transcriber (faster-whisper | CrisperWhisper | Qwen3) → woorden + probability
  └─ pyannote diarisatie → spreker per woord
  └─ project.json  ←→  web-editor (FastAPI + HTML/JS, lokaal op localhost)
                         └─ autosave, heatmap, klik-afspelen, export CSV/DOCX/SRT
```

Stack: Python 3.13, faster-whisper, deepfilternet, pyannote.audio, FastAPI, vanilla JS + wavesurfer.js voor de golfvorm. Eén `pip install`, één commando om te starten.

## 6. Risico's

1. Dysartrie: ruwe Whisper-WER kan bij deze spreker 30%+ zijn. De heatmap plus snelle correctie vangt dit op; LoRA fine-tune is de structurele oplossing.
2. Zekerheid is niet gekalibreerd: een "groen" woord kan toch fout zijn. Communiceer het als hint, niet als garantie.
3. pyannote vraagt een (gratis) Hugging Face-token en licentieacceptatie.
4. CrisperWhisper is non-commercieel gelicentieerd.

## Bronnen

- Whisper word probability: https://tessl.io/registry/tessl/pypi-faster-whisper/files/docs/utilities.md
- CrisperWhisper: https://github.com/nyrahealth/CrisperWhisper en https://arxiv.org/html/2408.16589v1
- Open ASR benchmarks 2026: https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks
- Dysartrie en Whisper: https://arxiv.org/pdf/2501.14994 en https://arxiv.org/pdf/2508.17980
- Coral Edge TPU en Whisper: https://community.home-assistant.io/t/is-it-possible-to-use-a-coral-tpu-m-2-usb-device-to-improvements-whisper-speech-to-text-recognition/722466
- Audio-voorbewerking en hallucinaties: https://github.com/EtienneAb3d/WhisperHallu en https://vapi.ai/blog/audio-preprocessing
- WhisperX (alignment, diarisatie, nl): https://docsearch.algolia.com/mcp/docs/repo/m-bain/whisperx
- Amberscript: https://www.amberscript.com/en/transcription-software/ en https://sonix.ai/resources/amberscript-review/
