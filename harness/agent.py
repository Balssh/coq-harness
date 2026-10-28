"""The play loop: the model calls the MCP tools, the harness manages memory and records the run.

One step = one model response (text + tool calls) and the results of those calls. After every
game action the harness snapshots the full game state and a screenshot for the replay.
"""

import asyncio
import json
import re
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

from harness.capture import Screenshotter
from harness.game import Game
from harness.llm import ChatClient, Reply
from harness.memory import MEMORY_TOOL_NAMES, MEMORY_TOOLS, Journal, Memory
from harness.recorder import Recorder

PROMPTS = Path(__file__).parent / "prompts"

DEFAULT_OBJECTIVE = ("Explore the world, talk with friendly and neutral NPCs, take on quests (start with "
                     "the ones in Joppa), fight hostile creatures you can beat, and level up. Stay alive.")

# Calls that still make sense while a popup or screen is open; other game actions queued
# in the same response are skipped, since the game ignores them until it's closed.
_SCREEN_OK = {"respond_popup", "close_menu", "get_state", "get_map", "trade_list", "trade_select", "trade_offer",
              "list_skills", "learn_skill", "raise_attribute"}

_DEATH = re.compile(r"\byou (have )?died\b|\byou are dead\b", re.I)


@dataclass
class Config:
    objective: str = DEFAULT_OBJECTIVE
    max_steps: int = 300
    max_minutes: float = 0.0          # 0 = no time limit
    new_game: bool = False            # from the main menu: new random character instead of continuing
    screenshots: bool = True
    shot_width: int = 1280
    keep_steps: int = 30              # steps kept verbatim in the context before summarizing
    full_result_steps: int = 6        # tool results older than this are shortened in the context
    max_context_chars: int = 160_000  # also summarize when the context gets this big
    max_calls_per_step: int = 4
    autosave_every: int = 50
    runs_dir: Path = Path("runs/harness")
    journal: Path = Path("runs/journal.md")
    label: str = ""
    llm_info: dict = field(default_factory=dict)


def _brief(state: dict) -> dict:
    """The few state fields the viewer's timeline and the watchdog need."""
    p = state.get("player") or {}
    popup = state.get("popup") or {}
    return {"hp": p.get("hp"), "hpMax": p.get("hpMax"), "level": p.get("level"), "xp": p.get("xp"),
            "x": p.get("x"), "y": p.get("y"), "zone": (state.get("zone") or {}).get("name"),
            "zoneId": (state.get("zone") or {}).get("id"), "screen": state.get("screen"),
            "popup": (popup.get("title") or popup.get("message") or "")[:120] if popup else "",
            "segment": (state.get("time") or {}).get("segment"), "dead": bool(state.get("isDead"))}


def _is_dead(state: dict) -> bool:
    if state.get("isDead"):
        return True
    popup = state.get("popup") or {}
    text = f"{popup.get('title', '')} {popup.get('message', '')}"
    hp = (state.get("player") or {}).get("hp")
    return bool(_DEATH.search(text)) or (state.get("inGame") and isinstance(hp, int) and hp <= 0)


def _render_steps(steps: list[list[dict]], result_chars: int = 500) -> str:
    """Plain-text transcript of steps, for summaries and lessons."""
    out = []
    for step in steps:
        for m in step:
            if m["role"] == "assistant":
                if m.get("content"):
                    out.append(f"You: {m['content']}")
                for c in m.get("tool_calls") or []:
                    out.append(f"-> {c['function']['name']}({c['function']['arguments']})")
            elif m["role"] == "tool":
                out.append("Result: " + m["content"][:result_chars].replace("\n", " | "))
            else:
                out.append("Harness: " + m["content"][:300])
    return "\n".join(out)


class Agent:
    def __init__(self, cfg: Config, llm: ChatClient, repo_root: Path):
        self.cfg = cfg
        self.llm = llm
        self.repo_root = repo_root
        self.memory = Memory()
        self.journal = Journal(cfg.journal)
        self.history: list[list[dict]] = []
        self.opening = ""
        self.step = 0
        self.n_snap = 0
        self.last_state: dict = {}
        self.stop_reason = ""
        self.tokens = {"prompt": 0, "completion": 0}
        self._progress: list[tuple] = []
        self._calls: list[str] = []
        self._shot_error_logged = False

    # ── recording ──────────────────────────────────────────────────────

    async def _snapshot(self, label: str) -> dict:
        state = await self.game.raw_state()
        idx = self.n_snap
        self.n_snap += 1
        self.rec.save_state(idx, state)
        frame = None
        if self.shots:
            jpeg = await asyncio.to_thread(self.shots.grab)
            if jpeg:
                frame = self.rec.save_frame(idx, jpeg)
            elif not self._shot_error_logged:
                self._shot_error_logged = True
                self.rec.event("error", self.step, where="screenshot", message=self.shots.last_error)
        self.rec.event("snapshot", self.step, index=idx, label=label, frame=frame, **_brief(state))
        if "error" not in state:
            self.last_state = state
        return state

    def _record_memory(self) -> None:
        self.rec.event("memory", self.step, **self.memory.snapshot())

    # ── context ────────────────────────────────────────────────────────

    def _system(self) -> str:
        return self.system_static + "\n\n" + self.memory.block()

    def _messages(self) -> list[dict]:
        msgs = [{"role": "system", "content": self._system()}, {"role": "user", "content": self.opening}]
        n = len(self.history)
        for i, step in enumerate(self.history):
            old = n - i > self.cfg.full_result_steps
            for m in step:
                if old and m["role"] == "tool" and len(m["content"]) > 1200:
                    m = {**m, "content": m["content"][:1200] + "\n…(older result shortened; call again for fresh data)"}
                msgs.append(m)
        return msgs

    async def _compact(self) -> None:
        """Summarize the oldest steps into memory.summary and drop them from the context."""
        size = sum(len(json.dumps(m)) for m in self._messages())
        if len(self.history) <= self.cfg.keep_steps and size <= self.cfg.max_context_chars:
            return
        drop = max(1, len(self.history) - self.cfg.keep_steps // 2)
        old, self.history = self.history[:drop], self.history[drop:]
        prompt = (PROMPTS / "summarize.md").read_text().format(
            previous=self.memory.summary or "(none)", turns=_render_steps(old))
        finish = ""
        try:
            reply = await self._write("You keep the memory of a Caves of Qud player.", prompt)
            finish = reply.finish_reason
            summary = reply.text.strip()
            if not summary:
                self.rec.event("error", self.step, where="summary", message=f"empty summary (finish: {finish})")
                summary = self.memory.summary
        except Exception as e:
            summary = self.memory.summary
            self.rec.event("error", self.step, where="summary", message=str(e))
        self.memory.summary = summary
        self.opening = "Continue playing. Older turns were summarized into your memory (\"The story so far\")."
        self.rec.event("summary", self.step, dropped_steps=drop, context_chars=size, summary=summary, finish=finish)
        self._record_memory()

    async def _write(self, system: str, prompt: str) -> Reply:
        """A text-only call (summary, lessons). Reasoning models can spend the whole budget
        thinking, so allow plenty and ask once more if no text came back."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        reply = await self.llm.chat(messages, max_tokens=8000)
        self._count(reply)
        if not reply.text.strip():
            messages[-1] = {"role": "user", "content": prompt + "\n\nAnswer directly with the text; keep any "
                            "deliberation very short."}
            reply = await self.llm.chat(messages, max_tokens=8000)
            self._count(reply)
        return reply

    def _count(self, reply: Reply) -> None:
        self.tokens["prompt"] += reply.usage.get("prompt_tokens", 0) or 0
        self.tokens["completion"] += reply.usage.get("completion_tokens", 0) or 0

    # ── one step ───────────────────────────────────────────────────────

    async def _run_call(self, call, step_msgs: list[dict]) -> dict | None:
        """Execute one tool call; returns the game state after it (None for memory tools)."""
        t0 = time.monotonic()
        state = None
        if "__invalid_json__" in call.arguments:
            text, err = f"Your arguments were not valid JSON: {call.arguments['__invalid_json__'][:200]}", True
        elif call.name in MEMORY_TOOL_NAMES:
            text, err = self.memory.handle(call.name, call.arguments), False
            self._record_memory()
        elif self.game.is_game_tool(call.name):
            text, err = await self.game.call(call.name, call.arguments)
            state = await self._snapshot(call.name)
        else:
            text, err = f"Unknown tool {call.name!r}.", True
        self.rec.event("tool", self.step, id=call.id, name=call.name, args=call.arguments, result=text,
                       is_error=err, latency=round(time.monotonic() - t0, 3), snapshot=self.n_snap - 1 if state else None)
        step_msgs.append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": text or "(no output)"})
        b = _brief(state or self.last_state)
        self._calls.append(f"{call.name}{json.dumps(call.arguments, sort_keys=True)} -> "
                           f"{(b['zoneId'], b['x'], b['y'], b['hp'], b['segment'], b['screen'], b['popup'])}")
        return state

    def _nudge(self, step_msgs: list[dict], text: str, kind: str) -> None:
        self.rec.event("nudge", self.step, kind=kind, text=text)
        if step_msgs and step_msgs[-1]["role"] == "tool":
            step_msgs[-1] = {**step_msgs[-1], "content": step_msgs[-1]["content"] + "\n\n" + text}
        else:
            step_msgs.append({"role": "user", "content": text})

    async def _step(self) -> None:
        self.step += 1
        try:
            reply = await self.llm.chat(self._messages(), self.tools)
        except Exception as e:
            self._llm_errors += 1
            self.rec.event("error", self.step, where="llm", message=str(e))
            print(f"[{self.step}] LLM error: {e}")
            if self._llm_errors >= 3:
                self.stop_reason = "llm_error"
            else:
                await asyncio.sleep(10)
            return
        self._llm_errors = 0
        self._count(reply)
        self.rec.event("llm", self.step, text=reply.text, reasoning=reply.reasoning,
                       tool_calls=[{"id": c.id, "name": c.name, "args": c.arguments} for c in reply.tool_calls],
                       usage=reply.usage, latency=round(reply.latency, 2), finish=reply.finish_reason)
        thought = (reply.text or reply.reasoning).replace("\n", " ")
        print(f"[{self.step}] {thought[:160]}")

        step_msgs = [reply.as_message()]
        if not reply.tool_calls:
            self._nudge(step_msgs, "You must call at least one tool every turn. If unsure, call get_state.", "no_tool")
            self.history.append(step_msgs)
            return

        zone_before = (self.last_state.get("zone") or {}).get("id")
        stop_rest = ""
        for i, call in enumerate(reply.tool_calls):
            blocked = (stop_rest and self.game.is_game_tool(call.name) and call.name not in _SCREEN_OK)
            if blocked or i >= self.cfg.max_calls_per_step:
                why = stop_rest if blocked else f"at most {self.cfg.max_calls_per_step} tool calls per turn"
                step_msgs.append({"role": "tool", "tool_call_id": call.id, "name": call.name,
                                  "content": f"Not run: {why}."})
                self.rec.event("tool", self.step, id=call.id, name=call.name, args=call.arguments,
                               result=f"Not run: {why}.", is_error=True, latency=0, snapshot=None)
                continue
            state = await self._run_call(call, step_msgs)
            print(f"      {call.name}({json.dumps(call.arguments)[1:-1][:80]}) -> "
                  f"{step_msgs[-1]['content'].splitlines()[0][:100] if step_msgs[-1]['content'] else ''}")
            if state is not None:
                if _is_dead(state):
                    self.stop_reason = "died"
                    break
                if state.get("inMainMenu") or state.get("screen") == "MainMenu":
                    self.stop_reason = "the game went back to the main menu"
                    break
                if state.get("popup"):
                    stop_rest = "a popup is open; answer it first"
                elif state.get("screen") not in (None, "", "Stage"):
                    stop_rest = f"the {state.get('screen')} screen is open; close_menu first"
                else:
                    stop_rest = ""
        zone_after = (self.last_state.get("zone") or {}).get("id")
        if zone_after and zone_before and zone_after != zone_before:
            name = (self.last_state.get("zone") or {}).get("name", "")
            self._nudge(step_msgs, f"You are now in a new zone: {name}. get_state / get_map show what's here.", "zone")
        self.history.append(step_msgs)
        self._watchdog(step_msgs)

    def _watchdog(self, step_msgs: list[dict]) -> None:
        b = _brief(self.last_state)
        self._progress.append((b["zoneId"], b["x"], b["y"], b["hp"], b["segment"], b["screen"], b["popup"]))
        if len(self._progress) >= 8 and len(set(self._progress[-8:])) == 1:
            self._nudge(self.history[-1], "WATCHDOG: nothing in the game has changed over your last 8 turns "
                        "(same position, HP, turn and screen). What you are doing is not working: check for an "
                        "open POPUP or SCREEN, call get_state, and try a different approach.", "stuck")
            self._progress.clear()
        # Same call with the same outcome (walking in a straight line changes the position, so it
        # doesn't count).
        if len(self._calls) >= 5 and len(set(self._calls[-5:])) == 1:
            self._nudge(self.history[-1], f"WATCHDOG: you made the same call 5 times in a row and nothing "
                        f"changed ({self._calls[-1].split(' -> ')[0][:80]}). Do something else.", "repeat")
            self._calls.clear()

    # ── run lifecycle ──────────────────────────────────────────────────

    async def _ensure_in_game(self) -> dict:
        state = await self.game.raw_state()
        if "error" in state:
            raise SystemExit(f"Can't read the game state: {state['error']}\n"
                             "Is Qud running with the CoQ MCP Bridge mod? (Player.log: '[mcp] MCP server listening')")
        # At the main menu the state still carries the last game's player, so check the menu first.
        at_menu = bool(state.get("inMainMenu")) or state.get("screen") == "MainMenu"
        if not at_menu and state.get("inGame") and state.get("player"):
            if not self.cfg.new_game:
                return state
            # Keep the loaded character: save it and go to the menu, then roll a new one.
            text, err = await self.game.call("quit_to_menu", timeout=120)
            self.rec.event("setup", 0, action="quit_to_menu", result=text[:2000], is_error=err)
            print(f"[setup] quit_to_menu: {text.splitlines()[0] if text else ''}")
            if err or not text.startswith("Saved and quit"):
                raise SystemExit(f"Could not leave the current game for --new-game: {text[:500]}")
            actions = ["new game"]
        elif state.get("inChargen"):
            actions = ["chargen_auto"]
        elif self.cfg.new_game:
            actions = ["new game"]
        else:
            actions = ["continue_game"]
        if actions == ["new game"]:
            await self._new_game()
            return await self._wait_in_game()
        for name in actions:
            text, err = await self.game.call(name)
            self.rec.event("setup", 0, action=name, result=text[:2000], is_error=err)
            print(f"[setup] {name}: {text.splitlines()[0] if text else ''}")
            if err or "failed" in text.lower()[:40] or '"error"' in text[:300]:
                if name == "continue_game":
                    return await self._new_game_fallback()
                raise SystemExit(f"{name} failed: {text[:500]}")
        return await self._wait_in_game()

    async def _new_game_fallback(self) -> dict:
        await self._new_game()
        return await self._wait_in_game()

    async def _new_game(self) -> None:
        """start_new_game + chargen_auto. Right after Qud launches the menu can ignore the first
        start_new_game, which shows up as chargen_auto finding no character builder; retry then."""
        for attempt in range(3):
            for name in ("start_new_game", "chargen_auto"):
                text, err = await self.game.call(name)
                self.rec.event("setup", 0, action=name, result=text[:2000], is_error=err)
                print(f"[setup] {name}: {text.splitlines()[0][:150] if text else ''}")
                if "EmbarkBuilder not found" in text:
                    break
                if err or '"error"' in text[:300]:
                    raise SystemExit(f"{name} failed: {text[:500]}")
            else:
                return
            await asyncio.sleep(3)
        raise SystemExit("Could not start a new game: the character builder never opened.")

    async def _wait_in_game(self, timeout: float = 300.0) -> dict:
        """Wait for the game to be playable. A new game shows "You embark for the caves of Qud" on
        top of the world-generation screen; accept it here. After that Qud is already waiting for
        the first move, although the world-generation view stays up until a turn passes."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = await self.game.raw_state()
            stack = str(state.get("viewStack") or "")
            if state.get("popup") and "WorldCreationProgress" in stack:
                text, _ = await self.game.call("respond_popup", {"dismiss": True})
                self.rec.event("setup", 0, action="accept embark popup", result=text[:500], is_error=False)
            elif (state.get("inGame") and state.get("player") and not state.get("inMainMenu")
                  and state.get("screen") not in ("MainMenu", "EmbarkBuilder")):
                if "WorldCreationProgress" in stack:
                    # Pass one turn so the map replaces the leftover generation screen.
                    text, _ = await self.game.call("wait", {"turns": 1})
                    self.rec.event("setup", 0, action="wait (leave world-generation screen)", result=text[:500], is_error=False)
                    continue
                return state
            await asyncio.sleep(2)
        raise SystemExit("The game did not reach play mode in time.")

    def _build_system_static(self) -> str:
        guide = (self.repo_root / "docs" / "qud_novice_notes.md").read_text(encoding="utf-8")
        guide = guide.split("\n", 1)[1] if guide.startswith("#") else guide  # drop the file's own title
        lessons = self.journal.recent()
        journal = ("\n# Lessons from your previous runs\n" + lessons) if lessons else ""
        return (PROMPTS / "system.md").read_text(encoding="utf-8").format(
            objective=self.cfg.objective, guide=guide.strip(), journal=journal)

    async def _lessons(self, outcome: str) -> None:
        if self.step < 5:
            return
        prompt = (PROMPTS / "lessons.md").read_text().format(outcome=outcome,
                                                              turns=_render_steps(self.history[-25:], 300))
        try:
            reply = await self._write(self._system(), prompt)
        except Exception as e:
            self.rec.event("error", self.step, where="lessons", message=str(e))
            return
        b = _brief(self.last_state)
        header = (f"Model `{self.llm.model}`, {outcome} after {self.step} steps; "
                  f"level {b['level']}, last seen in {b['zone']}.")
        self.journal.append(self.rec.run_id, header, reply.text)
        self.rec.event("lessons", self.step, text=reply.text)
        print("\nLessons:\n" + reply.text)

    async def run(self) -> Path:
        cfg = self.cfg
        run_id = time.strftime("%Y%m%d-%H%M%S") + "_" + re.sub(r"[^\w.-]+", "-", cfg.label or self.llm.model)
        self._llm_errors = 0
        self.shots = None
        async with Game(self.repo_root) as game:
            self.game = game
            self.tools = game.model_tools() + MEMORY_TOOLS
            self.system_static = self._build_system_static()
            self.rec = Recorder(cfg.runs_dir, run_id, {
                "model": self.llm.model, "base_url": self.llm.base_url, "llm": cfg.llm_info,
                "objective": cfg.objective, "max_steps": cfg.max_steps, "label": cfg.label,
                "tools": [t["function"]["name"] for t in self.tools]})
            (self.rec.dir / "system_prompt.md").write_text(self.system_static, encoding="utf-8")
            print(f"Recording to {self.rec.dir}")
            if cfg.screenshots:
                self.shots = await asyncio.to_thread(Screenshotter, cfg.shot_width)
                if not self.shots.available:
                    print(f"Screenshots off: {self.shots.last_error}")
                    self.shots = None
            loop = asyncio.get_running_loop()

            first_interrupt = 0.0

            def _interrupt() -> None:
                # `uv run` forwards the terminal's Ctrl-C, so one press can arrive twice.
                nonlocal first_interrupt
                now = time.monotonic()
                if not first_interrupt:
                    first_interrupt = now
                    print("\nStopping after this step (Ctrl-C again to abort)...")
                    self.stop_reason = self.stop_reason or "stopped by user"
                elif now - first_interrupt > 1.0:
                    raise KeyboardInterrupt
            loop.add_signal_handler(signal.SIGINT, _interrupt)

            try:
                self.rec.event("run_start", 0, objective=cfg.objective)
                await self._ensure_in_game()
                await self._snapshot("start")
                text, _ = await game.call("get_state")
                self.opening = "The game is running. Here is the full current state:\n\n" + text
                self._record_memory()
                started = time.monotonic()
                while not self.stop_reason:
                    if self.step >= cfg.max_steps:
                        self.stop_reason = f"step limit ({cfg.max_steps})"
                        break
                    if cfg.max_minutes and time.monotonic() - started > cfg.max_minutes * 60:
                        self.stop_reason = f"time limit ({cfg.max_minutes} min)"
                        break
                    await self._step()
                    if self.stop_reason:
                        break
                    if cfg.autosave_every and self.step % cfg.autosave_every == 0:
                        text, err = await game.call("save_game")
                        self.rec.event("autosave", self.step, result=text, is_error=err)
                    await self._compact()
            except Exception as e:
                self.stop_reason = self.stop_reason or f"error: {e}"
                self.rec.event("error", self.step, where="loop", message=repr(e))
                raise
            finally:
                outcome = self.stop_reason or "ended"
                # Only save a game the model actually played: saving during setup (e.g. on the
                # world-generation screen) writes a corrupt save.
                b = _brief(self.last_state)
                if (self.step > 0 and outcome != "died" and not outcome.startswith("error")
                        and b["screen"] not in ("MainMenu", "WorldCreationProgress", "EmbarkBuilder")):
                    try:
                        text, err = await game.call("save_game")
                        self.rec.event("autosave", self.step, result=text, is_error=err)
                    except Exception:
                        pass
                await self._lessons(outcome)
                b = _brief(self.last_state)
                self.rec.event("run_end", self.step, outcome=outcome, tokens=self.tokens)
                self.rec.finish(outcome=outcome, steps=self.step, tokens=self.tokens,
                                final={k: b[k] for k in ("hp", "hpMax", "level", "xp", "zone")})
                if self.shots:
                    self.shots.close()
                try:
                    loop.remove_signal_handler(signal.SIGINT)
                except Exception:
                    pass
                print(f"\nRun ended: {outcome}. {self.step} steps, tokens {self.tokens}. Recording: {self.rec.dir}")
        return self.rec.dir
