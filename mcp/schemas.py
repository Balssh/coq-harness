"""Decision schema for the MCP-based agent."""

from pydantic import BaseModel, Field


class Decision(BaseModel):
    reasoning: str = Field(
        description="Brief chain-of-thought: what you see, what you're thinking, why you chose this action."
    )
    tool: str = Field(
        description="The name of the tool to call (e.g. 'move', 'interact', 'wait')."
    )
    args: dict = Field(
        default_factory=dict,
        description="Arguments for the tool (object, may be empty {}).",
    )
    goal: str | None = Field(default=None, description="Your current high-level goal.")
    journal_note: str | None = Field(
        default=None,
        description="Optional: write a note to your cross-episode journal. Set to null to skip.",
    )

    model_config = {"extra": "ignore"}


def parse_decision(raw: str) -> Decision | None:
    import json
    try:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(json_lines)
        data = json.loads(text)
        return Decision(**data)
    except (json.JSONDecodeError, ValueError):
        return None
