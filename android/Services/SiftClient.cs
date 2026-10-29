using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;

namespace Sift.Services;

public sealed record DropResult(string Id, string Name);

public sealed class SiftException : Exception
{
    public SiftException(string message) : base(message) { }
}

/// <summary>Thin client for the Sift server API (LAN mode, X-Sift-Code header).</summary>
public sealed class SiftClient
{
    private static readonly HttpClient Http = new() { Timeout = Timeout.InfiniteTimeSpan };
    private readonly ServerSettings _s;

    public SiftClient(ServerSettings settings) => _s = settings;

    private HttpRequestMessage Req(HttpMethod method, string path)
    {
        var r = new HttpRequestMessage(method, _s.BaseUrl + path);
        r.Headers.TryAddWithoutValidation("X-Sift-Code", _s.Code);
        return r;
    }

    /// <summary>GET /api/projects. Returns the number of projects; throws SiftException with a Dutch message otherwise.</summary>
    public async Task<int> TestAsync(CancellationToken ct = default)
    {
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(TimeSpan.FromSeconds(6));
        HttpResponseMessage resp;
        try
        {
            resp = await Http.SendAsync(Req(HttpMethod.Get, "/api/projects"), cts.Token);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new SiftException(Strings.ErrTimeout);
        }
        catch (HttpRequestException ex)
        {
            throw new SiftException(Strings.ErrUnreachable + "\n(" + ex.Message + ")");
        }
        using (resp)
        {
            Check(resp);
            var json = await resp.Content.ReadAsStringAsync(cts.Token);
            try
            {
                using var doc = JsonDocument.Parse(json);
                return doc.RootElement.ValueKind == JsonValueKind.Array ? doc.RootElement.GetArrayLength() : 0;
            }
            catch (JsonException)
            {
                throw new SiftException(Strings.ErrNotSift);
            }
        }
    }

    /// <summary>POST /api/drop (multipart). Reports uploaded bytes via progress.</summary>
    public async Task<DropResult> DropAsync(string filePath, string fileName, string? projectName, bool autostart,
                                            IProgress<long>? progress, CancellationToken ct)
    {
        var info = new FileInfo(filePath);
        if (!info.Exists) throw new SiftException(Strings.ErrFileMissing);

        using var form = new MultipartFormDataContent();
        if (!string.IsNullOrWhiteSpace(projectName)) form.Add(new StringContent(projectName.Trim()), "name");
        form.Add(new StringContent(autostart ? "1" : "0"), "start");
        form.Add(new StringContent(autostart ? "1" : "0"), "autostart");

        var fileContent = new ProgressStreamContent(filePath, progress);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue(MimeFor(fileName));
        form.Add(fileContent, "file", fileName);

        var req = Req(HttpMethod.Post, "/api/drop");
        req.Content = form;

        HttpResponseMessage resp;
        try
        {
            resp = await Http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
        }
        catch (HttpRequestException ex)
        {
            throw new SiftException(Strings.ErrUnreachable + "\n(" + ex.Message + ")");
        }
        using (resp)
        {
            Check(resp);
            var json = await resp.Content.ReadAsStringAsync(ct);
            try
            {
                using var doc = JsonDocument.Parse(json);
                var id = doc.RootElement.TryGetProperty("id", out var pid) ? pid.GetString() ?? "" : "";
                var name = doc.RootElement.TryGetProperty("name", out var pn) ? pn.GetString() ?? id : id;
                if (id.Length == 0) throw new SiftException(Strings.ErrNotSift);
                return new DropResult(id, name);
            }
            catch (JsonException)
            {
                throw new SiftException(Strings.ErrNotSift);
            }
        }
    }

    private static void Check(HttpResponseMessage resp)
    {
        switch (resp.StatusCode)
        {
            case HttpStatusCode.Unauthorized: throw new SiftException(Strings.ErrCode);
            case HttpStatusCode.TooManyRequests: throw new SiftException(Strings.ErrBlocked);
            case HttpStatusCode.RequestEntityTooLarge: throw new SiftException(Strings.ErrTooLarge);
        }
        if (!resp.IsSuccessStatusCode)
            throw new SiftException(string.Format(Strings.ErrHttp, (int)resp.StatusCode));
    }

    public static string MimeFor(string name)
    {
        var ext = Path.GetExtension(name).ToLowerInvariant();
        return ext switch
        {
            ".mp3" => "audio/mpeg",
            ".m4a" => "audio/mp4",
            ".aac" => "audio/aac",
            ".wav" => "audio/wav",
            ".ogg" or ".opus" or ".oga" => "audio/ogg",
            ".flac" => "audio/flac",
            ".amr" => "audio/amr",
            ".wma" => "audio/x-ms-wma",
            ".mp4" or ".m4v" => "video/mp4",
            ".mov" => "video/quicktime",
            ".webm" => "video/webm",
            ".mkv" => "video/x-matroska",
            _ => "application/octet-stream",
        };
    }

    /// <summary>Streams a file into the request body in chunks and reports the running byte count.</summary>
    private sealed class ProgressStreamContent : HttpContent
    {
        private readonly string _path;
        private readonly IProgress<long>? _progress;
        private readonly long _length;

        public ProgressStreamContent(string path, IProgress<long>? progress)
        {
            _path = path; _progress = progress; _length = new FileInfo(path).Length;
        }

        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context)
            => CopyAsync(stream, CancellationToken.None);

        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context, CancellationToken ct)
            => CopyAsync(stream, ct);

        private async Task CopyAsync(Stream stream, CancellationToken ct)
        {
            await using var fs = new FileStream(_path, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 16, useAsync: true);
            var buf = new byte[1 << 16];
            long sent = 0;
            int n;
            while ((n = await fs.ReadAsync(buf, ct)) > 0)
            {
                await stream.WriteAsync(buf.AsMemory(0, n), ct);
                sent += n;
                _progress?.Report(sent);
            }
        }

        protected override bool TryComputeLength(out long length)
        {
            length = _length;
            return true;
        }
    }
}
