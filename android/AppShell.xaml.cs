using Sift.Pages;
using Sift.Services;

namespace Sift;

public partial class AppShell : Shell
{
    public AppShell()
    {
        InitializeComponent();
        Routing.RegisterRoute("scan", typeof(ScanPage));

        // A file shared from another app (WhatsApp, Bestanden) lands on the upload tab.
        AppState.SharedFileChanged += (_, _) => Dispatcher.Dispatch(async () =>
        {
            try { await GoToAsync("//upload"); } catch { /* shell not ready yet; UploadPage picks it up on appearing */ }
        });
    }
}
