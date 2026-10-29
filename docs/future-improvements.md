# Possible improvements

A reference list of ideas for later, gathered from the supervised runs (see
[`ml4-assessment.md`](ml4-assessment.md)) and the known limitations in [`harness.md`](harness.md).
None of these are planned or started. Within each section they are roughly in order of expected
value.

## Helping the model play better

- **Retreat by default when the numbers are bad.** Four of nine runs died in fights the model had
  already called too dangerous. The harness could act on its own danger estimate (two of the
  enemy's worst rounds would kill) by healing or calling `flee()` unless the model explicitly
  insists on fighting. Today the combat check only holds back one melee blow. This is a policy
  choice: how much should the harness play for the model?
- **A quest helper.** Quests are the weakest skill. A status line or tool could turn the quest log
  into one concrete next step, e.g. "Find the vermin: girshlings, under Red Rock, stratum 4:
  `go_to_place('Red Rock')`, then `go_stairs('down')`". It needs per-quest knowledge (a small data
  file like `data/creatures.json`) or a lookup in the game's quest data through the mod.
- **Point at healing items.** Run 7 died with a salve injector and three witchwood barks unused.
  When `DANGER:` is up, the line could name the healing item to use and the exact `use_item` call.
- **Hunger and resources.** Show "Hungry" more prominently and suggest the food to eat; warn before
  selling the last healing item or the ammo for the equipped weapon.
- **A reflection pass.** There's one model call per step and no planner or critic. A slower call
  every N steps (next to compaction) could review the goal, the quest and recent damage, and rewrite
  the plan.
- **More creature knowledge.** `data/creatures.json` covers common early creatures by hand. The mod
  could read creature blueprints (HP, attacks, special abilities) so every creature gets a `KNOW`
  line, not just the ones written up.
- **Searchable game knowledge.** Everything the model knows comes from the guide notes and the
  journal. A `lookup(topic)` tool over an offline copy of the wiki would help with items, factions
  and quests. The wiki is partly outdated, so the answers would need a warning.
- **Better lessons.** About half of the model's end-of-run lessons are wrong, usually because it
  misread tool output. The lessons could be checked against the recorded events before they're
  kept, or a second pass could merge them into the hand-kept sections instead of appending.

## The harness

- **Resumable runs.** Runs can't be resumed; a new run starts with empty notes. Saving the memory
  and summary next to a game save would allow 1,000-step runs over several sessions.
- **Longer runs.** At 250–300 steps the step limit, not death, ended five of nine runs. ML4 hasn't
  been seen past level 6 or deep underground.
- **Count tokens, not characters.** The context size is estimated in characters; a tokenizer (or
  the `usage` the API returns) would make compaction more precise.
- **Character variety.** The model picked Praetorian Prime six times out of nine. A `--character`
  option or a rotation would test other builds, and custom character creation (mutations, castes)
  isn't exercised at all.

## Evaluation

- **Unattended batches.** Run N games in a row with a fixed step limit and collect metrics per run:
  levels, deaths and their cause, quests finished, failed calls, tokens. The supervised runs were
  done one at a time by hand.
- **A results page.** A table or charts over all recorded runs in the replay viewer, so the effect
  of a change shows up across runs instead of in one anecdote.
- **Compare models.** `harness/llm.py` already speaks to OpenAI and OpenRouter. The same batch on
  several models would show which failures are ML4's and which are the harness's.
- **Fixed starts.** Start every run from the same save (or the same world seed) so runs are
  comparable.

## The mod and the MCP server

- **Game systems not exposed yet:** tinkering, cooking, the water ritual and reading books have no
  tools. They matter later in the game rather than in the opening.
- **Tests.** There's no automated test suite. Recorded states in `runs/harness/*/states/` could
  drive tests of the compact formatting, pathing, `flee` and `go_to_place` without the game running.
- **Faster turns.** Several tools wait for the turn to end by polling the state. An event pushed by
  the mod when the turn resolves would make long walks faster.

## Housekeeping

- **`docs/mcp/architecture.md`** describes an earlier `mcp/` agent that no longer exists; it should
  be rewritten or folded into [`how-it-works.md`](how-it-works.md).
- **Journal pruning by hand.** `runs/journal.md` is pruned by hand after every few runs. A
  `harness journal prune` command that asks the model to merge and deduplicate (with a human
  review) would save the chore.
