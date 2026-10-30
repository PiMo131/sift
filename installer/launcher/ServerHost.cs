// Start en stopt de Python-server (en de bootstrap bij de eerste keer). Geen UI; meldt fasen via het Phase-event.
// Uitvoer van de server gaat naar %LOCALAPPDATA%\Sift\sift.log.

using System.Diagnostics;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;

namespace Sift;

enum StartOutcome { Running, Attached, BootstrapFailed, StartFailed, Died }

sealed class ServerHost : IDisposable
{
    readonly Options _opt;
    readonly Layout _l;
    Process? _proc;
    JobObject? _job;
    StreamWriter? _log;
    readonly object _logLock = new();

    public ServerHost(Options opt, Layout layout)
    {
        _opt = opt; _l = layout;
        try
        {
            try { if (new FileInfo(_l.LogPath).Length > 5_000_000) File.Delete(_l.LogPath); } catch { }
            _log = new StreamWriter(_l.LogPath, append: true, Encoding.UTF8) { AutoFlush = true };
        }
        catch { _log = null; }
    }

    /// <summary>De server is door deze launcher gestart (en wordt bij afsluiten gestopt).</summary>
    public bool Owned => _proc != null && !_opt.NoWait;

    /// <summary>(fase, toelichting) — wordt op een achtergrondthread aangeroepen.</summary>
    public event Action<string, string>? Phase;

    public void Log(string line)
    {
        lock (_logLock) { try { _log?.WriteLine(line); } catch { } }
    }

    void Report(string phase, string detail = "") => Phase?.Invoke(phase, detail);

    public async Task<(StartOutcome outcome, string message)> StartAsync(CancellationToken ct)
    {
        string url = _opt.Url;
        Log($"=== {DateTime.Now:yyyy-MM-dd HH:mm:ss} launcher start {url} (Sift {_l.Version}{(_l.Dev ? ", dev-modus: " + _l.Root : "")})");

        // 1. Eerste keer (of na een update of --repair): afhankelijkheden installeren in een console-venster.
        if (!_l.Dev && (_opt.Repair || !BootstrapIsCurrent()))
        {
            Report("Onderdelen installeren", "De voortgang staat in het aparte venster. Dit gebeurt één keer en kan enkele minuten duren.");
            int rc = await Task.Run(RunBootstrap, ct);
            if (rc != 0)
            {
                return (StartOutcome.BootstrapFailed,
                    $"De installatie van de onderdelen van Sift is mislukt (code {rc}).\n\nLogboek: {_l.BootstrapLog}\n\n" +
                    "Controleer de internetverbinding en start Sift opnieuw, of gebruik 'Sift herstellen' in het Startmenu.");
            }
        }

        // 2. Draait Sift al op deze poort (bijvoorbeeld gestart met start.ps1)? Dan daar op aansluiten.
        if (await IsUpAsync(url))
        {
            Log("server draait al op deze poort; launcher sluit erop aan (stopt hem niet bij afsluiten)");
            return (StartOutcome.Attached, "");
        }

        // 3. Server starten: python.exe zonder venster (geen pythonw: subprocessen van de engines zouden anders elk een
        //    console-venster openen).
        Report("Server starten", "");
        var psi = new ProcessStartInfo(_l.Python)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = _l.WorkDir,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        psi.ArgumentList.Add("-m"); psi.ArgumentList.Add("sift");
        psi.ArgumentList.Add("--port"); psi.ArgumentList.Add(_opt.Port.ToString());
        psi.ArgumentList.Add("--no-browser");   // de launcher toont de interface zelf (of opent de browser in --browser-modus)
        psi.ArgumentList.Add("--lan");          // telefoon-toegang aan (beveiligd met 4-cijferige code; uit te zetten in de app)
        if (_l.Ffmpeg != null) psi.Environment["SIFT_FFMPEG"] = _l.Ffmpeg;   // dev-modus: sift.config.find_ffmpeg zoekt zelf
        psi.Environment["SIFT_PROJECTS"] = _l.Projects;
        psi.Environment["PYTHONUTF8"] = "1";
        psi.Environment["PYTHONUNBUFFERED"] = "1";

        try
        {
            if (!_opt.NoWait)
            {
                try { _job = new JobObject(); } catch (Exception ex) { Log("geen job object: " + ex.Message); _job = null; }
            }
            _proc = Process.Start(psi)!;
            if (_job != null && !_job.Assign(_proc)) { Log("AssignProcessToJobObject mislukt; val terug op taskkill"); _job.Dispose(); _job = null; }
        }
        catch (Exception ex)
        {
            return (StartOutcome.StartFailed, "Kon de Sift-server niet starten: " + ex.Message);
        }
        Log($"server gestart (pid {_proc.Id}, projecten {_l.Projects})");
        _proc.OutputDataReceived += (_, e) => { if (e.Data != null) Log(e.Data); };
        _proc.ErrorDataReceived += (_, e) => { if (e.Data != null) Log(e.Data); };
        _proc.BeginOutputReadLine();
        _proc.BeginErrorReadLine();

        // 4. Wachten tot de server antwoordt. Het importeren van torch en de modellen kan even duren; zolang het
        //    proces leeft blijven we wachten (de gebruiker kan via het systeemvak afsluiten).
        var sw = Stopwatch.StartNew();
        while (!ct.IsCancellationRequested)
        {
            if (_proc.HasExited)
            {
                return (StartOutcome.Died,
                    $"De Sift-server is direct gestopt (code {_proc.ExitCode}).\n\nLogboek: {_l.LogPath}\n\n" +
                    (_l.Dev ? "Controleer de virtuele omgeving (.venv) en requirements.txt." : "Probeer 'Sift herstellen' in het Startmenu."));
            }
            if (await IsUpAsync(url)) break;
            int s = (int)sw.Elapsed.TotalSeconds;
            if (s >= 90) Report("Server starten", $"Dit duurt langer dan verwacht ({s} s). Zie {_l.LogPath}.");
            else if (s >= 8) Report("Modellen en onderdelen laden", $"{s} s · de eerste keer kan dit even duren");
            else Report("Server starten", $"{s} s");
            await Task.Delay(500, ct);
        }
        ct.ThrowIfCancellationRequested();
        Log($"server bereikbaar na {sw.Elapsed.TotalSeconds:0.0} s");
        return (StartOutcome.Running, "");
    }

    int RunBootstrap()
    {
        var psi = new ProcessStartInfo(_l.Python)
        {
            UseShellExecute = false,
            CreateNoWindow = false,     // launcher heeft geen console: Windows opent er een voor python.exe
            WorkingDirectory = _l.AppDir,
        };
        psi.ArgumentList.Add(Path.Combine(_l.AppDir, "bootstrap.py"));
        if (_opt.Variant != null) psi.ArgumentList.Add(_opt.Variant);
        psi.Environment["SIFT_LOG_DIR"] = _l.LocalData;
        psi.Environment["PYTHONUTF8"] = "1";
        try
        {
            using var bp = Process.Start(psi)!;
            bp.WaitForExit();
            Log($"bootstrap klaar (code {bp.ExitCode})");
            return bp.ExitCode;
        }
        catch (Exception ex)
        {
            Log("bootstrap kon niet starten: " + ex.Message);
            return 99;
        }
    }

    // Zelfde stempel als bootstrap.py schrijft: "<versie> <sha256 van requirements.txt>".
    bool BootstrapIsCurrent()
    {
        try
        {
            string marker = Path.Combine(_l.Root, ".bootstrap-ok");
            if (!File.Exists(marker)) return false;
            string reqHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(_l.AppDir, "requirements.txt")))).ToLowerInvariant();
            return File.ReadAllText(marker).Trim() == $"{_l.Version} {reqHash}";
        }
        catch { return false; }
    }

    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromMilliseconds(1500) };

    public static async Task<bool> IsUpAsync(string url)
    {
        try
        {
            var body = await Http.GetStringAsync(url + "/api/info");
            return body.Contains("\"version\"");
        }
        catch { return false; }
    }

    /// <summary>Stopt de server met alle subprocessen (alleen als deze launcher hem gestart heeft) en wacht kort.</summary>
    public void Stop()
    {
        var p = _proc;
        if (p == null) return;
        _proc = null;
        if (_opt.NoWait) { Log("(launcher wacht niet op de server: --no-wait; server blijft draaien)"); return; }
        try
        {
            if (!p.HasExited)
            {
                Log($"server stoppen (pid {p.Id})");
                if (_job != null) _job.Terminate();
                else
                {
                    try
                    {
                        using var tk = Process.Start(new ProcessStartInfo("taskkill", $"/T /F /PID {p.Id}") { UseShellExecute = false, CreateNoWindow = true });
                        tk?.WaitForExit(5000);
                    }
                    catch { }
                    if (!p.HasExited) p.Kill(entireProcessTree: true);
                }
                p.WaitForExit(5000);
            }
            Log($"=== {DateTime.Now:yyyy-MM-dd HH:mm:ss} gestopt (code {(p.HasExited ? p.ExitCode.ToString() : "?")})");
        }
        catch (Exception ex) { Log("stoppen: " + ex.Message); }
        finally { _job?.Dispose(); _job = null; }
    }

    public void Dispose()
    {
        Stop();
        lock (_logLock) { _log?.Dispose(); _log = null; }
    }
}
