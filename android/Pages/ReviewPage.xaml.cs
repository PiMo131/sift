using Sift.Services;

namespace Sift.Pages;

public partial class ReviewPage : ContentPage
{
    private string? _loadedBase;   // BaseUrl of the server currently shown in the WebView

    /// <summary>
    /// The editor downloads exports via a blob: URL on a temporary anchor, which an Android WebView ignores.
    /// This shim hands the blob to the native side (SiftBridge, see Platforms/Android/WebViewBridge.cs) instead.
    /// </summary>
    private const string DownloadShim = """
        (function(){
          if (window.__siftShim || !window.SiftBridge) return;
          window.__siftShim = true;
          var orig = HTMLAnchorElement.prototype.click;
          HTMLAnchorElement.prototype.click = function(){
            var a = this;
            if (a.download !== undefined && a.href && a.href.indexOf('blob:') === 0) {
              fetch(a.href).then(function(r){ return r.blob(); }).then(function(b){
                var fr = new FileReader();
                fr.onload = function(){ SiftBridge.save(a.download || 'export', b.type || 'application/octet-stream', String(fr.result).split(',')[1] || ''); };
                fr.readAsDataURL(b);
              }).catch(function(e){ console.error('sift download', e); });
              return;
            }
            return orig.call(a);
          };
        })();
        """;

    public ReviewPage()
    {
        InitializeComponent();
        ServerSettings.Changed += (_, _) => Dispatcher.Dispatch(() => { _loadedBase = null; });
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        DeviceDisplay.Current.KeepScreenOn = true;

        var s = AppState.Server;
        NotConnected.IsVisible = !s.IsComplete;
        ServerLabel.Text = s.IsComplete ? s.HostPort : "";
        if (!s.IsComplete) return;

        var pid = AppState.ProjectToOpen;
        AppState.ProjectToOpen = null;

        if (_loadedBase == s.BaseUrl && pid is not null)
        {
            // Same server already loaded: a hash-only navigation would not re-run the editor's startup, so reload.
            var hash = $"#p={Uri.EscapeDataString(pid)}&v=editor";
            Web.Eval($"location.hash = {System.Text.Json.JsonSerializer.Serialize(hash)}; location.reload();");
        }
        else if (_loadedBase != s.BaseUrl || pid is not null)
        {
            Load(s.EditorUrl(pid));
        }
    }

    protected override void OnDisappearing()
    {
        DeviceDisplay.Current.KeepScreenOn = false;
        base.OnDisappearing();
    }

    private void Load(string url)
    {
        LoadBar.IsVisible = true;
        Web.Source = new UrlWebViewSource { Url = url };
    }

    private void OnNavigating(object? sender, WebNavigatingEventArgs e)
    {
        var s = AppState.Server;
        // Keep the WebView on the Sift server; anything else (e.g. links in a transcript) goes to the browser.
        if (s.IsComplete && !e.Url.StartsWith(s.BaseUrl, StringComparison.OrdinalIgnoreCase)
            && (e.Url.StartsWith("http://") || e.Url.StartsWith("https://")))
        {
            e.Cancel = true;
            _ = Launcher.Default.TryOpenAsync(e.Url);
            return;
        }
        LoadBar.IsVisible = true;
    }

    private void OnNavigated(object? sender, WebNavigatedEventArgs e)
    {
        LoadBar.IsVisible = false;
        var s = AppState.Server;
        if (e.Result == WebNavigationResult.Success && s.IsComplete && e.Url.StartsWith(s.BaseUrl, StringComparison.OrdinalIgnoreCase))
        {
            _loadedBase = s.BaseUrl;
            Web.Eval(DownloadShim);
        }
        else if (e.Result != WebNavigationResult.Success)
        {
            _loadedBase = null;
        }
    }

    private void OnReload(object? sender, EventArgs e)
    {
        var s = AppState.Server;
        if (!s.IsComplete) return;
        if (_loadedBase == s.BaseUrl) Web.Reload();
        else Load(s.EditorUrl());
    }

    private void OnHome(object? sender, EventArgs e)
    {
        var s = AppState.Server;
        if (!s.IsComplete) return;
        _loadedBase = null;
        Load(s.EditorUrl());
    }

    private async void OnGoConnect(object? sender, EventArgs e) => await Shell.Current.GoToAsync("//connect");

    protected override bool OnBackButtonPressed()
    {
        if (Web.CanGoBack)
        {
            Web.GoBack();
            return true;
        }
        return base.OnBackButtonPressed();
    }
}
