import React from "react";
import { Composition } from "remotion";
import { Presentation, totalFrames } from "./Presentation";
import { FPS } from "./theme";

export const Root: React.FC = () => (
  <Composition
    id="Presentation"
    component={Presentation}
    durationInFrames={totalFrames()}
    fps={FPS}
    width={1920}
    height={1080}
    defaultProps={{ subtitles: true }}
  />
);
