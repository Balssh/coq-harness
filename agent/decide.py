"""Decision flow: assemble prompt, call ML4, parse, validate, retry."""

import json
import os
import time
from pathlib import Path

from agent.llm import call_llm_with_images, image_to_base64
from agent.schemas import Decision, parse_decision
from memory.state import GameState
from perception.regions import Perception
from tools import all_tools, get_tool, tool_schemas, validate_args
from tools import image_to_png_bytes

_PROMPTS_DIR = Path(__file__).parent / "prompts"

MAX_RETRIES = 3


def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def _format_tools() -> str:
    """Format the tool list for the system prompt."""
    lines = []
    for t in all_tools():
        args_desc = ""
        if t.parameters.get("properties"):
            props = t.parameters["properties"]
            required = t.parameters.get("required", [])
            parts = []
            for pname, pspec in props.items():
                req = " (required)" if pname in required else " (optional)"
                enum = f" [{', '.join(pspec['enum'])}]" if "enum" in pspec else ""
                parts.append(f"{pname}{req}{enum}")
            args_desc = f" — args: {', '.join(parts)}"
        turn = " [advances turn]" if t.advances_turn else ""
        lines.append(f"- `{t.name}`{turn}{args_desc}: {t.description}")
    return "\n".join(lines)


def build_system_prompt(phase: str) -> str:
    """Build the full system prompt for the given phase."""
    base = _load_prompt("system_base.md")
    base = base.replace("{TOOLS}", _format_tools())
    fewshot = _load_prompt("fewshot.md")

    if phase == "chargen":
        creation = _load_prompt("system_creation.md")
        return f"{base}\n\n{fewshot}\n\n{creation}"
    else:
        play = _load_prompt("system_play.md")
        return f"{base}\n\n{fewshot}\n\n{play}"


def decide(
    perception: Perception,
    transcript: str,
    conversation: list[dict],
    journal: str,
    state: GameState,
    phase: str = "play",
) -> Decision:
    """Run one decision cycle.

    1. Build system prompt for the current phase
    2. Attach images to the last user message
    3. Call ML4
    4. Parse + validate the Decision
    5. Retry on failure (max 3), fallback to `wait`
    """
    system_prompt = build_system_prompt(phase)

    # In play phase the map is loaded — send cropped regions.
    # Otherwise (chargen, menus, loading) send the full screenshot.
    in_play = state.screen == "play"

    # Build the current turn's user message
    turn_text_parts = []
    if transcript:
        turn_text_parts.append(f"## Message Log Transcript\n{transcript}")
    if journal:
        turn_text_parts.append(f"## Journal (cross-episode notes)\n{journal}")
    turn_text_parts.append(
        f"## Current State\n"
        f"Turn: {state.turn_count}\n"
        f"Phase: {state.phase}\n"
        f"Goal: {state.goal or '(none)'}\n"
        f"Location: {state.location or '(unknown)'}\n"
        f"HP: {state.hp or '?'}/{state.max_hp or '?'}\n"
        f"Hunger: {state.hunger or '(unknown)'}\n"
    )
    if in_play:
        turn_text_parts.append(
            "\n## Your Turn\n"
            "Look at the images below (viewport = game world, log = message log).\n"
            "Respond with a single JSON object as described in the system prompt."
        )
    else:
        turn_text_parts.append(
            "\n## Your Turn\n"
            "Look at the full game screen image below.\n"
            "Respond with a single JSON object as described in the system prompt."
        )
    turn_text = "\n\n".join(turn_text_parts)

    # Determine which images to send.
    send_all = state.turn_count == 0 or state.turn_count % 10 == 0

    if in_play:
        images: dict[str, bytes] = {
            "viewport": image_to_png_bytes(perception.viewport),
            "log": image_to_png_bytes(perception.log),
        }
        labels = {
            "viewport": "Game Viewport (the tile-based world)",
            "log": "Message Log (recent game messages)",
        }
        if send_all:
            images["top_status"] = image_to_png_bytes(perception.top_status)
            images["abilities"] = image_to_png_bytes(perception.abilities)
            labels["top_status"] = "Top Status Bar (HP, level, XP, temperature, time, date)"
            labels["abilities"] = "Abilities Bar (ability icons with hotkeys — bottom of screen)"
    else:
        images = {
            "full": image_to_png_bytes(perception.full),
        }
        labels = {
            "full": "Full Game Screen",
        }

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation)
    messages.append({"role": "user", "content": turn_text})

    # Retry loop
    for attempt in range(MAX_RETRIES):
        raw = call_llm_with_images(messages, images, labels)

        decision = parse_decision(raw)
        if decision is None:
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"Your response was not valid JSON. Please respond with a single JSON object matching the schema. Error: could not parse JSON.\nYour response was:\n{raw[:500]}",
            })
            continue

        # Validate tool exists
        tool = get_tool(decision.tool)
        if tool is None:
            available = ", ".join(sorted(t.name for t in all_tools()))
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"Tool '{decision.tool}' does not exist. Available tools: {available}",
            })
            continue

        # Validate args
        err = validate_args(tool, decision.args)
        if err:
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": err,
            })
            continue

        return decision

    # All retries exhausted — fallback to wait
    print("[decide] All retries exhausted, falling back to 'wait'")
    return Decision(
        reasoning="Failed to get a valid decision after 3 retries. Falling back to wait.",
        tool="wait",
        args={},
        screen=state.screen or "unknown",
        goal=state.goal,
        hp=state.hp,
        max_hp=state.max_hp,
        hunger=state.hunger,
        location=state.location,
    )
