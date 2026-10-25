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
from tools import ToolResult, execute_tool, get_tool

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

    # Execute tool or keys (chargen tools don't advance turn)
    if decision.keys:
        from game.controller import press as _press, chord as _chord
        import time as _time
        sent = []
        for k in decision.keys:
            if isinstance(k, list):
                _chord(k)
                sent.append("+".join(k))
            else:
                _press(k)
                sent.append(k)
            _time.sleep(0.08)
        result = ToolResult(text=f"Sent keys: {' '.join(sent)}")
    elif decision.key:
        from game.controller import press
        press(decision.key)
        result = ToolResult(text=f"Pressed key: {decision.key}")
    else:
        result = execute_tool(decision.tool, decision.args)
    recorder.record_tool_result(result)
    # Skip after-action capture: turn-based game, no change before turn resolves
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

    # Bounded conversation — keep last 40 messages (20 turn-pairs)
    if len(_chargen_conversation) > 40:
        _chargen_conversation[:] = _chargen_conversation[-40:]

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
    """Quit to main menu and start a new game (for chargen retry).

    Sequence: Esc -> Save and Quit (or Abandon) -> title -> New Game (Enter)
    -> mode select -> Classic (Enter) -> preset/chargen screen.
    """
    from game.controller import press
    import time

    print("[chargen] Quitting to menu...")
    press("escape")
    time.sleep(0.5)
    # In the Esc menu, navigate to "Save and Quit" or "Quit to Menu"
    # The exact menu position varies — try the common path
    press("q")  # 'q' often = quit in Qud's menu
    time.sleep(0.5)
    press("enter")
    time.sleep(1.0)
    # Confirm quit if asked
    press("enter")
    time.sleep(1.5)
    # Now at main menu — New Game is the default cursor, press Enter
    press("enter")
    time.sleep(1.0)
    # Mode select — Classic is default, press Enter
    press("enter")
    time.sleep(1.0)
