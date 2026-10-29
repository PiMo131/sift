using System.Text.RegularExpressions;

namespace Sift.Services;

/// <summary>Address + code of the Sift server on the PC, persisted in Preferences.</summary>
public sealed class ServerSettings
{
    public const int DefaultPort = 8765;

    public string Host { get; set; } = "";
    public int Port { get; set; } = DefaultPort;
    public string Code { get; set; } = "";

    public bool IsComplete => Host.Length > 0 && Port > 0 && Code.Length > 0;
    public string BaseUrl => $"http://{Host}:{Port}";
    public string HostPort => Port == DefaultPort ? Host : $"{Host}:{Port}";

    /// <summary>URL for the WebView: the code in the query sets the sift_code cookie server-side.</summary>
    public string EditorUrl(string? projectId = null)
    {
        var url = $"{BaseUrl}/?code={Uri.EscapeDataString(Code)}";
        if (!string.IsNullOrEmpty(projectId))
            url += $"#p={Uri.EscapeDataString(projectId)}&v=editor";
        return url;
    }

    public static ServerSettings Load() => new()
    {
        Host = Preferences.Default.Get("server_host", ""),
        Port = Preferences.Default.Get("server_port", DefaultPort),
        Code = Preferences.Default.Get("server_code", ""),
    };

    public void Save()
    {
        Preferences.Default.Set("server_host", Host);
        Preferences.Default.Set("server_port", Port);
        Preferences.Default.Set("server_code", Code);
        Changed?.Invoke(null, EventArgs.Empty);
    }

    public static void Clear()
    {
        Preferences.Default.Remove("server_host");
        Preferences.Default.Remove("server_port");
        Preferences.Default.Remove("server_code");
        Changed?.Invoke(null, EventArgs.Empty);
    }

    public static event EventHandler? Changed;

    /// <summary>Parses "192.168.1.23", "192.168.1.23:8765", "http://192.168.1.23:8765/?code=4821" or "pc-naam:8765".</summary>
    public static bool TryParseAddress(string? text, out string host, out int port, out string? code)
    {
        host = ""; port = DefaultPort; code = null;
        text = (text ?? "").Trim();
        if (text.Length == 0) return false;
        if (!text.Contains("://")) text = "http://" + text;
        if (!Uri.TryCreate(text, UriKind.Absolute, out var uri)) return false;
        if (uri.Scheme != "http" && uri.Scheme != "https") return false;
        host = uri.Host;
        // Uri reports 80 when no port was typed; Sift's default is 8765.
        port = uri.IsDefaultPort ? DefaultPort : uri.Port;
        var m = Regex.Match(uri.Query, @"[?&]code=(\d{4,8})");
        if (m.Success) code = m.Groups[1].Value;
        return host.Length > 0;
    }

    public static bool IsValidCode(string? code) => code is not null && Regex.IsMatch(code, @"^\d{4,8}$");
}
