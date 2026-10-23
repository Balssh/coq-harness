# Smoke-test the Windows-side Python: verifies all bridge imports work.
# Self-locating — run from anywhere.

$dir = $PSScriptRoot

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

Push-Location $dir
try {
    & $py -c "import numpy, PIL, win32gui, windows_capture; print('all imports OK')"
} finally {
    Pop-Location
}
