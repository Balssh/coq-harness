"""Screen region constants and the Perception dataclass.

All coordinates are in window pixels, measured at a fixed Qud window
resolution. The window must not be resized during a run.

Measured at 1920x1080 (WGC capture resolution; window is 1536x864 at 125% DPI).

Actual Qud layout (play screen):
  - Top status bar:    y=0..54    (HP, level, XP, temperature, time, date)
  - Gameplay viewport: y=54..972  x=0..1440   (tile-based world, ~75% width)
  - Message log:       y=54..972  x=1440..1920 (scrollable text, ~25% width)
  - Abilities bar:     y=972..1080 (ability icons with hotkeys, full width)
"""

from dataclasses import dataclass

from PIL import Image

# Region rectangles: (x, y, w, h) in window coordinates
TOP_STATUS_REGION = (0, 0, 1920, 54)
VIEWPORT_REGION   = (0, 54, 1440, 918)
LOG_REGION        = (1440, 54, 480, 918)
ABILITIES_REGION  = (0, 972, 1920, 108)

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
    top_status: Image.Image
    abilities: Image.Image
    full: Image.Image  # full window frame (for recorder, and for non-play screens)


# Map region names to their rectangles
REGIONS: dict[str, tuple[int, int, int, int]] = {
    "top_status": TOP_STATUS_REGION,
    "viewport":   VIEWPORT_REGION,
    "log":        LOG_REGION,
    "abilities":  ABILITIES_REGION,
}
