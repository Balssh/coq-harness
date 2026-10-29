import { loadFont as loadMono } from "@remotion/google-fonts/IBMPlexMono";
import { loadFont as loadSans } from "@remotion/google-fonts/IBMPlexSans";
import { loadFont as loadSerif } from "@remotion/google-fonts/Newsreader";

export const mono = loadMono("normal", { weights: ["400", "600"], subsets: ["latin"] }).fontFamily;
export const sans = loadSans("normal", { weights: ["400", "600"], subsets: ["latin"] }).fontFamily;
export const serif = loadSerif("normal", { weights: ["500", "700"], subsets: ["latin"] }).fontFamily;

// Caves of Qud's own palette: dark teal ground, teal text, gold highlights, red danger.
export const C = {
  bg: "#071013",
  panel: "#0b181c",
  line: "#2a4b52",
  frame: "#3f7d84",
  text: "#d4e6e2",
  muted: "#7f9c99",
  teal: "#3fc7b4",
  gold: "#e9b949",
  red: "#e5534b",
  green: "#78c25a",
  orange: "#ff7a1a", // Mistral
  violet: "#a98bf0", // Claude
};

export const FPS = 30;
