# Few-Shot Examples

These examples show the expected JSON output format. They are illustrative —
your actual decisions will differ based on what you see.

---

## Example 1: Combat — Moving Away from an Enemy

**Situation**: You see a snapjaw two tiles to your north in the viewport.
Your HP is 12/25. The message log shows "A snapjaw snarls at you!"

```json
{
  "reasoning": "A snapjaw is nearby and hostile. I'm at half HP, so I should back off to a safer position before fighting. I'll move south to create distance, then reassess.",
  "tool": "move",
  "args": {"direction": "down"},
  "screen": "play",
  "goal": "Survive the snapjaw encounter and explore Joppa outskirts",
  "hp": 12,
  "max_hp": 25,
  "hunger": "Satiated",
  "location": "Joppa outskirts",
  "journal_note": null
}
```

---

## Example 2: Picking Up an Item

**Situation**: You see a "steel long sword" on the tile next to you.
The message log shows "You see: a steel long sword."

```json
{
  "reasoning": "There's a steel long sword on the adjacent tile. It's better than my starting weapon. I'll move onto it to pick it up.",
  "tool": "move",
  "args": {"direction": "right"},
  "screen": "play",
  "goal": "Find better equipment",
  "hp": 25,
  "max_hp": 25,
  "hunger": "Satiated",
  "location": "Joppa",
  "journal_note": null
}
```

---

## Example 3: Writing a Journal Note

**Situation**: You just learned from an NPC that the Red Rock caves are
dangerous for low-level characters.

```json
{
  "reasoning": "The NPC warned me about Red Rock caves. I should remember this for future runs. I'll write a journal note, then continue exploring Joppa.",
  "tool": "move",
  "args": {"direction": "up"},
  "screen": "play",
  "goal": "Explore Joppa and complete quests",
  "hp": 25,
  "max_hp": 25,
  "hunger": "Peckish",
  "location": "Joppa",
  "journal_note": "Red Rock caves are dangerous for low-level characters — avoid until level 5+. The mayor warned me about snapjaw packs."
}
```
