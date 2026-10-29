"""Voice the narration with Voxtral TTS 3 and check every take (Mistral API).

Reads video/narration.json. For each scene whose text changed, voices its "say" (else its "text")
with voxtral-mini-tts-3, transcribes the take with voxtral-small-transcribe-3 and compares the words.
A take that doesn't say what the script says is re-voiced (up to --takes times; the closest take
is kept). Writes public/audio/<scene>.mp3 and src/narration.generated.json with the text, duration,
match score and sentence timings of each scene, which the Remotion composition uses for timing
and subtitles.

    uv run python video/scripts/narrate.py            # only scenes whose text changed
    uv run python video/scripts/narrate.py --all      # re-voice everything
    uv run python video/scripts/narrate.py --voice gb_jane_neutral

"tempo" in narration.json speeds every scene up (pitch kept); changing it re-times the existing takes
without voicing them again.
"""
import argparse
import base64
import difflib
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

VIDEO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VIDEO.parent))
from harness.llm import find_api_key  # noqa: E402

AUDIO = VIDEO / "public" / "audio"
OUT = VIDEO / "src" / "narration.generated.json"
STT_MODEL = "voxtral-small-transcribe-3"
MIN_MATCH = 0.97

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
# spellings the voice is given vs. how the transcriber writes them
SAME = {"kood": "qud", "c#": "c sharp", "ffmpeg": "f f m peg", "mcp": "m c p", "llm": "l l m", "3d": "three d"}


def api(key: str, path: str, body: bytes, content_type: str) -> dict:
    req = urllib.request.Request(f"https://api.mistral.ai/v1/{path}", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def speak(key: str, model: str, voice: str, text: str) -> bytes:
    body = json.dumps({"model": model, "input": text, "voice_id": voice, "response_format": "mp3"})
    return base64.b64decode(api(key, "audio/speech", body.encode(), "application/json")["audio_data"])


def transcribe(key: str, path: Path) -> dict:
    """Text and sentence-level segments of a take."""
    b = uuid.uuid4().hex
    fields = {"model": STT_MODEL, "timestamp_granularities": "segment"}
    body = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                    for k, v in fields.items())
    body += (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
             f"Content-Type: audio/mpeg\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{b}--\r\n".encode()
    return api(key, "audio/transcriptions", body, f"multipart/form-data; boundary={b}")


def spell(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if n < 1000:
        return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " and " + spell(n % 100))
    return spell(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + spell(n % 1000))


def words(text: str) -> list[str]:
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text.lower()).replace("-", " ")
    for a, b in SAME.items():
        text = re.sub(rf"(?<!\w){re.escape(a)}(?!\w)", b, text)
    out = []
    for w in re.findall(r"[a-z0-9#']+", text):
        out.extend(spell(int(w)).split() if w.isdigit() and int(w) < 1_000_000 else [w])
    return out


def match(expected: str, heard: str) -> float:
    """Similarity of the letters said, so 'pop-ups' and 'popups' or '140' and 'a hundred and forty' agree."""
    a, b = "".join(words(expected)), "".join(words(heard))
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def cues(text: str, heard: dict) -> list[dict]:
    """Our own sentences, timed by where their words fall in the transcription's segments."""
    sentences = [s for s in re.split(r"(?<=[.!?:])\s+", text) if s]
    marks, n = [], 0  # (word index in the transcript, time)
    for seg in heard["segments"]:
        marks.append((n, seg["start"]))
        n += len(words(seg["text"]))
    marks.append((n, heard["segments"][-1]["end"]))
    total = sum(len(words(s)) for s in sentences)

    def time_at(i: int) -> float:
        pos = i / total * n
        for (a, ta), (b, tb) in zip(marks, marks[1:]):
            if a <= pos <= b:
                return round(ta + (tb - ta) * ((pos - a) / (b - a) if b > a else 0), 2)
        return marks[-1][1]

    out, i = [], 0
    for s in sentences:
        k = len(words(s))
        out.append({"text": s, "start": time_at(i), "end": time_at(i + k)})
        i += k
    return out


def finalize(path: Path, tempo: float = 1.0) -> None:
    """Re-encode a take as constant-bitrate MP3 with a length header, sped up by `tempo`.

    Voxtral's MP3s are variable-bitrate without one, so players and ffprobe estimate their
    length from the bitrate and can be seconds off, which threw off scene timing. Voxtral has
    no speed setting, so the pace is raised here (atempo keeps the pitch).
    """
    tmp = path.with_suffix(".cbr.mp3")
    speed = ["-filter:a", f"atempo={tempo}"] if abs(tempo - 1) > 1e-6 else []
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), *speed, "-c:a", "libmp3lame", "-b:a", "128k",
                    "-ar", "44100", str(tmp)], check=True)
    tmp.replace(path)


def scale(cues_: list[dict], factor: float) -> list[dict]:
    return [{**c, "start": round(c["start"] * factor, 2), "end": round(c["end"] * factor, 2)} for c in cues_]


def duration(path: Path) -> float:
    """Length found by decoding the whole file, not estimated from the header."""
    out = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-f", "null", "-"],
                         capture_output=True, text=True, check=True).stderr
    h, m, sec = re.findall(r"time=(\d+):(\d+):([\d.]+)", out)[-1]
    return int(h) * 3600 + int(m) * 60 + float(sec)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="re-voice every scene")
    ap.add_argument("--voice", help="override the voice in narration.json")
    ap.add_argument("--takes", type=int, default=4, help="most takes per scene before keeping the closest")
    args = ap.parse_args()

    spec = json.loads((VIDEO / "narration.json").read_text())
    voice = args.voice or spec["voice"]
    tempo = spec.get("tempo", 1.0)
    key = find_api_key("MISTRAL_API_KEY", VIDEO.parent)
    if not key:
        raise SystemExit("no MISTRAL_API_KEY (environment, .env or ~/.vibe/.env)")
    AUDIO.mkdir(parents=True, exist_ok=True)
    old = {s["id"]: s for s in json.loads(OUT.read_text())["scenes"]} if OUT.exists() else {}

    scenes = []
    for s in spec["scenes"]:
        path = AUDIO / f"{s['id']}.mp3"
        spoken = s.get("say", s["text"])
        digest = hashlib.sha1(f"{spec['model']}|{voice}|{spoken}|{s['text']}".encode()).hexdigest()[:12]
        prev = old.get(s["id"], {})
        if not args.all and path.exists() and prev.get("hash") == digest and "match" in prev:
            done = prev.get("tempo", 1.0) if prev.get("cbr") else None
            if done != tempo:  # re-encode, or change the speed of a take that was already sped up
                finalize(path, tempo / (done or 1.0))
                prev.update(seconds=round(duration(path), 3), cbr=True, tempo=tempo,
                            cues=scale(prev["cues"], (done or 1.0) / tempo))
            scenes.append(prev)
            print(f"  {s['id']}: {prev['seconds']:.1f}s (unchanged, match {prev['match']:.2f})")
            continue
        best = None
        for take in range(1, args.takes + 1):
            tmp = path.with_suffix(f".take{take}.mp3")
            tmp.write_bytes(speak(key, spec["model"], voice, spoken))
            heard = transcribe(key, tmp)
            score = match(spoken, heard["text"])
            print(f"  {s['id']} take {take}: match {score:.3f}", flush=True)
            if best is None or score > best[0]:
                if best:
                    best[1].unlink()
                best = (score, tmp, heard)
            else:
                tmp.unlink()
            if score >= MIN_MATCH:
                break
        score, tmp, heard = best
        tmp.replace(path)
        finalize(path, tempo)
        if score < MIN_MATCH:
            print(f"  ! {s['id']}: best take heard as: {heard['text']}")
        scenes.append({"id": s["id"], "text": s["text"], "audio": f"audio/{s['id']}.mp3",
                       "seconds": round(duration(path), 3), "cbr": True, "tempo": tempo, "hash": digest,
                       "match": round(score, 3), "cues": scale(cues(s["text"], heard), 1 / tempo)})
    OUT.write_text(json.dumps({"voice": voice, "scenes": scenes}, indent=2) + "\n")
    print(f"total {sum(s['seconds'] for s in scenes):.1f}s -> {OUT.relative_to(VIDEO.parent)}")


if __name__ == "__main__":
    main()
