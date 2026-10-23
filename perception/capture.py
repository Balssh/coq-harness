"""Capture and crop screenshots from the bridge into named regions."""

import io

from PIL import Image

from client.bridge_client import get_client
from perception.regions import (
    LOG_RECENT_HEIGHT,
    Perception,
    REGIONS,
)


def _png_to_image(png_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png_bytes)).convert("RGB")


def _crop(img: Image.Image, region: tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = region
    return img.crop((x, y, x + w, y + h))


def _scaled_regions(img_w: int, img_h: int) -> dict[str, tuple[int, int, int, int]]:
    """Scale the fixed 1920x1080 regions to the actual image size.

    Uses proportional scaling so crops stay correct even if the window
    is resized or the capture includes a small border.
    """
    sx = img_w / 1920.0
    sy = img_h / 1080.0
    result = {}
    for name, (x, y, w, h) in REGIONS.items():
        result[name] = (round(x * sx), round(y * sy), round(w * sx), round(h * sy))
    return result


def capture() -> Perception:
    """Grab a fresh full frame from the bridge and crop into all regions."""
    png = get_client().grab()
    full = _png_to_image(png)
    iw, ih = full.size

    regions = _scaled_regions(iw, ih)

    viewport = _crop(full, regions["viewport"])
    log_full = _crop(full, regions["log"])
    # Crop log to recent lines (bottom of the log region)
    lw, lh = log_full.size
    log = log_full.crop((0, max(0, lh - LOG_RECENT_HEIGHT), lw, lh))
    top_status = _crop(full, regions["top_status"])
    abilities = _crop(full, regions["abilities"])

    return Perception(
        viewport=viewport,
        log=log,
        top_status=top_status,
        abilities=abilities,
        full=full,
    )


def capture_region(name: str) -> Image.Image:
    """Capture a single named region. For tools that only need one region."""
    if name not in REGIONS:
        raise ValueError(f"Unknown region: {name!r}. Valid: {list(REGIONS)}")
    # Grab full frame and crop — grab_region on the bridge uses fixed coords
    # which may be off if the window size changed.
    png = get_client().grab()
    full = _png_to_image(png)
    iw, ih = full.size
    regions = _scaled_regions(iw, ih)
    return _crop(full, regions[name])


def capture_full() -> Image.Image:
    """Grab the full window frame as a PIL Image."""
    png = get_client().grab()
    return _png_to_image(png)
