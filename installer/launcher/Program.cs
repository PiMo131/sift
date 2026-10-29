// Sift-launcher (Windows).
//
// Mapindeling (zie installer/build.ps1):
//   Sift.exe                 dit programma
//   app\sift\...             het Python-pakket
//   app\bootstrap.py         eerste-keer-installatie van de Python-afhankelijkheden
//   app\requirements.txt     afhankelijkheden
//   app\VERSION              versie van Sift
//   python\python.exe        ingebedde Python 3.12
//   ffmpeg\ffmpeg.exe        ffmpeg + ffprobe
//   wheels\                  (alleen offline-bundel) voorgedownloade wheels
//   .bootstrap-ok            geschreven door bootstrap.py; inhoud = "<versie> <sha256 van requirements.txt>"
//
// Argumenten:  --repair        bootstrap opnieuw draaien (ook via de snelkoppeling "Sift herstellen")
//              --cpu | --gpu   torch-variant afdwingen (wordt aan bootstrap doorgegeven)
//              --port N        serverpoort (standaard 8765)
//              --no-browser
//              --no-wait       niet wachten tot de server stopt (voor tests/scripts)
//
// Exitcodes: 0 ok, 2 bootstrap mislukt, 3 server kon niet starten.

using System.Diagnostics;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace Sift;

static class Program
{
    const int DefaultPort = 8765;

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);
    const uint MB_OK = 0x0, MB_ICONERROR = 0x10, MB_ICONINFORMATION = 0x40;

    static void Alert(string text, bool error = true) =>
        MessageBoxW(IntPtr.Zero, text, "Sift", MB_OK | (error ? MB_ICONERROR : MB_ICONINFORMATION));

    static int Main(string[] args)
    {
        string root = AppContext.BaseDirectory.TrimEnd('\\', '/');
        string python = Path.Combine(root, "python", "python.exe");
        string appDir = Path.Combine(root, "app");
        string ffmpeg = Path.Combine(root, "ffmpeg", "ffmpeg.exe");
        string localData = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Sift");
        Directory.CreateDirectory(localData);

        bool repair = false, noBrowser = false, noWait = false;
        string? variant = null;
        int port = DefaultPort;
        for (int i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--repair": repair = true; break;
                case "--cpu": variant = "--cpu"; break;
                case "--gpu": variant = "--gpu"; break;
                case "--no-browser": noBrowser = true; break;
                case "--no-wait": noWait = true; break;
                case "--port" when i + 1 < args.Length && int.TryParse(args[i + 1], out var p): port = p; i++; break;
            }
        }

        if (!File.Exists(python) || !Directory.Exists(appDir))
        {
            Alert($"Sift is niet compleet geïnstalleerd (python of app-map ontbreekt in {root}).\nInstalleer Sift opnieuw.");
            return 3;
        }

        // 1. Eerste keer (of na een update of --repair): afhankelijkheden installeren in een console-venster.
        if (repair || !BootstrapIsCurrent(root))
        {
            var psi = new ProcessStartInfo(python)
            {
                UseShellExecute = false,
                CreateNoWindow = false,     // launcher heeft geen console: Windows opent er een nieuwe voor python.exe
                WorkingDirectory = appDir,
            };
            psi.ArgumentList.Add(Path.Combine(appDir, "bootstrap.py"));
            if (variant != null) psi.ArgumentList.Add(variant);
            psi.Environment["SIFT_LOG_DIR"] = localData;
            psi.Environment["PYTHONUTF8"] = "1";
            try
            {
                using var bp = Process.Start(psi)!;
                bp.WaitForExit();
                if (bp.ExitCode != 0)
                {
                    Alert($"De installatie van de onderdelen van Sift is mislukt (code {bp.ExitCode}).\n\n" +
                          $"Logboek: {Path.Combine(localData, "bootstrap.log")}\n\n" +
                          "Controleer de internetverbinding en start Sift opnieuw, of gebruik 'Sift herstellen' in het Startmenu.");
                    return 2;
                }
            }
            catch (Exception ex)
            {
                Alert("Kon de installatie niet starten: " + ex.Message);
                return 2;
            }
        }

        string url = $"http://127.0.0.1:{port}";

        // 2. Draait Sift al op deze poort? Dan alleen de browser openen.
        if (ServerIsUp(url))
        {
            if (!noBrowser) OpenBrowser(url);
            return 0;
        }

        // 3. Server starten. python.exe zonder venster (geen pythonw: subprocessen van de engines zouden anders
        //    elk een console-venster openen). Uitvoer gaat naar %LOCALAPPDATA%\Sift\sift.log.
        var spi = new ProcessStartInfo(python)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = appDir,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        spi.ArgumentList.Add("-m"); spi.ArgumentList.Add("sift");
        spi.ArgumentList.Add("--port"); spi.ArgumentList.Add(port.ToString());
        if (noBrowser) spi.ArgumentList.Add("--no-browser");
        spi.ArgumentList.Add("--lan"); // telefoon-toegang aan (beveiligd met 4-cijferige code; uit te zetten in de app)
        spi.Environment["SIFT_FFMPEG"] = ffmpeg;
        spi.Environment["SIFT_PROJECTS"] = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "Sift", "projects");
        spi.Environment["PYTHONUTF8"] = "1";
        spi.Environment["PYTHONUNBUFFERED"] = "1";

        string logPath = Path.Combine(localData, "sift.log");
        StreamWriter? log = null;
        try
        {
            try { if (new FileInfo(logPath).Length > 5_000_000) File.Delete(logPath); } catch { }
            log = new StreamWriter(logPath, append: true, Encoding.UTF8) { AutoFlush = true };
            log.WriteLine($"=== {DateTime.Now:yyyy-MM-dd HH:mm:ss} start {url} (Sift {ReadVersion(appDir)})");
        }
        catch { log = null; }

        Process server;
        try
        {
            server = Process.Start(spi)!;
        }
        catch (Exception ex)
        {
            Alert("Kon de Sift-server niet starten: " + ex.Message);
            return 3;
        }
        server.OutputDataReceived += (_, e) => { if (e.Data != null) log?.WriteLine(e.Data); };
        server.ErrorDataReceived += (_, e) => { if (e.Data != null) log?.WriteLine(e.Data); };
        server.BeginOutputReadLine();
        server.BeginErrorReadLine();

        // Wacht tot de server antwoordt (max 60 s; het laden van torch kan even duren).
        bool up = false;
        for (int i = 0; i < 120 && !server.HasExited; i++)
        {
            if (ServerIsUp(url)) { up = true; break; }
            Thread.Sleep(500);
        }
        if (!up && server.HasExited)
        {
            Alert($"De Sift-server is direct gestopt (code {server.ExitCode}).\n\nLogboek: {logPath}\n\n" +
                  "Probeer 'Sift herstellen' in het Startmenu.");
            log?.Dispose();
            return 3;
        }
        // Nog niet bereikbaar maar wel actief: toch doorgaan, de server opent zelf de browser.

        if (noWait)
        {
            log?.WriteLine("(launcher wacht niet op de server: --no-wait)");
            log?.Dispose();
            return 0;
        }
        server.WaitForExit();
        log?.WriteLine($"=== {DateTime.Now:yyyy-MM-dd HH:mm:ss} gestopt (code {server.ExitCode})");
        log?.Dispose();
        return 0;
    }

    static string ReadVersion(string appDir)
    {
        try { return File.ReadAllText(Path.Combine(appDir, "VERSION")).Trim(); } catch { return "?"; }
    }

    // Zelfde stempel als bootstrap.py schrijft: "<versie> <sha256 van requirements.txt>".
    static bool BootstrapIsCurrent(string root)
    {
        try
        {
            string marker = Path.Combine(root, ".bootstrap-ok");
            if (!File.Exists(marker)) return false;
            string appDir = Path.Combine(root, "app");
            string version = ReadVersion(appDir);
            string reqHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(appDir, "requirements.txt")))).ToLowerInvariant();
            return File.ReadAllText(marker).Trim() == $"{version} {reqHash}";
        }
        catch { return false; }
    }

    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromMilliseconds(1500) };

    static bool ServerIsUp(string url)
    {
        try
        {
            var body = Http.GetStringAsync(url + "/api/info").GetAwaiter().GetResult();
            return body.Contains("\"version\"");
        }
        catch { return false; }
    }

    static void OpenBrowser(string url)
    {
        try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); } catch { }
    }
}
