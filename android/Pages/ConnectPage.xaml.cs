using Sift.Services;

namespace Sift.Pages;

public partial class ConnectPage : ContentPage
{
    private CancellationTokenSource? _cts;

    public ConnectPage()
    {
        InitializeComponent();
        var s = AppState.Server;
        if (s.Host.Length > 0) AddressEntry.Text = s.HostPort;
        CodeEntry.Text = s.Code;
        ShowSaved();
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        ShowSaved();
    }

    private void ShowSaved()
    {
        var s = AppState.Server;
        ForgetButton.IsVisible = s.IsComplete;
        if (s.IsComplete && StatusLabel.Text == Strings.NotConnected)
            SetStatus(string.Format(Strings.Connected, s.HostPort), ok: null);
    }

    private void SetStatus(string text, bool? ok)
    {
        StatusLabel.Text = text;
        Dot.Fill = ok switch
        {
            true => (Color)Application.Current!.Resources["Ok"],
            false => (Color)Application.Current!.Resources["Bad"],
            _ => Color.FromArgb("#9ca3af"),
        };
    }

    private void ShowMessage(string? text, bool error)
    {
        MessageLabel.IsVisible = !string.IsNullOrEmpty(text);
        MessageLabel.Text = text ?? "";
        MessageLabel.TextColor = (Color)Application.Current!.Resources[error ? "Bad" : "Ok"];
    }

    private async void OnScan(object? sender, EventArgs e)
    {
        var status = await Permissions.CheckStatusAsync<Permissions.Camera>();
        if (status != PermissionStatus.Granted)
            status = await Permissions.RequestAsync<Permissions.Camera>();
        if (status != PermissionStatus.Granted)
        {
            ShowMessage(Strings.CameraDenied, error: true);
            return;
        }

        var page = new ScanPage();
        page.Scanned += async (_, text) =>
        {
            if (!ServerSettings.TryParseAddress(text, out var host, out var port, out var code) || code is null)
            {
                ShowMessage(Strings.QrNotSift, error: true);
                return;
            }
            AddressEntry.Text = port == ServerSettings.DefaultPort ? host : $"{host}:{port}";
            CodeEntry.Text = code;
            await TestAndSaveAsync();
        };
        await Navigation.PushModalAsync(new NavigationPage(page));
    }

    private async void OnTest(object? sender, EventArgs e) => await TestAndSaveAsync();

    private async Task TestAndSaveAsync()
    {
        if (!ServerSettings.TryParseAddress(AddressEntry.Text, out var host, out var port, out var qrCode))
        {
            ShowMessage(Strings.AddressInvalid, error: true);
            return;
        }
        var code = (CodeEntry.Text ?? "").Trim();
        if (code.Length == 0 && qrCode is not null) { code = qrCode; CodeEntry.Text = code; }
        if (!ServerSettings.IsValidCode(code))
        {
            ShowMessage(Strings.CodeInvalid, error: true);
            return;
        }

        _cts?.Cancel();
        _cts = new CancellationTokenSource();
        var settings = new ServerSettings { Host = host, Port = port, Code = code };
        SetBusy(true);
        ShowMessage(Strings.Testing, error: false);
        try
        {
            var n = await new SiftClient(settings).TestAsync(_cts.Token);
            settings.Save();
            ForgetButton.IsVisible = true;
            SetStatus(string.Format(Strings.ConnectedProjects, settings.HostPort, n), ok: true);
            ShowMessage(null, error: false);
        }
        catch (OperationCanceledException) { }
        catch (SiftException ex)
        {
            SetStatus(Strings.NotConnected, ok: false);
            ShowMessage(ex.Message, error: true);
        }
        catch (Exception ex)
        {
            SetStatus(Strings.NotConnected, ok: false);
            ShowMessage(Strings.ErrUnreachable + "\n(" + ex.Message + ")", error: true);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private void SetBusy(bool busy)
    {
        Busy.IsVisible = Busy.IsRunning = busy;
        TestButton.IsEnabled = !busy;
    }

    private void OnForget(object? sender, EventArgs e)
    {
        ServerSettings.Clear();
        AddressEntry.Text = "";
        CodeEntry.Text = "";
        ForgetButton.IsVisible = false;
        SetStatus(Strings.NotConnected, ok: null);
        ShowMessage(null, error: false);
    }
}
