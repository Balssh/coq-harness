import narration from "./narration.generated.json";
import { FPS } from "./theme";

export type SceneId = (typeof narration)["scenes"][number]["id"];

/** Silence before the voice starts in each scene, and after it ends. */
export const LEAD = Math.round(0.3 * FPS);
export const TAIL = Math.round(0.5 * FPS);

export const scene = (id: SceneId) => {
  const s = narration.scenes.find((x) => x.id === id);
  if (!s) throw new Error(`no narration for scene ${id}`);
  return s;
};

export const sceneFrames = (id: SceneId) => LEAD + Math.ceil(scene(id).seconds * FPS) + TAIL;

/** Frame (within the scene) at which sentence `i` of the narration starts. */
export const cue = (id: SceneId, i: number) => {
  const cues = scene(id).cues;
  return LEAD + Math.round(cues[Math.min(i, cues.length - 1)].start * FPS);
};
