"""Screen region constants and the Perception dataclass.

All coordinates are in window pixels, measured at a fixed Qud window
resolution. The window must not be resized during a run.

ACTUAL VALUES ARE PLACEHOLDERS — measure from a real Qud screenshot.
Default assumption: 1280x720 window.
"""

from dataclasses import dataclass

from PIL import Image

# Region rectangles: (x, y, w, h) in window coordinates
# PLACEHOLDER — measure from a real Qud screenshot at the chosen resolution.
VIEWPORT_REGION   = (0, 0, 960, 640)
LOG_REGION        = (960, 0, 320, 640)
STATS_REGION      = (0, 640, 1280, 40)
ABILITIES_REGION  = (0, 680, 1280, 40)

WINDOW_WIDTH  = 1280
WINDOW_HEIGHT = 720

# Number of recent log lines to keep (approximate pixel height per line ~16px)
LOG_LINE_HEIGHT = 16
LOG_LINES = 15

# Pixel height of the recent-log crop (bottom of log region)
LOG_RECENT_HEIGHT = LOG_LINES * LOG_LINE_HEIGHT


@dataclass
class Perception:
    viewport: Image.Image
    log: Image.Image
    stats: Image.Image
    abilities: Image.Image
    full: Image.Image  # full window frame (for recorder)


# Map region names to their rectangles
REGIONS: dict[str, tuple[int, int, int, int]] = {
    "viewport":  VIEWPORT_REGION,
    "log":       LOG_REGION,
    "stats":     STATS_REGION,
    "abilities": ABILITIES_REGION,
}
