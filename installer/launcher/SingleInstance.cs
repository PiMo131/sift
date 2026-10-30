// Eén Sift per poort: een benoemde mutex bewaakt dat, een named pipe brengt het venster van de eerste
// instantie naar voren als er een tweede gestart wordt.

using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Text;

namespace Sift;

sealed class SingleInstance : IDisposable
{
    readonly Mutex _mutex;
    readonly string _pipeName;
    readonly CancellationTokenSource _cts = new();
    public bool IsFirst { get; }

    [DllImport("user32.dll")] static extern bool AllowSetForegroundWindow(uint pid);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool GetNamedPipeServerProcessId(SafeHandle pipe, out uint pid);

    public SingleInstance(int port)
    {
        _pipeName = $"Sift.Launcher.{port}";
        _mutex = new Mutex(true, @"Local\" + _pipeName, out bool createdNew);
        IsFirst = createdNew;
    }

    /// <summary>Vraagt de al draaiende instantie haar venster te tonen.</summary>
    public void SignalShow()
    {
        try
        {
            using var client = new NamedPipeClientStream(".", _pipeName, PipeDirection.Out);
            client.Connect(3000);
            // Alleen het proces dat nu de voorgrond "bezit" (wij, net gestart door de gebruiker) mag dat recht
            // doorgeven; anders knippert het venster van de eerste instantie alleen in de taakbalk.
            if (GetNamedPipeServerProcessId(client.SafePipeHandle, out uint pid)) AllowSetForegroundWindow(pid);
            var bytes = Encoding.UTF8.GetBytes("show\n");
            client.Write(bytes, 0, bytes.Length);
            client.Flush();
        }
        catch { }
    }

    /// <summary>Luistert (op de achtergrond) naar "show"-verzoeken van latere instanties.</summary>
    public void Listen(Action onShow)
    {
        _ = Task.Run(async () =>
        {
            while (!_cts.IsCancellationRequested)
            {
                try
                {
                    using var server = new NamedPipeServerStream(_pipeName, PipeDirection.In, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous);
                    await server.WaitForConnectionAsync(_cts.Token);
                    using var reader = new StreamReader(server, Encoding.UTF8);
                    string? line = await reader.ReadLineAsync(_cts.Token);
                    if (line?.Trim() == "show") onShow();
                }
                catch (OperationCanceledException) { break; }
                catch { await Task.Delay(500); }
            }
        });
    }

    public void Dispose()
    {
        _cts.Cancel();
        try { if (IsFirst) _mutex.ReleaseMutex(); } catch { }
        _mutex.Dispose();
    }
}
