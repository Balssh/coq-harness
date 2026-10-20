# Spec: Perception

## Purpose

Crops the full Qud screenshot into regions the model needs, and prepares them
for the LLM API. Not all regions are sent every turn — see "Image Delivery" below.

## Regions

Four regions are cropped from the full window screenshot:

| Region | Location | Resolution | Notes |
|--------|----------|------------|-------|
| **Viewport** | Main game area (left/center) | Full res | Tiles, @, enemies, items, terrain. No downscaling for now; optimize later if needed |
| **Log** | Right side | Full res | Message log. Cropped to recent ~15 lines (old messages are usually irrelevant) |
| **Stats bar** | Bottom strip | Full res | HP, hunger, level, AV, DV, etc. |
| **Abilities bar** | Bottom strip | Full res | Available abilities/commands bound to keys |

## Image Delivery

Not all four regions are sent to the model every turn. Token cost matters.

| When | Regions sent |
|------|-------------|
| Every turn | viewport + log |
| Episode start (turn 0) | viewport + log + stats + abilities |
| Every 10 turns | viewport + log + stats + abilities (periodic refresh) |
| On request | `read_stats()` tool returns stats + abilities crops |

## Crop Coordinates

Hardcoded at a **fixed Qud window resolution**. The window must not be resized
during a run — changing the resolution invalidates all crop coordinates.

Coordinates are measured once from a Qud screenshot and stored as constants:

```python
# Example — actual values TBD after measuring a Qud screenshot
VIEWPORT_REGION = (0, 0, 960, 640)       # x, y, w, h
LOG_REGION      = (960, 0, 320, 640)
STATS_REGION    = (0, 640, 1280, 40)
ABILITIES_REGION = (0, 680, 1280, 40)

LOG_LINES = 15  # number of recent log lines to keep
```

The log region is cropped further to the bottom ~15 lines (most recent messages).

## API

```python
from PIL import Image

@dataclass
class Perception:
    viewport: Image.Image    # PIL Image, full res
    log: Image.Image         # PIL Image, full res, cropped to recent lines
    stats: Image.Image       # PIL Image, full res
    abilities: Image.Image   # PIL Image, full res

def capture() -> Perception:
    """Grab a fresh frame from the bridge and crop into regions."""
    ...

def capture_region(name: str) -> Image.Image:
    """Capture a single named region. For tools that only need one region."""
    ...
```

## Image Delivery to the Model

Images are converted to PNG bytes, then base64-encoded for the LLM API conversation.
The agent module (`agent/llm.py`) handles encoding — perception just returns PIL Images.

```python
# In agent/llm.py (not perception)
import base64, io

def image_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")
```

## File Layout

```
perception/
  __init__.py
  regions.py      # region constants (coordinates), Perception dataclass
  capture.py      # capture(), capture_region() — grabs frame, crops
```

## Dependencies

- `client/bridge_client.py` (for grabbing frames)
- `pillow` (PIL) for image cropping
- `game/screens.py` (for Screen enum, if needed)

## Open Items

- Exact crop coordinates TBD — need a Qud screenshot at the chosen window resolution.
- Fixed window resolution TBD — pick one and lock Qud to it.
- Log line cropping: "last 15 lines" assumes a fixed line height. May need to
  measure line height from a screenshot, or just crop a fixed pixel height.
- Downscaling: not now, but if token cost or latency becomes a problem, the
  viewport is the first candidate (log and stats must stay full res for readability).
