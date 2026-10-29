# ML4 assessment: how well Mistral Large 4 plays Caves of Qud (2026-10-29)

Mistral Large 4 (`mistral-large-4`, reasoning effort high), playing through the harness and MCP
tools described in [`harness.md`](harness.md), over nine supervised new-game runs of 118–300 steps
each (`ml4-opening-1` to `ml4-opening-9`). The harness changed between runs, so later runs had more
help; the table in [`harness.md`](harness.md#supervised-opening-runs-2026-10-29) lists what
changed after each one.

## Summary

ML4 is a competent early-game player inside this harness. It reliably takes a fresh character
through the Joppa opening and to level 4–6 within 250 steps. It isn't yet a player that makes
progress in the game: no run finished the first main quest, and four of the nine runs died, each
in a fight it could have walked away from.

What holds it back is judgment over time: when to stop a fight, when to spend a resource, how to
sequence a quest. Knowledge and mechanics are rarely the problem now. The harness has turned most
knowledge gaps into status lines: threat ratings, damage numbers, creature tactics, terrain, quest
steps.

## The runs

| Run | Character | Result | Highest level | Level 4 at step |
|---|---|---|---|---|
| 1 | Praetorian Prime | alive at 250 | 2 | – |
| 2 | Praetorian Prime | died at 118 (gelatinous frustum) | 4 | 83 |
| 3 | Praetorian Prime | alive at 300 | 3 | – |
| 4 | Gunwing | died at 127 (hulking baboon) | 1 | – |
| 5 | Praetorian Prime | died at 222 (Naphtaali, in a jungle) | 4 | 205 |
| 6 | Praetorian Prime | alive at 300 | 3 | – |
| 7 | First Gardener | died at 178 (hulking baboons) | 5 | 130 |
| 8 | Gunwing | alive at 250 | 6 | 141 |
| 9 | Praetorian Prime | alive at 250 | 5 | 120 |

Across the runs, 2–8% of tool calls failed (most often 2–4%), and in about 2,900 calls the model
produced invalid arguments once. Each run used 2.4–3.8M prompt tokens, about 12–13k per step, of
which Mistral reported 85–95% as cached after the first ~30 steps.

## Skill by skill

| Skill | Rating | Evidence |
|---|---|---|
| Using the tools | Strong | Reads results, answers popups and conversations, trades, equips gear, spends skill and attribute points every level, all without help. |
| Opening routine | Strong | Since the opening plan was added, it sweeps Joppa, talks to Mehmet, Argyve, Elder Irudad and Tam, takes both quests, sells junk and buys armor and a weapon in roughly the first 60 steps. |
| Leveling | Good, much improved | Runs 7–9 reached level 4 by step 120–141; of runs 1–6 only two did, at steps 83 and 205. It plays to the build: the Gunwing fired 127 times in run 8, the melee builds charge. |
| Navigation | Good with tools, weak alone | With `go_to_place` it went between Joppa and Red Rock without mistakes (19 calls in runs 7–9). In its own reasoning it still mixes up compass directions (run 7, step 118). On its own it walked into a jungle in run 5. It called `world_map` once in nine runs. |
| Combat tactics | Fair | Shoots at range, finishes nearly dead enemies, kites baboons. Doesn't disengage: in run 7 it kept shooting while two hulking baboons closed in, then crossed a zone edge at 8 HP with healing items unused, and one followed it. |
| Risk judgment | Weak | The main cause of death. In runs 2, 4, 5 and 7 it had the information (its own words calling the enemy too dangerous, the threat rating, the health warning, the zone CAUTION) and fought or carried on anyway. The `DANGER:` line and combat check help, but it acts on them only sometimes; it first called `flee()` on its own in run 9. |
| Resources | Weak | Sold all its bandages for ammo (run 8), died with a salve injector and three witchwood barks in its pack (run 7), let hunger reach Famished, made repeated trade passes. |
| Quests | Weak | Accepts quests and notes them, but follows multi-step quests badly. Argyve's quest was finished in runs 6 and 9. "What's Eating the Watervine?" never was: run 6 tried to hand in a snapjaw corpse, and later runs ran out of steps while exploring every level of the caves. |
| Memory and learning | Fair | Uses goals and notes well (8–16 per run). The lessons it writes at the end of a run are about half right. The wrong ones usually come from tool output it misread, e.g. "travel only works from zone edges" when hostiles in view were the cause. That's why `runs/journal.md` is pruned by hand. |

## The pattern behind the failures

The deaths share one shape. The model sees the danger, says so, and keeps going, because the next
action looks locally reasonable: one more shot, one more step to the edge. It handles single
decisions well and sequences of decisions badly, especially when stopping means giving up progress
(XP, a quest step, a half-dead enemy).

Prompts move this only partly. The facts are already in front of it. The open question is how much
the harness should decide for it.

## What would help next

1. **Make retreat the default when the numbers are bad.** The harness could act on its own danger
   estimate (two worst rounds would kill) by healing or fleeing unless the model explicitly
   insists. This is a policy choice about how much the harness plays for the model.
2. **A quest helper** that turns the quest log into a concrete next step each turn, e.g. "Find the
   vermin: girshlings, under Red Rock, stratum 4: `go_to_place('Red Rock')`, then
   `go_stairs('down')`". Quests are the weakest skill and the biggest gap to real progress.
3. **Longer runs** (500–1,000 steps). At 250–300 steps the step limit, not death, ended five of the
   nine runs; ML4 hasn't been seen past level 6 or deep underground.

## Caveats

- **Few runs.** Nine runs is a small sample, and the harness changed between them, so later runs are
  not like-for-like with earlier ones.
- **Starting characters.** The model picked its own preset each run (Praetorian Prime six times), so
  the results lean toward one sturdy melee build.
- **Approximate counts.** XP gains and quest counts were read from the message log; before the fix in
  mod 0.13.23 some old messages were shown again as new and counted twice.
