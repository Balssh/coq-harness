# Few-Shot Examples

These examples show the expected JSON output format.

---

## Example 1: Combat — Moving Away from an Enemy

**Situation**: You see a snapjaw two tiles to your north in the viewport.
Your HP is 12/25. The message log shows "A snapjaw snarls at you!"

```json
{
  "reasoning": "A snapjaw is nearby and hostile. I'm at half HP, so I should back off to a safer position before fighting. I'll move south to create distance, then reassess.",
  "tool": "move",
  "args": {"direction": "down"},
  "wait_for_turn": true,
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

## Example 2: Checking Inventory

**Situation**: You want to see what items you're carrying.

```json
{
  "reasoning": "I should check my inventory to see what food and gear I have before exploring further.",
  "tool": "open_screen",
  "args": {"screen": "inventory"},
  "wait_for_turn": false,
  "screen": "play",
  "goal": "Check inventory, then continue exploring",
  "hp": 25,
  "max_hp": 25,
  "hunger": "Peckish",
  "location": "Joppa",
  "journal_note": null
}
```

---

## Example 3: Using press() for a Menu Action

**Situation**: You're in the inventory screen. You see a healing salve in slot 'c'.
You want to quaff it. (Note: you could also use `use_item` from the play screen,
but you're already in the inventory menu.)

```json
{
  "reasoning": "I'm in the inventory and I see a healing salve in slot c. I'll select it and quaff it. In Qud's inventory, pressing the slot letter selects the item, then 'q' quaffs it.",
  "tool": "press",
  "args": {"keys": ["c", "q"]},
  "wait_for_turn": true,
  "screen": "menu",
  "goal": "Heal up before exploring further",
  "hp": 8,
  "max_hp": 25,
  "hunger": "Peckish",
  "location": "Joppa outskirts",
  "journal_note": null
}
```

---

## Example 4: Writing a Journal Note

**Situation**: You just learned from an NPC that the Red Rock caves are
dangerous for low-level characters.

```json
{
  "reasoning": "The NPC warned me about Red Rock caves. I should remember this for future runs. I'll write a journal note, then continue exploring Joppa.",
  "tool": "move",
  "args": {"direction": "up"},
  "wait_for_turn": true,
  "screen": "play",
  "goal": "Explore Joppa and complete quests",
  "hp": 25,
  "max_hp": 25,
  "hunger": "Peckish",
  "location": "Joppa",
  "journal_note": "Red Rock caves are dangerous for low-level characters — avoid until level 5+. The mayor warned me about snapjaw packs."
}
```
