"""Decision schema and validation helpers."""

from pydantic import BaseModel, Field


class Decision(BaseModel):
    reasoning: str = Field(description="Brief chain-of-thought about what to do and why")
    tool: str = Field(description="Tool name to call, e.g. 'move'")
    args: dict = Field(default_factory=dict, description="Tool arguments")
    screen: str = Field(
        description="Current screen: 'play', 'chargen', 'menu', 'death', or 'unknown'"
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
