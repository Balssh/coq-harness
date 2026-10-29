import React from "react";
import { AbsoluteFill, Img, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Backdrop, clip, Footage, Frame, Headline, Kicker, LogLines, Reveal, Screen, Typewriter, useIn } from "./components";
import { C, mono, sans, serif } from "./theme";
import { cue } from "./timing";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Re-times its children so that their frame 0 is `from`. */
const Shift: React.FC<{ from: number; len: number; children: React.ReactNode }> = ({ from, len, children }) => (
  <Sequence from={from} durationInFrames={len} layout="none">{children}</Sequence>
);

// ─── Intro: footage, then the reveal ──────────────────────────────────────────
export const Intro: React.FC = () => {
  const t = useIn(cue("intro", 3) - 4, 12);
  const dim = useIn(cue("intro", 2), 20);
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Footage name="baboons" hold={9} captions={false} zoomFrom={1.15} zoomTo={1.0} origin="45% 55%" style={{ inset: -2 }} />
      <AbsoluteFill style={{ background: `rgba(7,16,19,${0.72 * dim})` }} />
      <div style={{ position: "absolute", left: 96, top: 360, opacity: t }}>
        <div style={{ fontFamily: mono, fontSize: 24, letterSpacing: 4, color: C.muted }}>THE PLAYER</div>
        <div style={{ fontFamily: serif, fontWeight: 500, fontSize: 132, color: C.text, lineHeight: 1.05, marginTop: 8 }}>
          Mistral Large 4
        </div>
        <div style={{ fontFamily: mono, fontSize: 28, color: C.teal, marginTop: 22 }}>no screen. no keyboard. text and tools.</div>
      </div>
    </AbsoluteFill>
  );
};

// ─── Title ────────────────────────────────────────────────────────────────────
export const Title: React.FC = () => {
  const frame = useCurrentFrame();
  const name = "coq-harness";
  const n = Math.floor(interpolate(frame, [4, 4 + name.length * 2], [0, name.length], clamp));
  const rule = useIn(cue("title", 1) - 6, 16);
  return (
    <AbsoluteFill>
      <Backdrop density={0.12} />
      <div style={{ position: "absolute", left: 160, top: 380 }}>
        <div style={{ fontFamily: mono, fontWeight: 600, fontSize: 140, color: C.text, lineHeight: 1 }}>
          <span style={{ color: C.gold }}>@</span>{name.slice(0, n)}
          <span style={{ visibility: "hidden" }}>{name.slice(n)}</span>
        </div>
        <div style={{ height: 2, background: C.frame, width: 1100 * rule, margin: "36px 0 30px" }} />
        <Reveal at={cue("title", 1)}>
          <div style={{ fontFamily: serif, fontSize: 48, color: C.text }}>
            a harness that lets <span style={{ color: C.orange }}>Mistral Large 4</span> play <span style={{ color: C.teal }}>Caves of Qud</span>
          </div>
        </Reveal>
      </div>
    </AbsoluteFill>
  );
};

// ─── 01 The pixel attempt ─────────────────────────────────────────────────────
const KEYS = ["Space", "Esc", "Space", "Space", "Esc", "Enter", "Esc", "Space", "Esc"];

export const Pixels: React.FC = () => {
  const frame = useCurrentFrame();
  const at = cue("pixels", 3);
  const crop = interpolate(frame, [at - 10, at + 18], [100, 58], clamp);
  return (
    <AbsoluteFill>
      <Backdrop />
      <Kicker n="01" label="the first attempt: screenshots and keys" />
      <Screen src="clips/joppa/014.jpg" title="what the vision model got" style={{ left: 96, top: 150, width: 1000, height: 536 }}>
        <div style={{ position: "absolute", top: 0, bottom: 0, left: `${crop}%`, right: 0, background: C.bg }} />
        <div style={{ position: "absolute", top: 0, bottom: 0, left: `calc(${crop}% - 2px)`, width: 2, background: C.gold }} />
        <div style={{ position: "absolute", right: 24, bottom: 18, fontFamily: mono, fontSize: 22, color: C.gold, opacity: crop < 99 ? 1 : 0 }}>
          captured {Math.round(crop)}%
        </div>
      </Screen>
      <div style={{ position: "absolute", left: 96, top: 730, width: 1000, fontFamily: mono, fontSize: 28, color: C.muted }}>
        keys sent:&nbsp;
        {KEYS.map((k, i) => {
          const t = cue("pixels", 1) + i * 8;
          const lost = i % 3 === 1 && frame > at + 30;
          return (
            <span key={i} style={{ opacity: frame >= t ? 1 : 0, color: lost ? C.red : C.text, textDecoration: lost ? "line-through" : "none" }}>
              {k}{" "}
            </span>
          );
        })}
      </div>
      <div style={{ position: "absolute", left: 1160, top: 170, width: 664 }}>
        <LogLines size={28} gap={22} lines={[
          { text: "The capture is cropped.", at: at, color: C.gold },
          { text: "Your keypress is lost.", at: at + 30, color: C.gold },
          { text: "You are stuck in the Control Mapping menu.", at: at + 70, color: C.red },
          { text: "28 episodes. Best: 111 turns, then a croc.", at: at + 110, color: C.muted },
        ]} />
      </div>
    </AbsoluteFill>
  );
};

// ─── 02 Architecture ──────────────────────────────────────────────────────────
const LAYERS = [
  { role: "the game", name: "Caves of Qud + C# mod", sub: "a TCP server inside the game, reading its own data", c: C.teal, cue: 1 },
  { role: "the tools", name: "mcp_server.py", sub: "~40 semantic tools with compact text results", c: C.gold, cue: 3 },
  { role: "the agent loop", name: "harness/", sub: "prompts, memory, guards, recorder", c: C.violet, cue: 4 },
  { role: "the model", name: "Mistral API: mistral-large-4", sub: "chat completions with tool calls", c: C.orange, cue: 5 },
];
const LINKS = ["TCP :47321, [length][JSON]", "MCP over stdio", "HTTPS"];

export const Architecture: React.FC = () => {
  const frame = useCurrentFrame();
  const left = 560, w = 1000, h = 128;
  const tops = [722, 532, 342, 152]; // game at the bottom, model on top
  const flowing = cue("architecture", 5) + 20;
  return (
    <AbsoluteFill>
      <Backdrop />
      <Kicker n="02" label="moving inside the game" />
      {LAYERS.map((l, i) => {
        const t = useIn(cue("architecture", l.cue));
        return (
          <div key={l.name} style={{ opacity: t }}>
            <Frame title={l.role} color={l.c} pad="24px 30px" style={{ left, top: tops[i], width: w, height: h }}>
              <div style={{ fontFamily: mono, fontSize: 36, fontWeight: 600, color: C.text }}>{l.name}</div>
              <div style={{ fontFamily: sans, fontSize: 25, color: C.muted, marginTop: 4 }}>{l.sub}</div>
            </Frame>
          </div>
        );
      })}
      {LINKS.map((label, i) => {
        const y0 = tops[i + 1] + h, y1 = tops[i];
        const o = interpolate(frame, [cue("architecture", LAYERS[i + 1].cue), cue("architecture", LAYERS[i + 1].cue) + 10], [0, 1], clamp);
        const p = ((frame - flowing) % 40) / 40;
        return (
          <div key={label} style={{ opacity: o }}>
            <div style={{ position: "absolute", left: left + 560, top: y0, width: 2, height: y1 - y0, background: C.frame }} />
            {frame > flowing ? (
              <>
                <div style={{ position: "absolute", left: left + 555, top: y0 + 6 + (y1 - y0 - 24) * (1 - p), width: 12, height: 12, background: C.text }} />
                <div style={{ position: "absolute", left: left + 555, top: y0 + 6 + (y1 - y0 - 24) * p, width: 12, height: 12, background: C.gold }} />
              </>
            ) : null}
            <div style={{ position: "absolute", left: left + 590, top: y0 + 18, fontFamily: mono, fontSize: 22, color: C.muted }}>{label}</div>
          </div>
        );
      })}
      <div style={{ position: "absolute", left: 96, top: 360, width: 400 }}>
        <Reveal at={cue("architecture", 2)}>
          <div style={{ fontFamily: mono, fontSize: 26, color: C.text }}><span style={{ display: "inline-block", width: 14, height: 14, background: C.text, marginRight: 14 }} />state, up</div>
          <div style={{ fontFamily: sans, fontSize: 25, color: C.muted, margin: "8px 0 0 28px" }}>creatures, items, messages, quests, the map</div>
        </Reveal>
        <Reveal at={flowing} style={{ marginTop: 48 }}>
          <div style={{ fontFamily: mono, fontSize: 26, color: C.gold }}><span style={{ display: "inline-block", width: 14, height: 14, background: C.gold, marginRight: 14 }} />tool calls, down</div>
          <div style={{ fontFamily: sans, fontSize: 25, color: C.muted, margin: "8px 0 0 28px" }}>go_to, fire, trade, flee, talk</div>
        </Reveal>
      </div>
    </AbsoluteFill>
  );
};

// ─── 03 One real step ─────────────────────────────────────────────────────────
const STEP_FRAME = clip("baboons").findIndex((f) => f.step === 117 && f.call.startsWith("fire"));

export const Step: React.FC = () => {
  const frame = useCurrentFrame();
  const f = clip("baboons")[STEP_FRAME];
  const rows = [
    { k: "ML4 thinks", body: "Level 3! The first baboon died. One baboon remains at d=19. Shooting it from range before it closes.", c: C.orange, font: sans, size: 28, at: cue("step", 2) },
    { k: "tool call (MCP)", body: "fire(x=79, y=2)", c: C.gold, font: mono, size: 28, at: cue("step", 2) + 75 },
    { k: "command to the mod (TCP)", body: '{"action": "fire_at", "x": 79, "y": 2}', c: C.teal, font: mono, size: 24, at: cue("step", 3) },
    { k: "result, back to ML4", body: "Fired at (79,2) [baboon].\nHP 26/26  Lvl 3  XP 525/1060  Red Rock\nHostiles: baboon (79,2) d=19 HP=5/5 [Average]", c: C.green, font: mono, size: 22, at: cue("step", 3) + 60 },
  ];
  const zoom = interpolate(frame, [0, 400], [1.0, 1.3], clamp);
  return (
    <AbsoluteFill>
      <Backdrop />
      <Kicker n="03" label="one real step: run 8, step 117" />
      <Screen src={f.src} zoom={zoom} origin="68% 40%" title="Moroq, Gunwing, Red Rock" style={{ left: 96, top: 150, width: 820, height: 720 }} />
      <Frame title="one step" pad="10px 32px" style={{ left: 976, top: 150, width: 848 }}>
        {rows.map((r, i) => (
          <div key={r.k} style={{ padding: "20px 0", borderTop: i ? `1px solid ${C.line}` : "none", opacity: frame >= r.at ? 1 : 0.15 }}>
            <div style={{ fontFamily: mono, fontSize: 18, letterSpacing: 2, color: r.c, textTransform: "uppercase" }}>{r.k}</div>
            <div style={{ fontFamily: r.font, fontSize: r.size, color: C.text, marginTop: 8, whiteSpace: "pre-wrap", lineHeight: 1.4 }}>
              <Typewriter text={r.body} start={r.at} cps={70} />
            </div>
          </div>
        ))}
      </Frame>
    </AbsoluteFill>
  );
};

// ─── 04 What the model reads ──────────────────────────────────────────────────
const STATUS = [
  { t: "Fired at (0,23) [bloody hulking baboon].", c: C.text, cue: -1, note: "" },
  { t: "HP 8/29  Lvl 5  XP 2200/3340  outskirts, Red Rock", c: C.gold, cue: 1, note: "your health" },
  { t: "Hostiles: bloody hulking baboon (0,23) d=1 HP=1/15 [Average] hits you for 6-8", c: C.teal, cue: 2, note: "threat rating and damage" },
  { t: "KNOW hulking baboon: bites several times a round (6-9 each). Not before level 4, one at a time. Leave while it is still a few tiles away.", c: C.green, cue: 3, note: "tactics from earlier runs" },
  { t: "DANGER: the bloody hulking baboon has hit you for up to 8 and you have 8 HP: two such hits kill you. Retreat with flee(), heal, or shoot from range.", c: C.red, cue: 4, note: "a fight that can kill you" },
];

export const Status: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill>
      <Backdrop />
      <Kicker n="04" label="what the model reads" />
      <Headline top={104} size={54}>Not raw JSON. <span style={{ color: C.teal }}>Short lines that matter.</span></Headline>
      <Frame title="fire() returns" pad="30px 34px" style={{ left: 96, top: 222, width: 1180, background: "#050c0e" }}>
        {STATUS.map((l, i) => {
          const at = l.cue < 0 ? 0 : cue("status", l.cue) - 4;
          const on = frame >= at;
          return (
            <div key={i} style={{ position: "relative", marginBottom: i < STATUS.length - 1 ? 18 : 0 }}>
              <div style={{ fontFamily: mono, fontSize: 26, lineHeight: 1.45, color: l.c, opacity: on ? 1 : 0.12,
                borderLeft: `4px solid ${on && l.note ? l.c : "transparent"}`, paddingLeft: 16 }}>{l.t}</div>
              {l.note ? (
                <div style={{ position: "absolute", top: 0, left: "calc(100% + 70px)", width: 470, opacity: on ? 1 : 0,
                  fontFamily: sans, fontSize: 28, lineHeight: 1.3, color: l.c }}>
                  <span style={{ color: C.line }}>&mdash;&nbsp;</span>{l.note}
                </div>
              ) : null}
            </div>
          );
        })}
      </Frame>
      <Reveal at={cue("status", 4) + 30} style={{ position: "absolute", left: 96, top: 860 }}>
        <div style={{ fontFamily: mono, fontSize: 20, color: C.muted }}>real lines from runs 7 and 9</div>
      </Reveal>
    </AbsoluteFill>
  );
};

// ─── 05 Guards ────────────────────────────────────────────────────────────────
const GUARDS = [
  { t: "Routine popups", d: "accepted for the model, and reported to it", at: 0 },
  { t: "Combat check", d: "holds back one risky melee blow when DANGER is up", at: 45 },
  { t: "Loop watchdogs", d: "stuck in place, the same call five times, walking tile by tile", at: 105 },
  { t: "Running summary", d: "old steps folded into the story so far, so the context stays bounded", at: 165 },
  { t: "Lessons journal", d: "end-of-run lessons, read by the next run", at: -1 },
];

export const Guards: React.FC = () => (
  <AbsoluteFill>
    <Backdrop />
    <Kicker n="05" label="the harness around the model" />
    <Headline top={104} size={54}>The model decides. <span style={{ color: C.violet }}>The harness keeps it on track.</span></Headline>
    <div style={{ position: "absolute", left: 96, right: 96, top: 270, display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 80 }}>
      {GUARDS.map((g, i) => (
        <Reveal key={g.t} at={g.at < 0 ? cue("guards", 2) : cue("guards", 1) + g.at}>
          <div style={{ borderTop: `1px solid ${C.line}`, padding: "22px 0 30px", display: "flex", gap: 26 }}>
            <div style={{ fontFamily: mono, fontSize: 30, color: C.gold, width: 30 }}>{i + 1}</div>
            <div>
              <div style={{ fontFamily: sans, fontWeight: 600, fontSize: 34, color: C.text }}>{g.t}</div>
              <div style={{ fontFamily: sans, fontSize: 26, color: C.muted, marginTop: 6, lineHeight: 1.35 }}>{g.d}</div>
            </div>
          </div>
        </Reveal>
      ))}
    </div>
  </AbsoluteFill>
);

// ─── 06 Gameplay montage ──────────────────────────────────────────────────────
export const Play: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const parts = [
    { name: "joppa" as const, label: "Joppa: talking to villagers, taking quests", from: 12, to: 26, hold: 8 },
    { name: "trade" as const, label: "Trading: selling junk, buying bandages", from: 1, to: 20, hold: 6 },
    { name: "baboons" as const, label: "Red Rock: baboons, from range", from: 0, to: 18, hold: 10 },
  ];
  const cuts = [0, cue("play", 1) + 70, cue("play", 2) + 40, durationInFrames];
  const idx = frame < cuts[1] ? 0 : frame < cuts[2] ? 1 : 2;
  const p = parts[idx];
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Kicker n="06" label="then we let it play" />
      <div style={{ position: "absolute", left: 96, right: 96, top: 130, bottom: 150 }}>
        <Shift from={cuts[idx]} len={cuts[idx + 1] - cuts[idx]}>
          <Footage name={p.name} from={p.from} to={p.to} hold={p.hold} title={p.label} />
        </Shift>
      </div>
    </AbsoluteFill>
  );
};

// ─── 07 Results ───────────────────────────────────────────────────────────────
const RUNS = [
  { lvl: 2, died: false }, { lvl: 4, died: true }, { lvl: 3, died: false }, { lvl: 1, died: true }, { lvl: 4, died: true },
  { lvl: 3, died: false }, { lvl: 5, died: true }, { lvl: 6, died: false }, { lvl: 5, died: false },
];

export const Results: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const switchAt = cue("results", 3) - 6;
  if (frame >= switchAt) return <Frustum start={switchAt} len={durationInFrames - switchAt} />;
  const stats = [
    { v: "9", t: "runs", c: C.text, at: 0 },
    { v: "~2,900", t: "tool calls", c: C.teal, at: 6 },
    { v: "1", t: "invalid argument", c: C.green, at: 12 },
    { v: "6", t: "best level", c: C.gold, at: cue("results", 1) },
    { v: "4", t: "deaths", c: C.red, at: cue("results", 2) },
  ];
  const deaths = frame >= cue("results", 2);
  return (
    <AbsoluteFill>
      <Backdrop />
      <Kicker n="07" label="nine supervised runs" />
      <div style={{ position: "absolute", left: 96, right: 96, top: 130, display: "flex", justifyContent: "space-between" }}>
        {stats.map((s) => (
          <Reveal key={s.t} at={s.at}>
            <div style={{ fontFamily: serif, fontWeight: 500, fontSize: 104, color: s.c, lineHeight: 1 }}>{s.v}</div>
            <div style={{ fontFamily: mono, fontSize: 22, color: C.muted, marginTop: 10 }}>{s.t}</div>
          </Reveal>
        ))}
      </div>
      <div style={{ position: "absolute", left: 96, top: 350, fontFamily: mono, fontSize: 22, color: C.muted }}>highest level in each run</div>
      <div style={{ position: "absolute", left: 96, right: 96, top: 400, height: 430, display: "flex", alignItems: "flex-end", gap: 36, borderBottom: `2px solid ${C.frame}` }}>
        {RUNS.map((r, i) => {
          const g = interpolate(frame, [cue("results", 1) - 40 + i * 4, cue("results", 1) - 20 + i * 4], [0, 1], clamp);
          const red = r.died && deaths;
          return (
            <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%" }}>
              <div style={{ fontFamily: mono, fontSize: 26, color: red ? C.red : C.text, opacity: g }}>{red ? "died, " : ""}L{r.lvl}</div>
              <div style={{ width: "100%", height: `${(r.lvl / 6) * 82 * g}%`, marginTop: 10, background: red ? C.red : C.teal, opacity: red ? 0.85 : 0.55 }} />
            </div>
          );
        })}
      </div>
      <div style={{ position: "absolute", left: 96, right: 96, top: 846, display: "flex", gap: 36, fontFamily: mono, fontSize: 22, color: C.muted }}>
        {RUNS.map((_, i) => <div key={i} style={{ flex: 1, textAlign: "center" }}>run {i + 1}</div>)}
      </div>
    </AbsoluteFill>
  );
};

const Frustum: React.FC<{ start: number; len: number }> = ({ start, len }) => {
  const quoteAt = cue("results", 4) - 6;
  const q = useIn(quoteAt, 12);
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Shift from={start} len={len}>
        <Footage name="frustum" from={4} hold={8} captions={false} zoomFrom={1.05} zoomTo={1.25} origin="45% 60%" style={{ inset: -2 }} />
      </Shift>
      <AbsoluteFill style={{ background: `rgba(7,16,19,${0.35 + 0.45 * q})` }} />
      <div style={{ position: "absolute", left: 140, right: 140, top: 280, opacity: q }}>
        <div style={{ fontFamily: mono, fontSize: 24, color: C.orange, letterSpacing: 3 }}>ML4, RUN 2, STEP 93</div>
        <div style={{ fontFamily: serif, fontWeight: 500, fontSize: 92, color: C.text, lineHeight: 1.1, marginTop: 16 }}>
          &ldquo;That frustum (70 HP) is <span style={{ color: C.red }}>too dangerous.</span>&rdquo;
        </div>
        <Reveal at={quoteAt + 40}>
          <div style={{ fontFamily: mono, fontSize: 32, color: C.red, marginTop: 40 }}>step 118: You were killed by a gelatinous frustum.</div>
        </Reveal>
        <Reveal at={cue("results", 5)}>
          <div style={{ fontFamily: serif, fontSize: 46, color: C.muted, marginTop: 44 }}>
            Good at single decisions. <span style={{ color: C.gold }}>Weak at knowing when to stop.</span>
          </div>
        </Reveal>
      </div>
    </AbsoluteFill>
  );
};

// ─── 08 Replay viewer ─────────────────────────────────────────────────────────
export const Replay: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const t = interpolate(frame, [0, durationInFrames], [0, 1]);
  const marks = [
    { n: 1, t: "thoughts", x: 1330, y: 250, at: cue("replay", 1) },
    { n: 2, t: "tool calls and results", x: 1330, y: 330, at: cue("replay", 1) + 12 },
    { n: 3, t: "frames and map", x: 380, y: 560, at: cue("replay", 1) + 24 },
    { n: 4, t: "HP and event timeline", x: 160, y: 820, at: cue("replay", 2) },
  ];
  return (
    <AbsoluteFill>
      <Backdrop />
      <Kicker n="08" label="every run is recorded" />
      <Frame title="replay viewer, run 2" pad={0} style={{ left: 96, right: 96, top: 130, bottom: 150 }}>
        <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
          <Img src={staticFile("viewer_frustum.png")} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "50% 0%",
            transform: `scale(${1.0 + 0.12 * t})`, transformOrigin: "60% 30%" }} />
        </div>
      </Frame>
      {marks.map((m) => (
        <Reveal key={m.t} at={m.at} style={{ position: "absolute", left: m.x, top: m.y }}>
          <div style={{ fontFamily: mono, fontSize: 26, color: C.gold, background: C.bg, border: `2px solid ${C.gold}`, padding: "6px 14px" }}>
            {m.n}&nbsp;&nbsp;{m.t}
          </div>
        </Reveal>
      ))}
    </AbsoluteFill>
  );
};

// ─── 09 Assessment ────────────────────────────────────────────────────────────
type Grade = "strong" | "good" | "fair" | "weak";
const GRADE_COLOR: Record<Grade, string> = { strong: C.green, good: C.teal, fair: C.gold, weak: C.red };

const PLAYER: { k: string; g: Grade }[] = [
  { k: "Using the tools", g: "strong" },
  { k: "The Joppa opening", g: "strong" },
  { k: "Leveling up", g: "good" },
  { k: "Navigating with tools", g: "good" },
  { k: "Combat tactics", g: "fair" },
  { k: "Memory and lessons", g: "fair" },
  { k: "Judging risk", g: "weak" },
  { k: "Spending resources", g: "weak" },
  { k: "Multi-step quests", g: "weak" },
];
const CODER: { k: string; g: Grade; why: string; cue: number }[] = [
  { k: "Investigation, scaffolding", g: "strong", why: "the whole first harness, fast", cue: 4 },
  { k: "Tooling ingenuity", g: "strong", why: "its own reader for the game's .NET DLL", cue: 4 },
  { k: "Reporting its own work", g: "weak", why: "announced files it never wrote", cue: 5 },
  { k: "Finding root causes", g: "weak", why: "the developer found most of them", cue: 6 },
  { k: "Staying on hard problems", g: "weak", why: "swapped them for workarounds", cue: 5 },
];

const Row: React.FC<{ k: string; g: Grade; why?: string; at: number }> = ({ k, g, why, at }) => {
  const frame = useCurrentFrame();
  const on = frame >= at;
  return (
    <div style={{ padding: "11px 0", borderTop: `1px solid ${C.line}`, opacity: on ? 1 : 0.12 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 16 }}>
        <div style={{ fontFamily: sans, fontSize: 28, color: C.text }}>{k}</div>
        <div style={{ flex: 1 }} />
        <div style={{ fontFamily: mono, fontSize: 24, letterSpacing: 2, color: GRADE_COLOR[g], textTransform: "uppercase" }}>{g}</div>
      </div>
      {why ? <div style={{ fontFamily: sans, fontSize: 22, color: C.muted, marginTop: 2 }}>{why}</div> : null}
    </div>
  );
};

export const Assessment: React.FC = () => (
  <AbsoluteFill>
    <Backdrop />
    <Kicker n="09" label="mistral large 4, assessed" />
    <Headline top={104} size={54}>How good is it?</Headline>
    <Reveal at={cue("assessment", 1) - 6}>
      <Frame title="as a player: 9 runs" color={C.teal} pad="16px 30px 10px" style={{ left: 96, top: 226, width: 820 }}>
        {PLAYER.map((r, i) => (
          <Row key={r.k} k={r.k} g={r.g} at={cue("assessment", 1) + i * 12} />
        ))}
      </Frame>
    </Reveal>
    <Reveal at={cue("assessment", 2)}>
      <Frame title="as a coder: through Mistral Vibe" color={C.orange} pad="16px 30px 10px" style={{ left: 1004, top: 226, width: 820 }}>
        {CODER.map((r) => (
          <Row key={r.k} k={r.k} g={r.g} why={r.why} at={cue("assessment", r.cue)} />
        ))}
      </Frame>
    </Reveal>
    <Reveal at={cue("assessment", 6)} style={{ position: "absolute", left: 1004, top: 860, width: 820 }}>
      <div style={{ fontFamily: mono, fontSize: 20, color: C.muted }}>from docs/ml4-assessment.md and docs/development-history.md</div>
    </Reveal>
  </AbsoluteFill>
);

// ─── 10 How it was built ──────────────────────────────────────────────────────
const PHASES = [
  { when: "Oct 18 to 25", who: "Mistral Large 4 in Mistral Vibe", what: "the screenshot harness: capture, key injection, vision", c: C.orange, cue: 1 },
  { when: "Oct 26 to 27", who: "Mistral Large 4 in Mistral Vibe", what: "the pivot: a C# mod inside Qud and the first MCP server", c: C.orange, cue: 1 },
  { when: "Oct 28 to 29", who: "Claude Code", what: "rebuilt bridge, tools and harness, the replay viewer, nine runs", c: C.violet, cue: 1 },
];
// each item: name, what, and when it appears (frames after sentence `cue` of the narration starts)
const LISTS: { title: string; c: string; cue: number; items: [string, string, number][] }[] = [
  { title: "inspired by", c: C.gold, cue: 2, items: [
    ["heroes-3-mcp", "a Mistral model plays Heroes III through MCP", 30],
    ["llm-of-qud", "an LLM Qud player: mod plus MCP server", 75],
    ["raves-of-qud", "Qud streamed to a 2.5D view in Godot", 115],
  ] },
  { title: "built on", c: C.teal, cue: 2, items: [
    ["MCP Python SDK", "", 165], ["Pillow, FFmpeg, uv", "", 165], ["Remotion + React", "this video", 165],
  ] },
  { title: "mistral models", c: C.orange, cue: 2, items: [
    ["mistral-large-4", "the player", 190], ["voxtral-mini-tts-3", "the voice", 190], ["voxtral-small-transcribe-3", "take checks, subtitle timing", 190],
  ] },
];

export const Built: React.FC = () => {
  const line = useIn(cue("built", 1) - 10, 30);
  return (
    <AbsoluteFill>
      <Backdrop />
      <Kicker n="10" label="how it was built" />
      <Headline top={104} size={54}>One developer, working with AI agents.</Headline>
      <div style={{ position: "absolute", left: 96, top: 250, width: 1728 * line, height: 2, background: C.frame }} />
      {PHASES.map((p, i) => (
        <Reveal key={p.when} at={cue("built", p.cue) + i * 18} style={{ position: "absolute", left: 96 + i * 594, top: 242, width: 540 }}>
          <div style={{ width: 16, height: 16, background: p.c }} />
          <div style={{ fontFamily: mono, fontSize: 22, color: C.muted, marginTop: 18 }}>{p.when}</div>
          <div style={{ fontFamily: sans, fontWeight: 600, fontSize: 30, color: p.c, marginTop: 6 }}>{p.who}</div>
          <div style={{ fontFamily: sans, fontSize: 26, color: C.text, marginTop: 6, lineHeight: 1.35 }}>{p.what}</div>
        </Reveal>
      ))}
      {LISTS.map((l, i) => (
        <Reveal key={l.title} at={cue("built", l.cue) + l.items[0][2]} style={{ position: "absolute", left: 96 + i * 594, top: 500, width: 540 }}>
          <div style={{ fontFamily: mono, fontSize: 20, letterSpacing: 3, color: l.c, textTransform: "uppercase", paddingBottom: 10, borderBottom: `1px solid ${C.line}` }}>{l.title}</div>
          {l.items.map(([name, what, at]) => (
            <Reveal key={name} at={cue("built", l.cue) + at} style={{ marginTop: 16 }}>
              <div style={{ fontFamily: mono, fontSize: 26, color: C.text }}>{name}</div>
              {what ? <div style={{ fontFamily: sans, fontSize: 23, color: C.muted, marginTop: 2, lineHeight: 1.3 }}>{what}</div> : null}
            </Reveal>
          ))}
        </Reveal>
      ))}
    </AbsoluteFill>
  );
};

// ─── Outro ────────────────────────────────────────────────────────────────────
export const Outro: React.FC = () => (
  <AbsoluteFill>
    <Backdrop density={0.12} />
    <div style={{ position: "absolute", left: 160, top: 300 }}>
      <Reveal at={0}><div style={{ fontFamily: mono, fontSize: 24, letterSpacing: 4, color: C.muted }}>NEXT</div></Reveal>
      {["Longer runs.", "A quest helper.", "Teaching it when to walk away."].map((t, i) => (
        <Reveal key={t} at={cue("outro", 1) + i * 16}>
          <div style={{ fontFamily: serif, fontSize: 60, color: i === 2 ? C.gold : C.text, marginTop: 14 }}>{t}</div>
        </Reveal>
      ))}
      <Reveal at={cue("outro", 2) - 4}>
        <div style={{ fontFamily: mono, fontWeight: 600, fontSize: 54, color: C.text, marginTop: 70 }}>
          github.com/<span style={{ color: C.teal }}>Balssh/coq-harness</span>
        </div>
      </Reveal>
    </div>
  </AbsoluteFill>
);
