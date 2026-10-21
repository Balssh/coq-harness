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

WAIT_TIMEOUT = 3.0

# Conversation context (grows unbounded for the demo)
_conversation: list[dict] = []


def get_conversation() -> list[dict]:
    return _conversation


def clear_conversation() -> None:
    _conversation.clear()


def run_turn(phase: str = "play") -> Decision:
    """Execute one full turn. Returns the Decision made."""
    state = get_state()
    recorder = get_recorder()
    client = get_client()
    transcript = get_transcript()
    journal = get_journal()

    turn_start = time.monotonic()

    # 1. Capture perception
    perception = capture()

    # 2. Record turn start
    recorder.start_turn(state.turn_count)

    # 3. Call decide()
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

    # 4. Record decision
    recorder.record_decision(decision)

    # 5. Update harness state
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

    # 6. Journal note
    if decision.journal_note:
        journal.add(decision.journal_note)

    # 7. Execute tool
    result = execute_tool(decision.tool, decision.args)
    recorder.record_tool_result(result)

    # Capture intermediate frame after action keys sent
    if result.error:
        recorder.capture("after-error")
    else:
        recorder.capture("after-action")

    # 8. Turn clock: wait for log change if tool advances turn
    turn_changed = False
    wait_time = 0.0
    tool = get_tool(decision.tool)
    if tool and tool.advances_turn:
        t0 = time.monotonic()
        turn_changed = client.wait_for_change(timeout=WAIT_TIMEOUT)
        wait_time = time.monotonic() - t0

    # 9. Record turn end
    recorder.end_turn(turn_changed=turn_changed, wait_time=wait_time)

    # 10. Record timing
    turn_total_ms = (time.monotonic() - turn_start) * 1000
    recorder.record_timing(decision_ms=decision_ms, turn_total_ms=turn_total_ms)

    # 11. Append to conversation context
    user_parts = []
    if result.text:
        user_parts.append(f"Tool result: {result.text}")
    if result.error:
        user_parts.append("(This was an error result.)")
    user_parts.append(
        f"Turn {state.turn_count + 1} complete. "
        f"Turn changed: {turn_changed}. "
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

    return decision
