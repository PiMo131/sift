using Android.Webkit;
using Microsoft.Maui.Handlers;

namespace Sift.Platforms;

public static class PlatformSetup
{
    public static void Configure(MauiAppBuilder builder)
    {
        // The review tab shows the Sift editor over plain http on the LAN.
        WebViewHandler.Mapper.AppendToMapping("SiftWebView", (handler, view) =>
        {
            var wv = handler.PlatformView;
            var s = wv.Settings;
            s.JavaScriptEnabled = true;
            s.DomStorageEnabled = true;
            s.DatabaseEnabled = true;
            s.MediaPlaybackRequiresUserGesture = false;   // audio playback from the editor's own controls
            s.MixedContentMode = MixedContentHandling.AlwaysAllow;
            s.AllowFileAccess = false;
            s.LoadWithOverviewMode = true;
            s.UseWideViewPort = true;
            s.BuiltInZoomControls = false;
            s.SetSupportMultipleWindows(false);
            s.CacheMode = CacheModes.Default;

            CookieManager.Instance?.SetAcceptCookie(true);
            CookieManager.Instance?.SetAcceptThirdPartyCookies(wv, true);

            wv.AddJavascriptInterface(new WebViewBridge(), "SiftBridge");
            wv.SetDownloadListener(new ExternalDownloadListener());
        });
    }

    /// <summary>Non-blob downloads (direct export links) are handed to the system download manager with the session cookie.</summary>
    private sealed class ExternalDownloadListener : Java.Lang.Object, IDownloadListener
    {
        public void OnDownloadStart(string? url, string? userAgent, string? contentDisposition, string? mimetype, long contentLength)
        {
            if (url is null || url.StartsWith("blob:")) return; // blob: is handled by the JS shim + SiftBridge
            try
            {
                var ctx = Android.App.Application.Context;
                var req = new Android.App.DownloadManager.Request(Android.Net.Uri.Parse(url)!);
                var cookie = CookieManager.Instance?.GetCookie(url);
                if (!string.IsNullOrEmpty(cookie)) req.AddRequestHeader("Cookie", cookie);
                req.AddRequestHeader("X-Sift-Code", Services.AppState.Server.Code);
                var name = URLUtil.GuessFileName(url, contentDisposition, mimetype);
                req.SetDestinationInExternalPublicDir(Android.OS.Environment.DirectoryDownloads, "Sift/" + name);
                req.SetNotificationVisibility(Android.App.DownloadVisibility.VisibleNotifyCompleted);
                (ctx.GetSystemService(Android.Content.Context.DownloadService) as Android.App.DownloadManager)?.Enqueue(req);
            }
            catch (Exception ex)
            {
                Android.Util.Log.Warn("Sift", "download failed: " + ex);
            }
        }
    }
}
