# Dialogue — Additional Prompt

You are in a **conversation** with an NPC. The dialogue screen shows numbered
response options.

## Rules

- **Pick by number**: dialogue options are numbered (1, 2, 3...). Use
  `choose_option(n)` to select. Arrow-key navigation is unreliable — always
  use the number.
- **Goals in priority order**:
  1. Accept quests (XP, items, reputation)
  2. Ask for directions / lore if relevant
  3. "Let's Trade" if you need to buy/sell
  4. Accept water-ritual offers (offer a dram to legendary creatures)
  5. Say goodbye (or press Escape) when done
- **End conversations**: don't talk forever. Get the quest, get the info, leave.

## Tools for Dialogue

- `choose_option(n)` — select numbered option n (1-9)
- `press` — for non-numbered menus (arrow keys + enter, or escape to exit)
- `interact(direction)` — to start a new conversation with an adjacent NPC
