; Inno Setup 6-script voor Sift (Windows).
; Bouwen: installer\build.ps1 (zet eerst de map .build\stage klaar en roept dan ISCC aan met
;   /DAppVersion=<versie> /DStageDir=<pad naar stage> /DOutputDir=<pad naar dist>).
;
; De installer is "licht": Python 3.12 (embeddable), ffmpeg, het sift-pakket en de launcher. De zware
; Python-afhankelijkheden (torch, faster-whisper, ...) installeert bootstrap.py bij de eerste start, online of
; uit een map wheels\ die naast de installer staat (offline-bundel; die map wordt dan meegekopieerd).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef StageDir
  #define StageDir ".build\stage"
#endif
#ifndef OutputDir
  #define OutputDir "dist"
#endif
#define AppName "Sift"
#define AppPublisher "Sift"
#define AppURL "https://github.com/PiMo131/sift"
#define AppExe "Sift.exe"

[Setup]
AppId={{6B1E0C2D-5A77-4C0B-9F3E-5D1F7A2C9E41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} installer
; Altijd per gebruiker (%LOCALAPPDATA%\Programs\Sift): bootstrap.py en pip moeten in de programmamap kunnen
; schrijven, en de GPU-onderdelen zijn gigabytes groot. Daarom geen keuze voor "alle gebruikers".
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=Sift-Setup-{#AppVersion}
SetupIconFile=sift.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
; ruimte die bootstrap.py later nog nodig heeft (CPU ~1,5 GB, GPU ~5 GB); alleen voor de schijfruimtecontrole
ExtraDiskSpaceRequired=2500000000
ShowLanguageDialog=auto

[Languages]
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
dutch.Repair=Sift herstellen
english.Repair=Repair Sift
dutch.RepairComment=Installeert de Python-onderdelen van Sift opnieuw
english.RepairComment=Reinstalls the Python components of Sift
dutch.FirstRunNote=Bij de eerste start opent Sift een venster dat de resterende onderdelen installeert (torch, faster-whisper, ...; ongeveer 1 GB zonder en 3,5 GB met NVIDIA-GPU). Daarna worden bij de eerste transcriptie de Whisper-modellen gedownload (large-v3 is 3 GB). Projecten staan in Documenten\Sift\projects.
english.FirstRunNote=On first start Sift opens a window that installs the remaining components (torch, faster-whisper, ...; about 1 GB without and 3.5 GB with an NVIDIA GPU). After that, the Whisper models are downloaded on the first transcription (large-v3 is 3 GB). Projects are stored in Documents\Sift\projects.
dutch.FirewallNote=Sift luistert op poort 8765, ook op je lokale netwerk (voor de telefoon-koppeling, pas na het inschakelen van "LAN" in de app plus een code). Windows kan bij de eerste start vragen om toegang door de firewall; kies "Particuliere netwerken".
english.FirewallNote=Sift listens on port 8765, also on your local network (for the phone link, only after enabling "LAN" in the app plus a code). Windows may ask to allow it through the firewall on first start; choose "Private networks".
dutch.OfflineNote=Er is een map wheels\ gevonden naast de installer: de onderdelen worden daaruit geïnstalleerd, zonder internet.
english.OfflineNote=A wheels\ folder was found next to the installer: the components will be installed from it, without internet access.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Offline-bundel: wheels\ naast de installer wordt meegekopieerd (bootstrap.py gebruikt dan --no-index).
Source: "{src}\wheels\*"; DestDir: "{app}\wheels"; Flags: external recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist; Check: HasOfflineWheels

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Sift"
Name: "{group}\{cm:Repair}"; Filename: "{app}\{#AppExe}"; Parameters: "--repair"; Comment: "{cm:RepairComment}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; alles wat bootstrap.py en pip na de installatie hebben toegevoegd
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\wheels"
Type: files; Name: "{app}\.bootstrap-ok"
Type: filesandordirs; Name: "{localappdata}\Sift"
; Projecten in Documenten\Sift en de modellen in %USERPROFILE%\.cache\huggingface blijven staan.

[Code]
function HasOfflineWheels: Boolean;
begin
  Result := DirExists(ExpandConstant('{src}\wheels'));
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Note: String;
begin
  if CurPageID = wpFinished then
  begin
    Note := CustomMessage('FirstRunNote');
    if HasOfflineWheels then
      Note := Note + #13#10#13#10 + CustomMessage('OfflineNote');
    Note := Note + #13#10#13#10 + CustomMessage('FirewallNote');
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 + Note;
  end;
end;
