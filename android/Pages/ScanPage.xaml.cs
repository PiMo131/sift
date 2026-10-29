using ZXing.Net.Maui;

namespace Sift.Pages;

public partial class ScanPage : ContentPage
{
    private int _done;

    /// <summary>Raised once with the text of the first QR code seen; the page closes itself.</summary>
    public event EventHandler<string>? Scanned;

    public ScanPage()
    {
        InitializeComponent();
        Reader.Options = new BarcodeReaderOptions
        {
            Formats = BarcodeFormat.QrCode,
            AutoRotate = true,
            Multiple = false,
            TryHarder = true,
        };
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        Reader.IsDetecting = true;
    }

    protected override void OnDisappearing()
    {
        Reader.IsDetecting = false;
        base.OnDisappearing();
    }

    private void OnBarcodesDetected(object? sender, BarcodeDetectionEventArgs e)
    {
        var value = e.Results?.FirstOrDefault()?.Value;
        if (string.IsNullOrWhiteSpace(value)) return;
        if (Interlocked.Exchange(ref _done, 1) != 0) return;

        Reader.IsDetecting = false;
        Dispatcher.Dispatch(async () =>
        {
            try { HapticFeedback.Default.Perform(HapticFeedbackType.Click); } catch { }
            await Navigation.PopModalAsync();
            Scanned?.Invoke(this, value.Trim());
        });
    }

    private async void OnCancel(object? sender, EventArgs e)
    {
        Reader.IsDetecting = false;
        await Navigation.PopModalAsync();
    }

    protected override bool OnBackButtonPressed()
    {
        Dispatcher.Dispatch(async () => await Navigation.PopModalAsync());
        return true;
    }
}
