"""Screen capture via Windows Graphics Capture (WGC), by window title.

WGC captures the window even when fully occluded or off-screen.
The latest frame is kept in memory; grab() returns it as PNG bytes.
"""

import io
import threading
import time

import numpy as np
import windows_capture
from PIL import Image


class WindowCapture:
    """Continuously captures a window by title using WGC."""

    def __init__(self, window_title: str) -> None:
        self.window_title = window_title
        self._lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None  # HxWx4 BGRA
        self._frame_event = threading.Event()
        self._running = False
        self._capture_thread: threading.Thread | None = None
        self._error: str | None = None

    def start(self) -> None:
        """Start the WGC capture session in a background thread."""
        self._running = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        # Wait for first frame (or error)
        self._frame_event.wait(timeout=10.0)
        if self._error:
            raise RuntimeError(f"WGC capture failed: {self._error}")

    def stop(self) -> None:
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=5.0)

    def _capture_loop(self) -> None:
        try:
            capture = windows_capture.WindowsGraphicsCapture(
                window_name=self.window_title,
            )
            capture.start(self._on_frame)
            while self._running:
                time.sleep(0.1)
            capture.stop()
        except Exception as exc:
            self._error = str(exc)
            self._frame_event.set()

    def _on_frame(self, frame) -> None:
        """WGC callback — called on WGC's thread with a new frame."""
        # frame.buffer is a flat BGRA byte array; frame.width/height give dims
        arr = np.frombuffer(frame.buffer, dtype=np.uint8).reshape(
            frame.height, frame.width, 4
        )
        with self._lock:
            self._latest_frame = arr.copy()
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
