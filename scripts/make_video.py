"""Build the presentation video from the approved script and a video capture of demo mode (T9.28).

The owner's tool, run on the owner's machine only, after `scripts/capture_media.py --video` has
captured the demo's screenshots into the gitignored `data/capture/<time>/`. It reads the script the
owner approved (`docs/video/script.json`), speaks each sentence offline with Piper and its
`en_US-ljspeech` voice (`docs/SOURCES.md`, "Tools used to make media"; no service receives the
script), draws the title cards with the app's DejaVu Sans font, writes the subtitles from the same
sentences, and joins it all into an MP4 with FFmpeg, in `<capture>/video/`. It never writes outside
`data/capture/`, imports nothing of the app and never reads the key or the secrets file.

How to build the video again (`docs/TESTING.md`, "Presentation video (T9.28)", has the checklist):

1. Capture the screenshots: the steps in `scripts/capture_media.py`'s docstring, with `--video`.
2. Install Piper outside the repo, in a virtual environment of its own, with the voice beside it,
   as `docs/SOURCES.md` records (never into the project's `.venv`).
3. Run `python -m scripts.make_video --capture data/capture/<time> --piper <piper.exe>
   --voice <en_US-ljspeech-high.onnx> --ffmpeg <ffmpeg.exe>` (full paths for the tools), in a
   shell without `OPENROUTER_API_KEY` set, as Piper and FFmpeg inherit its environment.
4. Watch the whole video before it is uploaded; it stays in `data/capture/` and is never committed.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docs" / "video" / "script.json"
CAPTURE_ROOT = ROOT / "data" / "capture"
FONTS = ROOT / "assets" / "fonts"
FONT = FONTS / "DejaVuSans.ttf"
FONT_BOLD = FONTS / "DejaVuSans-Bold.ttf"
VIDEO_NAME = "fitcoach-demo.mp4"
# The screenshots `capture_media.py --video` writes (a name plus .png), and its chat frames.
FRAMES = "chat-frames"
SHOTS = frozenset(
    {
        FRAMES,
        "chat",
        "clients",
        "client-week",
        "review",
        "review-decide",
        "review-approved",
        "today",
        "my-week",
        "notifications",
    }
)
# The video's size and rate; the screenshots are taken at this size (capture_media.py).
SIZE = (1920, 1080)
FRAME_RATE = 30
# Piper's pace: below 1 speaks faster (its own pace is about 137 words a minute), so the approved
# script fits the 2 to 4 minutes of the ticket.
LENGTH_SCALE = 0.88
SENTENCE_PAUSE = 0.3
# One sentence takes Piper a few seconds (it loads the voice each time).
PIPER_TIMEOUT_SECONDS = 120
SCENE_PAUSE = 0.7
# The video's length the ticket asks for, checked when it is built; the script's own test
# estimates it from the words at about this pace.
MIN_SECONDS = 120
MAX_SECONDS = 240
WORDS_PER_MINUTE = 150
# The chat's frames play at most this long each while the answer appears.
FRAME_SECONDS = 0.5
# A subtitle longer than this is split in two at its middle comma.
MAX_SUBTITLE_CHARS = 90
# The app's light theme (.streamlit/config.toml [theme.light]).
BACKGROUND = "#FFFFFF"
TEXT = "#14171B"
PRIMARY = "#0F6E56"
# The subtitles: white DejaVu Sans on a dark box, in libass's units (a 288-line frame).
SUBTITLE_STYLE = (
    "FontName=DejaVu Sans,FontSize=13,PrimaryColour=&H00FFFFFF,BackColour=&H99000000,"
    "BorderStyle=3,Outline=5,Shadow=0,MarginV=16"
)
# Names a scene and the files built from it may use.
SAFE_NAME = re.compile(r"[a-z0-9-]+")


@dataclass(frozen=True)
class Scene:
    """One scene: a title card or screenshots, and the sentences said over it."""

    id: str
    card: tuple[str, ...]
    shows: tuple[tuple[str, int], ...]
    narration: tuple[str, ...]
    seconds: float


@dataclass(frozen=True)
class Cue:
    """A subtitle: its text and when it shows."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Segment:
    """What is on screen from `start` to `end`: a scene's card or one of its screenshots."""

    scene: str
    image: str
    start: float
    end: float


def load_script(path: Path = SCRIPT) -> list[Scene]:
    """Read the approved script and check it; raise ValueError naming the scene that is wrong."""
    data = json.loads(path.read_text(encoding="utf-8"))
    scenes = []
    for item in data["scenes"]:
        scene = Scene(
            id=item["id"],
            card=tuple(item.get("card", ())),
            shows=tuple((key, index) for key, index in item.get("shows", ())),
            narration=tuple(item["narration"]),
            seconds=float(item.get("seconds", 0)),
        )
        _check_scene(scene)
        scenes.append(scene)
    ids = [scene.id for scene in scenes]
    if len(set(ids)) != len(ids):
        raise ValueError("two scenes have the same id")
    return scenes


def _check_scene(scene: Scene) -> None:
    """Raise ValueError if a scene cannot be built."""
    if not SAFE_NAME.fullmatch(scene.id):
        raise ValueError(f"scene id: {scene.id}")
    if bool(scene.card) == bool(scene.shows):
        raise ValueError(f"scene {scene.id}: a card or screenshots, not both or neither")
    if not scene.narration and scene.seconds <= 0:
        raise ValueError(f"scene {scene.id}: no narration and no seconds")
    for text in (*scene.card, *scene.narration):
        # Piper reads the text from its standard input, which is not UTF-8 on Windows.
        if not text.strip() or not text.isascii():
            raise ValueError(f"scene {scene.id}: an empty or non-ASCII line")
    starts = [index for _, index in scene.shows]
    if scene.shows and (starts[0] != 0 or starts != sorted(set(starts))):
        raise ValueError(f"scene {scene.id}: screenshots must start at sentence 0, in order")
    for key, index in scene.shows:
        if key not in SHOTS or not 0 <= index < max(len(scene.narration), 1):
            raise ValueError(f"scene {scene.id}: unknown screenshot or sentence")


def check_capture(path: Path) -> Path:
    """Return the capture folder if it is a folder inside data/capture/, else raise ValueError."""
    folder = path.resolve()
    root = CAPTURE_ROOT.resolve()
    if folder == root or not folder.is_relative_to(root) or not folder.is_dir():
        raise ValueError("the capture must be a folder inside data/capture/")
    return folder


def missing_shots(capture: Path, scenes: Sequence[Scene]) -> list[str]:
    """Return the screenshots the scenes show that the capture folder lacks."""
    missing = []
    for key in sorted({key for scene in scenes for key, _ in scene.shows}):
        if key == FRAMES:
            if not sorted((capture / "frames").glob("*.png")):
                missing.append("frames/*.png")
        elif not (capture / f"{key}.png").is_file():
            missing.append(f"{key}.png")
    return missing


def piper_command(piper: Path, voice: Path, out: Path) -> list[str]:
    """Return Piper's arguments that speak the text on its standard input into a WAV file."""
    return [
        str(piper),
        "--model",
        str(voice),
        "--output-file",
        str(out),
        "--length-scale",
        f"{LENGTH_SCALE}",
    ]


def wav_seconds(path: Path) -> float:
    """Return a WAV file's length in seconds."""
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def subtitle_parts(text: str) -> list[str]:
    """Split a long sentence in two at the comma nearest its middle, so a subtitle stays short."""
    if len(text) <= MAX_SUBTITLE_CHARS:
        return [text]
    commas = [index for index, char in enumerate(text) if char == ","]
    if not commas:
        return [text]
    middle = min(commas, key=lambda index: abs(index - len(text) / 2))
    return [text[: middle + 1].strip(), text[middle + 1 :].strip()]


def build_timeline(
    scenes: Sequence[Scene], durations: dict[tuple[int, int], float]
) -> tuple[list[Cue], list[Segment], list[tuple[int, int, float]], float]:
    """Lay the scenes out in time: the subtitles, what is on screen, when each sentence starts."""
    cues: list[Cue] = []
    segments: list[Segment] = []
    spoken: list[tuple[int, int, float]] = []
    now = 0.0
    for scene_index, scene in enumerate(scenes):
        start = now
        starts = []
        for sentence_index, text in enumerate(scene.narration):
            if sentence_index:
                now += SENTENCE_PAUSE
            starts.append(now)
            length = durations[(scene_index, sentence_index)]
            spoken.append((scene_index, sentence_index, now))
            parts = subtitle_parts(text)
            part_start = now
            for part in parts:
                part_end = part_start + length * len(part) / sum(len(p) for p in parts)
                cues.append(Cue(part_start, part_end, part))
                part_start = part_end
            now += length
        now = max(now, start + scene.seconds) + SCENE_PAUSE
        if scene.card:
            segments.append(Segment(scene.id, "card", start, now))
        else:
            bounds = [start if index == 0 else starts[index] for _, index in scene.shows]
            ends = [*bounds[1:], now]
            for (key, _), begin, end in zip(scene.shows, bounds, ends, strict=True):
                segments.append(Segment(scene.id, key, begin, end))
    return cues, segments, spoken, now


def srt_time(seconds: float) -> str:
    """Return a time in SubRip's format, 00:01:02,345."""
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def srt(cues: Sequence[Cue]) -> str:
    """Return the subtitles as a SubRip file's text."""
    blocks = [
        f"{number}\n{srt_time(cue.start)} --> {srt_time(cue.end)}\n{cue.text}\n"
        for number, cue in enumerate(cues, start=1)
    ]
    return "\n".join(blocks)


def write_narration(clips: Sequence[tuple[Path, float]], total: float, out: Path) -> None:
    """Write one WAV with each sentence's clip at its start time and silence between them."""
    with wave.open(str(clips[0][0]), "rb") as first:
        params = first.getparams()
    rate = params.framerate
    frame_bytes = params.sampwidth * params.nchannels
    written = 0
    with wave.open(str(out), "wb") as narration:
        narration.setparams(params)
        for path, start in clips:
            gap = max(round(start * rate) - written, 0)
            narration.writeframes(bytes(gap * frame_bytes))
            with wave.open(str(path), "rb") as clip:
                frames = clip.readframes(clip.getnframes())
            narration.writeframes(frames)
            written += gap + len(frames) // frame_bytes
        narration.writeframes(bytes(max(round(total * rate) - written, 0) * frame_bytes))


def image_entries(segments: Sequence[Segment], frames: Sequence[str]) -> list[tuple[str, float]]:
    """Return each image the video shows, as a path from the video folder, with its seconds."""
    entries: list[tuple[str, float]] = []
    for segment in segments:
        length = segment.end - segment.start
        if segment.image == "card":
            entries.append((f"cards/{segment.scene}.png", length))
        elif segment.image == FRAMES:
            # The answer appears frame by frame, then its last frame stays for the rest.
            each = min(FRAME_SECONDS, length / len(frames))
            entries += [(f"../frames/{name}", each) for name in frames[:-1]]
            entries.append((f"../frames/{frames[-1]}", length - each * (len(frames) - 1)))
        else:
            entries.append((f"../{segment.image}.png", length))
    return entries


def concat_list(entries: Sequence[tuple[str, float]]) -> str:
    """Return FFmpeg's concat list: each image and its seconds, the last one named again."""
    lines = ["ffconcat version 1.0"]
    # The names are not escaped: they are this script's own (a scene id, checked by SAFE_NAME) or
    # capture_media.py's (`<shot>.png`, `frames/0000.png`), none with a quote.
    for path, seconds in entries:
        lines += [f"file '{path}'", f"duration {seconds:.3f}"]
    # FFmpeg's concat demuxer applies the last duration only when the file is named once more.
    lines.append(f"file '{entries[-1][0]}'")
    return "\n".join(lines) + "\n"


def video_command(ffmpeg: Path, total: float) -> list[str]:
    """Return FFmpeg's arguments, run in the video folder, that make the MP4 with its subtitles."""
    width, height = SIZE
    picture = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=white,"
        f"fps={FRAME_RATE},format=yuv420p,"
        f"subtitles=subtitles.srt:fontsdir=fonts:force_style='{SUBTITLE_STYLE}'"
    )
    return [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        # The list names the screenshots with "../", which the concat demuxer's safe mode refuses;
        # this script writes every line of it.
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        "images.txt",
        "-i",
        "narration.wav",
        "-vf",
        picture,
        "-c:v",
        "libopenh264",
        # OpenH264's default "quality" mode spent about 120 kb/s on the still screenshots and left
        # faint marks of the last one on the next; a set bitrate and a keyframe every 2 s do not.
        "-rc_mode",
        "bitrate",
        "-b:v",
        "4M",
        "-maxrate",
        "8M",
        "-g",
        f"{2 * FRAME_RATE}",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-t",
        f"{total:.3f}",
        "-movflags",
        "+faststart",
        VIDEO_NAME,
    ]


def draw_card(lines: Sequence[str], out: Path) -> None:
    """Draw a title card: the first line as its heading, the others below, on the app's colours."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = SIZE
    card = Image.new("RGB", SIZE, BACKGROUND)
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, 0, width, 14), fill=PRIMARY)
    long_text = sum(len(line) for line in lines) > 300
    heading = ImageFont.truetype(str(FONT_BOLD), 64 if long_text else 84)
    body = ImageFont.truetype(str(FONT), 32 if long_text else 44)
    margin = 160
    rows: list[tuple[str, ImageFont.FreeTypeFont, str]] = [(lines[0], heading, PRIMARY)]
    for line in lines[1:]:
        rows += [(row, body, TEXT) for row in _wrap(draw, line, body, width - 2 * margin)]
    gap = 22
    heights = [draw.textbbox((0, 0), row, font=font)[3] for row, font, _ in rows]
    # Above the subtitles' band at the bottom.
    y = max((height - 180 - sum(heights) - gap * len(rows)) // 2, 60)
    for (row, font, colour), row_height in zip(rows, heights, strict=True):
        draw.text((margin, y), row, font=font, fill=colour)
        y += row_height + gap + (24 if font is heading else 0)
    card.save(out)


def _wrap(draw, text: str, font, width: int) -> list[str]:
    """Break a line into rows no wider than `width` pixels."""
    rows: list[str] = []
    row = ""
    for word in text.split():
        candidate = f"{row} {word}".strip()
        if row and draw.textlength(candidate, font=font) > width:
            rows.append(row)
            row = word
        else:
            row = candidate
    return [*rows, row]


def _parse(args: Sequence[str] | None) -> argparse.Namespace:
    """Read the command line: the capture folder and the tools."""
    parser = argparse.ArgumentParser(description="Build the presentation video (T9.28).")
    parser.add_argument("--capture", type=Path, required=True, help="data/capture/<time>")
    parser.add_argument("--piper", type=Path, required=True, help="Piper's piper.exe")
    parser.add_argument("--voice", type=Path, required=True, help="en_US-ljspeech-high.onnx")
    parser.add_argument("--ffmpeg", type=Path, required=True, help="FFmpeg's ffmpeg.exe")
    return parser.parse_args(args)


def main(args: Sequence[str] | None = None) -> int:
    """Check the capture and the tools, then speak, draw and join the video in <capture>/video/."""
    # No observability.configure_logging() here, as in capture_media.py: it reads the secrets file
    # and puts the key in the environment Piper and FFmpeg would inherit; this script writes no log
    # lines and runs no model (T9.28).
    options = _parse(args)
    try:
        capture = check_capture(options.capture)
        scenes = load_script()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    for tool in (options.piper, options.voice, options.ffmpeg):
        if not tool.is_file():
            print(f"not found: {tool}", file=sys.stderr)
            return 2
    missing = missing_shots(capture, scenes)
    if missing:
        print(f"missing in the capture: {', '.join(missing)}", file=sys.stderr)
        return 2
    out = capture / "video"
    for folder in ("speech", "cards", "fonts"):
        (out / folder).mkdir(parents=True, exist_ok=True)
    clips: dict[tuple[int, int], Path] = {}
    for scene_index, scene in enumerate(scenes):
        for sentence_index, text in enumerate(scene.narration):
            clip = out / "speech" / f"{scene_index:02d}-{sentence_index:02d}.wav"
            try:
                subprocess.run(
                    piper_command(options.piper, options.voice, clip),
                    input=text + "\n",
                    text=True,
                    encoding="ascii",
                    errors="replace",
                    capture_output=True,
                    check=True,
                    timeout=PIPER_TIMEOUT_SECONDS,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                # Piper's own messages (it is given no key or secret), so a failure can be read.
                print(exc.stderr or "", file=sys.stderr)
                raise
            clips[(scene_index, sentence_index)] = clip
        if scene.card:
            draw_card(scene.card, out / "cards" / f"{scene.id}.png")
    durations = {key: wav_seconds(path) for key, path in clips.items()}
    cues, segments, spoken, total = build_timeline(scenes, durations)
    starts = [(clips[(scene, sentence)], start) for scene, sentence, start in spoken]
    write_narration(starts, total, out / "narration.wav")
    (out / "subtitles.srt").write_text(srt(cues), encoding="utf-8")
    for font in (FONT, FONT_BOLD):
        shutil.copy(font, out / "fonts" / font.name)
    frames = [path.name for path in sorted((capture / "frames").glob("*.png"))]
    (out / "images.txt").write_text(concat_list(image_entries(segments, frames)), encoding="utf-8")
    subprocess.run(video_command(options.ffmpeg, total), cwd=out, check=True)
    print(f"written: {out / VIDEO_NAME} ({total:.1f} s)")
    if not MIN_SECONDS <= total <= MAX_SECONDS:
        print(f"the video should last {MIN_SECONDS} to {MAX_SECONDS} s", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
