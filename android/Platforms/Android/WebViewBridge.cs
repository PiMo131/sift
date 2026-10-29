using Android.Content;
using Android.OS;
using Android.Provider;
using Android.Webkit;
using Java.Interop;
using Sift.Services;

namespace Sift.Platforms;

/// <summary>
/// window.SiftBridge in the review WebView. The editor's export buttons create a blob: download, which an
/// Android WebView cannot save by itself; the JS shim in ReviewPage sends the bytes here instead.
/// </summary>
public sealed class WebViewBridge : Java.Lang.Object
{
    [JavascriptInterface]
    [Export("save")]
    public void Save(string name, string mime, string base64)
    {
        try
        {
            var bytes = Convert.FromBase64String(base64);
            name = Path.GetFileName(string.IsNullOrWhiteSpace(name) ? "export" : name.Trim());
            if (string.IsNullOrWhiteSpace(mime)) mime = "application/octet-stream";
            var ctx = Android.App.Application.Context;

            if (OperatingSystem.IsAndroidVersionAtLeast(29))
            {
                var values = new ContentValues();
                values.Put(MediaStore.IMediaColumns.DisplayName, name);
                values.Put(MediaStore.IMediaColumns.MimeType, mime);
                values.Put(MediaStore.IMediaColumns.RelativePath, Android.OS.Environment.DirectoryDownloads + "/Sift");
                var uri = ctx.ContentResolver!.Insert(MediaStore.Downloads.ExternalContentUri, values)
                          ?? throw new IOException("MediaStore insert failed");
                using (var os = ctx.ContentResolver.OpenOutputStream(uri) ?? throw new IOException("open failed"))
                    os.Write(bytes, 0, bytes.Length);
                Toast(string.Format(Strings.Saved, name));
            }
            else
            {
                // Older Android: no scoped storage; save to the app cache and open the share sheet.
                var dir = Path.Combine(FileSystem.CacheDirectory, "exports");
                Directory.CreateDirectory(dir);
                var path = Path.Combine(dir, name);
                File.WriteAllBytes(path, bytes);
                MainThread.BeginInvokeOnMainThread(async () =>
                {
                    try { await Share.Default.RequestAsync(new ShareFileRequest(name, new ShareFile(path, mime))); }
                    catch (Exception ex) { Android.Util.Log.Warn("Sift", "share failed: " + ex); }
                });
            }
        }
        catch (Exception ex)
        {
            Android.Util.Log.Warn("Sift", "save failed: " + ex);
            Toast("Export mislukt: " + ex.Message);
        }
    }

    private static void Toast(string text) => MainThread.BeginInvokeOnMainThread(() =>
        Android.Widget.Toast.MakeText(Android.App.Application.Context, text, Android.Widget.ToastLength.Long)?.Show());
}
