"""Auto-deploy the Windows bridge and WSL relay.

Called at harness startup to ensure the full pipeline is up:
  1. WSL relay (client.relay) — listens on 0.0.0.0:9091 + 127.0.0.1:9090
  2. Windows bridge (bridge.server) — connects to relay at localhost:9091
  3. Qud window — must exist and not be minimized

If any piece is missing or broken, this module fixes it automatically.

Usage (from WSL):
    python -m bridge.deploy              # ensure everything is up
    python -m bridge.deploy --force      # kill and restart bridge
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRIDGE_SRC = PROJECT_ROOT / "bridge"
RELAY_MODULE = "client.relay"

# Windows-side paths
WIN_TEMP = Path("/mnt/c/Windows/Temp/coq-bridge")
WIN_BRIDGE_DIR = WIN_TEMP / "bridge"

# Windows Python (found via the bridge process or fallback)
WIN_PYTHON_CANDIDATES = [
    r"C:\Users\georg\AppData\Local\Python\pythoncore-3.15-64\python.exe",
    "python",  # fallback: hope it's on PATH
]

# Ports
RELAY_BRIDGE_PORT = 9091   # bridge connects here
RELAY_HARNESS_PORT = 9090  # harness connects here

# Bridge config
WINDOW_TITLE = "CavesOfQud"
LOG_REGION = "1440 54 480 918"

# Timeouts
RELAY_START_TIMEOUT = 10
BRIDGE_START_TIMEOUT = 15
QUD_CHECK_TIMEOUT = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"[deploy] {msg}", flush=True)


def _run(cmd: list[str], timeout: float = 30, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command. Returns CompletedProcess."""
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
    )


def _try_connect(host: str, port: int, timeout: float = 2.0) -> bool:
    """Try a TCP connect. Returns True if successful."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


def _powershell(script: str, timeout: float = 30) -> subprocess.CompletedProcess:
    """Run a PowerShell command via WSL interop."""
    return _run(["powershell.exe", "-Command", script], timeout=timeout)


# ---------------------------------------------------------------------------
# Relay management (WSL side)
# ---------------------------------------------------------------------------

def is_relay_running() -> bool:
    """Check if the relay is listening on the harness port."""
    return _try_connect("127.0.0.1", RELAY_HARNESS_PORT, timeout=2.0)


def start_relay() -> None:
    """Start the WSL relay as a background process."""
    _log("Starting WSL relay...")
    log_file = open("/tmp/relay.log", "a")
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", RELAY_MODULE],
        cwd=str(PROJECT_ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _log(f"Relay started (PID {proc.pid}), log: /tmp/relay.log")

    # Wait for it to start listening
    deadline = time.monotonic() + RELAY_START_TIMEOUT
    while time.monotonic() < deadline:
        if is_relay_running():
            _log("Relay is up.")
            return
        time.sleep(0.5)
    raise RuntimeError("Relay failed to start within timeout")


def ensure_relay() -> None:
    """Ensure the relay is running. Start it if not."""
    if is_relay_running():
        _log("Relay already running.")
    else:
        start_relay()


# ---------------------------------------------------------------------------
# Bridge health check (through the relay)
# ---------------------------------------------------------------------------

def is_bridge_healthy() -> bool:
    """Check if the bridge is connected and responding.

    Connects to the relay's harness port and sends a ping.
    """
    try:
        from client.bridge_client import BridgeClient, BridgeError
        client = BridgeClient(host="127.0.0.1", port=RELAY_HARNESS_PORT, timeout=5)
        client.connect()
        result = client.ping()
        client.close()
        return result.get("status") == "ok"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Bridge deployment (Windows side)
# ---------------------------------------------------------------------------

def _find_windows_python() -> str:
    """Find the Windows Python executable path."""
    # Try to find it from a running bridge process
    result = _powershell(
        "Get-WmiObject Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*bridge.server*' } | "
        "Select-Object -First 1 -ExpandProperty Path",
        timeout=10,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    # Fall back to candidates
    for candidate in WIN_PYTHON_CANDIDATES:
        if candidate == "python":
            return candidate
        # Check if the file exists via WSL
        wsl_path = candidate.replace("C:\\", "/mnt/c/").replace("\\", "/")
        if os.path.exists(wsl_path):
            return candidate

    return "python"  # last resort


def copy_bridge_files() -> None:
    """Copy bridge Python files to Windows temp."""
    _log(f"Copying bridge files to {WIN_BRIDGE_DIR}...")
    WIN_BRIDGE_DIR.mkdir(parents=True, exist_ok=True)

    # Copy __init__.py and all .py files
    for src in BRIDGE_SRC.glob("*.py"):
        dst = WIN_BRIDGE_DIR / src.name
        shutil.copy2(src, dst)
        _log(f"  {src.name} -> {dst}")

    # Copy requirements.txt if it exists
    req_src = BRIDGE_SRC / "requirements.txt"
    if req_src.exists():
        shutil.copy2(req_src, WIN_TEMP / "requirements.txt")


def kill_bridge_processes() -> None:
    """Kill any existing bridge processes on Windows."""
    _log("Killing existing bridge processes...")
    _powershell(
        "Get-WmiObject Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*bridge.server*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
        timeout=10,
    )
    time.sleep(1)


def start_bridge(python_path: str | None = None) -> None:
    """Start the Windows bridge process."""
    if python_path is None:
        python_path = _find_windows_python()
    _log(f"Starting Windows bridge (Python: {python_path})...")

    args = (
        f"-m bridge.server --connect localhost:{RELAY_BRIDGE_PORT} "
        f"--window-title {WINDOW_TITLE} --log-region {LOG_REGION}"
    )

    # Start hidden
    script = (
        f"Start-Process -FilePath '{python_path}' "
        f"-ArgumentList '{args}' "
        f"-WorkingDirectory '{WIN_TEMP.as_posix().replace('/mnt/c/', 'C:\\')}' "
        f"-WindowStyle Hidden"
    )
    result = _powershell(script, timeout=10)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to start bridge: {result.stderr}")
    _log("Bridge process started.")


def wait_for_bridge(timeout: float = BRIDGE_START_TIMEOUT) -> bool:
    """Wait for the bridge to connect and respond to ping."""
    _log(f"Waiting for bridge (timeout: {timeout}s)...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_bridge_healthy():
            _log("Bridge is healthy.")
            return True
        time.sleep(1.0)
    return False


def deploy_bridge(force: bool = False, max_retries: int = 2) -> None:
    """Ensure the Windows bridge is deployed and running.

    Steps:
    1. If force or bridge is not healthy, redeploy
    2. Copy bridge files to Windows
    3. Kill old bridge processes
    4. Start new bridge
    5. Wait for it to connect

    Retries up to max_retries times if the bridge fails to connect.
    """
    if not force and is_bridge_healthy():
        _log("Bridge already healthy. Skipping deployment.")
        return

    if force:
        _log("Force redeploy requested.")

    copy_bridge_files()
    kill_bridge_processes()

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        _log(f"Bridge start attempt {attempt}/{max_retries}...")
        try:
            start_bridge()
            if wait_for_bridge(timeout=BRIDGE_START_TIMEOUT):
                _log("Bridge is up.")
                return
            _log(f"Bridge did not connect within {BRIDGE_START_TIMEOUT}s.")
        except Exception as exc:
            _log(f"Bridge start failed: {exc}")
            last_error = exc
        # Kill any half-started process before retry
        kill_bridge_processes()
        time.sleep(2)

    raise RuntimeError(
        f"Bridge failed to start after {max_retries} attempts"
        + (f": {last_error}" if last_error else "")
    )


# ---------------------------------------------------------------------------
# Qud window management
# ---------------------------------------------------------------------------

def ensure_qud_running(timeout: float = QUD_CHECK_TIMEOUT) -> None:
    """Ensure the Qud process exists and the window is not minimized.

    This must run BEFORE the bridge starts, because WGC capture fails
    on minimized windows.
    """
    _log("Checking Qud process...")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _powershell(
            "Get-Process -Name 'CoQ' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id",
            timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            _log("Qud (CoQ) process not found. Please launch Caves of Qud. Waiting...")
            time.sleep(3)
            continue

        # Check if minimized and restore
        result = _powershell(
            "$w = Get-Process -Name 'CoQ' -ErrorAction SilentlyContinue; "
            "$h = $w.MainWindowHandle; "
            "Add-Type -MemberDefinition "
            "'[System.Runtime.InteropServices.DllImport(\"user32.dll\")] "
            "public static extern bool ShowWindow(System.IntPtr h, int n); "
            "[System.Runtime.InteropServices.DllImport(\"user32.dll\")] "
            "public static extern bool IsIconic(System.IntPtr h);' "
            "-Name W -Namespace W; "
            "if ([W.W]::IsIconic($h)) { "
            "  [W.W]::ShowWindow($h, 9) | Out-Null; "
            "  Write-Output 'restored' "
            "} else { "
            "  Write-Output 'ok' "
            "}",
            timeout=10,
        )
        status = result.stdout.strip() if result.returncode == 0 else "unknown"
        if "restored" in status:
            _log("Qud window was minimized — restored.")
            time.sleep(1)  # let it start rendering again
        elif "ok" in status:
            _log("Qud window is running and not minimized.")
        else:
            _log(f"Qud window status: {status}")

        return  # process exists and window is restored

    raise RuntimeError(f"Qud process not found after {timeout}s")


def wait_qud_capture(timeout: float = 30) -> None:
    """Wait until the bridge can successfully grab a frame from Qud.

    This must run AFTER the bridge starts.
    """
    _log("Waiting for Qud capture...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_bridge_healthy():
            try:
                from client.bridge_client import BridgeClient
                client = BridgeClient(host="127.0.0.1", port=RELAY_HARNESS_PORT, timeout=5)
                client.connect()
                data = client.grab()
                client.close()
                _log(f"Qud capture confirmed. Frame: {len(data)} bytes.")
                return
            except Exception as exc:
                _log(f"Bridge grab failed: {exc}. Retrying...")
        time.sleep(2)
    raise RuntimeError(f"Qud capture not available after {timeout}s")


def ensure_qud_window(timeout: float = QUD_CHECK_TIMEOUT) -> None:
    """Legacy: ensure Qud is running and bridge can capture.

    Prefer ensure_qud_running() + wait_qud_capture() separately.
    """
    ensure_qud_running(timeout)
    wait_qud_capture()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def ensure_all(force_bridge: bool = False, wait_qud: bool = True) -> None:
    """Ensure the full pipeline is up: relay -> Qud window -> bridge -> capture.

    Order matters:
    1. Relay must be up first (bridge connects to it)
    2. Qud window must be restored (not minimized) before bridge starts
       — WGC capture fails on minimized windows
    3. Bridge starts and connects to relay
    4. Verify bridge can capture frames from Qud
    """
    _log("=== Ensuring relay ===")
    ensure_relay()

    if wait_qud:
        _log("=== Ensuring Qud window (pre-bridge) ===")
        ensure_qud_running()

    _log("=== Ensuring bridge ===")
    deploy_bridge(force=force_bridge)

    if wait_qud:
        _log("=== Verifying Qud capture ===")
        wait_qud_capture()

    _log("=== All systems ready ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-deploy CoQ bridge infrastructure")
    parser.add_argument("--force", action="store_true",
                        help="Force redeploy of the bridge even if healthy")
    parser.add_argument("--no-qud", action="store_true",
                        help="Skip Qud window check")
    args = parser.parse_args()

    try:
        ensure_all(force_bridge=args.force, wait_qud=not args.no_qud)
    except Exception as exc:
        _log(f"FAILED: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
