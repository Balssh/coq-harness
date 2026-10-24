# Menu Screen — Additional Prompt

You are on a **menu screen** (inventory, equipment, skills, character sheet,
quests, journal, abilities, or mutations). Menus do NOT advance the turn clock.

## Menu Grammar

- **Arrow keys** navigate options (up/down to move, left/right for tabs/sliders).
- **Enter** confirms/selects the highlighted option.
- **Digits (1-9)** select numbered options directly.
- **Escape** closes the menu and returns to the game.
- **Letter keys** often trigger actions on the selected item:
  - Inventory: `d`=drop, `w`=wear/wield, `q`=quaff, `e`=eat
  - Equipment: `t`=take off

## Common Screens

| Screen | Key | What It Shows |
|--------|-----|---------------|
| Inventory | Shift+I | Your items. Select + letter to use. |
| Equipment | Shift+E | Equipped gear. `t` to take off. |
| Skills | P | Skills tree. Spend skill points. |
| Character Sheet | X | Attributes, level, stats. |
| Quests | Shift+Q | Active quests and progress. |
| Journal | Shift+J | Quest log and notes. |
| Abilities | Shift+A | Activated abilities and cooldowns. |
| Mutations | Shift+M | Mutation powers. |

## Tools for Menus

- `press` — send arrow keys, enter, escape, or letter shortcuts
- `choose_option(n)` — press a digit for numbered options
- `open_screen(screen)` — switch to a different screen (returns screenshot)
- `press(['escape'])` when done — don't leave menus open
