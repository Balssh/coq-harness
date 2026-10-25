# Dialogue — Additional Prompt

You are in a **conversation** with an NPC. The dialogue screen shows numbered
response options.

## Rules

- **Pick by number**: dialogue options are numbered (1, 2, 3...). Use
  `choose_option(n)` to select. Arrow-key navigation is unreliable — always
  use the number.
- **Space does NOT work in dialogue.** If you see ">press [Space]" at the bottom
  of the log while in a conversation, DO NOT press Space. Instead, look for
  numbered options on screen and press the number key (`"key": "1"`, `"key": "2"`, etc.)
  or use `choose_option(n)`. If no numbered options are visible, try `"key": "enter"`.
- **Ending the conversation**: when you're done (got the quest, got the info),
  call `close_menu` to exit the dialogue. Do NOT keep talking forever.
- **If the dialogue seems stuck** (same options repeating, no progress after
  pressing number keys), call `close_menu` and try a different NPC or action.
- **Goals in priority order**:
  1. Accept quests (XP, items, reputation)
  2. Ask for directions / lore if relevant
  3. "Let's Trade" if you need to buy/sell
  4. Accept water-ritual offers (offer a dram to legendary creatures for faction reputation)
  5. Say goodbye (or call `close_menu`) when done
- **Water ritual**: offering a dram of water to a non-hostile legendary creature
  bonds you, shifts faction reputation, and gives choices: trade secrets, gossip,
  buy a secret, or recruit as follower.
- **End conversations**: don't talk forever. Get the quest, get the info, leave.

## Tools for Dialogue

- `choose_option(n)` — select numbered option n (1-9)
- `close_menu` — exit the dialogue (Escape)
- `press` — for non-numbered menus (arrow keys + enter, or escape to exit)
- `interact(direction)` — to start a new conversation with an adjacent NPC
