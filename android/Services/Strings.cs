namespace Sift.Services;

/// <summary>UI-teksten (Nederlands).</summary>
public static class Strings
{
    public const string AppName = "Sift";
    public const string Tagline = "Opnames naar je pc sturen en transcripten nakijken";

    // tabs
    public const string TabConnect = "Verbinden";
    public const string TabUpload = "Opname sturen";
    public const string TabReview = "Nakijken";

    // connect
    public const string ConnectTitle = "Verbind met je pc";
    public const string ConnectIntro = "Zet in Sift op de pc de LAN-modus aan. Op het scherm verschijnen een QR-code en een code van 4 cijfers.";
    public const string ScanQr = "QR-code scannen";
    public const string OrManual = "Of vul het adres zelf in";
    public const string AddressLabel = "Adres van de pc";
    public const string AddressPlaceholder = "bijv. 192.168.1.23:8765";
    public const string CodeLabel = "Code";
    public const string CodePlaceholder = "4 cijfers";
    public const string TestConnection = "Verbinding testen";
    public const string Testing = "Bezig met verbinden…";
    public const string Connected = "Verbonden met {0}";
    public const string ConnectedProjects = "Verbonden met {0} ({1} projecten)";
    public const string NotConnected = "Nog niet verbonden";
    public const string SameWifiHint = "Telefoon en pc moeten op hetzelfde wifi-netwerk zitten. Werkt het niet? Controleer of LAN-modus op de pc aan staat, of de Windows-firewall poort 8765 doorlaat, en of je niet op gastwifi of mobiele data zit.";
    public const string ScanHint = "Richt de camera op de QR-code op het scherm van je pc.";
    public const string ScanTitle = "QR-code scannen";
    public const string CameraDenied = "Geen toegang tot de camera. Geef Sift cameratoegang in de Android-instellingen, of vul het adres handmatig in.";
    public const string QrNotSift = "Deze QR-code is geen Sift-adres.";
    public const string AddressInvalid = "Vul een geldig adres in, bijvoorbeeld 192.168.1.23:8765.";
    public const string CodeInvalid = "De code bestaat uit 4 cijfers.";
    public const string Forget = "Vergeten";

    // upload
    public const string UploadTitle = "Opname sturen";
    public const string UploadIntro = "Kies een opname op je telefoon, of deel er een vanuit WhatsApp of Bestanden naar Sift.";
    public const string PickFile = "Bestand kiezen";
    public const string NoFile = "Nog geen bestand gekozen";
    public const string ProjectName = "Projectnaam (optioneel)";
    public const string AutoStart = "Direct transcriberen";
    public const string AutoStartHint = "Start de pipeline op de pc meteen met de standaardinstellingen.";
    public const string Send = "Versturen";
    public const string Cancel = "Annuleren";
    public const string Sending = "Versturen… {0} van {1}";
    public const string Sent = "Verstuurd: {0}";
    public const string SentStarted = "Verstuurd en gestart: {0}";
    public const string OpenProject = "Openen in Nakijken";
    public const string ConnectFirst = "Verbind eerst met je pc via het tabblad Verbinden.";
    public const string GoConnect = "Naar Verbinden";
    public const string SharedReceived = "Opname ontvangen van een andere app.";
    public const string Cancelled = "Geannuleerd.";

    // review
    public const string ReviewTitle = "Nakijken";
    public const string Reload = "Vernieuwen";
    public const string Home = "Projecten";
    public const string Saved = "Opgeslagen in Downloads/Sift: {0}";

    // errors
    public const string ErrUnreachable = "De pc is niet bereikbaar. Zit je telefoon op hetzelfde wifi-netwerk als de pc en staat Sift met LAN-modus aan?";
    public const string ErrTimeout = "Geen antwoord van de pc. Zit je telefoon op hetzelfde wifi-netwerk en staat Sift met LAN-modus aan?";
    public const string ErrCode = "De code klopt niet. Kijk op het scherm van de pc.";
    public const string ErrBlocked = "Te veel foute pogingen; wacht een minuut en probeer het opnieuw.";
    public const string ErrNotSift = "Op dit adres draait geen Sift-server.";
    public const string ErrTooLarge = "Het bestand is te groot (maximaal 2 GB).";
    public const string ErrHttp = "De server gaf een fout (HTTP {0}).";
    public const string ErrFileMissing = "Het bestand is niet meer beschikbaar. Kies het opnieuw.";
    public const string ErrShare = "Kon de gedeelde opname niet lezen.";
}
