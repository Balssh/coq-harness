@echo off
rem Start the bridge in relay-connect mode (Windows -> WSL relay, for when
rem the firewall blocks inbound connections from WSL).
rem
rem Usage: run_bridge.bat [relay_host:port]
rem   relay_host:port  address of the WSL relay, e.g. 172.24.x.x:9091
rem   If omitted, the BRIDGE_RELAY environment variable is used.

cd /d "%~dp0"

rem The renamed interpreter (bridgepython.exe) cannot locate its stdlib on
rem its own, so PYTHONHOME must point at a pythoncore install. Auto-detect
rem one; set PYTHONHOME yourself to override.
if not defined PYTHONHOME (
    for /d %%D in ("%LOCALAPPDATA%\Python\pythoncore-*") do set "PYTHONHOME=%%~fD"
)

set "RELAY=%~1"
if not defined RELAY set "RELAY=%BRIDGE_RELAY%"
if not defined RELAY (
    echo Usage: run_bridge.bat relay_host:port
    echo   e.g. run_bridge.bat 172.24.0.1:9091
    echo   or set the BRIDGE_RELAY environment variable
    exit /b 1
)

rem Prefer the renamed interpreter next to this script (bypasses the
rem firewall block on python.exe); fall back to python on PATH.
set "PY=bridgepython.exe"
if not exist "%~dp0bridgepython.exe" set "PY=python"

echo Starting bridge (connect mode) to %RELAY%... > bridge_debug.log
"%PY%" -u -m bridge.server --window-title "Caves of Qud" --connect %RELAY% --log-region 1440 0 480 1000 >> bridge_debug.log 2>&1
