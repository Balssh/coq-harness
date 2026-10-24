# Play Mode — Additional Prompt

You are playing the game. The turn clock is active: after calling a tool that
advances the turn, the harness waits for the message log to update before
showing you the next screenshot.

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
- **Talk**: stand next to an NPC, use `interact(direction)`, then select
  "Chat" or use `choose_option(n)` if a dialogue appears.
- **Dialogue choices are NUMBERED** — always use `choose_option(n)`.
- **Trade**: from dialogue, select "Let's Trade" or press Tab.

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
