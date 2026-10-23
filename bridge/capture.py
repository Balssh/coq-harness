"""Screen capture via Windows Graphics Capture (WGC), by window HWND.

WGC captures the window even when fully occluded or off-screen.
The latest frame is kept in memory; grab() returns it as PNG bytes.

Uses windows-capture v2 API (WindowsCapture + start_free_threaded).

Reliability: the WGC session can die mid-run (window destroyed, driver
reset, ...). When that happens the session is marked closed and the next
get_frame() transparently restarts it, so callers never see a stale frame
presented as fresh without any signal. restart() also re-finds the window
by title, so it follows the game if the window is re-created (new HWND).
"""

import io
import threading
import time

import numpy as np
import windows_capture
import win32gui
from PIL import Image


class WindowCapture:
    """Continuously captures a window by HWND using WGC."""

    def __init__(self, window_title: str, hwnd: int | None = None) -> None:
        self.window_title = window_title
        self._hwnd = hwnd or win32gui.FindWindow(None, window_title)
        if not self._hwnd:
            raise RuntimeError(f"Window not found: {window_title!r}")

        self._lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None  # HxWx4 BGRA
        self._frame_time: float = 0.0                # time.monotonic() of latest frame
        self._frame_event = threading.Event()
        self._error: str | None = None
        self._closed = False   # WGC session ended (closed_handler fired)
        self._stopped = False  # intentional stop() — never auto-restart
        self._capture: windows_capture.WindowsCapture | None = None
        self._control: windows_capture.CaptureControl | None = None

    def start(self) -> None:
        """Start the WGC capture session. Requires a first frame."""
        self._start_session(first_frame_timeout=10.0, require_frame=True)

    def restart(self) -> None:
        """Restart the WGC session after it died.

        Re-finds the window by title (it may have been re-created with a new
        HWND). Does not require a fresh frame: WGC only delivers frames when
        content changes, so a static screen yields no frame right after
        restart even though the session is healthy.
        """
        self._start_session(first_frame_timeout=5.0, require_frame=False)

    def _start_session(self, first_frame_timeout: float, require_frame: bool) -> None:
        self._stop_control()
        self._frame_event.clear()
        self._error = None
        self._closed = False

        # The window may have been re-created since we last looked
        hwnd = win32gui.FindWindow(None, self.window_title)
        if hwnd:
            self._hwnd = hwnd

        self._capture = windows_capture.WindowsCapture(
            window_hwnd=self._hwnd,
            cursor_capture=False,
            draw_border=False,
        )
        self._capture.frame_handler = self._on_frame
        self._capture.closed_handler = self._on_closed
        self._control = self._capture.start_free_threaded()

        # Wait for first frame, session close, or timeout
        self._frame_event.wait(timeout=first_frame_timeout)
        if self._error:
            self._closed = True
            raise RuntimeError(f"WGC capture failed: {self._error}")
        if require_frame and self._latest_frame is None:
            self._closed = True
            raise RuntimeError(
                f"WGC capture started but no frame received within {first_frame_timeout}s"
            )

    def stop(self) -> None:
        self._stopped = True
        self._stop_control()

    def _stop_control(self) -> None:
        if self._control is not None:
            try:
                self._control.stop()
            except Exception:
                pass
            self._control = None

    @property
    def is_alive(self) -> bool:
        """True if the capture session is running (not closed, not stopped)."""
        return not self._closed and not self._stopped and self._control is not None

    @property
    def frame_age(self) -> float | None:
        """Seconds since the latest frame arrived, or None if no frame yet."""
        if self._latest_frame is None:
            return None
        return time.monotonic() - self._frame_time

    def _on_frame(self, frame, _ctrl) -> None:
        """WGC callback — called on WGC's thread with a new frame.

        frame.frame_buffer is a numpy array HxWx4 BGRA uint8.
        """
        arr = frame.frame_buffer.copy()
        with self._lock:
            self._latest_frame = arr
            self._frame_time = time.monotonic()
        self._frame_event.set()

    def _on_closed(self) -> None:
        self._closed = True
        if self._latest_frame is None and self._error is None:
            self._error = "Capture closed before first frame"
        self._frame_event.set()

    def get_frame(self) -> np.ndarray:
        """Return the latest frame as HxWx4 BGRA numpy array.

        If the capture session died, tries to restart it once. Raises
        RuntimeError if the session is stopped or restart fails.
        """
        if self._stopped:
            raise RuntimeError("Capture is stopped")
        if self._closed:
            self.restart()
        with self._lock:
            if self._latest_frame is None:
                raise RuntimeError("No frame captured yet")
            return self._latest_frame.copy()

    def grab_png(self) -> bytes:
        """Return the latest frame as PNG bytes (RGB)."""
        frame = self.get_frame()
        # BGRA -> RGB
        rgb = frame[:, :, :3][:, :, ::-1]
        img = Image.fromarray(rgb, mode="RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def grab_region_png(self, x: int, y: int, w: int, h: int) -> bytes:
        """Return a cropped region of the latest frame as PNG bytes (RGB)."""
        frame = self.get_frame()
        region = frame[y:y + h, x:x + w]
        rgb = region[:, :, :3][:, :, ::-1]
        img = Image.fromarray(rgb, mode="RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def grab_region_array(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        """Return a cropped region as a numpy array (HxWx4 BGRA). For diffing."""
        frame = self.get_frame()
        return frame[y:y + h, x:x + w].copy()
