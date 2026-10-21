"""Frame-diff on the message log region for turn detection.

Polls the log region of the latest capture, compares to the previous sample,
and signals when enough pixels have changed.
"""

import time

import numpy as np

from bridge.capture import WindowCapture


class FrameDiffer:
    """Detects changes in a fixed region of the captured window."""

    def __init__(
        self,
        capture: WindowCapture,
        region: tuple[int, int, int, int],  # x, y, w, h
        threshold: int = 50,                # min changed pixels
        poll_interval: float = 0.05,        # seconds between polls
    ) -> None:
        self.capture = capture
        self.region = region
        self.threshold = threshold
        self.poll_interval = poll_interval
        self._baseline: np.ndarray | None = None

    def _sample(self) -> np.ndarray:
        x, y, w, h = self.region
        return self.capture.grab_region_array(x, y, w, h)

    def _diff_count(self, a: np.ndarray, b: np.ndarray) -> int:
        """Count pixels that differ between two BGRA arrays."""
        if a.shape != b.shape:
            return a.size  # shapes differ -> treat as fully changed
        diff = np.any(a != b, axis=2)
        return int(np.count_nonzero(diff))

    def reset_baseline(self) -> None:
        """Take a fresh baseline sample. Call before sending an action."""
        self._baseline = self._sample()

    def wait_for_change(self, timeout: float) -> tuple[bool, float]:
        """Block until the region changes or timeout expires.

        Returns (changed, elapsed_seconds).
        """
        if self._baseline is None:
            self.reset_baseline()

        start = time.monotonic()
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                return False, elapsed

            current = self._sample()
            changed_pixels = self._diff_count(self._baseline, current)
            if changed_pixels >= self.threshold:
                self._baseline = current
                return True, elapsed

            time.sleep(self.poll_interval)
