import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, random, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import clips from "./clips.generated.json";
import { C, mono, sans, serif } from "./theme";

export type ClipFrame = (typeof clips)["joppa"][number];
export type ClipName = keyof typeof clips;
export const clip = (name: ClipName): ClipFrame[] => clips[name];

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** 0 → 1 over `len` frames starting at `at`, eased out. */
export const useIn = (at: number, len = 10) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [at, at + len], [0, 1], { ...clamp, easing: Easing.out(Easing.quad) });
};

/** Fades the whole scene in and out. */
export const SceneFade: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = interpolate(frame, [0, 8, durationInFrames - 8, durationInFrames], [0, 1, 1, 0], clamp);
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

const GLYPHS = ".,'`~:;^\"";

/** Sparse field of dim map glyphs, like an unexplored Qud zone. */
export const Backdrop: React.FC<{ density?: number }> = ({ density = 0.08 }) => {
  const frame = useCurrentFrame();
  const cells: React.ReactNode[] = [];
  for (let y = 0; y < 27; y++) {
    for (let x = 0; x < 48; x++) {
      const seed = `${x}-${y}`;
      if (random(seed) > density) continue;
      const o = 0.05 + 0.05 * Math.sin(frame / 50 + random(seed + "p") * 6.28);
      cells.push(
        <span key={seed} style={{ position: "absolute", left: x * 40 + 12, top: y * 40 + 6, opacity: o, color: C.teal }}>
          {GLYPHS[Math.floor(random(seed + "g") * GLYPHS.length)]}
        </span>,
      );
    }
  }
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <div style={{ position: "absolute", inset: 0, fontFamily: mono, fontSize: 24 }}>{cells}</div>
    </AbsoluteFill>
  );
};

/** Section label in the top left corner. */
export const Kicker: React.FC<{ n: string; label: string }> = ({ n, label }) => {
  const t = useIn(0, 14);
  return (
    <div style={{ position: "absolute", left: 96, top: 64, opacity: t, fontFamily: mono, fontSize: 22,
      letterSpacing: 3, color: C.muted, textTransform: "uppercase" }}>
      <span style={{ color: C.gold }}>{n}</span>&nbsp;&nbsp;{label}
    </div>
  );
};

/** Serif headline that fades up. */
export const Headline: React.FC<{ children: React.ReactNode; at?: number; size?: number; top?: number }> = ({
  children, at = 4, size = 60, top = 112,
}) => {
  const t = useIn(at, 14);
  return (
    <div style={{ position: "absolute", left: 96, right: 96, top, fontFamily: serif, fontWeight: 500, fontSize: size,
      color: C.text, opacity: t, transform: `translateY(${(1 - t) * 12}px)`, lineHeight: 1.15 }}>
      {children}
    </div>
  );
};

/** Fades and slides in at frame `at`. */
export const Reveal: React.FC<{ at: number; children: React.ReactNode; style?: React.CSSProperties; dy?: number }> = ({
  at, children, style, dy = 10,
}) => {
  const t = useIn(at);
  return <div style={{ ...style, opacity: t, transform: `translateY(${(1 - t) * dy}px)` }}>{children}</div>;
};

/** Reveals text character by character. */
export const Typewriter: React.FC<{ text: string; start?: number; cps?: number }> = ({ text, start = 0, cps = 50 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const n = Math.max(0, Math.floor(((frame - start) / fps) * cps));
  // keep the full text laid out (invisible) so the box doesn't grow while typing
  return (
    <span>
      {text.slice(0, n)}
      <span style={{ visibility: "hidden" }}>{text.slice(n)}</span>
    </span>
  );
};

/**
 * A Qud-style window: square border with its title set into the top edge.
 * Height follows the content unless given.
 */
export const Frame: React.FC<{
  title?: string; color?: string; style?: React.CSSProperties; children?: React.ReactNode; pad?: number | string;
}> = ({ title, color = C.frame, style, children, pad = "26px 30px" }) => (
  <div style={{ position: "absolute", border: `2px solid ${color}`, background: C.panel, padding: pad, boxSizing: "border-box", ...style }}>
    {title ? (
      <div style={{ position: "absolute", zIndex: 2, top: -15, left: 22, padding: "0 10px", background: C.bg, fontFamily: mono,
        fontSize: 20, letterSpacing: 2, color, textTransform: "uppercase", lineHeight: "28px" }}>
        {title}
      </div>
    ) : null}
    {children}
  </div>
);

/** A screenshot in a frame. */
export const Screen: React.FC<{ src: string; style?: React.CSSProperties; zoom?: number; origin?: string; title?: string; children?: React.ReactNode }> = ({
  src, style, zoom = 1, origin = "50% 50%", title, children,
}) => (
  <Frame title={title} pad={0} style={{ background: "#000", ...style }}>
    <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
      <Img src={staticFile(src)} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${zoom})`, transformOrigin: origin }} />
      {children}
    </div>
  </Frame>
);

/**
 * Plays recorded frames of a clip (each held `hold` video frames) with a slow push-in,
 * plus the model's thought and tool call as captions.
 */
export const Footage: React.FC<{
  name: ClipName; from?: number; to?: number; hold?: number; style?: React.CSSProperties; title?: string;
  captions?: boolean; origin?: string; zoomFrom?: number; zoomTo?: number;
}> = ({ name, from = 0, to, hold = 8, style, title, captions = true, origin = "40% 50%", zoomFrom = 1.0, zoomTo = 1.1 }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const frames = clip(name).slice(from, to);
  const i = Math.min(frames.length - 1, Math.floor(frame / hold));
  const f = frames[i];
  const zoom = interpolate(frame, [0, durationInFrames], [zoomFrom, zoomTo], clamp);
  // the newest non-empty thought at or before this frame
  let thought = "", since = 0;
  for (let k = i; k >= 0; k--) if (frames[k].thought) { thought = frames[k].thought; since = k; break; }
  while (since > 0 && frames[since - 1].thought === thought) since--;
  return (
    <div style={{ position: "absolute", inset: 0, ...style }}>
      <Screen src={f.src} zoom={zoom} origin={origin} title={title} style={{ inset: 0 }}>
        {captions ? <Hud f={f} /> : null}
      </Screen>
      {captions && thought ? <ThoughtBox thought={thought} call={f.call} start={since * hold} /> : null}
    </div>
  );
};

const Hud: React.FC<{ f: ClipFrame }> = ({ f }) => {
  const low = f.hp / f.hpMax < 0.4;
  return (
    <div style={{ position: "absolute", top: 0, right: 0, padding: "8px 16px", background: C.bg, fontFamily: mono,
      fontSize: 22, color: C.muted, borderLeft: `2px solid ${C.frame}`, borderBottom: `2px solid ${C.frame}` }}>
      step <span style={{ color: C.text }}>{f.step}</span>&nbsp;&nbsp;lvl <span style={{ color: C.text }}>{f.level}</span>
      &nbsp;&nbsp;HP <span style={{ color: low ? C.red : C.green }}>{f.hp}/{f.hpMax}</span>
    </div>
  );
};

const ThoughtBox: React.FC<{ thought: string; call: string; start: number }> = ({ thought, call, start }) => (
  <Frame title="ML4" color={C.orange} pad="20px 26px" style={{ left: 40, right: 40, bottom: 34, background: "rgba(7,16,19,.94)" }}>
    <div style={{ fontFamily: sans, fontSize: 27, lineHeight: 1.35, color: C.text }}>
      <Typewriter text={thought} start={start} cps={80} />
    </div>
    {call ? <div style={{ fontFamily: mono, fontSize: 22, color: C.teal, marginTop: 8 }}>&gt; {call}</div> : null}
  </Frame>
);

/** Lines that appear one by one, in the style of Qud's message log. */
export const LogLines: React.FC<{ lines: { text: React.ReactNode; at: number; color?: string }[]; size?: number; gap?: number }> = ({
  lines, size = 30, gap = 14,
}) => (
  <div style={{ display: "flex", flexDirection: "column", gap, fontFamily: mono, fontSize: size }}>
    {lines.map((l, i) => (
      <Reveal key={i} at={l.at} dy={0}>
        <span style={{ color: C.muted }}>:: </span>
        <span style={{ color: l.color ?? C.text }}>{l.text}</span>
      </Reveal>
    ))}
  </div>
);
