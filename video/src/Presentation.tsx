import React from "react";
import { AbsoluteFill, Audio, interpolate, Sequence, Series, staticFile, useCurrentFrame } from "remotion";
import { SceneFade } from "./components";
import narration from "./narration.generated.json";
import {
  Architecture, Assessment, Built, Guards, Intro, Outro, Pixels, Play, Replay, Results, Status, Step, Title,
} from "./scenes";
import { C, FPS, sans } from "./theme";
import { LEAD, SceneId, scene, sceneFrames } from "./timing";

const SCENES: Record<SceneId, React.FC> = {
  intro: Intro, title: Title, pixels: Pixels, architecture: Architecture, step: Step, status: Status,
  guards: Guards, play: Play, results: Results, replay: Replay, assessment: Assessment, built: Built, outro: Outro,
};

export const totalFrames = () => narration.scenes.reduce((n, s) => n + sceneFrames(s.id as SceneId), 0);

/** Burned-in subtitles, one narration sentence at a time. */
const Subtitles: React.FC<{ id: SceneId }> = ({ id }) => {
  const frame = useCurrentFrame() - LEAD;
  const t = frame / FPS;
  const c = scene(id).cues.find((x, i, all) => t >= x.start - 0.1 && t < (all[i + 1]?.start ?? x.end + 0.6));
  if (!c) return null;
  const o = interpolate(t, [c.start - 0.1, c.start + 0.1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 34, display: "flex", justifyContent: "center", opacity: o }}>
      <div style={{ maxWidth: 1400, textAlign: "center", fontFamily: sans, fontSize: 31, lineHeight: 1.3, color: C.text,
        background: "rgba(4,10,12,.88)", padding: "8px 22px" }}>{c.text}</div>
    </div>
  );
};

export const Presentation: React.FC<{ subtitles: boolean }> = ({ subtitles }) => (
  <AbsoluteFill style={{ background: C.bg }}>
    <Series>
      {narration.scenes.map((s) => {
        const id = s.id as SceneId;
        const Scene = SCENES[id];
        return (
          <Series.Sequence key={id} durationInFrames={sceneFrames(id)} name={id}>
            <SceneFade><Scene /></SceneFade>
            <Sequence from={LEAD} layout="none"><Audio src={staticFile(s.audio)} /></Sequence>
            {subtitles ? <Subtitles id={id} /> : null}
          </Series.Sequence>
        );
      })}
    </Series>
  </AbsoluteFill>
);
