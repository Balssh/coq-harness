# Character Creation — Additional Prompt

You are in **character creation**. Your goal is to create a viable character
that can survive the early game. You have limited steps — don't overthink it.

## RECOMMENDED: Use Presets (Exact Flow)

The fastest path is a **preset character** (one confirm skips the entire
custom chargen tree). Since your mission is to **explore, talk to NPCs, and
fight hostiles**, pick a preset that can survive combat:

- **Gunwing** (Mutant Gunslinger) — **RECOMMENDED**. 22 Agility, starts with
  a gun and ammo. Ranged combat is much safer than melee — you can kill
  enemies from a distance. High DV (dodge) helps you survive.
- **Praetorian Prime** (True Kin) — 22 Str/21 Toughness, rifle + slugs.
  Good armor, HP, and a ranged weapon. True Kin start with better stats,
  equipment, and more skill points than Mutants.
- **Marsh Taur** (Mutant Marauder) — 22 Str melee bruiser. High HP and melee
  damage, plus a Charge ability. Good for learning combat, but melee is riskier.

### Build Tips (from qudzoo)
- **Attribute priorities**: Your primary attribute should be 2+ points above
  your secondary. For ranged: Agility > Toughness > Strength.
- **Agility** → DV (dodge) and ranged accuracy. **Toughness** → HP.
  **Strength** → melee damage. **Intelligence** → skill points.
  **Willpower** → mental abilities and cooldown recovery. **Ego** → psychic powers.
- **Skills matter more than gear**: invest skill points in combat skills
  (DV/AV), wayfaring (navigate world map), and cooking (Harvestry).
- **True Kin** start stronger but need loot to scale. **Mutants** are powerful
  early but need mutation levels to grow.
- **Always keep a ranged weapon equipped** — there's no delay switching.

Here is the exact verified flow:

1. **Title screen** → report `"screen": "title"` → `confirm()` — selects "New Game"
2. **Mode select** → report `"screen": "mode_select"` → `confirm()` — selects "Classic"
3. **Character Type (Presets tab)** → report `"screen": "chargen"` → `confirm()` —
   selects a preset (e.g. Gunwing, Praetorian, Marsh Taur)
4. **Choose Genotype** → `confirm()` — selects the genotype (e.g. "Mutated Human"
   or "True Kin"). The highlighted option is already correct for your preset.
   If you see "You must make a selection before advancing", press `confirm()`.
5. **Attributes screen** → `next()` — proceeds past the attributes summary
6. **Customize screen (Name: <random>)** → `next()` — the random name is already
   filled in, just press Num9 to proceed. Do NOT press `confirm()` here!
7. **Starting Location** → `confirm()` — selects a location (e.g. Joppa)
8. **World generation** → wait for the game world to appear
9. Report `"screen": "play"`

**IMPORTANT**: After selecting a preset, the game may show a "Choose Genotype"
screen. The correct genotype for your preset is already highlighted. Just press
`confirm()` (Enter) to accept it. If you see an error "You must make a selection
before advancing", it means you need to press `confirm()` first.

### Name Screen — CRITICAL

On the **Customize** screen, the name field already has a random name.
The flow is very simple:

- **Just press `next()` (Num9)** to proceed. The random name is fine.
- **Optionally**, press `press(["r"])` to randomize the name, then `next()`.
- **NEVER press `confirm()` (Enter) on the Customize screen.** Enter activates
  text-edit mode on the name field. If you then press `next()` (Num9), it will
  type "9" into the name instead of advancing the screen. You will see the name
  changing character by character — that means you are in text-edit mode.
- If you accidentally enter text-edit mode: press `confirm()` (Enter) to exit
  edit mode, then press `next()` (Num9) to proceed.

### Critical Rules

- **`confirm()` (Enter)** selects the highlighted option. Use it on the title
  screen (New Game), mode select (Classic), character-type screen, genotype
  screen, and starting-location screen. **NOT on the Customize screen.**
- **`next()` (Num 9)** advances to the next chargen screen. Use it on the
  Attributes screen and the Customize screen.
- **Use the semantic tools (`confirm`, `next`, `select`, `back`)** — do NOT
  use `press()` with raw keys during chargen. The semantic tools send the
  correct keys for each screen. If you use `press("space")` when the game
  expects Enter, you will get errors like "You must make a selection."
- **Do NOT use `select(left/right)` to switch tabs** — use `next()` instead.
- **Do NOT use `quit`, `abandon`, or `restart_run`** — they are disabled during
  chargen.
- **If the screen doesn't match expectations**, don't spam keys — report
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

**IMPORTANT**: Your very first action on the play screen must be
`open_screen("abilities")` — inspect your abilities, note what each does,
and write a `journal_note` summarizing them. You will need this knowledge
in every combat encounter. Then proceed to `show_labels` to survey the area.
