"""Command line: play a run, or replay recorded runs.

    python -m harness play [--model M] [--max-steps N] [--new-game] ...
    python -m harness replay [RUN]
    python -m harness export RUN [--speed 2] [--smart] [--annotations]
    python -m harness.deploy            # copy the mod into Qud's Mods folder
"""

import argparse
import asyncio
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _play(args) -> None:
    from harness.agent import DEFAULT_OBJECTIVE, Agent, Config
    from harness.llm import make_client

    extra = json.loads(args.extra_body) if args.extra_body else {}
    llm = make_client(args.provider, REPO_ROOT, model=args.model, base_url=args.base_url, key_env=args.key_env,
                      reasoning=args.reasoning, temperature=args.temperature, extra_body=extra)
    cfg = Config(objective=args.objective or DEFAULT_OBJECTIVE, max_steps=args.max_steps,
                 max_minutes=args.max_minutes, new_game=args.new_game, character=args.character,
                 screenshots=not args.no_screenshots,
                 keep_steps=args.keep_steps, runs_dir=REPO_ROOT / "runs" / "harness",
                 journal=REPO_ROOT / "runs" / "journal.md", label=args.label,
                 llm_info={"provider": args.provider, "temperature": args.temperature,
                           "extra_body": llm.extra_body})
    asyncio.run(Agent(cfg, llm, REPO_ROOT).run())


def _replay(args) -> None:
    from harness.replay import serve

    root = REPO_ROOT / "runs" / "harness"
    run = None
    if args.run:
        p = Path(args.run)
        run = p.name if p.exists() else args.run
    serve(root, run, port=args.port, open_browser=not args.no_browser)


def _export(args) -> None:
    from harness.video import export

    root = REPO_ROOT / "runs" / "harness"
    run_dir = Path(args.run) if Path(args.run).exists() else root / args.run
    if not (run_dir / "meta.json").exists():
        raise SystemExit(f"no run at {run_dir}")

    def progress(done: int, total: int) -> None:
        if done == total or done % 25 == 0:
            print(f"  {done}/{total} frames")
    out = export(run_dir, Path(args.out) if args.out else None, args.seconds_per_frame, speed=args.speed,
                 smart=args.smart, annotations=args.annotations, progress=progress)
    print(f"Wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m harness", description="LLM plays Caves of Qud through the MCP server.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("play", help="play one run (Qud must be running with the mod)")
    p.add_argument("--provider", default="mistral", help="mistral (default), openai, openrouter, or any name with --base-url")
    p.add_argument("--model", help="model id (default for mistral: mistral-large-4)")
    p.add_argument("--base-url", help="OpenAI-compatible API base URL, e.g. http://localhost:8000/v1")
    p.add_argument("--key-env", help="environment variable holding the API key")
    p.add_argument("--reasoning", help="reasoning_effort to request: high (Mistral default), medium, low, none; "
                   "'default' sends nothing and lets the model decide")
    p.add_argument("--temperature", type=float)
    p.add_argument("--extra-body", help='extra JSON for the chat request, e.g. \'{"reasoning_effort": "high"}\'')
    p.add_argument("--max-steps", type=int, default=300, help="model responses before stopping (default 300)")
    p.add_argument("--max-minutes", type=float, default=0, help="wall-clock limit (default none)")
    p.add_argument("--new-game", action="store_true", help="start a new character (see --character) "
                   "instead of continuing the last save")
    p.add_argument("--character", default="choose", help="for --new-game: 'choose' (default; the model picks, "
                   "preferring the game's preset characters), 'random', or a preset name such as 'Marsh Taur'")
    p.add_argument("--objective", help="replace the default objective in the system prompt")
    p.add_argument("--keep-steps", type=int, default=24, help="steps kept verbatim before older ones are summarized")
    p.add_argument("--no-screenshots", action="store_true", help="don't capture the game window")
    p.add_argument("--label", default="", help="name for this run in the replay list")
    p.set_defaults(func=_play)

    r = sub.add_parser("replay", help="open the replay viewer")
    r.add_argument("run", nargs="?", help="run id or directory (default: list all runs)")
    r.add_argument("--port", type=int, default=8765)
    r.add_argument("--no-browser", action="store_true")
    r.set_defaults(func=_replay)

    e = sub.add_parser("export", help="render a recorded run to MP4 (needs ffmpeg)")
    e.add_argument("run", help="run id or directory")
    e.add_argument("--speed", type=float, default=1.0, help="playback speed: 2 = twice as fast, 0.5 = half (default 1)")
    e.add_argument("--seconds-per-frame", type=float, default=1.0,
                   help="how long each snapshot is shown at speed 1 (default 1.0)")
    e.add_argument("--smart", action="store_true", help="smart pacing: linger on fights and events, skip idle frames")
    e.add_argument("--annotations", action="store_true", help="burn the reviewer notes from the viewer into the video")
    e.add_argument("--out", help="output file (default: <run>/replay_<speed>x[_smart][_notes].mp4)")
    e.set_defaults(func=_export)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
