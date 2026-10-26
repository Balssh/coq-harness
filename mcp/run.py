"""Episode lifecycle manager for the MCP-based agent.

Simpler than the screenshot-based version — no bridge, no relay, no WSL.
Just connect to the in-game MCP server on localhost:47321.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from mcp.client import McpClient, McpError, get_client, init_client
from mcp.loop import clear_conversation, run_turn
from mcp.schemas import Decision
from mcp.tools import execute_tool

MAX_TURNS = 5000
MAX_EPISODE_SECONDS = 2 * 3600


def wait_for_game(client: McpClient, timeout: float = 120.0) -> None:
    """Poll the MCP server until it responds (Qud must be running with the mod)."""
    print(f"[run] Waiting for MCP server at {client.host}:{client.port} (timeout: {timeout}s)...")
    print("[run] Please launch Caves of Qud with the CoQ MCP Bridge mod enabled.")
    print("[run] Start or load a game, then take one step to activate the mod.")

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            state = client.get_state(timeout=5.0)
            print(f"[run] MCP server connected! Player: {state.name}, Location: {state.location}")
            return
        except McpError:
            pass
        time.sleep(2.0)
    raise RuntimeError(f"Timed out waiting for MCP server after {timeout}s")


def _make_run_dir(episode_num: int) -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    run_dir = Path("runs") / f"mcp_{date_str}_episode-{episode_num}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _log_event(run_dir: Path, event: dict) -> None:
    log_path = run_dir / "log.jsonl"
    event["timestamp"] = time.time()
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def run_episode(
    episode_num: int,
    mcp_host: str = "127.0.0.1",
    mcp_port: int = 47321,
    skip_chargen: bool = False,
) -> None:
    """Run one full episode."""
    client = init_client(host=mcp_host, port=mcp_port)
    print(f"[run] Connected to MCP server at {mcp_host}:{mcp_port}")

    wait_for_game(client)

    if not skip_chargen:
        state = client.get_state(timeout=10.0)
        if not state.in_game:
            print("[run] WARNING: Game is not in an active play state (title screen or chargen).")
            print("[run] MCP mode does not support character creation yet.")
            print("[run] Please start or load a game in Qud, then restart the agent.")
            print("[run] Use --skip-chargen to suppress this check.")
            return

    clear_conversation()

    run_dir = _make_run_dir(episode_num)
    print(f"[run] Logging to {run_dir}")

    _log_event(run_dir, {"type": "run_start", "episode": episode_num})

    journal_notes: list[str] = []
    journal_path = Path("runs") / "journal.json"
    if journal_path.exists():
        try:
            with open(journal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            journal_notes = data.get("notes", [])
        except Exception:
            pass

    episode_start = time.monotonic()
    turn_count = 0

    try:
        while True:
            if turn_count >= MAX_TURNS:
                print(f"[run] Turn budget exceeded: {turn_count}")
                break

            elapsed = time.monotonic() - episode_start
            if elapsed >= MAX_EPISODE_SECONDS:
                print(f"[run] Time budget exceeded: {elapsed / 3600:.1f} hours")
                break

            def on_state(state):
                _log_event(run_dir, {
                    "type": "state",
                    "turn": turn_count,
                    "hp": state.hp,
                    "hpMax": state.hp_max,
                    "level": state.level,
                    "location": state.location,
                    "position": state.position,
                    "inCombat": state.in_combat,
                    "messages": state.messages[-10:],
                })

            def on_decision(decision: Decision):
                _log_event(run_dir, {
                    "type": "decision",
                    "turn": turn_count,
                    "reasoning": decision.reasoning,
                    "tool": decision.tool,
                    "args": decision.args,
                    "goal": decision.goal,
                    "journal_note": decision.journal_note,
                })
                if decision.journal_note:
                    journal_notes.append(decision.journal_note)

            def on_result(decision: Decision, result):
                _log_event(run_dir, {
                    "type": "tool_result",
                    "turn": turn_count,
                    "tool": decision.tool,
                    "text": result.text,
                    "error": result.error,
                })

            decision, new_state = run_turn(
                journal="\n".join(journal_notes[-20:]),
                phase="play",
                on_state=on_state,
                on_decision=on_decision,
                on_result=on_result,
            )

            turn_count += 1

            if turn_count % 10 == 0:
                print(f"[run] Turn {turn_count}: HP {new_state.hp}/{new_state.hp_max}, "
                      f"Level {new_state.level}, Location: {new_state.location}")

            death_msgs = ("you die", "you are dead", "game over", "rest in peace",
                          "tombstone", "your journey ends")
            recent_msgs = " ".join(state.messages[-5:]).lower() if (state := new_state) else ""
            died = (
                new_state.is_dead
                or (new_state.hp is not None and new_state.hp <= 0)
                or any(dm in recent_msgs for dm in death_msgs)
            )
            if died:
                print("[run] Player died!")
                break

            if decision.tool == "abandon":
                print("[run] Model chose to abandon the run.")
                break

            if decision.tool == "quit":
                print("[run] Model chose to quit.")
                break

    except KeyboardInterrupt:
        print("\n[run] Interrupted by user.")
    except McpError as exc:
        print(f"\n[run] MCP error: {exc}")
    finally:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(journal_path, "w", encoding="utf-8") as f:
            json.dump({"notes": journal_notes}, f, indent=2, ensure_ascii=False)

        _log_event(run_dir, {
            "type": "run_end",
            "episode": episode_num,
            "turns": turn_count,
            "duration_seconds": round(time.monotonic() - episode_start, 1),
        })

        print(f"\n[run] Episode {episode_num} ended at turn {turn_count}")
        print(f"[run] Log saved to: {run_dir}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="CoQ MCP Harness — ML4 plays Caves of Qud via in-game MCP server"
    )
    parser.add_argument("--host", default="127.0.0.1", help="MCP server host")
    parser.add_argument("--port", type=int, default=47321, help="MCP server port")
    parser.add_argument("--episode", type=int, default=1, help="Starting episode number")
    parser.add_argument("--skip-chargen", action="store_true",
                        help="Skip character creation — continue from current game state")
    args = parser.parse_args()

    episode_num = args.episode
    while True:
        try:
            run_episode(
                episode_num,
                mcp_host=args.host,
                mcp_port=args.port,
                skip_chargen=args.skip_chargen,
            )
        except RuntimeError as exc:
            print(f"\n[run] Error: {exc}")
            try:
                input("Press Enter to retry, or Ctrl+C to quit...")
            except (KeyboardInterrupt, EOFError):
                break
        except KeyboardInterrupt:
            print("\n[run] Interrupted by user.")
            break

        print(f"\n--- Episode {episode_num} ended ---")
        try:
            input("Press Enter to start a new episode, or Ctrl+C to quit...")
        except (KeyboardInterrupt, EOFError):
            break
        episode_num += 1


if __name__ == "__main__":
    main()
