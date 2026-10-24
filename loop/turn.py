"""The main turn loop: capture -> decide -> execute -> wait -> record."""

import json
import time

from agent.decide import decide
from agent.schemas import Decision
from client.bridge_client import get_client
from recording.recorder import get_recorder
from memory.journal import get_journal
from memory.state import get_state, update
from memory.transcript import get_transcript
from perception.capture import capture
from tools import execute_tool, get_tool

WAIT_TIMEOUT = 1.5

MAX_CONVERSATION_TURNS = 20
_conversation: list[dict] = []


def get_conversation() -> list[dict]:
    return _conversation


def clear_conversation() -> None:
    _conversation.clear()


def run_turn(phase: str = "play") -> tuple[Decision, bool]:
    """Execute one full turn. Returns (Decision, turn_changed)."""
    state = get_state()
    recorder = get_recorder()
    client = get_client()
    transcript = get_transcript()
    journal = get_journal()

    turn_start = time.monotonic()

    perception = capture()
    recorder.start_turn(state.turn_count)

    decision_start = time.monotonic()
    decision = decide(
        perception=perception,
        transcript=transcript.get(max_turns=30),
        conversation=_conversation,
        journal=journal.get(),
        state=state,
        phase=phase,
    )
    decision_ms = (time.monotonic() - decision_start) * 1000

    recorder.record_decision(decision)

    update(
        turn_count=state.turn_count + 1,
        screen=decision.screen,
        goal=decision.goal,
        hp=decision.hp,
        max_hp=decision.max_hp,
        hunger=decision.hunger,
        location=decision.location,
        phase=decision.screen,
    )

    if decision.journal_note:
        journal.add(decision.journal_note)

    result = execute_tool(decision.tool, decision.args)
    recorder.record_tool_result(result)

    if result.error:
        recorder.capture("after-error")
    else:
        recorder.capture("after-action")

    # Turn clock: wait for log change if the tool advances the turn
    # OR if the model explicitly set wait_for_turn=true (e.g., for press())
    tool = get_tool(decision.tool)
    should_wait = (tool and tool.advances_turn) or decision.wait_for_turn

    turn_changed = False
    wait_time = 0.0
    if should_wait:
        t0 = time.monotonic()
        turn_changed = client.wait_for_change(timeout=WAIT_TIMEOUT)
        wait_time = time.monotonic() - t0

    recorder.end_turn(turn_changed=turn_changed, wait_time=wait_time)

    turn_total_ms = (time.monotonic() - turn_start) * 1000
    recorder.record_timing(decision_ms=decision_ms, turn_total_ms=turn_total_ms)

    user_parts = []
    if result.text:
        user_parts.append(f"Tool result: {result.text}")
    if result.error:
        user_parts.append("(This was an error result.)")
    if should_wait and not turn_changed:
        user_parts.append(
            "Note: The message log did not change after this action. "
            "This is normal for actions like bumping into a wall, waiting, "
            "or certain menu interactions — the turn still advanced, "
            "there was just no new log message."
        )
    user_parts.append(
        f"Turn {state.turn_count + 1} complete. "
        f"HP: {decision.hp or '?'}/{decision.max_hp or '?'}, "
        f"Hunger: {decision.hunger or '?'}, "
        f"Location: {decision.location or '?'}"
    )
    _conversation.append({
        "role": "assistant",
        "content": json.dumps(decision.model_dump(), ensure_ascii=False),
    })
    _conversation.append({
        "role": "user",
        "content": "\n".join(user_parts),
    })

    max_messages = MAX_CONVERSATION_TURNS * 2
    if len(_conversation) > max_messages:
        _conversation[:] = _conversation[-max_messages:]

    return decision, turn_changed
