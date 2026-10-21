"""Screen capture via Windows Graphics Capture (WGC), by window HWND.

WGC captures the window even when fully occluded or off-screen.
The latest frame is kept in memory; grab() returns it as PNG bytes.

Uses windows-capture v2 API (WindowsCapture + start_free_threaded).
"""

import io
import threading

import numpy as np
import windows_capture
import win32gui
from PIL import Image


class WindowCapture:
    """Continuously captures a window by HWND using WGC."""

    def __init__(self, window_title: str) -> None:
        self.window_title = window_title
        self._hwnd = win32gui.FindWindow(None, window_title)
        if not self._hwnd:
            raise RuntimeError(f"Window not found: {window_title!r}")

        self._lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None  # HxWx4 BGRA
        self._frame_event = threading.Event()
        self._error: str | None = None
        self._capture: windows_capture.WindowsCapture | None = None
        self._control: windows_capture.CaptureControl | None = None

    def start(self) -> None:
        """Start the WGC capture session."""
        self._capture = windows_capture.WindowsCapture(
            window_hwnd=self._hwnd,
            cursor_capture=False,
            draw_border=False,
        )
        self._capture.frame_handler = self._on_frame
        self._capture.closed_handler = self._on_closed
        self._control = self._capture.start_free_threaded()

        # Wait for first frame (or error)
        self._frame_event.wait(timeout=10.0)
        if self._error:
            raise RuntimeError(f"WGC capture failed: {self._error}")
        if self._latest_frame is None:
            raise RuntimeError("WGC capture started but no frame received within 10s")

    def stop(self) -> None:
        if self._control is not None:
            try:
                self._control.stop()
            except Exception:
                pass

    def _on_frame(self, frame, _ctrl) -> None:
        """WGC callback — called on WGC's thread with a new frame.

        frame.frame_buffer is a numpy array HxWx4 BGRA uint8.
        """
        arr = frame.frame_buffer.copy()
        with self._lock:
            self._latest_frame = arr
        self._frame_event.set()

    def _on_closed(self) -> None:
        if self._latest_frame is None and self._error is None:
            self._error = "Capture closed before first frame"
            self._frame_event.set()

    def get_frame(self) -> np.ndarray:
        """Return the latest frame as HxWx4 BGRA numpy array.

        Raises RuntimeError if no frame has been captured yet.
        """
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
