# Start the bridge detached (listen mode). Self-locating — run from anywhere.

$dir = $PSScriptRoot
$logOut = Join-Path $dir 'bridge.log'
$logErr = Join-Path $dir 'bridge.err'

# The renamed interpreter (bridgepython.exe) cannot locate its stdlib on its
# own, so PYTHONHOME must point at a pythoncore install. Auto-detect the
# newest one; set PYTHONHOME yourself to override.
if (-not $env:PYTHONHOME) {
    $candidates = Get-ChildItem "$env:LOCALAPPDATA\Python" -Filter 'pythoncore-*' -Directory -ErrorAction SilentlyContinue
    if ($candidates) {
        $env:PYTHONHOME = ($candidates | Sort-Object { [version]($_.Name.Substring('pythoncore-'.Length).Split('-')[0]) } -Descending | Select-Object -First 1).FullName
    }
}

# Prefer the renamed interpreter next to this script (bypasses the firewall
# block on python.exe); fall back to python on PATH.
$py = Join-Path $dir 'bridgepython.exe'
if (-not (Test-Path $py)) { $py = 'python' }

# Clear old logs
Remove-Item $logOut, $logErr -ErrorAction SilentlyContinue

# Kill any existing bridge
Get-Process python, bridgepython -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# Start bridge detached
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $py
$psi.Arguments = '-m bridge.server --window-title "Caves of Qud" --host 0.0.0.0 --port 9090'
$psi.WorkingDirectory = $dir
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi

$outWriter = New-Object System.IO.StreamWriter($logOut, $false)
$errWriter = New-Object System.IO.StreamWriter($logErr, $false)
$proc.add_OutputDataReceived({
    param($s, $e)
    if ($e.Data -ne $null) { $outWriter.WriteLine($e.Data); $outWriter.Flush() }
})
$proc.add_ErrorDataReceived({
    param($s, $e)
    if ($e.Data -ne $null) { $errWriter.WriteLine($e.Data); $errWriter.Flush() }
})

$proc.Start() | Out-Null
$proc.BeginOutputReadLine()
$proc.BeginErrorReadLine()

Write-Host "Bridge started, PID=$($proc.Id)"
Start-Sleep -Seconds 4

if ($proc.HasExited) {
    Write-Host "BRIDGE DIED"
    Write-Host "--- stderr ---"
    Get-Content $logErr
    Write-Host "--- stdout ---"
    Get-Content $logOut
} else {
    Write-Host "Bridge running"
    Write-Host "--- stdout ---"
    Get-Content $logOut
}
