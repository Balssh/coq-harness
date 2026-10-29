# The presentation video

A motion-graphics presentation of coq-harness (about 3:15, 1080p30), made with
[Remotion](https://www.remotion.dev/) and narrated by Mistral's Voxtral TTS 3. The gameplay footage,
and the model's thoughts and tool calls on screen, come from real recorded runs.

```
cd video
npm install
uv run python scripts/clips.py      # copy frames, thoughts and tool calls out of runs/harness/
uv run python scripts/narrate.py    # voice and check the narration with Voxtral (needs MISTRAL_API_KEY)
npm run studio                      # preview and scrub in the browser
npm run render                      # out/coq-harness.mp4 (subtitles on, loudness normalised)
npm run render:nosubs               # the same without burned-in subtitles
```

`npm run render` needs `ffmpeg` on the PATH, both for the loudness pass and in `narrate.py`. In a
WSL install without the system libraries Chrome needs, point `LD_LIBRARY_PATH` at them.

## The narration

`narration.json` holds the script: one entry per scene with the subtitle `text`, and an optional
`say` that is spelled for the voice, for example "Kood" for Qud and "f f m peg" for FFmpeg. The
voice is the preset `en_paul_confident`. Voxtral has no speed setting, because the pace follows the
voice. On top of the voice's own pace, `"tempo": 1.08` speeds the takes up with ffmpeg's `atempo`,
which keeps the pitch. The result is about 185 words per minute.

`scripts/narrate.py` handles each scene whose text changed, in five steps:

1. **Voice it:** `POST /v1/audio/speech` with `voxtral-mini-tts-3`, the only Voxtral 3 speech model.
2. **Check it:** transcribe the take with `voxtral-small-transcribe-3`, the largest transcription
   model, and compare its words with the script. If they match less than 97%, it records a new
   take, up to 4 tries, and keeps the closest. The current takes match at 98–100%.
3. **Re-encode it:** apply the tempo and convert the take to constant-bitrate MP3 with a length header. Voxtral returns
   variable-bitrate MP3 without one, so ffprobe and players can only estimate its length, and the
   estimate can be several seconds off. This was why the voice and subtitles drifted in the first
   cut.
4. **Measure it:** find the scene's length by decoding the whole file, not from the header.
5. **Time the subtitles:** use the transcription's sentence timestamps.

It writes `public/audio/*.mp3` and `src/narration.generated.json`.

## How it fits together

| File | What |
|---|---|
| `scripts/clips.py` | Pulls clips out of `runs/harness/`: Joppa, trading, the Red Rock baboons, and the run 2 frustum death. For each frame it keeps the HP, level, and the model's thought and tool call. Writes `public/clips/` and `src/clips.generated.json` |
| `src/timing.ts` | Each scene lasts as long as its narration. `cue(scene, i)` is the frame where sentence `i` starts, so animations land on the words |
| `src/scenes.tsx` | The 13 scenes |
| `src/components.tsx` | Qud-style frames (title set into the border), the footage player with thought captions, message-log lines, the typewriter |
| `src/theme.ts` | Palette (Qud's teal, gold and red) and fonts (IBM Plex Mono and Sans, Newsreader) |
| `public/viewer_*.png` | Screenshots of the replay viewer |

`runs/` is git-ignored, so `public/clips/` (copied from it) is too. Re-running `clips.py` needs the
recorded runs.
