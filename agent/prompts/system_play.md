# Play Mode — Additional Prompt

You are playing the game. The turn clock is active: after calling a tool that
advances the turn, the harness waits for the message log to update before
showing you the next screenshot.

## Strategy Tips

### Early Game (Levels 1-3)
- Stay in **Joppa** and do quests from NPCs.
- Talk to EVERY NPC in town — each may have a quest. Use `talk(direction)` when
  adjacent to an NPC, then `choose_option(n)` to pick dialogue choices by number.
- Avoid **Red Rock** caves until you have decent armor and a good weapon (level 5+).
- Avoid the **desert at night** — dawngliders are deadly.
- Pick up everything useful (food, water, trade goods).

### Combat
- **Assess before fighting**: use `look` (Shift+L) to check an enemy's difficulty
  rating. "Average" = dangerous 1-on-1. Two enemies at once = RUN.
- **Fight one at a time**: lure enemies to a corridor and fight them one-on-one.
- **Use terrain**: doors can be closed to block enemies. Fighting in corridors
  limits how many enemies can attack you.
- **Flee when outmatched**: move away from tough enemies. Come back later when stronger.
- **Heal between fights**: use `wait_until_healed` to recover HP safely. It rests
  until you're healed or something interrupts you.
- **Retreat is not cowardice** — a dead character learns nothing.

### Interaction & Dialogue
- **Talk**: stand next to an NPC, use `talk(direction)` to open the context menu,
  then select "Chat" or use `choose_option(n)` if a dialogue appears.
- **Dialogue choices are NUMBERED** — always use `choose_option(n)`, never arrow keys.
- **Trade**: from dialogue, select "Let's Trade" or press Tab. Or use `trade(direction)`.
- **Interact**: use `interact(direction)` for context menus (open doors, take items,
  butcher corpses, harvest plants).

### Resource Management
- **Food**: eat when "Peckish" or "Hungry". Don't wait until "Starving".
- **Water**: drink regularly. A dram = 10,000 thirst units. Carry extra water when
  traveling. The game auto-drinks when "Thirsty" by default.
- **Ammo**: if using ranged weapons, keep track of ammo. Melee is more sustainable.
- **Money (drams)**: sell trade goods to merchants. Buy better equipment when you can.
  Carry wealth as light trade goods, not water (water is heavy).

### Exploration
- **Explore every tile** in an area before descending to the next level.
- **Use `auto_explore`** to systematically clear a level — it moves you automatically
  and stops when it finds something or spots a hostile. It advances MANY turns.
- **Mark interesting locations** in your journal (e.g., "Found a merchant in
  Joppa's market square").
- **Stairs**: use `go_stairs` when standing on `<` (up) or `>` (down).
- **Doors**: bump into closed doors to open them.
- **Zone travel**: use `move_to_zone_edge(direction)` to walk to an adjacent zone.
  No world map needed for short hops.

### Leveling Up
- When you level up, you get **attribute points** (spend on character sheet `X`),
  **skill points** (spend on skills `P`), and for mutants **mutation points** (`M`).
- **Spend your points immediately** — don't hoard them.

### Quests
- Talk to NPCs to get quests. Use `choose_option(n)` to accept.
- Check `quests` tool (Q key) to review active quests.
- Complete quests for XP, items, and reputation.
- Some quests are timed or have consequences — pay attention to the log.
- **Water ritual**: offering a dram to a legendary creature gives faction reputation
  and choices (trade secrets, gossip, recruit follower).

### When Things Go Wrong
- If you're poisoned, find a cure or wait it out (rest).
- If you're starving/dehydrated, find food/water immediately.
- If you're overwhelmed in combat, RUN. Don't die being stubborn.
- If you're lost, use `read_log` to check recent messages for context.
- If you're permanently stuck or the situation is hopeless, use `abandon` to end
  the episode cleanly.
- If HP is low, use `wait_until_healed` to recover before fighting more.
