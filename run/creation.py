"""Model-led character creation.

The model navigates Qud's chargen screens using the chargen tools
(select, confirm, back, name_random). Budget: 100 steps / 10 min, max 3 retries.
"""

import time

from agent.decide import decide
from client.bridge_client import get_client
from recording.recorder import get_recorder
from loop.watchdog import WatchdogAction, get_watchdog
from memory.journal import get_journal
from memory.state import get_state, update
from perception.capture import capture
from tools import execute_tool, get_tool

MAX_CHARGEN_RETRIES = 3

# Chargen-only conversation context
_chargen_conversation: list[dict] = []


def _chargen_turn() -> str:
    """Run one chargen step. Returns the model-reported screen string."""
    state = get_state()
    recorder = get_recorder()

    # Capture
    perception = capture()
    recorder.start_turn(state.turn_count)

    # Decide (chargen phase)
    decision = decide(
        perception=perception,
        transcript="",  # no transcript during chargen
        conversation=_chargen_conversation,
        journal=get_journal().get(),
        state=state,
        phase="chargen",
    )

    # Record
    recorder.record_decision(decision)

    # Update state
    update(
        turn_count=state.turn_count + 1,
        screen=decision.screen,
        goal=decision.goal,
    )

    # Journal note
    if decision.journal_note:
        get_journal().add(decision.journal_note)

    # Execute tool (chargen tools don't advance turn)
    result = execute_tool(decision.tool, decision.args)
    recorder.record_tool_result(result)
    recorder.capture("after-action")
    recorder.end_turn(turn_changed=False, wait_time=0.0)

    # Add to conversation
    import json
    _chargen_conversation.append({
        "role": "assistant",
        "content": json.dumps(decision.model_dump(), ensure_ascii=False),
    })
    _chargen_conversation.append({
        "role": "user",
        "content": f"Turn {state.turn_count + 1}. Screen: {decision.screen}. "
                   f"Tool result: {result.text}",
    })

    return decision.screen


def run_chargen() -> bool:
    """Run model-led chargen. Returns True if successful, False if all retries exhausted."""
    watchdog = get_watchdog()

    for attempt in range(1, MAX_CHARGEN_RETRIES + 1):
        print(f"\n[chargen] Attempt {attempt}/{MAX_CHARGEN_RETRIES}")
        _chargen_conversation.clear()
        watchdog.start_chargen()
        update(turn_count=0, screen="chargen", phase="chargen")

        success = _chargen_loop()
        if success:
            print("[chargen] Character creation complete!")
            return True

        print(f"[chargen] Attempt {attempt} failed.")
        if attempt < MAX_CHARGEN_RETRIES:
            print("[chargen] Retrying... (quit to menu and start new game)")
            _quit_to_menu_and_restart()

    print("[chargen] All retries exhausted.")
    return False


def _chargen_loop() -> bool:
    """Run chargen steps until the model reports 'play' screen or watchdog triggers."""
    watchdog = get_watchdog()
    state = get_state()

    while True:
        screen = _chargen_turn()
        state = get_state()

        if screen == "play":
            return True

        if screen == "death":
            print("[chargen] Model reported death during chargen?!")
            return False

        # Watchdog check
        action = watchdog.check_chargen(screen=screen)
        if action == WatchdogAction.RESTART_CHARGEN:
            return False


def _quit_to_menu_and_restart() -> None:
    """Quit to main menu and start a new game (for chargen retry)."""
    from game.controller import press
    import time

    print("[chargen] Quitting to menu...")
    press("escape")
    time.sleep(0.5)
    press("q")  # quit to menu
    time.sleep(0.5)
    press("enter")
    time.sleep(1.0)
    # Now at main menu — select "New Game"
    press("enter")
    time.sleep(1.0)
