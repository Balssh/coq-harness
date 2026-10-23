# Death Screen — Additional Prompt

You have **died**. The tombstone screen shows your death summary: cause of death,
score, turns survived, and stats.

## What To Do

1. **Read the death summary carefully.** Note what killed you, your final score,
   turns survived, and any notable achievements.
2. **Write a final `journal_note`** — this is critical. Record:
   - What killed you (enemy type, situation, location)
   - What you should avoid in future runs
   - How far you got (level, quests completed, areas explored)
   - Any useful discoveries (loot locations, quest hints, danger zones)
3. **Report `"screen": "death"`** — the harness will handle the restart sequence
   (Space at tombstone -> title -> New Game -> mode select -> preset).

## Example Journal Note

```
[death] Killed by a pack of baboons in Red Rock level 3 at turn 340, level 4.
Learned: don't enter Red Rock below level 5. Baboons are much faster than expected.
Reached: Joppa quests (2/3), found a steel dagger and leather armor. Score: 1,200.
```
