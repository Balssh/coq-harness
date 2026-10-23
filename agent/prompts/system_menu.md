# Menu Screen — Additional Prompt

You are on a **menu screen** (inventory, equipment, skills, character sheet,
quests, journal, abilities, or mutations). Menus do NOT advance the turn clock.

## Menu Grammar

- **Arrow keys** navigate options (up/down to move, left/right for tabs/sliders).
- **Enter** confirms/selects the highlighted option.
- **Digits (1-9)** select numbered options directly.
- **Escape** closes the menu and returns to the game (never advances the turn).
- **Letter keys** often trigger actions on the selected item (e.g., in inventory:
  `d`=drop, `w`=wear/wield, `q`=quaff, `e`=eat, `t`=take off in equipment).

## Common Screens

| Screen | Key | What It Shows |
|---|---|---|
| Inventory | I (Shift+I) | Your items. Select + letter to use. |
| Equipment | E (Shift+E) | Equipped gear. `t` to take off. |
| Skills | P | Skills tree. Spend skill points here. |
| Character Sheet | X | Attributes, level, stats. Spend attribute points. |
| Quests | Q (Shift+Q) | Active quests and progress. |
| Journal | J (Shift+J) | Quest log and notes. |
| Abilities | A (Shift+A) | Activated abilities and cooldowns. |
| Mutations | M (Shift+M) | Mutation powers. Spend mutation points. |

## Tools for Menus

- `close_menu` — close the current menu/dialog (Escape). Use this when done
  reading any menu, or when an interaction failed and you need to dismiss
  a popup.
- `send_keys` — send arrow keys, enter, escape, or letter shortcuts
- `choose_option(n)` — press a digit for numbered options
- The dedicated info tools (`inventory`, `character_sheet`, etc.) open these
  screens and return a screenshot for you to read.
