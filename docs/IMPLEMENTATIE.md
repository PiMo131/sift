# Implementatieoverzicht (UX-implementatieopdracht, 30 oktober 2026)

Status per fase: **afgerond**, **gedeeltelijk** of **geblokkeerd**, met reden. Branch: zie het rapport bij oplevering;
alle commits bouwen voort op `99d5245` (main). Verificatie: `docs/VERIFICATIE.md`.

## Vooraf: wat bij herinspectie van de code werd gevonden

| Bevinding uit de review | Gereproduceerd? | Wat bleek |
|---|---|---|
| Wijzigingen in het tekstvak worden pas bij het verlaten verwerkt, autosave kan eerder lopen | Ja, erger dan gedacht | `commitSegment` hing aan `element.onfocusout`; die eigenschap bestaat niet in Chromium, dus wijzigingen werden **nooit** bij het verlaten vastgelegd, alleen via Tab/Ctrl+Enter. Autosave schreef dus de oude tekst. |
| Vervangingen niet op sprekerlabels; CSV/JSON niet; 'alleen highlights' niet in CSV/SRT; UI claimt 'geldt voor elk formaat' | Ja, alle vier | Bevestigd met de fictieve naam 'Anna de Vries' in tekst, label, opmerking en alternatief (tests/test_pseudonym_export.py). |
| Stijlkeuze rendert het exportformulier opnieuw, ingevulde vervangingen verdwijnen | Ja | `renderExport()` bouwde het hele formulier opnieuw zonder de tekst te bewaren. |
| (nieuw) Verwerken van een fragment en daarna de hele opname | Ja | De genormaliseerde audio en afspeelbestanden van het fragment werden niet ongeldig gemaakt; 'hele opname' bleef het fragment. |
| (nieuw) Projectmap in OneDrive | Ja | `os.replace` gaf intermitterend `PermissionError (WinError 5)` tijdens de verwerking; de pipeline viel dan uit. |
| (nieuw) Valse 'modellen oneens' door verschoven woordtijden | Ja | Whisper-woordtijden verschillen een woord tussen modellen; de uitlijning op tijdsoverlap gaf 93 'meningsverschillen' op een schoon demo-interview, na correctie 6. |

## Fase 1 — betrouwbaarheid en gegevensbehoud

| Onderdeel | Status | Toelichting |
|---|---|---|
| 1.1 Automatisch opslaan | **afgerond** | `Saver` in `app.js`: actief tekstvak wordt vóór elke opslag/snapshot/export/projectwissel vastgelegd (zonder het tekstvak opnieuw te renderen, dus de cursor blijft staan); statussen *wijzigingen aanwezig / bezig met opslaan / opgeslagen / mislukt* met knop *Opnieuw* en automatische herhaling; per opslag een token én project-id, zodat een laat antwoord van een ander interview nooit 'opgeslagen' toont of gegevens overschrijft; een tekstvak van een vorig interview kan niet in het nieuwe transcript committen (`ownTxt`); wijzigingen tijdens een lopende opslag blijven 'aanwezig' en volgen; `beforeunload` met `sendBeacon`; Ctrl+S. Browsertests voor de vier acceptatiecriteria (`tests/test_ui_playwright.py`). |
| 1.2 Export en pseudonimisering | **afgerond** | Contract per formaat (`export.CONTRACTS`: opties, wat gaat mee, wat niet, eerlijke noot); interface toont alleen geldige opties; vervangingen in één regex-doorgang op kopie van tekst, sprekernamen, opmerkingen, alternatieven, titel en bestandsnaam; tabel in plaats van `naam = plaatshouder`; 'Alleen gemarkeerde citaten' in elk ondersteund formaat; JSON heet *Transcriptgegevens (JSON)*; back-up expliciet gescheiden en gemarkeerd als niet-gepseudonimiseerd. |
| 1.3 Versies, herstel, back-up | **afgerond** | Versielijst met datum, naam, voorbeeld en herstellen (automatisch 'voor herstel'); *Versie bewaren* bevat niet-vastgelegde invoer; ongedaan/opnieuw (`History`) voor tekst, alternatieven, sprekers, splitsen/samenvoegen, markeringen; back-up-zip met opname, transcript, sprekers, opmerkingen, versies, modeluitvoer, instellingen en onderzoek (`backup.py` documenteert wat niet meegaat); import valideert paden en overschrijft nooit. |
| Reliabiliteit extra | **afgerond** | Hernieuwde atomaire schrijfactie bij OneDrive/virusscanner (`project.atomic_replace`), reddingskopie + eerlijke 503 als het blijft mislukken. |

## Fase 2 — eerste gebruik zonder technische voorkennis

| Onderdeel | Status | Toelichting |
|---|---|---|
| 2.1 Nieuwe opname | **afgerond** | Flow: opname → naam → taal → sprekers (incl. *weet ik niet* = schatting via silhouettescore, eerlijk uitgelegd) → namen/termen → *Transcript maken*; configuratie op basis van hardware (`config.recommended_settings`); modelnamen, consensus, GPU/CPU, LUFS, compressor, hotwords onder *Geavanceerd*; geen 'Allemaal'; niet-geïnstalleerde engines zijn geen gewone keuze; *Probeer eerst twee minuten* met begin en lengte in mm:ss, daarna *Nu de hele opname verwerken*; uitleg over tijdcodes van een fragment en omrekenen bij export (`time_offset`). |
| 2.2 Verwerking en voortgang | **afgerond** | *Opname verwerken* met vier stappen in gewone taal; modeldownload apart met grootte en voortgang (`engines/fasterwhisper.ensure_downloaded`); resterende tijd met marge zodra >8 s en >8 % gevorderd; logs en modelstatistieken onder *Technische details*; fouten → vervolgstappen (`pipeline.friendly_error`); onderbreken stopt het subproces echt en bewaart afgeronde runs en correcties; hervatten slaat gecachte stappen over; status 'bezig' na een herstart wordt 'onderbroken'. |
| 2.3 Statussen | **afgerond** | Nog te verwerken / Bezig met verwerken / Transcript beschikbaar / Nakijken bezig / Gecontroleerd / Verwerking onderbroken of mislukt (`review.display_status`); *Gecontroleerd* alleen via expliciete knop, intrekbaar. |

## Fase 3 — nakijkmodus

| Onderdeel | Status | Toelichting |
|---|---|---|
| 3.1 Interface | **afgerond** | Gewone tekst, zekere woorden zonder markering; aandachtspunten met tekens (`?`, `≠`, `⟲`, `⚠`) ook zonder kleur; kleurmarkering optioneel; zijpanelen inklapbaar (rechterpaneel start ingeklapt onder 1100 px); afspelen/pauze/terug/vooruit/snelheid/positie direct bereikbaar; fragment, herhalen, terugspoelen, pauze bij typen, versterking, origineel en 'klik speelt af' in een compact paneel *Luisteropties*; voortgang op basis van gebruikerscontrole. |
| 3.2 Aandachtspunten | **afgerond** | Knoppen *Vorig / Volgend aandachtspunt*, filters (aandacht nodig, modellen verschillen, later, ontbrekende tekst, ook afgehandelde), acties *Klopt zo / Aangepast / Later opnieuw luisteren*; afgehandelde punten komen niet terug tenzij het woord verandert (`checked` wordt dan teruggezet); *Interessant citaat* en *Later luisteren* apart met eigen lijsten; migratie highlight → citaat met melding; tekst over volledige luistercontrole. |
| 3.3 Bediening en toegankelijkheid | **afgerond** | Ctrl+S = opslaan, spreker = Alt+S; Tab/Shift+Tab gewone focusnavigatie, aandachtspunten Alt+↑/↓ (J/K buiten tekst); geen globale sneltoetsen in dialogen/velden (`inDialogOrField`); echte knoppen met aria-labels, zichtbare focus (`:focus-visible`), gekoppelde labels; ongedaan maken rendert vanuit de toestand; gecontroleerd op 1366×768 en 1920×1080 bij 100/125/150 % (viewport-emulatie in Playwright, zie VERIFICATIE). |

## Fase 4 — transcriptieafspraken en export vanuit het doel

| Onderdeel | Status | Toelichting |
|---|---|---|
| 4.1 Transcriptieafspraken | **afgerond** | Per onderzoek: stopwoorden, herhalingen, afgebroken zinnen, pauzes, lachen, onverstaanbaar, overlap, elk met voor/na-voorbeeld en de regel 'automatisch / zelf' (`conventions.py`); alleen stopwoorden-weglaten gebeurt automatisch en alleen bij export; werkbalkknoppen gebruiken de gekozen notatie; exporteerbaar als tekst; geen methodologisch oordeel. |
| 4.2 Exportflow | **afgerond** | Doel eerst (Word / MAXQDA / NVivo / Citaten / Ondertitels / Geavanceerd); alleen relevante instellingen; voorbeeld met tekst, labels en tijdcodes; instellingen blijven bewaard bij wisselen en worden per interview opgeslagen (`export_prefs`); Word met regelnummering, neutrale titel en optioneel controleoverzicht; MAXQDA en NVivo apart, met de eerlijke noot 'niet getest in de doelapp'. |

## Fase 5 — zekerheid en ontbrekende passages

| Onderdeel | Status | Toelichting |
|---|---|---|
| 5.1 Modelscore | **afgerond** | Primaire teksten 'Aandacht nodig' en 'Modellen geven verschillende woorden'; ruwe score alleen onder *Details* met uitleg dat het geen kans op correctheid is; `p`, `edited` en `checked` blijven aparte eigenschappen; bevestigen verandert de score niet (test). |
| 5.2 Mogelijk ontbrekende tekst | **afgerond, met beperkingen** | `gaps.py`: VAD-spraak zonder transcriptwoorden en dekkingsverschillen tussen modellen (hint, nooit ingevoegd); uitgesmeerde woordtijden tellen niet als dekking; markering *Mogelijk ontbrekende tekst — luister terug* in tekst en golfvorm; acties *Luister terug / Tekst toevoegen / Geen ontbrekende tekst*; afwijzingen blijven bewaard. Getest met de weggelaten zin, zachte passage en stilte van het demo-interview (echte audio) en met unit-tests. Beperkingen staan in de module en in de README. |

## Fase 6 — installatie, README, onderzoeken

| Onderdeel | Status | Toelichting |
|---|---|---|
| 6.1 Windows-installatie | **geblokkeerd (bewust buiten deze branch)** | De installer (Inno Setup + bootstrap) en Android-app worden in een andere branch gemaakt (`installer/`, `android/` op main). Hier alleen `docs/INSTALLATIE.md` met vereisten, schijfruimte, modeldownloads, opslaglocatie, licentievoorwaarden en de eisen aan de installer. Geen build, test, ondertekening of publicatie geclaimd. |
| 6.2 README en demo | **afgerond** | README van boven naar beneden voor gebruikers (wat/voor wie, starten, demo, flow met actuele screenshots, lokaal vs internet, beperkingen), ontwikkelaarsdetails onderaan; vergelijkingstabel met absolute claims verwijderd; snelheden gedateerd; benchmark beschreven als beperkte proef zonder referentietranscript; fictief demo-interview met generator en script; screenshots via `docs/screenshots.py`. |
| 6.3 Onderzoek als verzameling interviews | **afgerond** | `studies.py`: onderzoek = naam, gedeelde woordenlijst, afspraken, exportvoorkeuren, standaardtaal/sprekers; interview = bestaand project met `study_id` (bestaande id's blijven); woordenlijst wordt expliciet samengevoegd bij de volgende verwerking (`effective_terms`), start geen verwerking en wijzigt geen correcties; per interview status en volgende stap; back-up/herstel nemen het onderzoek mee; migratie v1→v2 omkeerbaar (`migrate.py`), bestaande projecten blijven laden. |

## Echte beperkingen

- Geen Windows-installer, geen validatie op een schone Windows-machine, geen ondertekening (andere branch).
- MAXQDA/NVivo-import is niet in die programma's getest; de bestanden volgen een formaatbeschrijving.
- De controle op ontbrekende tekst mist passages die álle modellen en de spraakdetectie overslaan en kan afgaan op niet-spraakgeluiden. Ze is getest op synthetische spraak; echte, rommelige opnames gedragen zich anders.
- Modelscores zijn niet gekalibreerd; aandachtspunten vinden niet alle fouten.
- Pseudonimisering is tekstvervanging: wat niet in de tabel staat (plaatsen, organisaties, beschrijvingen) blijft herkenbaar.
- 'Weet ik niet' bij het aantal sprekers is een schatting (silhouettescore, 2–5); bij gelijkende stemmen zijn correcties nodig.
- Browsertests emuleren zoom door kleinere viewports; echt browserzoom en echte toetsenbordlay-outs zijn niet met een gebruiker getest.
- De UI is alleen in Chromium (Playwright) en Edge gecontroleerd.
- Resterende-tijdschatting is een extrapolatie van de voortgang van het lopende model; de eerste seconden en de modeldownload hebben geen schatting.
- Linux/macOS: alleen `start.sh`, niet opnieuw getest in deze branch.

## Wat nog een echte gebruikerstest vraagt

- De nakijkflow met aandachtspunten bij een echte, rommelige opname (zachte spreker): is de volgorde van punten en de drempel bruikbaar?
- Begrijpelijkheid van de statusteksten en foutstappen voor iemand zonder technische achtergrond.
- Toetsenbordbediening met een screenreader; de aria-labels zijn aanwezig maar niet met een screenreader beoordeeld.
- De exportbestanden in MAXQDA en NVivo zelf.
- Het gedrag van de projectmap in OneDrive over langere tijd.
