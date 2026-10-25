# Title / Mode Select — Additional Prompt

You are at the **main menu** or **mode select screen** (before character creation).

## Expected Flow

1. **Title screen**: "New Game" is the DEFAULT cursor position. Use `confirm()`
   to select it. Do NOT select Continue, Options, or Achievements.
2. **Mode select**: Choose **Classic** (permadeath — this is the mode we play).
   Classic is typically the default — use `confirm()`.
3. **Character type**: Choose **Preset** for the fastest start.
4. Report your screen accurately: `"title"`, `"mode_select"`, or `"chargen"`.

## Rules

- `select(direction)` moves the cursor, `confirm()` presses Enter.
- If you see the title screen, use `confirm()` (New Game is default).
- If you see mode select, use `confirm()` (Classic is default).
- If you accidentally end up on Continue/Options/Achievements, use `back()`
  or navigate back.
- Do NOT use `quit`, `abandon`, or `restart_run` on these screens.
