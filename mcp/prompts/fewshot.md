# Examples

## Example 1: Exploring

**Game State:**
```
=== Player: Amos ===
HP: 25/25  Level: 1  XP: 0/100
Location: Joppa
Position: (40, 12)

=== Nearby Objects ===
Creatures: 3, Items: 1, Doors: 2, Containers: 1, Walls: 15
  Elder Irudad at (41,12) (dist 1) [creature, friendly, HP 30/30, Lvl 3]
  Mekhmet at (38,14) (dist 3) [creature, friendly, HP 20/20, Lvl 1]
  Vinewafer at (40,12) (dist 0) [item]
  Wooden Door at (39,12) (dist 1) [door]

=== Recent Messages ===
  You enter Joppa.
  The village of Joppa spreads before you.
```

**Response:**
```json
{
  "reasoning": "I'm in Joppa with full HP. There's a vinewafer on my tile and Elder Irudad is adjacent. Let me pick up the vinewafer first, then talk to Irudad.",
  "tool": "get",
  "args": {},
  "goal": "Pick up items and talk to NPCs in Joppa",
  "journal_note": "Starting in Joppa. Elder Irudad (mayor) is nearby, Mekhmet is 3 tiles south."
}
```

## Example 2: Moving Toward an NPC

**Game State:**
```
=== Player: Amos ===
HP: 25/25  Level: 1  XP: 50/100
Location: Joppa
Position: (40, 12)

=== Nearby Objects ===
Creatures: 2, Items: 0, Doors: 2, Containers: 0, Walls: 10
  Tam at (43,12) (dist 3) [creature, friendly, HP 25/25, Lvl 2]
  Warden Yrame at (40,9) (dist 3) [creature, friendly, HP 30/30, Lvl 3]

=== Recent Messages ===
  You pick up a vinewafer.
  You feel satiated.
```

**Response:**
```json
{
  "reasoning": "Tam the merchant is 3 tiles to the east (x=43, my x=40). I should move right to get closer. Then I can buy a gun.",
  "tool": "move",
  "args": {"direction": "right"},
  "goal": "Buy a musket from Tam",
  "journal_note": null
}
```

## Example 3: Combat

**Game State:**
```
=== Player: Amos ===
HP: 18/25  Level: 2  XP: 80/200
Location: Salt Marsh
Position: (20, 15)
In Combat: true

=== Nearby Objects ===
Creatures: 1, Items: 0, Doors: 0, Containers: 0, Walls: 3
  Snapjaw at (21,15) (dist 1) [creature, HOSTILE, HP 6/8, Lvl 1]

=== Recent Messages ===
  The snapjaw bites you! You take 3 damage.
  You strike the snapjaw! It takes 5 damage.
```

**Response:**
```json
{
  "reasoning": "I'm fighting a snapjaw. It's almost dead (HP 6/8) and I have a gun equipped. I should shoot it with press_command to deal damage safely.",
  "tool": "press_command",
  "args": {"command": "CmdFire"},
  "goal": "Kill the snapjaw and continue exploring",
  "journal_note": null
}
```

## Example 4: Dialogue

**Game State:**
```
=== Player: Amos ===
HP: 25/25  Level: 2  XP: 150/200
Location: Joppa
Position: (41, 12)

=== Recent Messages ===
  Elder Irudad says: "Welcome, traveler. What brings you to Joppa?"
  [1] Tell him about your journey.
  [2] Ask about quests.
  [3] Ask for a water ritual.
  [4] Say goodbye.
```

**Response:**
```json
{
  "reasoning": "Elder Irudad is offering dialogue options. I should ask about quests first to get started, then do a water ritual for reputation.",
  "tool": "choose_option",
  "args": {"option": 2},
  "goal": "Get quests from Elder Irudad",
  "journal_note": "Elder Irudad offers quests and water rituals."
}
```

## Example 5: Auto-Explore

**Game State:**
```
=== Player: Amos ===
HP: 25/25  Level: 3  XP: 350/400
Location: Salt Marsh
Position: (10, 8)
In Combat: false

=== Nearby Objects ===
Creatures: 0, Items: 0, Doors: 0, Containers: 0, Walls: 0

=== Recent Messages ===
  You enter the salt marsh.
  The air smells of salt and decay.
```

**Response:**
```json
{
  "reasoning": "I'm in the salt marsh with no nearby threats. I should auto_explore to discover the area efficiently instead of walking tile-by-tile.",
  "tool": "auto_explore",
  "args": {},
  "goal": "Explore the salt marsh and find enemies to fight for XP",
  "journal_note": "Entered salt marsh. Will auto-explore to find weak enemies."
}
```
