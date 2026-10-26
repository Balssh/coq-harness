"""Decision flow for the MCP-based agent.

No images — the agent sees structured game state as text.
"""

import json
from pathlib import Path

from mcp.client import GameStateData
from mcp.llm import call_llm
from mcp.schemas import Decision, parse_decision
from mcp.tools import all_tools, get_tool, tools_for_screen

_PROMPTS_DIR = Path(__file__).parent / "prompts"

MAX_RETRIES = 3


def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def _format_tools() -> str:
    lines = []
    for t in all_tools():
        args_desc = ""
        if t.parameters.get("properties"):
            props = t.parameters["properties"]
            required = t.parameters.get("required", [])
            parts = []
            for pname, pspec in props.items():
                req = " (required)" if pname in required else " (optional)"
                enum = f" [{', '.join(str(e) for e in pspec['enum'])}]" if "enum" in pspec else ""
                parts.append(f"{pname}{req}{enum}")
            args_desc = f" — args: {', '.join(parts)}"
        turn = " [advances turn]" if t.advances_turn else ""
        lines.append(f"- `{t.name}`{turn}{args_desc}: {t.description}")
    return "\n".join(lines)


def build_system_prompt() -> str:
    base = _load_prompt("system_base.md")
    base = base.replace("{TOOLS}", _format_tools())
    fewshot = _load_prompt("fewshot.md")
    play = _load_prompt("system_play.md")
    return "\n\n".join([base, fewshot, play])


def decide(
    state: GameStateData,
    conversation: list[dict],
    journal: str,
    phase: str = "play",
) -> Decision:
    """Run one decision cycle using structured state (no images)."""
    system_prompt = build_system_prompt()

    state_text = state.format_for_prompt()

    turn_text_parts = []
    turn_text_parts.append(f"## Current Game State\n{state_text}")
    if journal:
        turn_text_parts.append(f"\n## Journal (cross-episode notes)\n{journal}")
    turn_text_parts.append(
        "\n## Your Turn\n"
        "Analyze the game state above and respond with a single JSON object "
        "calling one tool, as described in the system prompt."
    )
    turn_text = "\n\n".join(turn_text_parts)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation)
    messages.append({"role": "user", "content": turn_text})

    available_tools = all_tools()
    available_names = ", ".join(sorted(t.name for t in available_tools))

    for attempt in range(MAX_RETRIES):
        raw = call_llm(messages)

        decision = parse_decision(raw)
        if decision is None:
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": (
                    "Your response was not valid JSON. Please respond with a single "
                    f"JSON object matching the schema. Error: could not parse JSON.\n"
                    f"Your response was:\n{raw[:500]}"
                ),
            })
            continue

        tool = get_tool(decision.tool)
        if tool is None:
            all_names = ", ".join(sorted(t.name for t in all_tools()))
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"Tool '{decision.tool}' does not exist. Available tools: {all_names}",
            })
            continue

        return decision

    print("[decide] All retries exhausted, falling back to wait")
    return Decision(
        reasoning="Failed to get a valid decision after 3 retries. Falling back to wait.",
        tool="wait",
        args={"turns": 1},
    )
