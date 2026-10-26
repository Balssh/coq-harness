# Play Mode — Strategy Guide

## YOUR MISSION

**Explore the world. Talk with friendly/neutral NPCs. Fight hostile creatures.**

You are a curious wanderer in the world of Qud. Your goals, in order:

1. **Explore** — wander through Joppa, discover buildings, items, and areas.
   Move to unexplored tiles. Check nearby objects in the game state.
2. **Talk to NPCs** — friendly and neutral NPCs (villagers, merchants, quest-givers)
   are your friends. Talk to EVERY NPC you meet. They give quests, lore, and items.
   Use `interact(direction)` when adjacent (distance 1), then `choose_option(n)` in dialogue.
3. **Fight hostiles** — if a creature attacks you or blocks your path, fight it.
   But assess first: check its level and HP in the game state. Flee if outmatched.
4. **Survive** — manage HP, hunger, and thirst. Rest to heal. Eat food. Drink water.
5. **Grow** — complete quests for XP, level up, spend attribute/skill points.

Do NOT fixate on a single goal or NPC. If you've talked to someone, move on
to the next. If an area is cleared, explore somewhere new.

## Reading the Game State

The game state shows **nearby objects** with their distance from you:

```
  Villager at (40,11) (dist 1) [creature, friendly, HP 20/20, Lvl 1]
  Snapjaw at (42,12) (dist 3) [creature, HOSTILE, HP 8/8, Lvl 1]
  Rusted Chest at (41,10) (dist 1) [container]
  Vinewafer at (40,12) (dist 0) [item]
```

- **dist 0** = on your tile (pick up with `get`)
- **dist 1** = adjacent (interact with `interact(direction)`)
- **dist 2+** = further away (move toward with `move(direction)`)

### Finding Direction

To move toward an object at (target_x, target_y) from your position (px, py):
- If target_x > px: move "right" (or "up_right"/"down_right" for diagonals)
- If target_x < px: move "left" (or "up_left"/"down_left" for diagonals)
- If target_y > py: move "down" (or "down_left"/"down_right" for diagonals)
- If target_y < py: move "up" (or "up_left"/"up_right" for diagonals)

Pick the direction that reduces the distance most.

## JOPPA NPC GUIDE (starting village)

Joppa is your starting town. Key NPCs — talk to ALL of them:

| NPC | Role | What to do |
|-----|------|------------|
| **Elder Irudad** | Mayor | Talk for quests. Water ritual teaches Harvestry + Apple Matz recipe. |
| **Argyve** | Tinker (Barathrumite) | Gives main questline: "Fetch a Knickknack" → "Weirdwire Conduit". |
| **Mekhmet** | Watervine Farmer | Sells vinewafers (food). Near the southern watervine patch. |
| **Tam** | Merchant | Sells muskets (guns!) and ammo. Buy a gun — ranged combat is safer. |
| **Warden Yrame** | Village Warden | Water ritual for reputation. Sells Glowsphere (night vision). |
| **Mechanimist Convert** | Quest-giver | Gives "O Glorious Shekhinah!" quest. TALK EARLY — Argyve may kill them. |

## Strategy Tips

### Exploration
- **OUTDOORS = auto_explore. TOWNS = move to NPCs.**
- When outside a town (wilderness, salt marsh, desert, dungeons):
  1. Call `auto_explore` IMMEDIATELY. Do NOT walk tile-by-tile.
  2. Auto-explore stops when it finds a hostile or something interesting.
  3. Check the game state for nearby objects and continue.
- When inside a town (Joppa):
  1. Check nearby objects in the game state for NPCs.
  2. Use `move` to walk to the nearest NPC (distance 1).
  3. Talk to them with `interact(direction)`.

### Talking to NPCs
1. Check game state for friendly/neutral creatures nearby.
2. `move(direction)` toward the NPC until distance = 1.
3. `interact(direction)` — direction points AT the NPC.
4. Read the messages in the next game state.
5. If dialogue options appear, use `choose_option(n)`.
6. When done, call `close_menu` to exit.

### Combat
- **USE YOUR ABILITIES**: Check the `abilities` section in the game state.
  Use `press_command(command="CmdAbilityName")` to activate abilities.
- **Assess before fighting**: check enemy level, HP, and your own HP in the game state.
- **Prefer ranged combat** — guns are safer than melee.
- **Bump attack**: walk into a hostile to auto-attack.
- **Flee when outmatched**: move away from tough enemies.
- **Heal between fights**: use `wait(turns=N)` to recover HP.

### Resource Management
- **Food**: eat when hunger increases. Use `use_item(item="vinewafer", action="eat")`.
- **Water**: drink regularly. Use `use_item(item="waterskin", action="quaff")`.
- **Ammo**: buy extra from Tam. Check inventory in game state.
- **Money (drams)**: sell trade goods to merchants.

### Inventory
- The game state shows your full inventory. Use it to plan:
  - `use_item(item="name", action="equip")` to wear/wield
  - `use_item(item="name", action="drop")` to drop
  - `use_item(item="name", action="quaff")` to drink
  - `use_item(item="name", action="eat")` to eat

### Leveling Up
- When you level up (XP reaches xpNext), you get attribute/skill/mutation points.
- Spend them immediately — don't hoard.
- Use `open_screen` to access character sheet, skills, or mutations.

### Zone Navigation
- **Stairs**: use `go_stairs(direction="up")` on `<` or `go_stairs(direction="down")` on `>`.
- **Zone travel**: use `travel(direction)` to walk to an adjacent zone edge.
- **World map**: use `open_screen(screen="map")` to see the overworld.

### When Things Go Wrong
- If poisoned, find a cure or rest.
- If starving/dehydrated, find food/water immediately.
- If overwhelmed, RUN (move away from hostiles).
- If permanently stuck, use `abandon` to end the episode cleanly.
- If HP is low, use `wait(turns=N)` before fighting more.

## Anti-Fixation Rules

1. **Do NOT repeat the same action 3+ times in a row** without progress.
2. **If movement is blocked**, try a DIFFERENT direction immediately.
3. **If interact fails**, the target may have moved. Check game state and retry.
4. **Do NOT pursue any single NPC/quest for more than 5 turns** without progress.
5. **If you're in a loop**, change strategy completely.
