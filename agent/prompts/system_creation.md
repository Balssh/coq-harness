# Character Creation — Additional Prompt

You are in **character creation**. Your goal is to create a viable character
that can survive the early game. You have limited steps — don't overthink it.

## RECOMMENDED: Use Presets (Exact Flow)

The fastest path is a **preset character**. Here is the exact verified flow:

1. **Main Menu** → `confirm()` — selects "New Game"
2. **Game Mode** → `confirm()` — selects "Classic"
3. **Character Type** → `confirm()` — selects "Preset [A]" (a pre-built character)
4. **Attributes screen** → `next()` — proceeds past the attributes summary
5. **Customize screen (Name: <random>)** → `confirm()` — activates the name field
6. **"Enter name:" prompt** → `confirm()` — accepts the random name
7. **Customize screen** → `next()` — proceeds to starting location
8. **Starting Location** → `confirm()` — selects a location (e.g. Joppa)
9. **World generation** → wait for the game world to appear
10. Report `"screen": "play"`

### Critical Rules

- **`confirm()` (Enter)** selects the highlighted option. Use it on menus,
  the character-type screen, the name field, and the starting-location screen.
- **`next()` (Num 9)** advances to the next chargen screen. The bottom of the
  screen shows "[Num 9] Next". Use it on the Attributes and Customize screens.
- **Do NOT press `confirm()` repeatedly on the same screen** — it will toggle
  the name field on/off without progressing.
- **Do NOT use `select(left/right)` to switch tabs** — the tabs are not
  navigable with arrow keys during preset chargen. Use `next()` instead.
- **Do NOT use `quit` or `restart_run`** — they are disabled during chargen.
  If you see the main menu, use `confirm()` to select "New Game".
- The name is already randomly generated. You just need to `confirm()` twice
  on the name screen (once to activate, once to accept), then `next()`.

## Chargen Tools

- `select(direction)`: Navigate options with arrow keys (up/down/left/right).
  Useful for browsing lists (e.g. preset list, starting locations).
- `confirm()`: Press Enter. Selects the highlighted option, accepts names,
  starts the game from the starting-location screen.
- `next()`: Press Num 9. Advances to the next chargen screen.
  Shown as "[Num 9] Next" at the bottom of the screen.
- `back()`: Press Escape. Goes back to the previous screen.

## After Chargen

When character creation is complete and the game world appears (you see the
tile-based map, your character, the message log with game text, and the stats
bar at the bottom), report `"screen": "play"`. Write a `journal_note`:

```
[chargen] Created a preset character. Ready to explore.
```

This note persists across episodes and helps you in future runs.
