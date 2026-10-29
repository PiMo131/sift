using Microsoft.Extensions.Logging;
using ZXing.Net.Maui.Controls;

namespace Sift;

public static class MauiProgram
{
    public static MauiApp CreateMauiApp()
    {
        var builder = MauiApp.CreateBuilder();
        builder
            .UseMauiApp<App>()
            .UseBarcodeReader();

        Platforms.PlatformSetup.Configure(builder);

#if DEBUG
        builder.Logging.AddDebug();
#endif
        return builder.Build();
    }
}
