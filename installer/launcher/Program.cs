// Sift-launcher (Windows): bureaubladprogramma dat de Python-server start en de interface in een eigen venster toont.
// Argumenten en mapindeling: zie Options.cs. Exitcodes: 0 ok, 2 bootstrap mislukt, 3 server/omgeving kon niet starten.

namespace Sift;

static class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        ApplicationConfiguration.Initialize();

        var opt = Options.Parse(args);
        var layout = Layout.Detect(opt);
        if (layout == null)
        {
            MessageBox.Show($"Sift is niet compleet geïnstalleerd (python of app-map ontbreekt in {AppContext.BaseDirectory}).\n" +
                            "Installeer Sift opnieuw. Ontwikkelaars: start de exe vanuit de repo (met .venv) of via start-app.ps1.",
                            "Sift", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 3;
        }

        // Eén Sift per poort: draait er al een, dan diens venster naar voren halen.
        using var single = new SingleInstance(opt.Port);
        if (!single.IsFirst)
        {
            single.SignalShow();
            return 0;
        }

        Icon icon = LoadIcon();
        if (!opt.Browser)
        {
            switch (RuntimeCheck.Ensure(icon))
            {
                case RuntimeDecision.UseBrowser: opt.Browser = true; break;
                case RuntimeDecision.Cancel: return 0;
            }
        }

        using var host = new ServerHost(opt, layout);
        using var form = new MainForm(opt, layout, host, single, icon);
        Application.Run(form);
        return form.ExitCode;
    }

    static Icon LoadIcon()
    {
        try
        {
            using var s = typeof(Program).Assembly.GetManifestResourceStream("Sift.sift.ico");
            if (s != null) return new Icon(s);
        }
        catch { }
        try { return Icon.ExtractAssociatedIcon(Application.ExecutablePath) ?? SystemIcons.Application; } catch { return SystemIcons.Application; }
    }
}
