"""Screenshots of the Qud window for the replay, taken without focusing it.

One long-lived powershell.exe (started from WSL) answers capture requests on
stdin with a base64 JPEG on stdout. It uses PrintWindow with
PW_RENDERFULLCONTENT, which renders the window even when it is behind other
windows; a minimized window has nothing to render, so it fails then.
"""

import base64
import queue
import shutil
import subprocess
import threading

_SCRIPT = r'''
$ErrorActionPreference = "Stop"
Add-Type @"
using System; using System.Runtime.InteropServices;
public class QudWin {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  public struct RECT { public int L, T, R, B; }
}
"@
Add-Type -AssemblyName System.Drawing
[QudWin]::SetProcessDPIAware() | Out-Null
$jpeg = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq "image/jpeg" }
$params = New-Object System.Drawing.Imaging.EncoderParameters 1
$params.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter ([System.Drawing.Imaging.Encoder]::Quality, [long]80)
[Console]::Out.WriteLine("READY")
while ($true) {
  $line = [Console]::In.ReadLine()
  if ($line -eq $null -or $line -eq "quit") { break }
  try {
    $p = Get-Process CoQ | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p -eq $null) { [Console]::Out.WriteLine("ERR game window not found"); continue }
    $h = $p.MainWindowHandle
    if ([QudWin]::IsIconic($h)) { [Console]::Out.WriteLine("ERR window is minimized"); continue }
    $r = New-Object QudWin+RECT
    [QudWin]::GetWindowRect($h, [ref]$r) | Out-Null
    $w = $r.R - $r.L; $hh = $r.B - $r.T
    $bmp = New-Object System.Drawing.Bitmap $w, $hh
    $g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
    [QudWin]::PrintWindow($h, $dc, 2) | Out-Null
    $g.ReleaseHdc($dc); $g.Dispose()
    $max = [int]$line
    if ($max -gt 0 -and $w -gt $max) {
      $nh = [int]($hh * $max / $w)
      $small = New-Object System.Drawing.Bitmap $max, $nh
      $g2 = [System.Drawing.Graphics]::FromImage($small)
      $g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
      $g2.DrawImage($bmp, 0, 0, $max, $nh); $g2.Dispose(); $bmp.Dispose(); $bmp = $small
    }
    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, $jpeg, $params); $bmp.Dispose()
    [Console]::Out.WriteLine("OK " + [Convert]::ToBase64String($ms.ToArray()))
  } catch { [Console]::Out.WriteLine("ERR " + $_.Exception.Message) }
}
'''


class Screenshotter:
    """grab() -> JPEG bytes, or None (with .last_error) when capture isn't possible."""

    def __init__(self, max_width: int = 1280):
        self.max_width = max_width
        self.last_error = ""
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        exe = shutil.which("powershell.exe")
        if not exe:
            self.last_error = "powershell.exe not found (screenshots need WSL + Windows)"
            return
        encoded = base64.b64encode(_SCRIPT.encode("utf-16-le")).decode()
        self._proc = subprocess.Popen([exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True, bufsize=1)
        threading.Thread(target=self._pump, daemon=True).start()
        if self._read(30.0) != "READY":
            self.last_error = "capture helper did not start"
            self.close()

    @property
    def available(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _pump(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            self._lines.put(line.rstrip("\r\n"))

    def _read(self, timeout: float) -> str | None:
        try:
            return self._lines.get(timeout=timeout)
        except queue.Empty:
            return None

    def grab(self, timeout: float = 10.0) -> bytes | None:
        with self._lock:
            if not self.available:
                return None
            try:
                self._proc.stdin.write(f"{self.max_width}\n")
                self._proc.stdin.flush()
            except OSError as e:
                self.last_error = str(e)
                return None
            line = self._read(timeout)
            if line is None:
                self.last_error = "capture timed out"
                return None
            if line.startswith("OK "):
                return base64.b64decode(line[3:])
            self.last_error = line[4:] if line.startswith("ERR ") else line
            return None

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write("quit\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
        self._proc = None
