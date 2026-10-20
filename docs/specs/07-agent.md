# Spec: Agent

## Purpose

The agent module is the brain. It assembles prompts, calls Mistral Large 4 (ML4),
parses decisions, validates tool calls, and manages the conversation context.

ML4 is the policy. The agent is the plumbing around it.

## Decision Schema (`agent/schemas.py`)

The model outputs a single JSON object each turn:

```python
from pydantic import BaseModel

class Decision(BaseModel):
    reasoning: str              # brief chain-of-thought
    tool: str                   # tool name, e.g. "move"
    args: dict                  # tool arguments, e.g. {"direction": "west"}
    screen: str                 # "play" | "chargen" | "menu" | "death" | "unknown"
    goal: str                   # current high-level goal
    hp: int | None = None       # reported HP from stats bar
    max_hp: int | None = None
    hunger: str = ""            # "Satiated" | "Hungry" | "Starving" | etc.
    location: str = ""          # "Joppa" | "Red Rock cave level 2" | etc.
    journal_note: str | None = None  # optional: write a note to the journal
```

The model also reports state (screen, hp, hunger, location, goal) every turn.
The harness caches these in `memory/state.py` for logging and journal context.

## LLM Integration (`agent/llm.py`)

- **Provider**: Mistral AI API (`https://api.mistral.ai`)
- **Model**: `mistral-large-latest` (ML4)
- **Vision**: images sent as base64-encoded PNG in the conversation
- **API key**: from `MISTRAL_API_KEY` environment variable

```python
def call_llm(messages: list[dict]) -> str:
    """Call Mistral Large 4, return the raw text response."""
    ...

def call_llm_with_images(
    messages: list[dict],
    images: dict[str, bytes],  # {"viewport": png_bytes, "log": png_bytes, ...}
) -> str:
    """Call ML4 with images attached to the last user message."""
    ...
```

## Image Delivery

Not all four regions are sent every turn. Token cost matters even for a demo.

| When | Images sent |
|------|-------------|
| Every turn | viewport + log |
| Episode start (turn 0) | viewport + log + stats + abilities |
| Every 10 turns | viewport + log + stats + abilities |
| On request | `read_stats()` tool returns stats + abilities crops |

The `read_stats()` tool (in `tools/info.py`) captures the stats bar and abilities
bar regions and returns them as `ToolResult.image` (two images, or a combined crop).

## Prompts (`agent/prompts/`)

### `system_base.md`

The always-present system prompt. Contains:

1. **Role**: "You are playing Caves of Qud. You see the game screen and call tools to act."
2. **Output format**: JSON schema for `Decision`, with examples
3. **Tool list**: names, descriptions, parameter schemas (from `tools.tool_schemas()`)
4. **Distilled Qud manual** (trusted from general knowledge, verified in-game where critical):
   - Movement: 8-directional, numpad or arrow keys
   - Combat: melee and ranged, AV/DV mechanics
   - Stats: HP, AV (armor value), DV (dodge value), MA (mental armor), level, XP
   - Items: weapons, armor, food, water, trade goods, artifacts
   - Factions: reputation matters, don't attack faction guards
   - Common dangers: snapjaws, baboons, dawngliders, robots, poisons, diseases
   - Survival: eat food, drink water, manage hunger and thirst
   - World: procedurally generated, towns (Joppa, Grit Gate, etc.), caves, ruins
5. **How to read the screen**: what each region shows (viewport = game world, log = messages, stats = HP/hunger, abilities = available actions)
6. **Guidelines**: explore, survive, complete quests, don't die

### `system_creation.md`

Appended during chargen phase. Contains:

- Character creation flow overview
- Build archetypes (melee fighter, esper, ranged, etc.)
- Which stats matter for each archetype
- Mutation evaluation guidance (which mutations are good/bad)
- Goal: create a viable character, don't overthink

### `system_play.md`

Appended during play phase. Contains:

- General strategy hints
- Combat tips (when to fight, when to flee)
- Resource management (food, water, ammo)
- Quest guidance

### Few-shot examples

2 examples in `system_base.md` showing the expected JSON output format:

1. A movement example: model sees an enemy, decides to move away
2. An interaction example: model picks up an item

## Decision Flow (`agent/decide.py`)

```python
def decide(
    perception: Perception,
    transcript: str,
    conversation: list[dict],
    tools: list[dict],
    journal: str,
    state: GameState,
) -> Decision:
    """
    1. Assemble the prompt (system + conversation + current turn context)
    2. Attach images (viewport + log, plus stats/abilities if turn 0 or every 10)
    3. Call ML4
    4. Parse JSON response into Decision
    5. Validate: tool exists, args match schema
    6. Retry on failure (max 3), fallback to wait
    7. Return Decision
    """
    ...
```

### Retry Logic

| Failure | Action |
|---------|--------|
| Invalid JSON | Retry with error message appended to conversation (max 3) |
| Unknown tool name | Retry with "Tool 'X' does not exist. Available: ..." (max 3) |
| Args fail schema validation | Retry with validation error (max 3) |
| 3 retries exhausted | Fallback to `wait` tool, log warning |

### Context Management

The conversation grows each turn. Each turn appends:

1. **User message**: images (viewport + log [+ stats + abilities]) + transcript update + tool result from previous turn
2. **Assistant message**: the model's Decision JSON

For the demo: **let it grow**. No summarization, no truncation. If context
limits become a problem, a max conversation length (e.g., keep last 50 turns)
can be added later.

## File Layout

```
agent/
  __init__.py
  schemas.py           # Decision (pydantic), validation helpers
  llm.py               # call_llm(), call_llm_with_images(), Mistral API client
  decide.py            # decide() — assemble prompt, call LLM, parse, retry
  prompts/
    system_base.md     # role, output format, tools, Qud manual, guidelines
    system_creation.md # chargen guidance
    system_play.md     # play strategy hints
    fewshot.md         # 2 example decisions
```

## Dependencies

- `mistralai` (official Python SDK) or `httpx` (raw API calls)
- `pydantic` (schema validation)
- `perception/` (for Perception images)
- `memory/` (for transcript, journal, state)
- `tools/` (for tool schemas)

## Open Items

- Exact prompt wording — this is the biggest prompt-engineering task. Iterate
  based on replay viewer observations.
- Qud manual accuracy — trust general knowledge, but verify keybindings in-game
  (Esc → k). Some mechanics (AV/DV formulas) may be simplified in the prompt.
- `read_stats()` tool — needs to be added to `tools/info.py` (not yet in spec 04).
- Conversation length limit — not for the demo, but keep in mind.
- Image encoding format: PNG is lossless but large. JPEG would be smaller but
  lossy. For the demo, PNG (text in the log must stay readable).
