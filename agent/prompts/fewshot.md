# Few-Shot Examples

These examples show the expected JSON output format.

---

## Example 0: First Turn — Inspecting Abilities

**Situation**: You just finished character creation and the game world has
loaded. This is your very first turn on the play screen.

```json
{
  "reasoning": "This is my first turn in the game world. Before doing anything else, I need to inspect my abilities so I know what I can do in combat. I'll open the abilities screen to see my mutations, skills, and their hotkeys.",
  "tool": "open_screen",
  "args": {"screen": "abilities"},
  "wait_for_turn": false,
  "screen": "play",
  "goal": "Inspect abilities, note them in journal, then survey Joppa with show_labels",
  "hp": 25,
  "max_hp": 25,
  "hunger": "Satiated",
  "location": "Joppa",
  "journal_note": "Abilities: [Freezing Ray] ranged ice attack, [Charge] melee dash, [Salve Injector] heal. Hotkeys noted. Will use Freezing Ray as primary combat ability."
}
```

---

## Example 1: Exploring — Moving Toward an Unexplored Area

**Situation**: You're in Joppa. You've talked to a few NPCs and looted nearby
chests. The viewport shows an unexplored street to the east with a building
you haven't entered.

```json
{
  "reasoning": "I've explored the western part of Joppa. There's an unexplored area to the east with buildings I haven't checked. Let me head east to discover more.",
  "tool": "move",
  "args": {"direction": "right"},
  "wait_for_turn": true,
  "screen": "play",
  "goal": "Explore eastern Joppa, find more NPCs to talk to and buildings to loot",
  "hp": 25,
  "max_hp": 25,
  "hunger": "Satiated",
  "location": "Joppa",
  "journal_note": null
}
```

---

## Example 2: Talking to an NPC

**Situation**: `show_labels` reveals a villager named "Argyve" two tiles to
your north. You're adjacent (one tile south of him).

```json
{
  "reasoning": "I see Argyve the tinker nearby. He gives the main questline — I should talk to him. I'm already adjacent, so I'll interact north to open the conversation menu.",
  "tool": "interact",
  "args": {"direction": "up"},
  "wait_for_turn": false,
  "screen": "play",
  "goal": "Talk to Argyve and start the main questline",
  "hp": 25,
  "max_hp": 25,
  "hunger": "Satiated",
  "location": "Joppa",
  "journal_note": null
}
```

---

## Example 3: Fighting a Hostile — Assessing and Engaging

**Situation**: A snapjaw (hostile dog creature) is approaching from the west.
Your HP is 20/25. You have a musket equipped.

```json
{
  "reasoning": "A snapjaw is hostile and approaching. It's a weak enemy — good for early XP. I have a gun, so I'll let it come closer and shoot. I'll move east to create space, then it will follow and I can shoot it.",
  "tool": "move",
  "args": {"direction": "right"},
  "wait_for_turn": true,
  "screen": "play",
  "goal": "Fight the snapjaw for XP, then continue exploring Joppa outskirts",
  "hp": 20,
  "max_hp": 25,
  "hunger": "Satiated",
  "location": "Joppa outskirts",
  "journal_note": null
}
```

---

## Example 4: Fleeing from a Tough Enemy + Journal Note

**Situation**: A baboon (very dangerous) is two tiles away. Your HP is 10/25.
The message log shows "A baboon whoops!"

```json
{
  "reasoning": "A baboon is extremely dangerous for my level. I'm at low HP. I need to run away immediately — move south to put distance between us, then keep moving away from the salt marsh.",
  "tool": "move",
  "args": {"direction": "down"},
  "wait_for_turn": true,
  "screen": "play",
  "goal": "Escape the baboon and return to Joppa to heal",
  "hp": 10,
  "max_hp": 25,
  "hunger": "Peckish",
  "location": "Salt marsh",
  "journal_note": "Baboons are extremely dangerous at low level — always flee. Found in the salt marsh east of Joppa."
}
```

---

## Example 5: Using show_labels to Find NPCs

**Situation**: You're in Joppa but can't find any NPCs to talk to. The viewport
shows several colored symbols but you're not sure what they are.

```json
{
  "reasoning": "I need to find NPCs to talk to. Let me use show_labels to see names and identify villagers, merchants, and quest-givers in the viewport.",
  "tool": "show_labels",
  "args": {},
  "wait_for_turn": false,
  "screen": "play",
  "goal": "Find NPCs in Joppa to talk to and get quests",
  "hp": 25,
  "max_hp": 25,
  "hunger": "Satiated",
  "location": "Joppa",
  "journal_note": null
}
```

---

## Example 6: Dismissing a ">press [Space]" Prompt

**Situation**: The message log shows ">press [Space]" at the bottom. You just
finished a conversation with an NPC.

```json
{
  "reasoning": "The game is showing a '>press [Space]' prompt after the conversation. I'll press space to dismiss it and continue exploring.",
  "tool": "press",
  "args": {"keys": ["space"]},
  "wait_for_turn": false,
  "screen": "play",
  "goal": "Continue exploring Joppa and find the next NPC to talk to",
  "hp": 25,
  "max_hp": 25,
  "hunger": "Satiated",
  "location": "Joppa",
  "journal_note": null
}
```

---

## Example 7: Auto-Exploring a New Zone

**Situation**: You've walked to a new screen (zone) east of Joppa. It's
unexplored salt marsh with some creatures visible.

```json
{
  "reasoning": "I'm in a new zone. The best way to explore is to auto-explore — the game will move me through all interesting tiles and stop when a hostile threatens me. Then I'll check points of interest with backspace. Let me start auto-exploring.",
  "tool": "auto_explore",
  "args": {},
  "wait_for_turn": true,
  "screen": "play",
  "goal": "Explore this zone with autoexplore, then check points of interest for NPCs, items, or stairs",
  "hp": 25,
  "max_hp": 25,
  "hunger": "Satiated",
  "location": "Salt marsh (east of Joppa)",
  "journal_note": null
}
```

## Example 8: After Auto-Explore Stops — Check Points of Interest

**Situation**: Auto-explore just stopped. The message log says "Auto-explore
stopped: hostile nearby" or similar. You are in the salt marsh wilderness.

```json
{
  "reasoning": "Auto-explore stopped. I need to see what's interesting nearby — stairs, items, NPCs, landmarks. Press backspace to open the points-of-interest menu, then I'll pick something to investigate.",
  "tool": "",
  "key": "backspace",
  "args": {},
  "wait_for_turn": true,
  "screen": "play",
  "goal": "Check points of interest after auto-explore, navigate to stairs or items",
  "hp": 25,
  "max_hp": 25,
  "hunger": "Satiated",
  "location": "Salt marsh (east of Joppa)",
  "journal_note": null
}
```

## Example 9: Leaving Joppa — First Wilderness Action

**Situation**: You've finished talking to all NPCs in Joppa. You step outside
the town gates onto open salt marsh terrain. The screen shows grass, dirt,
and some creatures in the distance. No buildings nearby.

```json
{
  "reasoning": "I'm outside Joppa now — this is wilderness. I should NOT walk tile-by-tile. Auto-explore is the right tool: it will move me through the whole area automatically and stop when something interesting happens. Let me start.",
  "tool": "auto_explore",
  "args": {},
  "wait_for_turn": true,
  "screen": "play",
  "goal": "Auto-explore the salt marsh to discover areas, find weak enemies for XP, and locate points of interest",
  "hp": 25,
  "max_hp": 25,
  "hunger": "Satiated",
  "location": "Salt marsh (outside Joppa)",
  "journal_note": "Left Joppa to explore the salt marsh. Will auto-explore, fight weak enemies (snapjaws), and avoid crocs near water."
}
```
