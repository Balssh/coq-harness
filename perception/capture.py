"""Capture and crop screenshots from the bridge into named regions."""

import io

from PIL import Image

from client.bridge_client import get_client
from perception.regions import (
    LOG_RECENT_HEIGHT,
    LOG_REGION,
    Perception,
    REGIONS,
)


def _png_to_image(png_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png_bytes)).convert("RGB")


def _crop(img: Image.Image, region: tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = region
    return img.crop((x, y, x + w, y + h))


def capture() -> Perception:
    """Grab a fresh full frame from the bridge and crop into all regions."""
    png = get_client().grab()
    full = _png_to_image(png)

    viewport = _crop(full, REGIONS["viewport"])
    log_full = _crop(full, LOG_REGION)
    # Crop log to recent lines (bottom of the log region)
    lw, lh = log_full.size
    log = log_full.crop((0, max(0, lh - LOG_RECENT_HEIGHT), lw, lh))
    stats = _crop(full, REGIONS["stats"])
    abilities = _crop(full, REGIONS["abilities"])

    return Perception(
        viewport=viewport,
        log=log,
        stats=stats,
        abilities=abilities,
        full=full,
    )


def capture_region(name: str) -> Image.Image:
    """Capture a single named region. For tools that only need one region."""
    if name not in REGIONS:
        raise ValueError(f"Unknown region: {name!r}. Valid: {list(REGIONS)}")
    region = REGIONS[name]
    x, y, w, h = region
    png = get_client().grab_region(x, y, w, h)
    return _png_to_image(png)


def capture_full() -> Image.Image:
    """Grab the full window frame as a PIL Image."""
    png = get_client().grab()
    return _png_to_image(png)
