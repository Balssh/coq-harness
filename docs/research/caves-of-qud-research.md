# Caves of Qud for an Agent Harness — Research Brief

*Playing Classic mode (permadeath), vision-in → input-out, no debug console. Focused on what coq-harness needs: controls, presets, game flow, and concrete prompts/tools/modules to add or improve.*

## Key controls

Everything is remappable (`Esc` → Key Mapping); verify once in-game, then freeze. The game distinguishes number-row `D0–9` from numpad keys.

| Action | Key |
|---|---|
| Move / attack | Direction key (numpad default; arrows+Shift diagonals; vi-keys HJKL/YUBN). Walking into a hostile = attack |
| Force attack neutral/wall | `Ctrl` + direction |
| Attack nearest hostile | `Shift+A` |
| Look | `L` (description, gear, health, difficulty rating) |
| Interact (context menu) | `Space` + direction — chat, open, take, butcher, harvest… |
| Pick up | `G` |
| Inventory / Equipment | `I` / `E` |
| Skills / Character sheet | `P` / `X` (attribute points spent here) |
| Quests / Journal | `Q` / `J` |
| Abilities / Message log | `A` / `Ctrl+M` |
| Mutations (spend points) | `M` |
| Autoexplore | Bound key (stops at hostiles, reason in the log) |
| Move to square / zone edge | `Ctrl+Enter` / `Shift+Enter` + direction |
| Wait one turn / until healed | `.` / `~` |
| Stairs up / down | `-` / `+` (going up from the surface enters the world map) |
| Dialogue option | **Press the option's number** (arrow navigation unreliable post-1.0) |
| Trade (from dialogue) | `Tab` or "Let's Trade" |
| System menu | `Esc` → Options / Game Info / Save and Quit / Abandon |

Sources: [Tomothy's Beginner FAQ](https://steamcommunity.com/sharedfiles/filedetails/?id=1711493305), [Wiki — Controls](https://wiki.cavesofqud.com/wiki/Controls) *(flagged out of date — verify in-game)*, [Reddit — dialogue](https://www.reddit.com/r/cavesofqud/comments/1815293/cant_navigate_dialogue_with_numpad/).

## Preset characters

Nine presets, split by genotype; each accepts with one confirm and skips the whole custom-creation tree. ([Wiki — Presets](https://wiki.cavesofqud.com/wiki/Presets), [Palladium Reef patch notes](https://freeholdgames.itch.io/cavesofqud/devlog/307634/the-palladium-reef-feature-arc-is-complete-and-now-live-patch-notes-here))

| Preset | Genotype | Archetype | In one line |
|---|---|---|---|
| **Marsh Taur** | Mutant | Marauder | 22 Str melee bruiser; Freezing Ray, Multiple Legs, Amphibian. The tutorial character — a known quantity for episode 1 |
| **Dream Tortoise** | Mutant | — | Melee fighter with a tortoise shell (great natural armor, but no body armor slot); community-rated very solid beginner start |
| **Gunwing** | Mutant | Gunslinger | 22 Agi ranged build — beak, flight, and ~250 lead slugs; kills from a distance |
| **Star-Eye Esper** | Mutant | Apostle | 21 Ego psychic caster: Clairvoyance, Light Manipulation; fights without closing distance |
| **Firefrond** | Mutant | Watervine Farmer | 20 TN farmer-cook: vinewafers, farmer's token, cookbook — a tanky cooking/trading playstyle |
| **bzzzt** | Mutant | — | Electricity-themed build (details unverified in this research); one player's first "win" preset |
| **Praetorian Prime** | True Kin | Praetorian | 22 Str / 21 TN heavy trooper: rifle, lead slugs, salve injectors |
| **First Gardener** | True Kin | — | Details not verified in this research |
| **First Child of the Hearth** | True Kin | — | Details not verified in this research |

**Why presets matter for the harness:** picking one turns chargen from five navigated screens into a single confirm — the cheapest episode start, and a controlled variable (same build every episode) while everything else varies.

## Game flow (what the prompts need to know)

```
[Title] → New Game → [Mode select] → [Preset or Chargen] → [World gen]
   ↑                                                       ↓
   │          [Play: zone view] ⇄ [Menus / Dialogue / Trade]
   │               overland zone-to-zone walking (Shift+Enter chain)
   │                     [Death screen] → Space at tombstone
   └──────────────────────────────────────────┘
```

- **Title:** New Game is the default cursor; menu also has Continue / Options / Achievements. ([Reddit — main menu](https://www.reddit.com/r/cavesofqud/comments/ua26ue/bugged_main_menu/))
- **Mode select comes right after New Game** — pick Classic, then the preset screen. Currently missing from the chargen spec.
- **Chargen (custom):** genotype → calling/caste → mutations (≤12 pts, ≤1 defect) or implant → attributes (≤44 pts; 2 pts per +1 above 18) → name (`Enter` accepts a random one) → confirm → world gen.
- **Level-up:** +1 to every stat at levels 6/12/18…, +1 allocatable at 3/9/15… (spend on `X`); skill points 50/level (70 True Kin) +4/level per Int above 10 (spend on `P`, skills cost 50–200 SP); mutants 1 mutation point/level, 4 → buy via `M`. ([Wiki — Skills](https://wiki.cavesofqud.com/wiki/Skills), [Wiki — Experience](https://wiki.cavesofqud.com/wiki/Experience))
- **Overland travel:** walking off a zone edge loads the adjacent zone; `Shift+Enter` + direction auto-pathfinds to that edge. No world map needed for short hops — same play screen the whole way. ([Jan 2021 devlog](https://freeholdgames.itch.io/cavesofqud/devlog/209559/feature-friday-january-1-2021))
- **Death (Classic):** tombstone screen → **Space** wipes the save and returns to the title flow. The restart sequence is: Space → title → New Game → mode select → preset → play. ([Wiki — Death](https://wiki.cavesofqud.com/wiki/Death))
- **Reset without dying:** `Esc` → **Abandon** ends the run immediately — the clean "terminate this episode" primitive for a stuck/budget-exceeded episode (verify whether a confirmation dialog appears).
- **Save/quit:** `Esc` offers only Save-and-Quit (no plain save) unless "Allow save and load commands" is enabled in Options → debug (then `F5`/`F9` work). In Classic the save is deleted at death anyway. ([Steam — save hotkeys](https://steamcommunity.com/app/333640/discussions/0/1457328392111783585/))

## Key game mechanics

### Attributes (what each point buys you)

| Attribute | Governs |
|---|---|
| **Strength** | Melee penetration, carry weight |
| **Agility** | Attack accuracy, DV (dodge) |
| **Toughness** | Max HP, poison/disease resistance — beginner rule: never start below 18 |
| **Intelligence** | Skill points per level, artifact identification |
| **Willpower** | Ability cooldown length, mental defense — dumping it = one-shot deaths to psychic attacks |
| **Ego** | Buy/sell prices, mental-mutation power |

- Every **2 points over the base = +1 modifier**; saves are 1d20 + modifier vs difficulty. Skills have flat attribute requirements (odd values meet them).
- **Chargen rule:** 44 points; 1 pt per +1 up to 18, then 2 pts per +1 (max 24 before calling/caste bonuses). ([Wiki — Attributes](https://wiki.cavesofqud.com/wiki/Ego))

### Water economy

- The **dram** is the base currency unit and the only drink: **+10,000 thirst units per dram**; a waterskin holds 64 drams. Fresh water weighs 0.25 lb/dram — carry wealth as light goods (copper nuggets), not water. ([Wiki — Water](https://wiki.cavesofqud.com/wiki/Water))
- Thirst states: Tumescent → Quenched → **Thirsty** → Parched → Dehydrated (death at 0). Auto-drink on reaching "Thirsty" is on by default. Salt water doesn't quench.
- **Water ritual:** offer a dram to a non-hostile legendary creature → water-bonded, faction rep shifts, and a choice menu: trade secrets (+50 rep), gossip (+100), buy a secret (−50), or recruit as follower. The main reputation lever. ([Wiki — Water ritual](https://wiki.cavesofqud.com/wiki/Water_ritual))
- **Hunger** is separate: it debuffs but doesn't kill directly.

### Combat math

- **To hit:** 1d20 + attacker Agility modifier vs 1d20 + defender DV.
- **Damage:** penetration = 3×(1d10−2 + bonus) vs target AV; if all three beat AV, penetration rounds repeat (spiral damage). Resistances are flat percentages. Mental Armor defends psychics; Willpower is True Kin's only mental defense.
- Look difficulty ratings: **"Average" = dangerous 1-on-1; two at once = run.** ([Tomothy's FAQ](https://steamcommunity.com/sharedfiles/filedetails/?id=1711493305))

### XP, leveling, reputation

- XP comes mainly from killing similar-or-higher level creatures (exponential falloff; 0 XP two tiers below you).
- Level-ups grant: attribute points (every stat at 6/12/18…; allocatable at 3/9/15…), skill points (50/level mutant, 70/level True Kin, +4/level per Int above 10), and for mutants 1 mutation point/level.
- Reputation: >600 = friendly, ≤−601 = attack on sight, across dozens of factions; Look shows any creature's demeanor.
- **Death score** = XP + best artifact + quests + turns survived + zones visited + lairs found (+100,000 Brightsheol) — a ready-made scalar episode metric. ([Wiki — Death](https://wiki.cavesofqud.com/wiki/Death))

## Harness improvements: prompts, tools, modules

What to add or change in coq-harness, based on the flow above and the repo's current specs.

### Prompts (per screen)

The repo already composes `system_base` + phase add-ons — give **each screen its own add-on** so the model gets only the grammar that applies. Suggested set:

**`system_base` (always on):** decision schema (reasoning, tool, args, screen, goal, hp, thirst, location, journal_note); report the screen label *before* acting; one tool call per turn; error results are information, not failure.

**Title / mode-select prompt:**
- Expected screens: title menu (New Game is the *default* cursor — don't assume Continue) → mode select → preset/chargen.
- Goal: reach the preset screen and report arrival. Never click Continue, Options, or Achievements.
- Grammar: arrows to move, Enter to confirm; report `title` / `mode_select` so the phase logic can verify progress.

**Chargen prompt (`system_creation`):**
- Name the expected sequence: mode select → Classic → preset screen → (custom: genotype → calling/caste → mutations ≤12 pts ≤1 defect → attributes 44 pts, 2-per-point above 18) → name (`Enter` = random) → confirm → world gen.
- Default policy: accept a preset (one `confirm`); only run the custom pipeline when instructed.
- If the screen doesn't match expectation after a `confirm`, don't spam confirm — report `unknown` and let the watchdog/retry budget handle it.

**Play prompt (`system_play`):**
- Interaction grammar: dialogue options = *press the number*; `Tab` = trade from conversation.
- Survival priors: `L` unfamiliar creatures before engaging ("Average" = dangerous alone, flee from two); retreat + `~` at low HP; drink before Parched; avoid AoE near neutrals.
- Level-up reminder: attribute points on `X`, skill points on `P`, mutation points on `M` — spend them, don't hoard.
- Turn awareness: autoexplore and zone travel advance many turns per call — expect multiple frames and stop-reasons in the log.

**Menu prompt (any modal screen):**
- Grammar: arrows navigate, Enter selects, digits when options are numbered, `Esc` closes and never advances the turn clock.
- Known screens: `I` inventory, `E` equipment, `P` skills, `X` sheet, `Q` quests, `J` journal, `A` abilities.

**Dialogue prompt:**
- Read the numbered options, pick by digit; goals in order: get quest → ask directions → "Let's Trade" if needed; accept water-ritual offers when reputation matters; end with goodbye (or `Esc`).

**Trade prompt:**
- Two panes: their wares / your inventory; select goods, offer, confirm — the cheaper side pays the difference in drams; Ego scales prices; equipped items can't be sold. Decide a target before opening.

**Death prompt:**
- Read the summary (cause, score, turns), write the final journal note (what killed me, what to avoid), then report `death` and stop — the harness owns the Space → restart sequence.

**Screen-report vocabulary to add:** `title`, `mode_select`, `world_map`, `zone_transition`, `dialogue`, `trade` — the current enum (chargen/play/menu/death/unknown) can't distinguish a mode-select screen from a chargen one, and dialogue/trade have different exit semantics than generic menus.

### Tools

| Add / fix | Why |
|---|---|
| `move_to_zone_edge(direction)` | The travel primitive (`Shift+Enter` + NSEW); chains into the overland route to any nearby destination |
| `choose_option(n)` (or document digit presses in `talk`) | Dialogue is digit-key driven |
| `trade()` via `Tab` | Open trade from an open conversation |
| Fix `go_stairs` keys | `-` up, `+` down — not letter keys |
| Fix `SCREEN_KEYS` placeholders | Use `I` inventory, `E` equipment, `P` skills, `X` sheet, `Q` quests, `J` journal, `A` abilities (repo's shift-chords contradict every researched source) |
| `abandon()` | `Esc` → Abandon = terminate a stuck episode cleanly, no death required |
| `wait_until_healed()` | `~` — the recovery primitive every beginner guide relies on |
| `read_quests()` | Open `Q`, capture, close — quest state is otherwise invisible across turns |
| `restart_episode()` | The fixed inter-episode sequence: Space at tombstone → title → New Game → mode select → preset |
| `autoexplore()` | One key, advances **many turns** — expect a burst of frame changes ending in a log stop-reason (hostile spotted, done, interrupted). Feed the final frame + log to the model so it can read *why* it stopped; don't let the watchdog misread it as "stuck" |
| `send_keys(sequence)` / `choose_option(n)` | **Key chaining:** emit a bounded sequence through the controller (`["i", "c", "enter"]`, chords like `["shift", "x"]`), and map a numbered menu option to its digit press. Turns menu micromanagement (equip flow, dialogue replies, stat screens) into single tool calls and keeps the model out of raw-key territory |

### Modules

- **`game/screens.py`:** correct the keybindings (above); consider splitting `MENU` into `dialogue` / `trade` / `world_map` — they look visually distinct and have different exit semantics, which the turn clock and prompt switching care about.
- **`run/creation.py`:** add the mode-select and preset screens to the flow (currently jumps from New Game straight to build choices). A preset accept is one `confirm` — wire it as the default path, with custom chargen as the fallback curriculum.
- **`run/manager.py`:** the game is still sitting on the tombstone when the episode "ends" — the restart sequence (Space → New Game → …) belongs to the harness, and `abandon()` gives the watchdog a non-death termination path.
- **`loop/turn.py` / watchdog:** zone transitions and autoexplore interruptions both announce themselves as frame changes + log lines; treat "autoact stopped" messages as turn-loop events, not noise.
- **Perception:** message-log region already exists; add the Look tooltip bar (top of screen in modern UI) as a second text crop — it's the game's built-in pixel→text reading of any creature.

## Scenario suite (no single-quest overfit, no console needed)

All organic — reachable by just playing, no setup commands:

1. **Village quests:** Mehmet's *Watervine* quest as the one scripted regression yardstick; Argyve's artifact chain (first two steps = bring any artifact; rust wells west of Joppa are the intended source); Otho's *A Call to Arms*. ([Wiki — Joppa](https://wiki.cavesofqud.com/wiki/Joppa), [Steam — quest lines](https://steamcommunity.com/app/333640/discussions/0/598513360098567113/))
2. **Deterministic exploration:** a historic-site statue is guaranteed in the zone just north of Joppa — an NPC-free, verifiable "walk one zone north and interact" task. ([Wiki — Historic site](https://wiki.cavesofqud.com/wiki/Historic_site))
3. **Procedural variety:** rotate the four random starting villages + world seeds for layout diversity with zero tooling changes. ([Wiki — Joppa](https://wiki.cavesofqud.com/wiki/Joppa))
4. **Survival milestones:** survive N turns, reach level 3, accumulate X drams — measurable without any quest logic.

## Caveats

- Wiki [Controls](https://wiki.cavesofqud.com/wiki/Controls) page is flagged out of date; keys above were anchored on the full-release community FAQ and cross-checked — verify once in-game (`Esc` → Key Mapping), then freeze.
- Dialogue digit-key navigation is from player reports after the 1.0-era UI rework; verify on your pinned build.
- Preset details for bzzzt, First Gardener, and First Child of the Hearth weren't verified from sources — check them in the preset screen itself.

## Sources (key)

- **Wiki:** [Controls](https://wiki.cavesofqud.com/wiki/Controls) · [Presets](https://wiki.cavesofqud.com/wiki/Presets) · [Player Character](https://wiki.cavesofqud.com/wiki/Player_Character) · [Skills](https://wiki.cavesofqud.com/wiki/Skills) · [Experience](https://wiki.cavesofqud.com/wiki/Experience) · [Death](https://wiki.cavesofqud.com/wiki/Death) · [Joppa](https://wiki.cavesofqud.com/wiki/Joppa) · [Historic site](https://wiki.cavesofqud.com/wiki/Historic_site) · [Options](https://wiki.cavesofqud.com/wiki/Options) · [Trading](https://wiki.cavesofqud.com/wiki/Trade)
- **Community:** [Tomothy's Beginner FAQ](https://steamcommunity.com/sharedfiles/filedetails/?id=1711493305) · [Qudzoo — Practical Application](https://www.qudzoo.com/advice/novice/application) · [TheGamer — map & stairs](https://www.thegamer.com/caves-of-qud-how-to-use-map-stairs-parasangs/)
- **Devlogs:** [Jan 2021 — move-to-zone-edge](https://freeholdgames.itch.io/cavesofqud/devlog/209559/feature-friday-january-1-2021) · [Nov 2023 — autoact stop reasons](https://freeholdgames.itch.io/cavesofqud/devlog/640522/feature-friday-november-24-2023) · [Palladium Reef — presets & modes](https://freeholdgames.itch.io/cavesofqud/devlog/307634/the-palladium-reef-feature-arc-is-complete-and-now-live-patch-notes-here)
