"""Main turn loop for the MCP-based agent.

No screenshots — uses structured game state from the MCP server.
"""

import json
import time

from mcp.client import GameStateData, McpError, get_client
from mcp.decide import decide
from mcp.schemas import Decision
from mcp.tools import ToolResult, execute_tool, get_tool

MAX_CONVERSATION_TURNS = 20
WAIT_TIMEOUT = 30.0

_conversation: list[dict] = []
_recent_actions: list[str] = []
ANTI_REPEAT_THRESHOLD = 3


def get_conversation() -> list[dict]:
    return _conversation


def clear_conversation() -> None:
    _conversation.clear()
    _recent_actions.clear()


def run_turn(
    journal: str = "",
    phase: str = "play",
    on_state: callable = None,
    on_decision: callable = None,
    on_result: callable = None,
) -> tuple[Decision, GameStateData]:
    """Execute one full turn. Returns (Decision, new_state).

    Flow:
    1. Get current game state from MCP server
    2. Ask ML4 for a decision
    3. Execute the tool (sends command to MCP server)
    4. Wait for the game state to update (turn resolution)
    5. Return the decision and new state
    """
    client = get_client()

    state = client.get_state(timeout=WAIT_TIMEOUT)

    if on_state:
        on_state(state)

    decision = decide(
        state=state,
        conversation=_conversation,
        journal=journal,
        phase=phase,
    )

    if on_decision:
        on_decision(decision)

    result = execute_tool(decision.tool, decision.args)

    if on_result:
        on_result(decision, result)

    tool = get_tool(decision.tool)
    should_wait = (tool and tool.advances_turn) or decision.tool in (
        "auto_explore", "travel", "go_stairs"
    )

    if should_wait:
        try:
            new_state = client.wait_for_turn(timeout=WAIT_TIMEOUT)
        except McpError:
            new_state = client.get_state(timeout=WAIT_TIMEOUT)
    else:
        time.sleep(0.3)
        try:
            new_state = client.get_state(timeout=5.0)
        except McpError:
            new_state = state

    user_parts = []
    if result.text:
        user_parts.append(f"Tool result: {result.text}")
    if result.error:
        user_parts.append("(This was an error result.)")

    state_text = new_state.format_for_prompt(max_cells=50, max_messages=20)

    if len(_recent_actions) >= 3:
        recent = _recent_actions[-5:-1]
        user_parts.append(
            f"Your recent actions: {' → '.join(recent)}. "
            f"Do NOT repeat these — do something different."
        )

    action_str = f"{decision.tool}:{json.dumps(decision.args, sort_keys=True)}"
    _recent_actions.append(action_str)
    if len(_recent_actions) > 10:
        _recent_actions.pop(0)

    repeat_count = 0
    for a in reversed(_recent_actions):
        if a == action_str:
            repeat_count += 1
        else:
            break
    if repeat_count >= ANTI_REPEAT_THRESHOLD:
        user_parts.append(
            f"\n*** WARNING: You have called '{action_str}' {repeat_count} times "
            f"in a row with no progress. STOP repeating this action. "
            f"If movement is blocked, try a DIFFERENT direction. "
            f"If interact failed, try a different target. "
            f"DO NOT repeat the same action again. ***"
        )

    user_parts.append(f"\n## Updated Game State\n{state_text}")

    decision_dump = {
        "reasoning": decision.reasoning,
        "tool": decision.tool,
        "args": decision.args,
        "goal": decision.goal,
        "journal_note": decision.journal_note,
    }
    _conversation.append({
        "role": "assistant",
        "content": json.dumps(decision_dump, ensure_ascii=False),
    })
    _conversation.append({
        "role": "user",
        "content": "\n".join(user_parts),
    })

    max_messages = MAX_CONVERSATION_TURNS * 2
    if len(_conversation) > max_messages:
        _conversation[:] = _conversation[-max_messages:]

    return decision, new_state
