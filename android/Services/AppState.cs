namespace Sift.Services;

/// <summary>A recording waiting to be uploaded: picked with the file picker or shared from another app.</summary>
public sealed record PendingFile(string Path, string Name, long Size)
{
    public string SizeText => FormatSize(Size);

    public static string FormatSize(long bytes)
    {
        if (bytes < 1024) return $"{bytes} B";
        if (bytes < 1024 * 1024) return $"{bytes / 1024.0:0.#} kB";
        if (bytes < 1024L * 1024 * 1024) return $"{bytes / (1024.0 * 1024):0.#} MB";
        return $"{bytes / (1024.0 * 1024 * 1024):0.##} GB";
    }
}

/// <summary>Process-wide state: server settings, a file shared into the app, a project to open in the review tab.</summary>
public static class AppState
{
    public static ServerSettings Server { get; private set; } = ServerSettings.Load();

    static AppState()
    {
        ServerSettings.Changed += (_, _) => Server = ServerSettings.Load();
    }

    /// <summary>Set by MainActivity when another app shares audio/video to Sift; consumed by UploadPage.</summary>
    public static PendingFile? SharedFile { get; set; }
    public static event EventHandler? SharedFileChanged;

    public static void SetSharedFile(PendingFile file)
    {
        SharedFile = file;
        SharedFileChanged?.Invoke(null, EventArgs.Empty);
    }

    /// <summary>Project to open the next time the review tab appears (after an upload).</summary>
    public static string? ProjectToOpen { get; set; }
}
