// Opdrachtregelargumenten en mapindeling van de launcher.
//
// Argumenten:  --repair          bootstrap opnieuw draaien (ook via de snelkoppeling "Sift herstellen")
//              --cpu | --gpu     torch-variant afdwingen (wordt aan bootstrap doorgegeven)
//              --port N          serverpoort (standaard 8765)
//              --projects <map>  projectenmap (standaard Documenten\Sift\projects; dev-modus: <repo>\projects)
//              --browser         geen eigen venster: Sift in de standaardbrowser openen (zoals vroeger)
//              --no-browser      met --browser: de browser niet openen
//              --no-wait         met --browser: niet wachten tot de server stopt (voor tests/scripts)
//              --devtools        contextmenu en ontwikkelhulpmiddelen van WebView2 aanzetten
//
// Mapindeling (geïnstalleerd, zie installer/build.ps1):
//   Sift.exe                 dit programma
//   app\sift\...             het Python-pakket
//   app\bootstrap.py         eerste-keer-installatie van de Python-afhankelijkheden
//   python\python.exe        ingebedde Python 3.12
//   ffmpeg\ffmpeg.exe        ffmpeg + ffprobe
//   .bootstrap-ok            geschreven door bootstrap.py
// Dev-modus: de exe staat ergens in de repo (installer\launcher\bin\...); dan wordt omhoog gezocht naar een map met
// sift\__init__.py en .venv\Scripts\python.exe, en draait de server met die Python vanuit de repo (geen bootstrap,
// ffmpeg zoekt sift.config zelf).

namespace Sift;

sealed class Options
{
    public const int DefaultPort = 8765;

    public bool Repair, Browser, NoBrowser, NoWait, DevTools;
    public string? Variant;        // "--cpu" | "--gpu"
    public int Port = DefaultPort;
    public string? Projects;

    public static Options Parse(string[] args)
    {
        var o = new Options();
        for (int i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--repair": o.Repair = true; break;
                case "--cpu": o.Variant = "--cpu"; break;
                case "--gpu": o.Variant = "--gpu"; break;
                case "--browser": o.Browser = true; break;
                case "--no-browser": o.NoBrowser = true; break;
                case "--no-wait": o.NoWait = true; break;
                case "--devtools": o.DevTools = true; break;
                case "--port" when i + 1 < args.Length && int.TryParse(args[i + 1], out var p): o.Port = p; i++; break;
                case "--projects" when i + 1 < args.Length: o.Projects = Path.GetFullPath(args[i + 1]); i++; break;
            }
        }
        if (o.NoWait) o.Browser = true;   // zonder venster is er niets om op te wachten
        return o;
    }

    public string Url => $"http://127.0.0.1:{Port}";
}

sealed class Layout
{
    public bool Dev;
    public string Root = "";        // geïnstalleerd: programmamap; dev: hoofdmap van de repo
    public string Python = "";
    public string WorkDir = "";     // cwd van de server: {app}\app of de repo
    public string? Ffmpeg;          // alleen geïnstalleerd
    public string LocalData = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Sift");
    public string Projects = "";
    public string Exports = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "Sift", "exports");

    public string LogPath => Path.Combine(LocalData, "sift.log");
    public string BootstrapLog => Path.Combine(LocalData, "bootstrap.log");
    public string AppDir => Dev ? Root : Path.Combine(Root, "app");

    public static Layout? Detect(Options opt)
    {
        string exeDir = AppContext.BaseDirectory.TrimEnd('\\', '/');
        var l = new Layout();
        string python = Path.Combine(exeDir, "python", "python.exe");
        if (File.Exists(python) && Directory.Exists(Path.Combine(exeDir, "app")))
        {
            l.Root = exeDir;
            l.Python = python;
            l.WorkDir = Path.Combine(exeDir, "app");
            l.Ffmpeg = Path.Combine(exeDir, "ffmpeg", "ffmpeg.exe");
            l.Projects = opt.Projects ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "Sift", "projects");
        }
        else
        {
            string? repo = null;
            for (var d = new DirectoryInfo(exeDir); d != null; d = d.Parent)
            {
                if (File.Exists(Path.Combine(d.FullName, "sift", "__init__.py")) &&
                    File.Exists(Path.Combine(d.FullName, ".venv", "Scripts", "python.exe")))
                { repo = d.FullName; break; }
            }
            if (repo == null) return null;
            l.Dev = true;
            l.Root = repo;
            l.Python = Path.Combine(repo, ".venv", "Scripts", "python.exe");
            l.WorkDir = repo;
            l.Projects = opt.Projects ?? Path.Combine(repo, "projects");
        }
        Directory.CreateDirectory(l.LocalData);
        return l;
    }

    public string Version
    {
        get
        {
            try
            {
                if (!Dev) return File.ReadAllText(Path.Combine(AppDir, "VERSION")).Trim();
                foreach (var line in File.ReadLines(Path.Combine(Root, "sift", "__init__.py")))
                {
                    var m = System.Text.RegularExpressions.Regex.Match(line, "__version__\\s*=\\s*\"([^\"]+)\"");
                    if (m.Success) return m.Groups[1].Value + " (dev)";
                }
            }
            catch { }
            return "?";
        }
    }
}
