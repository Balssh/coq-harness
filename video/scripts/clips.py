"""Pull gameplay clips out of recorded runs for the video.

For each clip below, copies the run's frames (runs/harness/<run>/frames) into public/clips/<clip>/
and writes src/clips.generated.json: per frame, the step, HP, level and zone, and the model's
thought and tool call for that step, so the video can caption the footage with what ML4 was thinking.

    uv run python video/scripts/clips.py
"""
import json
import re
import shutil
from pathlib import Path

VIDEO = Path(__file__).resolve().parents[1]
RUNS = VIDEO.parent / "runs" / "harness"
OUT_DIR = VIDEO / "public" / "clips"
OUT = VIDEO / "src" / "clips.generated.json"

# clip name -> (run name suffix, first step, last step)
CLIPS = {
    "joppa": ("ml4-opening-8", 1, 30),
    "trade": ("ml4-opening-8", 30, 42),
    "baboons": ("ml4-opening-8", 110, 121),
    "frustum": ("ml4-opening-2", 88, 118),
}


def clean(text: str) -> str:
    text = re.sub(r"\{\{\w\|", "", text or "").replace("}}", "")  # Qud colour markup
    return " ".join(text.split())


def first_sentences(text: str, limit: int = 180) -> str:
    text = clean(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[:end + 1] if end > 60 else cut.rstrip() + "…"


def call_str(name: str, args: dict) -> str:
    return f"{name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"


def extract(name: str, run: str, first: int, last: int) -> list[dict]:
    run_dir = next(RUNS.glob(f"*_{run}"))
    events = [json.loads(line) for line in (run_dir / "events.jsonl").open()]
    thought: dict[int, str] = {}
    calls: dict[int, dict] = {}
    for e in events:
        if e["type"] == "llm" and first <= e["step"] <= last:
            thought[e["step"]] = first_sentences(e.get("text") or e.get("reasoning") or "")
        elif e["type"] == "tool" and e.get("snapshot") is not None:
            calls[e["snapshot"]] = e
    dest = OUT_DIR / name
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    frames = []
    for e in events:
        if e["type"] != "snapshot" or not first <= e["step"] <= last or not e.get("frame"):
            continue
        src = run_dir / e["frame"]
        if not src.exists():
            continue
        out = dest / f"{len(frames):03d}.jpg"
        shutil.copyfile(src, out)
        call = calls.get(e["index"])
        frames.append({
            "src": f"clips/{name}/{out.name}", "step": e["step"],
            "hp": e["hp"], "hpMax": e["hpMax"], "level": e["level"], "zone": clean(e["zone"]),
            "dead": e.get("dead", False),
            "thought": thought.get(e["step"], ""),
            "call": call_str(call["name"], call["args"]) if call else "",
            "result": clean(call["result"].split("\n")[0])[:120] if call else "",
        })
    return frames


def main() -> None:
    data = {name: extract(name, *spec) for name, spec in CLIPS.items()}
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    for name, frames in data.items():
        print(f"{name}: {len(frames)} frames, {sum(1 for f in frames if f['thought'])} with thoughts")


if __name__ == "__main__":
    main()
