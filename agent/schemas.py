"""Decision schema and validation helpers."""

from pydantic import BaseModel, Field


class Decision(BaseModel):
    reasoning: str = Field(description="Brief chain-of-thought about what to do and why")
    tool: str = Field(default="", description="Tool name to call, e.g. 'move'. Leave empty if using 'key' instead.")
    key: str | None = Field(
        default=None,
        description=(
            "Press a single key directly (alternative to calling a tool). "
            "Use for: dismissing '>press [Space]' prompts (key='space'), "
            "selecting a letter/number option in a menu (key='1', key='a'), "
            "navigating a menu with arrows (key='up', key='down', key='enter', key='escape'). "
            "Do NOT use for movement or combat — use the 'move' tool instead. "
            "Raw key presses do NOT advance the turn clock."
        ),
    )
    args: dict = Field(default_factory=dict, description="Tool arguments")
    screen: str = Field(
        description=(
            "Current screen. Report exactly what you see: "
            "'title' (main menu), 'mode_select' (Classic/Roleplay choice), "
            "'chargen' (character creation), 'play' (in-game world view), "
            "'menu' (inventory/equipment/skills/sheet/quests/etc.), "
            "'dialogue' (talking to an NPC), 'trade' (buying/selling), "
            "'world_map' (overland map), 'death' (tombstone/ death summary), "
            "or 'unknown' if you can't tell."
        )
    )
    goal: str = Field(default="", description="Current high-level goal")
    hp: int | None = Field(default=None, description="Current HP from stats bar")
    max_hp: int | None = Field(default=None, description="Max HP from stats bar")
    hunger: str = Field(default="", description="Hunger level: Satiated, Peckish, Hungry, etc.")
    location: str = Field(default="", description="Current location name, e.g. 'Joppa'")
    journal_note: str | None = Field(
        default=None,
        description="Optional: write a note to the cross-episode journal",
    )

    model_config = {"extra": "ignore"}


def parse_decision(raw: str) -> Decision | None:
    """Parse a JSON string into a Decision. Returns None on failure."""
    import json
    try:
        # Handle potential markdown code fences
        text = raw.strip()
        if text.startswith("```"):
            # Extract JSON from code fence
            lines = text.split("\n")
            json_lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(json_lines)
        data = json.loads(text)
        return Decision(**data)
    except (json.JSONDecodeError, ValueError):
        return None
