// Het Sift-venster: opstartscherm terwijl de server start, daarna de interface in WebView2; systeemvakicoon;
// sneltoetsen (F5, F11, Ctrl+/−/0); externe links naar de standaardbrowser; downloads naar Documenten\Sift\exports.

using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Sift;

sealed class MainForm : Form
{
    static readonly Color Bg = ColorTranslator.FromHtml("#f6f5f1");
    static readonly Color TextColor = ColorTranslator.FromHtml("#1f2328");
    static readonly Color Muted = ColorTranslator.FromHtml("#6b7280");
    static readonly Color Accent = ColorTranslator.FromHtml("#2f855a");

    readonly Options _opt;
    readonly Layout _l;
    readonly ServerHost _host;
    readonly WindowSettings _settings;
    readonly Icon _icon;
    readonly CancellationTokenSource _cts = new();

    // opstartscherm
    readonly Panel _splash = new();
    readonly Panel _card = new();
    readonly PictureBox _logo = new();
    readonly Label _title = new(), _phase = new(), _detail = new();
    readonly ProgressBar _progress = new();
    readonly LinkLabel _logLink = new();
    readonly Button _quitBtn = new(), _browserBtn = new();

    WebView2? _wv;
    bool _wvShown;

    // systeemvak
    readonly NotifyIcon _tray = new();
    readonly ToolStripMenuItem _exitOnCloseItem = new("Afsluiten bij sluiten venster") { CheckOnClick = true };

    bool _allowVisible, _exiting, _fullscreen;
    Rectangle _preFsBounds;
    FormWindowState _preFsState;

    public int ExitCode { get; private set; }

    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hWnd);

    public MainForm(Options opt, Layout layout, ServerHost host, SingleInstance single, Icon icon)
    {
        _opt = opt; _l = layout; _host = host; _icon = icon;
        _settings = WindowSettings.Load(_l.LocalData);
        _allowVisible = !opt.Browser;

        Text = "Sift";
        Icon = icon;
        AutoScaleMode = AutoScaleMode.None;
        BackColor = Bg;
        float k = DeviceDpi / 96f;
        MinimumSize = new Size((int)(1100 * k), (int)(700 * k));
        _settings.ApplyTo(this, MinimumSize);
        KeyPreview = true;

        BuildSplash(k);
        BuildTray();
        single.Listen(() => { try { BeginInvoke(ShowFromTray); } catch { } });

        _host.Phase += (p, d) => { try { BeginInvoke(() => SetPhase(p, d)); } catch { } };
        ResizeEnd += (_, _) => RememberBounds();
        Move += (_, _) => RememberBounds();

        // handle aanmaken en het opstarten op de berichtenlus zetten (ook in --browser-modus, waarin het venster
        // nooit getoond wordt en Load dus niet komt)
        _ = Handle;
        BeginInvoke(async () => await StartupAsync());
    }

    protected override void SetVisibleCore(bool value) => base.SetVisibleCore(_allowVisible && value);

    // ------------------------------------------------------------------ opstartscherm
    void BuildSplash(float k)
    {
        _splash.Dock = DockStyle.Fill;
        _splash.BackColor = Bg;
        _card.Size = new Size((int)(560 * k), (int)(360 * k));
        _card.BackColor = Bg;

        try
        {
            using var s = typeof(MainForm).Assembly.GetManifestResourceStream("Sift.sift.ico");
            if (s != null) using (var big = new Icon(s, 128, 128)) _logo.Image = big.ToBitmap();
        }
        catch { }
        if (_logo.Image == null) _logo.Image = _icon.ToBitmap();
        _logo.SizeMode = PictureBoxSizeMode.Zoom;
        _logo.Size = new Size((int)(96 * k), (int)(96 * k));
        _logo.Location = new Point((_card.Width - _logo.Width) / 2, 0);

        _title.Text = "Sift wordt gestart…";
        _title.Font = new Font("Segoe UI Semibold", 18f);
        _title.ForeColor = TextColor;
        _title.TextAlign = ContentAlignment.MiddleCenter;
        _title.SetBounds(0, (int)(112 * k), _card.Width, (int)(40 * k));

        _phase.Font = new Font("Segoe UI", 11f);
        _phase.ForeColor = TextColor;
        _phase.TextAlign = ContentAlignment.MiddleCenter;
        _phase.SetBounds(0, (int)(158 * k), _card.Width, (int)(28 * k));

        _detail.Font = new Font("Segoe UI", 9.5f);
        _detail.ForeColor = Muted;
        _detail.TextAlign = ContentAlignment.TopCenter;
        _detail.SetBounds((int)(20 * k), (int)(190 * k), _card.Width - (int)(40 * k), (int)(96 * k));

        _progress.Style = ProgressBarStyle.Marquee;
        _progress.MarqueeAnimationSpeed = 30;
        _progress.SetBounds((int)(130 * k), (int)(294 * k), _card.Width - (int)(260 * k), (int)(6 * k));

        _logLink.Text = "Logboek openen";
        _logLink.Font = new Font("Segoe UI", 9.5f);
        _logLink.LinkColor = Accent;
        _logLink.TextAlign = ContentAlignment.MiddleCenter;
        _logLink.SetBounds(0, (int)(292 * k), _card.Width, (int)(24 * k));
        _logLink.Visible = false;
        _logLink.LinkClicked += (_, _) => OpenLog();

        _quitBtn.Text = "Afsluiten";
        _quitBtn.Font = new Font("Segoe UI", 10f);
        _quitBtn.SetBounds((_card.Width - (int)(130 * k)) / 2, (int)(322 * k), (int)(130 * k), (int)(34 * k));
        _quitBtn.Visible = false;
        _quitBtn.Click += (_, _) => Quit();

        _browserBtn.Text = "In de browser openen";
        _browserBtn.Font = new Font("Segoe UI", 10f);
        _browserBtn.SetBounds((_card.Width - (int)(130 * k)) / 2 - (int)(200 * k), (int)(322 * k), (int)(190 * k), (int)(34 * k));
        _browserBtn.Visible = false;
        _browserBtn.Click += (_, _) => OpenBrowser();

        _card.Controls.AddRange(new Control[] { _logo, _title, _phase, _detail, _progress, _logLink, _quitBtn, _browserBtn });
        _splash.Controls.Add(_card);
        _splash.Resize += (_, _) => CenterCard();
        Controls.Add(_splash);
        CenterCard();
        SetPhase("Voorbereiden", "");
    }

    void CenterCard() => _card.Location = new Point(Math.Max(0, (_splash.Width - _card.Width) / 2), Math.Max(0, (_splash.Height - _card.Height) / 2 - _card.Height / 8));

    void SetPhase(string phase, string detail)
    {
        _phase.Text = phase + "…";
        _detail.Text = detail;
    }

    void ShowError(string message, bool offerBrowser)
    {
        _title.Text = "Sift kon niet starten";
        _phase.Text = "";
        _detail.Text = message;
        _detail.ForeColor = TextColor;
        _progress.Visible = false;
        _logLink.Visible = true;
        _quitBtn.Visible = true;
        _browserBtn.Visible = offerBrowser;
        if (offerBrowser) _quitBtn.Left = (_card.Width - _quitBtn.Width) / 2 + (int)(100 * (DeviceDpi / 96f));
        _splash.Visible = true;
        _splash.BringToFront();
        if (!Visible) ShowFromTray();
    }

    // ------------------------------------------------------------------ systeemvak
    void BuildTray()
    {
        var menu = new ContextMenuStrip();
        var show = new ToolStripMenuItem(_opt.Browser ? "Sift openen in browser" : "Sift tonen") { Font = new Font(menu.Font, FontStyle.Bold) };
        show.Click += (_, _) => ShowFromTray();
        var browser = new ToolStripMenuItem("Openen in browser");
        browser.Click += (_, _) => OpenBrowser();
        var projects = new ToolStripMenuItem("Projectenmap openen");
        projects.Click += (_, _) => OpenFolder(_l.Projects);
        var log = new ToolStripMenuItem("Logboek openen");
        log.Click += (_, _) => OpenLog();
        _exitOnCloseItem.Checked = _settings.ExitOnClose;
        _exitOnCloseItem.CheckedChanged += (_, _) => { _settings.ExitOnClose = _exitOnCloseItem.Checked; _settings.Save(); };
        var quit = new ToolStripMenuItem("Afsluiten");
        quit.Click += (_, _) => Quit();
        menu.Items.Add(show);
        if (!_opt.Browser) menu.Items.Add(browser);
        menu.Items.Add(projects);
        menu.Items.Add(log);
        menu.Items.Add(new ToolStripSeparator());
        if (!_opt.Browser) { menu.Items.Add(_exitOnCloseItem); menu.Items.Add(new ToolStripSeparator()); }
        menu.Items.Add(quit);

        _tray.Icon = _icon;
        _tray.Text = _opt.Port == Options.DefaultPort ? "Sift" : $"Sift (poort {_opt.Port})";
        _tray.ContextMenuStrip = menu;
        _tray.DoubleClick += (_, _) => ShowFromTray();
        _tray.Visible = true;
    }

    public void ShowFromTray()
    {
        if (_opt.Browser) { OpenBrowser(); return; }
        _allowVisible = true;
        if (!Visible) Show();
        if (WindowState == FormWindowState.Minimized) WindowState = _settings.Maximized ? FormWindowState.Maximized : FormWindowState.Normal;
        // Windows weigert SetForegroundWindow soms vanuit een proces op de achtergrond; TopMost aan/uit helpt daarbij.
        TopMost = true; TopMost = false;
        SetForegroundWindow(Handle);
        Activate();
        _wv?.Focus();
    }

    void HideToTray()
    {
        RememberBounds();
        if (_fullscreen) SetFullscreen(false);
        Hide();
        if (!_settings.TrayHintShown)
        {
            _settings.TrayHintShown = true;
            _settings.Save();
            _tray.ShowBalloonTip(5000, "Sift draait verder", "Sift staat in het systeemvak (rechtsonder). Dubbelklik op het icoon om het venster te tonen; 'Afsluiten' stopt Sift.", ToolTipIcon.Info);
        }
    }

    void Quit()
    {
        _exiting = true;
        Close();
    }

    void RememberBounds()
    {
        if (!Visible || _fullscreen || WindowState == FormWindowState.Minimized) return;
        _settings.CaptureFrom(this);
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (!_exiting && e.CloseReason == CloseReason.UserClosing && !_settings.ExitOnClose && !_opt.Browser)
        {
            e.Cancel = true;
            HideToTray();
            return;
        }
        _exiting = true;
        _cts.Cancel();
        RememberBounds();
        _settings.Save();
        _tray.Visible = false;
        _host.Stop();
        base.OnFormClosing(e);
    }

    // ------------------------------------------------------------------ opstarten
    async Task StartupAsync()
    {
        try
        {
            Task wvInit = _opt.Browser ? Task.CompletedTask : InitWebViewAsync();
            var (outcome, message) = await _host.StartAsync(_cts.Token);
            if (outcome is StartOutcome.BootstrapFailed or StartOutcome.StartFailed or StartOutcome.Died)
            {
                ExitCode = outcome == StartOutcome.BootstrapFailed ? 2 : 3;
                if (_opt.Browser) { MessageBox.Show(message, "Sift", MessageBoxButtons.OK, MessageBoxIcon.Error); Quit(); }
                else ShowError(message, offerBrowser: false);
                return;
            }

            if (_opt.Browser)
            {
                if (!_opt.NoBrowser) OpenBrowser();
                if (!_host.Owned) Quit();   // niets om te bewaken (--no-wait, of de server draaide al)
                return;
            }

            await wvInit;
            if (_wv?.CoreWebView2 == null)
            {
                ShowError("Het Sift-venster (WebView2) kon niet worden gestart. Je kunt Sift wel in de browser openen; de server draait.", offerBrowser: true);
                return;
            }
            SetPhase("Interface laden", "");
            _wv.CoreWebView2.Navigate(_opt.Url);
        }
        catch (OperationCanceledException) { }
        catch (Exception ex)
        {
            _host.Log("launcher: " + ex);
            ExitCode = 3;
            if (_opt.Browser) { MessageBox.Show(ex.Message, "Sift", MessageBoxButtons.OK, MessageBoxIcon.Error); Quit(); }
            else ShowError("Onverwachte fout: " + ex.Message, offerBrowser: true);
        }
    }

    // ------------------------------------------------------------------ WebView2
    async Task InitWebViewAsync()
    {
        try
        {
            _wv = new WebView2 { Dock = DockStyle.Fill, Visible = false, DefaultBackgroundColor = Bg };
            Controls.Add(_wv);
            var options = new CoreWebView2EnvironmentOptions { AdditionalBrowserArguments = "--autoplay-policy=no-user-gesture-required" };
            var env = await CoreWebView2Environment.CreateAsync(null, Path.Combine(_l.LocalData, "webview2"), options);
            await _wv.EnsureCoreWebView2Async(env);
            var core = _wv.CoreWebView2;
            var s = core.Settings;
            s.AreDefaultContextMenusEnabled = _opt.DevTools;
            s.AreDevToolsEnabled = _opt.DevTools;
            s.IsStatusBarEnabled = false;
            s.IsZoomControlEnabled = true;
            s.AreBrowserAcceleratorKeysEnabled = true;
            s.IsSwipeNavigationEnabled = false;
            s.IsGeneralAutofillEnabled = false;
            s.IsPasswordAutosaveEnabled = false;
            try { Directory.CreateDirectory(_l.Exports); core.Profile.DefaultDownloadFolderPath = _l.Exports; } catch (Exception ex) { _host.Log("downloadmap: " + ex.Message); }

            core.NewWindowRequested += (_, e) =>
            {
                e.Handled = true;
                if (IsLocal(e.Uri)) core.Navigate(e.Uri); else OpenExternal(e.Uri);
            };
            core.NavigationStarting += (_, e) =>
            {
                if (!IsLocal(e.Uri)) { e.Cancel = true; OpenExternal(e.Uri); }
            };
            core.PermissionRequested += (_, e) =>
            {
                if (e.PermissionKind == CoreWebView2PermissionKind.Microphone) e.State = CoreWebView2PermissionState.Allow;
            };
            core.ContainsFullScreenElementChanged += (_, _) => SetFullscreen(core.ContainsFullScreenElement);
            core.ProcessFailed += (_, e) => _host.Log($"webview2 procesfout: {e.ProcessFailedKind} {e.Reason}");
            _wv.NavigationCompleted += OnNavigationCompleted;
            _wv.KeyDown += OnWebViewKeyDown;   // de WinForms-control geeft AcceleratorKeyPressed door als KeyDown
            if (_settings.Zoom is > 0.3 and < 4) _wv.ZoomFactor = _settings.Zoom;
            _wv.ZoomFactorChanged += (_, _) => { _settings.Zoom = _wv.ZoomFactor; _settings.Save(); };
            _host.Log($"webview2 {RuntimeCheck.Version()} gereed");
        }
        catch (Exception ex)
        {
            _host.Log("webview2 kon niet starten: " + ex);
            if (_wv != null) { Controls.Remove(_wv); _wv.Dispose(); _wv = null; }
        }
    }

    void OnNavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        if (_wv == null) return;
        if (!e.IsSuccess && !_wvShown)
        {
            _host.Log($"navigatie mislukt: {e.WebErrorStatus}");
            ShowError($"De interface kon niet worden geladen ({e.WebErrorStatus}).", offerBrowser: true);
            return;
        }
        if (_wvShown) return;
        _wvShown = true;
        _wv.Visible = true;
        _wv.BringToFront();
        _splash.Visible = false;
        _wv.Focus();
    }

    bool IsLocal(string uri)
    {
        if (!Uri.TryCreate(uri, UriKind.Absolute, out var u)) return true;
        if (u.Scheme is "about" or "blob" or "data" or "javascript") return true;
        if (u.Scheme is not ("http" or "https")) return false;
        return u.IsLoopback;
    }

    void OnWebViewKeyDown(object? sender, KeyEventArgs e)
    {
        bool ctrl = e.Control;
        bool handled = true;
        switch (e.KeyCode)
        {
            case Keys.F11: SetFullscreen(!_fullscreen); break;
            case Keys.Escape when _fullscreen: SetFullscreen(false); break;
            case Keys.F5: _wv?.Reload(); break;
            case Keys.Oemplus or Keys.Add when ctrl: Zoom(1.1); break;
            case Keys.OemMinus or Keys.Subtract when ctrl: Zoom(1 / 1.1); break;
            case Keys.D0 or Keys.NumPad0 when ctrl: if (_wv != null) _wv.ZoomFactor = 1.0; break;
            default: handled = false; break;
        }
        if (handled) { e.Handled = true; e.SuppressKeyPress = true; }
    }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        // ook als het opstartscherm de focus heeft
        if (keyData == Keys.F11) { SetFullscreen(!_fullscreen); return true; }
        if (keyData == Keys.Escape && _fullscreen) { SetFullscreen(false); return true; }
        return base.ProcessCmdKey(ref msg, keyData);
    }

    void Zoom(double factor)
    {
        if (_wv == null) return;
        _wv.ZoomFactor = Math.Clamp(_wv.ZoomFactor * factor, 0.5, 3.0);
    }

    void SetFullscreen(bool on)
    {
        if (on == _fullscreen) return;
        _fullscreen = on;
        if (on)
        {
            _preFsState = WindowState;
            _preFsBounds = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
            WindowState = FormWindowState.Normal;
            FormBorderStyle = FormBorderStyle.None;
            WindowState = FormWindowState.Maximized;
        }
        else
        {
            WindowState = FormWindowState.Normal;
            FormBorderStyle = FormBorderStyle.Sizable;
            Bounds = _preFsBounds;
            WindowState = _preFsState;
        }
    }

    // ------------------------------------------------------------------ hulpjes
    void OpenBrowser() => OpenExternal(_opt.Url);

    void OpenExternal(string url)
    {
        try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); } catch (Exception ex) { _host.Log("openen mislukt: " + ex.Message); }
    }

    void OpenFolder(string dir)
    {
        try { Directory.CreateDirectory(dir); Process.Start(new ProcessStartInfo("explorer.exe", $"\"{dir}\"") { UseShellExecute = true }); } catch { }
    }

    void OpenLog()
    {
        try
        {
            if (File.Exists(_l.LogPath)) Process.Start(new ProcessStartInfo(_l.LogPath) { UseShellExecute = true });
            else OpenFolder(_l.LocalData);
        }
        catch { OpenFolder(_l.LocalData); }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _tray.Dispose();
            _wv?.Dispose();
            _cts.Dispose();
        }
        base.Dispose(disposing);
    }
}
