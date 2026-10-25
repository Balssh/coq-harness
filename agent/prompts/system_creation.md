# Character Creation — Additional Prompt

You are in **character creation**. Your goal is to create a viable character
that can survive the early game. You have limited steps — don't overthink it.

## RECOMMENDED: Use Presets (Exact Flow)

The fastest path is a **preset character** (one confirm skips the entire
custom chargen tree). Since your mission is to **explore, talk to NPCs, and
fight hostiles**, pick a preset that can survive combat:

- **Gunwing** (Mutant Gunslinger) — **RECOMMENDED**. 22 Agi, starts with a gun.
  Ranged combat is much safer than melee — you can kill enemies from a distance.
- **Praetorian Prime** (True Kin) — 22 Str/21 Toughness, rifle + slugs.
  Good armor and ranged weapon. Solid all-rounder.
- **Marsh Taur** (Mutant Marauder) — 22 Str melee bruiser.
  High HP and melee damage, but melee is riskier. Good for learning combat.

Here is the exact verified flow:

1. **Title screen** → report `"screen": "title"` → `confirm()` — selects "New Game"
2. **Mode select** → report `"screen": "mode_select"` → `confirm()` — selects "Classic"
3. **Character Type** → report `"screen": "chargen"` → `confirm()` — selects a preset
4. **Attributes screen** → `next()` — proceeds past the attributes summary
5. **Customize screen (Name: <random>)** → `confirm()` — activates the name field
6. **"Enter name:" prompt** → `confirm()` — accepts the random name
7. **Customize screen** → `next()` — proceeds to starting location
8. **Starting Location** → `confirm()` — selects a location (e.g. Joppa)
9. **World generation** → wait for the game world to appear
10. Report `"screen": "play"`

### Critical Rules

- **`confirm()` (Enter)** selects the highlighted option. Use it on the title
  screen (New Game), mode select (Classic), character-type screen, name field,
  and starting-location screen.
- **`next()` (Num 9)** advances to the next chargen screen.
- **Do NOT press `confirm()` repeatedly on the same screen** — it will toggle
  the name field on/off without progressing.
- **Do NOT use `select(left/right)` to switch tabs** — use `next()` instead.
- **Do NOT use `quit`, `abandon`, or `restart_run`** — they are disabled during
  chargen.
- The name is already randomly generated. You just need to `confirm()` twice
  on the name screen (once to activate, once to accept), then `next()`.
- **If the screen doesn't match expectations**, don't spam confirm — report
  the actual screen and let the watchdog handle it.

## Chargen Tools

- `select(direction)`: Navigate options with arrow keys (up/down/left/right).
- `confirm()`: Press Enter. Selects the highlighted option.
- `next()`: Press Num 9. Advances to the next chargen screen.
- `back()`: Press Escape. Goes back to the previous screen.

## After Chargen

When character creation is complete and the game world appears, report
`"screen": "play"`. Write a `journal_note`:

```
[chargen] Created a preset character. Ready to explore.
```
