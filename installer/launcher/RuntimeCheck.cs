// Controle op de Microsoft Edge WebView2 Runtime (Evergreen). Staat standaard op Windows 11 en op Windows 10 met
// Edge; ontbreekt hij, dan bieden we aan de officiële bootstrapper van Microsoft te downloaden en te draaien, of
// Sift in de gewone browser te openen.

using System.Diagnostics;
using System.Net.Http;
using Microsoft.Web.WebView2.Core;

namespace Sift;

enum RuntimeDecision { Available, UseBrowser, Cancel }

static class RuntimeCheck
{
    public const string BootstrapperUrl = "https://go.microsoft.com/fwlink/p/?LinkId=2124703";

    public static string? Version()
    {
        try { return CoreWebView2Environment.GetAvailableBrowserVersionString(); }
        catch { return null; }
    }

    public static RuntimeDecision Ensure(Icon icon)
    {
        if (Version() != null) return RuntimeDecision.Available;
        while (true)
        {
            using var dlg = new RuntimeDialog(icon);
            var r = dlg.ShowDialog();
            if (r == DialogResult.Retry)
            {
                if (Version() != null) return RuntimeDecision.Available;
                continue;   // installatie afgebroken of mislukt: opnieuw kiezen
            }
            if (r == DialogResult.Ignore) return RuntimeDecision.UseBrowser;
            return RuntimeDecision.Cancel;
        }
    }

    sealed class RuntimeDialog : Form
    {
        readonly Label _status;
        readonly Button _install, _browser, _cancel;

        public RuntimeDialog(Icon icon)
        {
            Text = "Sift";
            Icon = icon;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(560, 250);
            Font = new Font("Segoe UI", 10f);
            AutoScaleMode = AutoScaleMode.Dpi;

            var text = new Label
            {
                Left = 20, Top = 18, Width = 520, Height = 120,
                Text = "Sift toont zijn venster met Microsoft Edge WebView2, maar die runtime ontbreekt op deze computer.\n\n" +
                       "Kies 'WebView2 installeren' om de officiële installer van Microsoft (ongeveer 2 MB) te downloaden en te " +
                       "starten; daarna start Sift verder. Of open Sift in je gewone browser.",
            };
            _status = new Label { Left = 20, Top = 145, Width = 520, Height = 40, ForeColor = Color.DimGray };
            _install = new Button { Text = "WebView2 installeren", Left = 20, Top = 195, Width = 190, Height = 34 };
            _browser = new Button { Text = "In de browser openen", Left = 220, Top = 195, Width = 190, Height = 34, DialogResult = DialogResult.Ignore };
            _cancel = new Button { Text = "Annuleren", Left = 420, Top = 195, Width = 120, Height = 34, DialogResult = DialogResult.Cancel };
            _install.Click += async (_, _) => await InstallAsync();
            Controls.AddRange(new Control[] { text, _status, _install, _browser, _cancel });
            AcceptButton = _install; CancelButton = _cancel;
        }

        async Task InstallAsync()
        {
            _install.Enabled = _browser.Enabled = false;
            try
            {
                string dir = Path.Combine(Path.GetTempPath(), "Sift-WebView2");
                Directory.CreateDirectory(dir);
                string exe = Path.Combine(dir, "MicrosoftEdgeWebView2Setup.exe");
                _status.Text = "Downloaden van Microsoft…";
                using (var http = new HttpClient { Timeout = TimeSpan.FromMinutes(5) })
                {
                    var bytes = await http.GetByteArrayAsync(BootstrapperUrl);
                    await File.WriteAllBytesAsync(exe, bytes);
                }
                _status.Text = "Installer gestart; volg de aanwijzingen van Microsoft…";
                using var p = Process.Start(new ProcessStartInfo(exe) { UseShellExecute = true });
                if (p != null) await p.WaitForExitAsync();
                _status.Text = Version() != null ? "WebView2 is geïnstalleerd." : "De installatie is niet voltooid (code " + (p?.ExitCode ?? -1) + ").";
                DialogResult = DialogResult.Retry;
            }
            catch (Exception ex)
            {
                _status.Text = "Downloaden of starten mislukt: " + ex.Message;
                _install.Enabled = _browser.Enabled = true;
            }
        }
    }
}
