# Sift op je telefoon (Android)

De Android-app is een dunne schil om de Sift-server op je pc: je stuurt er opnames mee naar de pc (ook rechtstreeks vanuit WhatsApp) en je kijkt transcripten na in dezelfde editor als op de pc. Er komt geen cloud aan te pas: telefoon en pc praten rechtstreeks met elkaar over je eigen wifi.

Drie tabbladen:

| Tabblad | Wat je ermee doet |
|---|---|
| **Verbinden** | QR-code van de pc scannen (of adres + code intypen) en de verbinding testen |
| **Opname sturen** | Een opname kiezen of ontvangen via *Delen*, projectnaam geven, versturen, direct laten transcriberen |
| **Nakijken** | De Sift-editor van de pc, schermvullend; woorden aantikken, fragment horen, corrigeren, exporteren |

## 1. Installeren

1. Download `Sift-<versie>.apk` van de [releases-pagina](https://github.com/PiMo131/sift/releases) op je telefoon (of zet het bestand erop via kabel, Drive of WhatsApp-naar-jezelf).
2. Tik op het bestand. Android vraagt om *installeren uit onbekende bronnen* toe te staan voor de app waarmee je de APK opent (Bestanden, Chrome, Drive); sta dat toe.
3. Tik op **Installeren**. Vereist Android 8.0 of nieuwer.

Bij een update installeer je gewoon de nieuwe APK over de oude heen. Alleen als de nieuwe APK met een andere sleutel is gesigneerd (bijvoorbeeld een debug-build over een release-build) moet je de oude eerst verwijderen.

## 2. Verbinden via QR

Op de pc:

1. Start Sift (`.\start.ps1`) en zet **LAN-modus** aan. Sift luistert dan ook op het wifi-adres van de pc (bijvoorbeeld `http://192.168.1.23:8765`) en toont een QR-code met een **code van 4 cijfers**.
2. Zorg dat Windows Firewall poort 8765 doorlaat voor een *privé*-netwerk (Windows vraagt dit meestal zelf bij de eerste keer).

Op de telefoon:

1. Open Sift, tabblad **Verbinden**, tik op **QR-code scannen** en geef cameratoegang.
2. Richt de camera op het scherm van de pc. De app leest adres en code, test de verbinding en onthoudt de server.
3. Geen camera of lukt het scannen niet? Vul het adres (`192.168.1.23:8765`) en de code zelf in en tik op **Verbinding testen**.

De code beschermt je transcripten: elke aanvraag van buiten de pc zelf moet hem meesturen. Na vijf foute pogingen blokkeert de pc het toestel een minuut.

**Werkt het niet?**

- Telefoon en pc moeten op **hetzelfde wifi-netwerk** zitten. Gastwifi, mobiele data en sommige bedrijfsnetwerken ("client isolation") blokkeren verkeer tussen apparaten.
- Staat LAN-modus op de pc aan? Zonder LAN-modus luistert Sift alleen op `127.0.0.1`.
- Laat de Windows-firewall poort 8765 door? Controleer via *Windows-beveiliging → Firewall → Een app toestaan* of Python erin staat voor privénetwerken.
- Een VPN op telefoon of pc kan het lokale netwerk afschermen; zet die even uit.
- Het wifi-adres van de pc kan veranderen (nieuwe router, ander netwerk). Scan dan de QR-code opnieuw.

## 3. Een WhatsApp-opname naar Sift sturen

WhatsApp-spraakberichten en gedeelde audio ("WhatsApp Audio 2026-10-29 at 22.04.58.mp4") hoef je niet eerst op te slaan:

1. Houd in WhatsApp het spraakbericht of audiobestand ingedrukt en kies **Delen** (of **Doorsturen → Delen**).
2. Kies **Sift** in de lijst met apps. Sift opent op het tabblad **Opname sturen** met het bestand al ingevuld.
3. Pas eventueel de projectnaam aan en laat **Direct transcriberen** aan staan als de pipeline meteen mag starten met de standaardinstellingen (taal, modellen, sprekerscheiding zoals in Sift ingesteld). Zet hem uit als je eerst op de pc de instellingen wilt kiezen.
4. Tik op **Versturen**. Je ziet de voortgang; grote opnames (uren interview) kunnen even duren over wifi. Het scherm blijft aan tijdens het versturen.
5. Daarna: **Openen in Nakijken** opent het project meteen in de editor.

Hetzelfde werkt vanuit Bestanden, Google Drive, een dictafoon-app of een opname-app: overal waar je *Delen* kiest staat Sift tussen de apps voor audio en video. Via **Bestand kiezen** kun je ook zelf een bestand op de telefoon aanwijzen.

Toegestaan zijn alle formaten die Sift op de pc ook accepteert (mp3, m4a, wav, mp4, ogg/opus, flac, aac, …), tot 2 GB per bestand.

## 4. Nakijken op de telefoon

Het tabblad **Nakijken** laadt de Sift-editor van de pc. Alles werkt zoals op de pc: tik op een woord om het fragment te horen, kies een alternatief, typ over de tekst heen, wissel van spreker. Wijzigingen worden automatisch op de pc opgeslagen; de telefoon bewaart zelf niets.

- **Projecten** (linksboven) gaat terug naar de projectlijst; **Vernieuwen** laadt de pagina opnieuw.
- De Android-terugknop gaat eerst terug binnen de editor; pas op de projectlijst verlaat hij het tabblad.
- Het scherm blijft aan zolang dit tabblad open is, zodat de audio niet stopt tijdens het luisteren.
- **Exporteren** (Word, tekst, CSV, SRT, MAXQDA) werkt ook op de telefoon: het bestand komt in `Downloads/Sift` terecht (Android 10 en nieuwer) of opent het deelmenu (oudere Android).
- De pipeline-pagina en modelvergelijking zijn er ook, maar op een telefoonscherm is de editor het prettigst.

Koptelefoon aanbevolen: de luidspreker van een telefoon laat zachte sprekers slechter horen dan je pc-speakers.

## 5. Zelf bouwen

Vereist: [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0) met de MAUI-workload, Microsoft OpenJDK 17 en de Android SDK (platform 34). Via Visual Studio Installer: workload *.NET Multi-platform App UI development*; of handmatig:

```powershell
dotnet workload install maui-android
winget install Microsoft.OpenJDK.17
```

Bouwen:

```powershell
.\android\build.ps1              # Release -> android\dist\Sift-<versie>.apk
.\android\build.ps1 -Install     # en meteen installeren op het aangesloten toestel (adb)
```

De versie komt uit `sift/__init__.py` (`__version__`). Zonder keystore wordt de APK met de debug-sleutel gesigneerd; dat werkt prima om zelf te installeren. Voor een release-build kopieer je `android/Signing.props.example` naar `android/Signing.props` en vul je je eigen keystore in (`Signing.props` en `*.keystore` staan in `.gitignore` en komen nooit in de repository).

### Automatisch via GitHub Actions

De workflow `.github/workflows/android.yml` bouwt bij elke tag `v*` (en handmatig via *Run workflow*) een APK en hangt hem aan de release. Met deze repository-secrets wordt hij met je release-sleutel gesigneerd; zonder secrets wordt een debug-gesigneerde APK gebouwd en staat dat in de job summary:

| Secret | Inhoud |
|---|---|
| `ANDROID_KEYSTORE_B64` | de keystore als base64: `[Convert]::ToBase64String([IO.File]::ReadAllBytes("sift.keystore"))` |
| `ANDROID_KEYSTORE_PASSWORD` | wachtwoord van de keystore |
| `ANDROID_KEY_ALIAS` | alias van de sleutel (bijv. `sift`) |
| `ANDROID_KEY_PASSWORD` | wachtwoord van de sleutel |

Keystore maken (eenmalig, bewaar hem goed; zonder deze sleutel kun je later geen updates over de geïnstalleerde app heen zetten):

```powershell
keytool -genkeypair -v -keystore sift.keystore -alias sift -keyalg RSA -keysize 2048 -validity 10000
```

### Opbouw van de code

```
android/
  Sift.csproj                  .NET 8 MAUI, alleen Android (min API 26, target 34), package nl.sift.app
  AppShell.xaml                drie tabbladen
  Pages/ConnectPage            QR scannen (ZXing.Net.Maui), handmatig adres, verbinding testen
  Pages/UploadPage             bestand kiezen / gedeeld bestand, upload met voortgang naar POST /api/drop
  Pages/ReviewPage             WebView met de editor (JavaScript, DOM-opslag, http op het LAN, scherm aan)
  Services/SiftClient.cs       GET /api/projects en POST /api/drop met X-Sift-Code
  Services/ServerSettings.cs   adres + code in Preferences, parser voor de QR-URL
  Platforms/Android/           MainActivity (Delen-doel voor audio/* en video/*), WebView-instellingen, exportbrug
  build.ps1                    dotnet publish -> dist/Sift-<versie>.apk
```

De app praat met de server via drie dingen: `GET /api/projects` (verbindingstest), `POST /api/drop` (multipart: `file`, `name`, `start`) en de editorpagina `/?code=<code>#p=<project>&v=editor`. De code gaat mee als header `X-Sift-Code`; in de WebView zet `?code=` de cookie `sift_code`.
