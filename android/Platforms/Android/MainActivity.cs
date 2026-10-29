using Android.App;
using Android.Content;
using Android.Content.PM;
using Android.OS;
using Android.Provider;
using Sift.Services;

namespace Sift;

[Activity(Theme = "@style/Maui.SplashTheme", MainLauncher = true, LaunchMode = LaunchMode.SingleTask, Exported = true,
          ConfigurationChanges = ConfigChanges.ScreenSize | ConfigChanges.Orientation | ConfigChanges.UiMode | ConfigChanges.ScreenLayout | ConfigChanges.SmallestScreenSize | ConfigChanges.Density)]
// Share target: "Delen" from WhatsApp (voice notes, "WhatsApp Audio ... .mp4"), Bestanden, recorder apps.
[IntentFilter(new[] { Intent.ActionSend }, Categories = new[] { Intent.CategoryDefault }, DataMimeTypes = new[] { "audio/*", "video/*", "application/ogg", "application/octet-stream" })]
public class MainActivity : MauiAppCompatActivity
{
    protected override void OnCreate(Bundle? savedInstanceState)
    {
        base.OnCreate(savedInstanceState);
        HandleShare(Intent);
    }

    protected override void OnNewIntent(Intent? intent)
    {
        base.OnNewIntent(intent);
        HandleShare(intent);
    }

    private void HandleShare(Intent? intent)
    {
        if (intent?.Action != Intent.ActionSend) return;
        var uri = intent.ClipData?.ItemCount > 0 ? intent.ClipData.GetItemAt(0)?.Uri : null;
#pragma warning disable CA1422 // GetParcelableExtra(string) is deprecated in API 33 but the typed overload needs 33+
        uri ??= intent.GetParcelableExtra(Intent.ExtraStream) as Android.Net.Uri;
#pragma warning restore CA1422
        if (uri is null) return;
        intent.SetAction(null); // handle once (the intent is re-delivered on rotation otherwise)

        var mime = intent.Type;
        Task.Run(() =>
        {
            try
            {
                var file = CopyToCache(uri, mime);
                AppState.SetSharedFile(file);
            }
            catch (Exception ex)
            {
                Android.Util.Log.Warn("Sift", "share failed: " + ex);
                RunOnUiThread(() => Android.Widget.Toast.MakeText(this, Strings.ErrShare, Android.Widget.ToastLength.Long)?.Show());
            }
        });
    }

    /// <summary>Copies a content:// stream into the app cache so it can be uploaded later without the share grant.</summary>
    private PendingFile CopyToCache(Android.Net.Uri uri, string? mime)
    {
        var resolver = ContentResolver!;
        string? name = null;
        try
        {
            using var cursor = resolver.Query(uri, new[] { IOpenableColumns.DisplayName }, null, null, null);
            if (cursor is not null && cursor.MoveToFirst())
            {
                var idx = cursor.GetColumnIndex(IOpenableColumns.DisplayName);
                if (idx >= 0) name = cursor.GetString(idx);
            }
        }
        catch { }
        name ??= uri.LastPathSegment ?? "opname";
        name = Path.GetFileName(name.Replace('\\', '/'));
        if (Path.GetExtension(name).Length == 0)
        {
            var ext = Android.Webkit.MimeTypeMap.Singleton?.GetExtensionFromMimeType(mime ?? "") ?? (mime?.StartsWith("video/") == true ? "mp4" : "m4a");
            name += "." + ext;
        }

        var dir = Path.Combine(FileSystem.CacheDirectory, "shared");
        Directory.CreateDirectory(dir);
        foreach (var old in Directory.GetFiles(dir)) { try { File.Delete(old); } catch { } }

        var dest = Path.Combine(dir, name);
        using (var input = resolver.OpenInputStream(uri) ?? throw new IOException("open failed"))
        using (var output = File.Create(dest))
        {
            input.CopyTo(output, 1 << 16);
        }
        return new PendingFile(dest, name, new FileInfo(dest).Length);
    }
}
