# Caves of Qud — early-game notes for the agent

Distilled from the Qudzoo New Player Guide (https://www.qudzoo.com/advice/novice:
ui, fundamentals, positioning, application, sheet). Intended as prompt material
for any LLM driving the MCP tools.

## Survival rules
- **Never fight at low HP.** Track how much each enemy hit does (the message log
  has exact numbers) and keep a buffer of 2-3 hits. Below ~50-60% HP: retreat,
  heal, or leave via stairs / zone edge. Running away is always fine.
- **Rest to full after every fight** (`wait` repeatedly until HP is full) before
  moving on. There is no time pressure: eating is free and water lasts.
- **Avoid "Very Tough" and "Impossible" creatures**; treat "Tough" with caution.
  Difficulty scale: Trivial > Easy > Average > Tough > Very Tough > Impossible.
  Health scale: Perfect > Fine > Injured > Wounded > Badly Wounded.
- **Retreat toward explored territory**, never forward into the unknown.
- Healing: salve injectors (good), witchwood bark (heals but may confuse).
- Water ("drams", `$`) is both drink and currency. Keep ~128 drams (2 waterskins).
  Thirst is handled automatically while you carry fresh water. Below 50 drams,
  stay near a town. Dehydrated! = constant damage.
- Hunger: Sated > Hungry > Famished! (Famished only slows you). Eat when hungry.
- Weight: over the carry limit you cannot move at all.

## Combat positioning (the most important skill)
- Fight one enemy at a time: back into corridors/doorways so only one tile is
  adjacent to you. Watch the diagonals — diagonal moves cost the same as
  cardinal ones and enemies use them.
- If an enemy is approaching, **wait for it to step next to you** instead of
  walking into its reach — you get the first hit.
- Ranged enemies won't come to you; close the distance using cover (walls,
  trees) to break line of sight.
- Kill the enemy you can kill fastest first (removes a damage source sooner).
- Zone-edge trick: step across a zone border and one tile back; pursuers arrive
  one at a time and cannot shoot until they are on your screen.
- Use abilities/mutations — forgetting them is the #1 newbie mistake. Always
  keep a ranged weapon equipped; it costs nothing to fire.
- Bump-attack = move into a hostile. Moving into a friendly swaps places.

## Joppa and the first quest ("What's Eating the Watervine?")
1. Explore Joppa, talk to **Mehmet** -> accept the job. (Water ritual is
   optional.)
2. Don't enter Red Rock at level 1. Approach from the parasang **south** of Red
   Rock (1 parasang north of Joppa on the world map), walk north zone by zone.
   Entering Red Rock completes a quest step (+XP).
3. Level up on **baboons** around Red Rock: 1-2 baboons — stand still and let
   them run out of stones, then melee them. 3+ — use the zone-edge trick.
   **Hulking baboons** (yellow, throw boulders): skip until level 4+.
4. Aim for level 5-7 before going down the Red Rock stairs. Underground you need
   a light source (torch equipped).
5. The watervine vermin are **girshlings**, in the caves under Red Rock (take
   the stairs down; on stratum 4 in our runs). Kill one, pick up its corpse,
   return to Joppa and show it to **Elder Irudad** -> meds reward (salve
   injectors). Other corpses (snapjaws, baboons) don't count: the quest log's
   "Find the Vermin" step ticks only when you find the girshlings.
6. Give Argyve cheap artifacts for his quest; his reward line gives a
   **recoiler** (teleport home) — get one before deeper cave diving.

## Dangers seen in our own runs
- Giant amoeba (Red Rock stratum 2): ~8-11 damage per hit vs a level-1 char,
  killed us. Don't melee it at low level; retreat to the stairs early.
- Dreadroots: hostile plants that cause terror.

## World / economy
- Zone = one screen; parasang = 3x3 zones = one world-map tile.
- Further east = more dangerous. Salt marsh (start) is level 1; desert canyon /
  salt dunes ~5; jungles 17+. Avoid hills, mountains, rivers, banana groves,
  rainbow wood early.
- Copper nuggets etc. are trade goods worth carrying. Items worth >=4 drams per
  pound are worth picking up to sell.
- Armor: aim for 6-8 AV early.

## Using the MCP tools (lessons from test runs)
- Every action result shows a short status: HP, hostiles with coordinates, new
  messages. Call `get_state` for inventory and everything nearby.
- Popups pause the game. Answer them with `respond_popup`; they often come in
  chains (quest step -> XP -> level up). Containers open an item list:
  `respond_popup(option=N)` takes one item, `button="take_all"` takes all.
- After every fight: `rest()`. After a level-up: `list_skills` + `learn_skill`,
  and `raise_attribute` when you have attribute points. Unspent points = weak
  character.
- Targeted abilities and mutations (Freezing Ray, Proselytize, Mark Target...): `use_ability(name)`
  aims at the nearest visible hostile; pass `x, y` for another target. Mind their range.
- Ranged first: `fire()` shoots the nearest hostile (auto-reload). Shooting a
  hulking baboon while it walks up killed it before it reached melee. Ammo is
  consumed — keep track of arrows.
- Some hostile plants (dreadroots) don't block movement, so walking into them
  doesn't attack: use `attack` (works on anything, incl. vines).
- `attack()` with no arguments hits the adjacent hostile; `attack(x, y)` hits that
  adjacent cell. Safer than working out compass directions for a bump-attack.
  Dreadroots cause terror when they die nearby.
- `flee()` does the zone-edge trick for you: it walks to the edge or stairs you reach well ahead
  of the hostiles and leaves the zone. `go_to_place("Joppa")` walks to a known place zone by zone.
- `go_to(x, y)` stops next to a creature target without attacking; then use
  `move` / `attack` toward it.
- The "Your health has dropped below 60%!" popup is dismissed for you and shows
  up as a `WARNING:` line — treat it as the signal to decide whether to retreat.
- Trading: `interact` with a merchant, pick "Let's trade", `trade_list`, then
  `trade_select(side, index, count)` (side 0 = buy, 1 = sell; count=-1 = whole
  stack) and `trade_offer`; confirm the dram popup with `respond_popup`. Water is
  money: arrows cost ~0.02 drams each, scrap (bent metal, microchips) sells for
  2-4 drams. `close_menu` leaves the screen, which returns to the conversation.
- The map and state only show what you know: `?` on `get_map` is unexplored, and
  creatures appear only while in line of sight.
- World-map steps take several seconds each (lots of game time passes).
- Melee damage numbers seen at level 3-5 with AV 2: baboon 2-6 per round,
  hulking baboon 7-9 per round (x4-5 bites), giant centipede 1-4.
