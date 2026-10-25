"""Episode lifecycle manager.

Lifecycle: wait for game -> chargen -> play -> death -> pause -> next episode.
The user launches Qud manually. The harness connects to the bridge and waits.
"""

import sys
import time
from datetime import datetime
from pathlib import Path

from client.bridge_client import BridgeClient, BridgeError, get_client, init_client
from recording.recorder import get_recorder, start_recorder, stop_recorder
from loop.phases import Phase, current_phase, phase_from_screen, transition_to
from loop.turn import clear_conversation, run_turn
from loop.watchdog import WatchdogAction, get_watchdog
from memory.journal import get_journal
from memory.state import get_state, reset as reset_state, update
from memory.transcript import get_transcript

# Module-level restart signal (set by restart_run tool)
_restart_requested = False


def signal_restart() -> None:
    global _restart_requested
    _restart_requested = True


def _consume_restart() -> bool:
    global _restart_requested
    if _restart_requested:
        _restart_requested = False
        return True
    return False


def wait_for_game(client: BridgeClient, timeout: float = 60.0) -> None:
    """Poll the bridge until the Qud window is available."""
    print(f"[run] Waiting for Qud window (timeout: {timeout}s)...")
    print("[run] Please launch Caves of Qud on Windows.")
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            result = client.ping()
            if result.get("status") == "ok":
                # Try a grab to confirm the window is actually there
                try:
                    client.grab()
                    print("[run] Qud window found!")
                    return
                except BridgeError:
                    pass  # window not found yet
        except BridgeError:
            pass  # bridge not up yet or window not found
        time.sleep(2.0)
    raise RuntimeError(f"Timed out waiting for Qud window after {timeout}s")


def _make_run_dir(episode_num: int) -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    run_dir = Path("runs") / f"{date_str}_episode-{episode_num}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def run_episode(episode_num: int, bridge_host: str = "localhost", bridge_port: int = 9090, skip_chargen: bool = False) -> None:
    """Run one full episode: chargen -> play -> death -> pause.
    If skip_chargen is True, goes straight to play (for continuing an existing game)."""
    from run.creation import run_chargen

    # Connect to bridge
    client = init_client(host=bridge_host, port=bridge_port)
    print(f"[run] Connected to bridge at {bridge_host}:{bridge_port}")

    # Wait for Qud
    wait_for_game(client)

    # Reset state for new episode
    reset_state()
    get_transcript().clear()
    clear_conversation()
    get_watchdog().reset()

    # Load journal from disk
    journal = get_journal()
    journal_path = Path("runs") / "journal.json"
    journal.load(str(journal_path))
    if journal.get():
        print(f"[run] Loaded journal with {len(journal.get().splitlines())} notes")

    # Start recorder
    run_dir = _make_run_dir(episode_num)
    recorder = start_recorder(str(run_dir))
    print(f"[run] Recording to {run_dir}")

    # Start episode watchdog
    get_watchdog().start_episode()

    try:
        if skip_chargen:
            # Skip chargen — continuing from an existing game in play mode
            print("[run] Skipping chargen (continuing existing game)")
            # Clear any lingering menus/dialogs from previous session
            from game.controller import press
            press("escape")
            import time as _time
            _time.sleep(0.5)
            press("escape")
            _time.sleep(0.5)
            transition_to(Phase.PLAY)
            update(phase="play", screen="play", turn_count=0)
        else:
            # Phase 1: Character creation
            transition_to(Phase.CHARGEN)
            update(phase="chargen")
            chargen_ok = run_chargen()
            if not chargen_ok:
                print("[run] Chargen failed after all retries. Ending episode.")
                recorder.save_meta(episode=episode_num, result="chargen_failed")
                return

            # Phase 2: Play
            transition_to(Phase.PLAY)
            update(phase="play")

        _play_loop()

    finally:
        # Save journal
        journal.save(str(journal_path))
        # Save meta + close recorder
        state = get_state()
        recorder.save_meta(
            episode=episode_num,
            final_turn=state.turn_count,
            final_location=state.location,
            final_hp=state.hp,
            final_goal=state.goal,
        )
        stop_recorder()
        print(f"\n[run] Episode {episode_num} ended at turn {state.turn_count}")
        print(f"[run] Recording saved to: {run_dir}")
        print(f"[run] Replay: python -m recording.replay {run_dir}")


def _play_loop() -> None:
    """Main play loop. Runs until death, watchdog trigger, or restart signal."""
    state = get_state()
    watchdog = get_watchdog()

    while True:
        if _consume_restart():
            print("[run] Restart requested by model.")
            transition_to(Phase.DEATH)
            break

        decision, turn_changed = run_turn(phase="play")
        state = get_state()

        # Check phase from model's report
        screen_phase = phase_from_screen(decision.screen)

        if screen_phase == Phase.DEATH:
            print("[run] Model reported death screen. Episode ending.")
            transition_to(Phase.DEATH)
            break

        if screen_phase == Phase.CHARGEN:
            print("[run] WARNING: Model reported chargen during play. Continuing.")

        # Watchdog check with actual turn_changed value
        action = watchdog.check_play(
            screen=decision.screen,
            turn_count=state.turn_count,
            turn_changed=turn_changed,
        )

        if action == WatchdogAction.END_EPISODE:
            print("[run] Watchdog triggered end of episode.")
            transition_to(Phase.DEATH)
            break


def main() -> None:
    """Entry point. Loops: run episode -> pause -> wait for user -> next episode."""
    import argparse

    parser = argparse.ArgumentParser(description="CoQ Harness — ML4 plays Caves of Qud")
    parser.add_argument("--host", default="localhost", help="Bridge host (default: localhost)")
    parser.add_argument("--port", type=int, default=9090, help="Bridge port (default: 9090)")
    parser.add_argument("--episode", type=int, default=1, help="Starting episode number")
    parser.add_argument("--skip-chargen", action="store_true",
                        help="Skip character creation — continue from current game state")
    args = parser.parse_args()

    episode_num = args.episode
    while True:
        try:
            run_episode(episode_num, bridge_host=args.host, bridge_port=args.port,
                        skip_chargen=args.skip_chargen)
        except BridgeError as exc:
            print(f"\n[run] Bridge error: {exc}")
            print("[run] Is the bridge running on Windows? Restart it and try again.")
            try:
                input("Press Enter to retry, or Ctrl+C to quit...")
            except (KeyboardInterrupt, EOFError):
                break
        except KeyboardInterrupt:
            print("\n[run] Interrupted by user.")
            break
        except Exception as exc:
            print(f"\n[run] Unexpected error: {exc}")
            import traceback
            traceback.print_exc()
            try:
                input("Press Enter to continue to next episode, or Ctrl+C to quit...")
            except (KeyboardInterrupt, EOFError):
                break

        print(f"\n--- Episode {episode_num} ended ---")
        try:
            input("Press Enter to start a new episode, or Ctrl+C to quit...")
        except (KeyboardInterrupt, EOFError):
            break
        episode_num += 1
