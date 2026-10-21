"""Screen region constants and the Perception dataclass.

All coordinates are in window pixels, measured at a fixed Qud window
resolution. The window must not be resized during a run.

Measured at 1920x1080 (WGC capture resolution; window is 1536x864 at 125% DPI).
"""

from dataclasses import dataclass

from PIL import Image

# Region rectangles: (x, y, w, h) in window coordinates
# Measured from a real Qud screenshot at 1920x1080.
VIEWPORT_REGION   = (0, 0, 1440, 1000)
LOG_REGION        = (1440, 0, 480, 1000)
STATS_REGION      = (0, 1000, 1920, 40)
ABILITIES_REGION  = (0, 1040, 1920, 40)

WINDOW_WIDTH  = 1920
WINDOW_HEIGHT = 1080

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
