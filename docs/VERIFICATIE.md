# Verificatie (30 oktober 2026)

Alle controles zijn uitgevoerd met het **fictieve demo-interview** (`demo/demo_interview.m4a`, 160 s, synthetische
stemmen, verzonnen namen). Er is geen echt interviewmateriaal gebruikt. Omgeving: Windows 11, Python 3.13.14,
faster-whisper 1.2.1 (CUDA, NVIDIA RTX 2000 Ada 8 GB), Playwright 1.64 met Chromium. Projectmap: een lege tijdelijke map
per run (`SIFT_PROJECTS`).

## Wat met echte audiotranscriptie is gedaan en wat met mocks

| Echte transcriptie (GPU, large-v3 + large-v3-turbo, SpeechBrain-sprekers, Silero VAD) | Mocks / voorbereide gegevens |
|---|---|
| De twaalf stappen van de minimale verificatie (`tests/walkthrough_demo.py`, logboek in `docs/verificatie_log.txt`), inclusief fragment van 1 minuut en daarna de hele opname | Unit-tests voor export, pseudonimisering, migratie, back-up, API, controlestatus en de controle op ontbrekende tekst gebruiken een vast fictief transcript (`tests/conftest.py`) zonder audio |
| De screenshots in `docs/` (`docs/screenshots.py` tegen een Sift met het verwerkte demo-interview) | De browsertests (`tests/test_ui_playwright.py`) draaien tegen een echte Sift-server met fictieve projecten zonder audio (de speler geeft 404; niet relevant voor opslaan, versies, sneltoetsen, lay-out) |
| De proef om de 'weggelaten zin' zo in te spreken dat beide modellen hem overslaan en de VAD hem wél ziet (tien varianten van volume en tempo; gekozen: −44 dB, +75 %) | Vertraagde en mislukte opslag zijn gesimuleerd door de PUT-aanvraag in de browser te vertragen (2–2,5 s) of met HTTP 503 te beantwoorden |

## Minimale verificatie (twaalf stappen)

Uitvoering: `python tests/walkthrough_demo.py` (start een eigen server op een lege projectmap, stuurt Chromium aan, echte
transcriptie). Resultaat van de laatste run staat in `docs/verificatie_log.txt`. Samenvatting:

| # | Stap | Resultaat | Hoe gecontroleerd |
|---|---|---|---|
| 1 | Open Sift als nieuwe gebruiker | OK | lege projectmap; startpagina toont 'Nog niets' en het formulier *Nieuw interview* |
| 2 | Maak een onderzoek en voeg een interview toe | OK | onderzoek via *+ Nieuw onderzoek*, woordenlijst en afspraak 'stopwoorden weglaten' opgeslagen; interview gekoppeld via het formulier |
| 3 | Taal, sprekers en vaktermen zonder modelkeuze | OK | *Geavanceerd* bleef dicht; `project.json` bevat de aanbevolen modellen voor deze computer (large-v3 + turbo) |
| 4 | Kort fragment, daarna de hele opname | OK | fragment 0:00–1:00 verwerkt (`settings.end == 60`, 12 segmenten, ± 45 s), daarna *Nu de hele opname verwerken*: 38 segmenten, 160 s; de uitleg over tijdcodes van een fragment stond op het scherm |
| 5 | Tekst corrigeren, aandachtspunt bevestigen, passage op 'Later luisteren' | OK | correctie op schijf met cursor in de tekst; *Klopt zo* zet `checked=true` en laat `p` ongewijzigd; Alt+L zet `later=true` op het segment |
| 6 | Citaat markeren, spreker corrigeren | OK | Alt+C → `quote=true`; sprekermenu → andere spreker; namen hernoemd naar *Interviewer* / *Anna de Vries* (fictief) |
| 7 | Opslaan met focus in de tekst, vertraagde respons, fout | OK | vertraging 2 s: tijdens 'bezig met opslaan' doorgetypt, beide wijzigingen op schijf; 503: status 'opslaan mislukt: testfout', *Opnieuw* → opgeslagen, niets verloren |
| 8 | Versie bewaren, tekst wijzigen, versie herstellen | OK | versie bevat de tekst inclusief nog niet opgeslagen invoer; na herstel staat de wijziging van daarna niet meer in `transcript.json`; automatische versie 'voor herstel' aanwezig |
| 9 | Fictieve naam vervangen, Word- en gegevensexport | OK | 'Anna de Vries' → [persoon1], 'Zwolle' → [plaats1]: in `word/document.xml` en in de CSV komen de namen niet voor, de plaatshouders wel, ook in sprekerlabel, titel en bestandsnaam; `transcript.json` ongewijzigd; regelnummering en controleoverzicht aanwezig |
| 10 | Alleen citaten exporteren | OK | citatenbestand bevat uitsluitend het gemarkeerde segment |
| 11 | Back-up maken en herstellen in een lege omgeving | OK | zip met 15 bestanden (opname, transcript, versies, runs, vad, study.json); project én onderzoek verwijderd; via *Back-up terugzetten* hersteld: tekst, audio, labels, markeringen, opmerkingen, taal en de woordenlijst van het onderzoek terug |
| 12 | Toetsenbord, schermgrootte, zoom | OK | Tab/Shift+Tab verlaten/bereiken het tekstvak (geen woordsprong), Ctrl+S slaat op, Alt+↓ springt naar een aandachtspunt; geen horizontale scroll en alle essentiële knoppen binnen beeld bij 1366×768 en 1920×1080 op 100/125/150 % (zoom geëmuleerd als kleinere viewport: 1093×614, 911×512, 1536×864, 1280×720) |
| — | JavaScript-fouten tijdens de doorloop | geen | `pageerror`-listener |

## Regressietests (pytest)

`python -m pytest tests` → 65 tests, allemaal geslaagd (backend 57, browser 8). Belangrijkste onderwerpen:

- **P0 autosave** (`test_ui_playwright.py`): typen met de cursor in de tekst → opgeslagen en na herladen aanwezig; doortypen tijdens een vertraagde opslag; mislukte opslag blijft 'mislukt' tot de herhaling slaagt; wisselen van interview tijdens een lopende opslag houdt de gegevens bij het juiste interview en toont geen 'opgeslagen' van het andere; versie bewaren bevat niet-vastgelegde invoer; undo/redo; Tab/Ctrl+S/Alt+S; lay-out op kleine schermen; exportflow bewaart de vervangingstabel bij wisselen.
- **P0 export** (`test_pseudonym_export.py`): per formaat dat vervangingen gelden voor alle velden die meegaan (tekst, sprekers, opmerkingen, alternatieven, titel, bestandsnaam); 'alleen citaten' in elk ondersteund formaat; origineel ongewijzigd; niet-ondersteunde opties worden genegeerd volgens het contract; één doorgang zonder kettingreacties; woordgrenzen en hoofdletters.
- **Migratie** (`test_migrate_review_gaps.py`): v1 → v2 en terug zonder verlies van tekst; oude projecten laden via de API zonder dat het bestand op schijf verandert tot de volgende opslag.
- **Back-up** (`test_server_backup.py`): maken → herstellen in lege omgeving → inhoud vergelijken; tweede keer herstellen overschrijft niet (kopie met achtervoegsel); onveilige paden en vreemde zips geweigerd.
- **Ontbrekende tekst** (`test_migrate_review_gaps.py`): VAD-spraak zonder woorden, stilte niet gemeld, dekkingsverschil met hint, uitgesmeerde woordtijden, afwijzingen blijven bewaard.
- **Uitlijning** (`test_consensus.py`): verschoven woordtijden geven geen valse meningsverschillen; een model dat een passage mist telt als hiaat.

## De demo-aandachtspunten (echte audio)

| Ingebouwd in het script | Wat Sift ervan maakte |
|---|---|
| Zachte passage (−16 dB, regel 8) | Na normalisatie door beide modellen volledig herkend; geen aandachtspunt nodig. |
| Stilte van 4 s (na regel 6) | Geen aandachtspunt: de spraakdetectie ziet geen spraak, dus geen 'ontbrekende tekst' (echte stilte wordt niet gemeld). |
| Weggelaten zin (−44 dB, +75 %, regel 11, ± 1:26–1:31) | Beide modellen slaan de zin over. Sift meldt *Mogelijk ontbrekende tekst — luister terug* op 1:29,0–1:30,6. Let op: het basismodel smeerde de eerste woorden van de volgende vraag terug over dit interval; zonder de correctie voor uitgesmeerde woordtijden werd het interval niet gevonden. Bij een iets luidere variant (−40 dB) herkende large-v3 de zin soms wél en turbo niet: dan is er geen hiaat maar 13 'aandacht nodig'-woorden. |
| 'Eh' in regel 2 | Door beide modellen weggelaten; 'eh' in regel 17 wel herkend. Illustreert dat 'verbatim' niet betekent dat elke aarzeling is herkend. |

Aantal aandachtspunten op het hele demo-interview: 93 vóór de correctie van de uitlijning (bijna allemaal vals door
verschoven woordtijden), 6–7 erna (4 'aandacht nodig', 3 'modellen verschillen', 1 'mogelijk ontbrekende tekst').

## Niet geverifieerd

- Import van de MAXQDA-/NVivo-bestanden in MAXQDA of NVivo zelf.
- Echt browserzoom (alleen viewport-emulatie), andere browsers dan Chromium/Edge, screenreaders.
- Een Windows-installer (andere branch).
- Gedrag op een computer zonder GPU is alleen via de hardwaredetectie getest, niet met een volledige verwerking op de CPU in deze branch (de snelheden in de README komen uit `benchmark/BENCHMARK.md`).
- Opslaan in een OneDrive-map over langere tijd; de herhaalde schrijfactie is getest met de projectmap in de OneDrive-worktree van deze branch, waar de oorspronkelijke code één keer uitviel op `WinError 5`.
