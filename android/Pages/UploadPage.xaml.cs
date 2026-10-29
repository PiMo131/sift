using Sift.Services;

namespace Sift.Pages;

public partial class UploadPage : ContentPage
{
    private static readonly FilePickerFileType AudioVideo = new(new Dictionary<DevicePlatform, IEnumerable<string>>
    {
        { DevicePlatform.Android, new[] { "audio/*", "video/*" } },
    });

    private PendingFile? _file;
    private DropResult? _result;
    private CancellationTokenSource? _cts;

    public UploadPage()
    {
        InitializeComponent();
        AppState.SharedFileChanged += (_, _) => Dispatcher.Dispatch(TakeSharedFile);
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        NotConnectedCard.IsVisible = !AppState.Server.IsComplete;
        TakeSharedFile();
        UpdateButtons();
    }

    private void TakeSharedFile()
    {
        var shared = AppState.SharedFile;
        if (shared is null) return;
        AppState.SharedFile = null;
        SetFile(shared);
        ShowMessage(Strings.SharedReceived, error: false);
    }

    private void SetFile(PendingFile file)
    {
        _file = file;
        _result = null;
        OpenButton.IsVisible = false;
        FileLabel.Text = file.Name;
        FileInfoLabel.Text = file.SizeText;
        FileInfoLabel.IsVisible = true;
        if (string.IsNullOrWhiteSpace(NameEntry.Text) || NameEntry.Text == _lastSuggestedName)
        {
            _lastSuggestedName = SuggestName(file.Name);
            NameEntry.Text = _lastSuggestedName;
        }
        ShowMessage(null, error: false);
        UpdateButtons();
    }

    private string? _lastSuggestedName;

    private static string SuggestName(string fileName)
    {
        var stem = Path.GetFileNameWithoutExtension(fileName).Trim();
        return stem.Length == 0 ? "" : stem;
    }

    private void UpdateButtons()
    {
        SendButton.IsEnabled = _file is not null && AppState.Server.IsComplete && _cts is null;
        PickButton.IsEnabled = _cts is null;
    }

    private async void OnPick(object? sender, EventArgs e)
    {
        try
        {
            var r = await FilePicker.Default.PickAsync(new PickOptions { FileTypes = AudioVideo, PickerTitle = Strings.PickFile });
            if (r is null) return;
            var size = new FileInfo(r.FullPath).Length;
            SetFile(new PendingFile(r.FullPath, r.FileName, size));
        }
        catch (Exception ex)
        {
            ShowMessage(ex.Message, error: true);
        }
    }

    private async void OnSend(object? sender, EventArgs e)
    {
        if (_file is null || _cts is not null) return;
        if (!AppState.Server.IsComplete) { ShowMessage(Strings.ConnectFirst, error: true); return; }

        var file = _file;
        var autostart = AutoStartSwitch.IsToggled;
        _cts = new CancellationTokenSource();
        UpdateButtons();
        Progress.Progress = 0;
        Progress.IsVisible = ProgressLabel.IsVisible = CancelButton.IsVisible = true;
        OpenButton.IsVisible = false;
        ShowMessage(null, error: false);
        DeviceDisplay.Current.KeepScreenOn = true;

        var total = PendingFile.FormatSize(file.Size);
        var lastShown = 0L;
        var progress = new Progress<long>(sent =>
        {
            if (sent - lastShown < 256 * 1024 && sent != file.Size) return;
            lastShown = sent;
            Progress.Progress = file.Size > 0 ? Math.Min(1.0, (double)sent / file.Size) : 1;
            ProgressLabel.Text = string.Format(Strings.Sending, PendingFile.FormatSize(sent), total);
        });

        try
        {
            var client = new SiftClient(AppState.Server);
            _result = await client.DropAsync(file.Path, file.Name, NameEntry.Text, autostart, progress, _cts.Token);
            Progress.Progress = 1;
            ProgressLabel.Text = total;
            ShowMessage(string.Format(autostart ? Strings.SentStarted : Strings.Sent, _result.Name), error: false);
            OpenButton.IsVisible = true;
        }
        catch (OperationCanceledException)
        {
            ShowMessage(Strings.Cancelled, error: true);
        }
        catch (SiftException ex)
        {
            ShowMessage(ex.Message, error: true);
        }
        catch (Exception ex)
        {
            ShowMessage(Strings.ErrUnreachable + "\n(" + ex.Message + ")", error: true);
        }
        finally
        {
            DeviceDisplay.Current.KeepScreenOn = false;
            _cts.Dispose();
            _cts = null;
            CancelButton.IsVisible = false;
            if (_result is null) Progress.IsVisible = ProgressLabel.IsVisible = false;
            UpdateButtons();
        }
    }

    private void OnCancel(object? sender, EventArgs e) => _cts?.Cancel();

    private async void OnOpen(object? sender, EventArgs e)
    {
        if (_result is null) return;
        AppState.ProjectToOpen = _result.Id;
        await Shell.Current.GoToAsync("//review");
    }

    private async void OnGoConnect(object? sender, EventArgs e) => await Shell.Current.GoToAsync("//connect");

    private void ShowMessage(string? text, bool error)
    {
        MessageLabel.IsVisible = !string.IsNullOrEmpty(text);
        MessageLabel.Text = text ?? "";
        MessageLabel.TextColor = (Color)Application.Current!.Resources[error ? "Bad" : "Ok"];
    }
}
