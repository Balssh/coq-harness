# Play Mode — Additional Prompt

You are playing the game. The turn clock is active: after calling a tool that
advances the turn, the harness waits for the message log to update before
showing you the next screenshot.

## FIRST TURN PROTOCOL (do this before anything else)

**The message log is a scrolling history.** Old messages stay visible. If the log
shows "There's nothing you can interact with" or other old messages, IGNORE them —
they are from past turns, not current popups. Do NOT try to dismiss log messages.

**If you see ">press [Space]"** at the bottom of the log, the game is waiting for
input. Usually press Space (`"key": "space"`). **BUT if numbered dialogue options
are visible on screen, Space won't work** — press a number key (`"key": "1"`,
`"key": "2"`, etc.) or use `choose_option(n)` to select an option. If Space
doesn't change the screen after 2 presses, try `"key": "enter"` or a number key.

**Your first action should be `show_labels`.** This shows labels on all items
and NPCs in the viewport. NPCs are colored symbols (blue, purple, green, etc.)
with names. Identify the nearest NPC, then move toward it.

## Finding and Talking to NPCs — Step by Step

1. **`show_labels`** — see NPC names and locations on the map.
2. **`move(direction)`** — walk toward the nearest NPC. Keep moving until you
   are on a tile directly adjacent to them (one tile away, not on top of them).
3. **`look`** — **ALWAYS do this before `interact`.** Call `look`
   ONCE to enter look mode. The cursor starts on YOUR character. Then follow
   this EXACT sequence:
   - **Step 3a**: Call `move(direction)` ONCE to move the cursor ONE tile
     toward the target NPC. Then STOP — do not call move again yet.
   - **Step 3b**: Read the NEXT screenshot's message log. It will describe
     what's on the tile under the cursor (e.g., "a stone wall", "Villager:
     a traveler", "the way is blocked"). This tells you if the NPC is there.
   - **Step 3c**: Call `close_menu` (Escape) to exit look mode.
   - **Step 3d**: If the description confirmed an NPC on that tile, call
     `interact(direction)` with the SAME direction you moved the cursor.
   - **DO NOT call `look` again** — it toggles look mode OFF.
   - **DO NOT call `move` more than once** before reading the result.
   - If the description says "the way is blocked" or "a wall", the target is
     NOT in that direction. Exit look mode and try a different direction.
4. **`interact(direction)`** — where direction points AT the NPC (the same direction
   you moved the look cursor). This opens the interaction context menu.
5. **Read the next screenshot**:
   - Context menu appeared (a list of actions like "Chat", "Trade" on screen)?
     Select "Chat" — press the number or letter shown next to it.
   - Dialogue appeared directly (numbered responses on screen)?
     Use `choose_option(n)` to respond.
   - Log says "nothing you can interact with"? This is just a LOG message (history),
     not a popup. No need to dismiss it. Move to a DIFFERENT NPC.
     Do NOT retry the same direction.
   - See ">press [Space]" at the bottom of the log? Set `"key": "space"`.
6. **In dialogue**: pick numbered options with `choose_option(n)`.
   When done, call `close_menu` to exit.

**Why `look` matters**: The game world is tile-based. You can only interact with
things on ADJACENT tiles (one tile away, in a cardinal or diagonal direction).
If you call `interact` toward a tile that has nothing on it, you get
"There's nothing you can interact with." Use `look` to verify what's actually
on the target tile BEFORE calling `interact`.

**Key distinction**:
- **Log messages** (text in the right panel) = history. Ignore old ones.
- **Popups/menus** (overlay on the viewport) = active. Close with `close_menu`.
- **">press [Space]"** (at bottom of log) = game waiting. Set `"key": "space"`.

**CRITICAL — when `interact` fails**:
If `interact(direction)` results in "There's nothing you can interact with" in the
log, DO NOT call `interact` again with the same direction. Instead:
1. Press `"key": "space"` to dismiss the ">press [Space]" prompt.
2. Use `show_labels` to re-check NPC positions.
3. `move` to a tile that is DIRECTLY adjacent to an NPC (not diagonal, not two
   tiles away — exactly one tile away, cardinal direction).
4. Then try `interact(direction)` again with the correct cardinal direction.
If it fails twice in a row, try a DIFFERENT NPC.

**CRITICAL — when movement is blocked**:
If the message log says "the way is blocked" or "a wall blocks your way",
DO NOT move in that direction again. Pick a COMPLETELY DIFFERENT direction
on your very next turn. If you've bumped into a wall 2+ times in the same
direction, you are stuck — try a perpendicular direction (e.g., if up is
blocked, try left or right). Never repeat a blocked direction more than once.

**CRITICAL — check if you're in look mode**:
If you called `look` recently and then called `move`, you may still be in
LOOK MODE (moving the cursor, not your character). Signs you're in look mode:
- Your character (@) hasn't moved on screen
- The log shows tile descriptions like "a stone wall" or "the way is blocked"
  instead of movement results
If you're stuck in look mode, call `close_menu` to exit, then move normally.

## Strategy Tips

### Early Game (Levels 1-3)
- Stay in **Joppa** and do quests from NPCs.
- Talk to EVERY NPC in town — each may have a quest. Use `interact(direction)`
  when adjacent, then `choose_option(n)` to pick dialogue choices.
- Avoid **Red Rock** caves until level 5+ with decent armor and weapon.
- Avoid the **desert at night** — dawngliders are deadly.
- Pick up everything useful (food, water, trade goods).

### Combat
- **Assess before fighting**: use `look` to check an enemy's difficulty rating.
- **Fight one at a time**: lure enemies to a corridor.
- **Use terrain**: doors can be closed to block enemies.
- **Flee when outmatched**: move away from tough enemies.
- **Heal between fights**: use `wait_until_healed` to recover HP safely.

### Interaction & Dialogue
- Follow the **Finding and Talking to NPCs** protocol at the top of this prompt.
- **Interact**: use `interact(direction)` for context menus (open doors, take items,
  butcher corpses, harvest plants, talk to NPCs).
- **Dialogue choices are NUMBERED** — always use `choose_option(n)`.
- **Trade**: from dialogue, select "Let's Trade" or press Tab. Or use `interact(direction)`
  and select the trade option from the context menu.

### Resource Management
- **Food**: eat when "Peckish" or "Hungry".
- **Water**: drink regularly. Carry extra water when traveling.
- **Money (drams)**: sell trade goods to merchants. Buy better equipment.

### Exploration
- **Explore every tile** in an area before descending.
- **Use `auto_explore`** to systematically clear a level.
- **Mark interesting locations** in your journal.
- **Stairs**: use `go_stairs` when standing on `<` or `>`.
- **Zone travel**: use `travel(direction)` to walk to an adjacent zone.

### Leveling Up
- Spend attribute points (character sheet), skill points (skills), and
  mutation points (mutations) immediately — don't hoard.

### When Things Go Wrong
- If poisoned, find a cure or rest.
- If starving/dehydrated, find food/water immediately.
- If overwhelmed, RUN.
- If permanently stuck, use `abandon` to end the episode cleanly.
- If HP is low, use `wait_until_healed` before fighting more.
