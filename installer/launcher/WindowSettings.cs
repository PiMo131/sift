// Onthouden venstergrootte/-positie en voorkeuren, in %LOCALAPPDATA%\Sift\window.json.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Sift;

sealed class WindowSettings
{
    public int X { get; set; } = -1;
    public int Y { get; set; } = -1;
    public int Width { get; set; }
    public int Height { get; set; }
    public bool Maximized { get; set; }
    public bool ExitOnClose { get; set; }       // "Afsluiten bij sluiten venster" (anders: naar het systeemvak)
    public bool TrayHintShown { get; set; }     // de melding "Sift draait verder in het systeemvak" één keer tonen
    public double Zoom { get; set; } = 1.0;

    [JsonIgnore] public string Path { get; private set; } = "";

    static readonly JsonSerializerOptions JsonOpts = new() { WriteIndented = true };

    public static WindowSettings Load(string localData)
    {
        string path = System.IO.Path.Combine(localData, "window.json");
        WindowSettings s;
        try { s = JsonSerializer.Deserialize<WindowSettings>(File.ReadAllText(path), JsonOpts) ?? new WindowSettings(); }
        catch { s = new WindowSettings(); }
        s.Path = path;
        return s;
    }

    public void Save()
    {
        try { File.WriteAllText(Path, JsonSerializer.Serialize(this, JsonOpts)); } catch { }
    }

    /// <summary>Past de onthouden afmetingen toe als ze op een aangesloten scherm passen; anders een nette standaard.</summary>
    public void ApplyTo(Form f, Size minSize)
    {
        var area = Screen.PrimaryScreen?.WorkingArea ?? new Rectangle(0, 0, 1600, 900);
        var bounds = new Rectangle(X, Y, Width, Height);
        bool ok = Width >= minSize.Width && Height >= minSize.Height && X >= -8 && Y >= -8 &&
                  Screen.AllScreens.Any(s => s.WorkingArea.IntersectsWith(bounds) && s.WorkingArea.Contains(new Point(X + 40, Y + 40)));
        if (!ok)
        {
            int w = Math.Min(area.Width - 40, 1400), h = Math.Min(area.Height - 40, 900);
            w = Math.Max(w, Math.Min(minSize.Width, area.Width)); h = Math.Max(h, Math.Min(minSize.Height, area.Height));
            bounds = new Rectangle(area.Left + (area.Width - w) / 2, area.Top + (area.Height - h) / 2, w, h);
        }
        f.StartPosition = FormStartPosition.Manual;
        f.Bounds = bounds;
        if (Maximized) f.WindowState = FormWindowState.Maximized;
    }

    public void CaptureFrom(Form f)
    {
        Maximized = f.WindowState == FormWindowState.Maximized;
        var b = f.WindowState == FormWindowState.Normal ? f.Bounds : f.RestoreBounds;
        X = b.X; Y = b.Y; Width = b.Width; Height = b.Height;
    }
}
