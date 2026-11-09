"""The presentation video's build script, with no Piper, FFmpeg or browser run (T9.28)."""

import ast
import json
import wave
from pathlib import Path

import pytest

from scripts import make_video

SCRIPT = Path(make_video.__file__)
ROOT = Path(__file__).resolve().parents[1]


def _scene(**fields) -> dict:
    """Return a valid screenshot scene for a script file, with some fields replaced."""
    scene = {"id": "clients", "shows": [["clients", 0]], "narration": ["One.", "Two."]}
    scene.update(fields)
    return scene


def _write_script(tmp_path: Path, *scenes: dict) -> Path:
    """Write a script file with these scenes and return its path."""
    path = tmp_path / "script.json"
    path.write_text(json.dumps({"scenes": list(scenes)}), encoding="utf-8")
    return path


def _wav(path: Path, seconds: float, rate: int = 1000) -> Path:
    """Write a mono 16-bit WAV of silence this many seconds long."""
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(bytes(round(seconds * rate) * 2))
    return path


def test_the_committed_script_loads():
    """The approved script passes the build's checks and names only shots the capture makes."""
    scenes = make_video.load_script()
    assert scenes[0].id == "opening" and scenes[-1].id == "credits"
    assert {key for scene in scenes for key, _ in scene.shows} <= make_video.SHOTS


@pytest.mark.parametrize(
    "scene",
    [
        _scene(shows=[["settings", 0]]),  # a screenshot the capture does not make
        _scene(shows=[["clients", 2]]),  # past the last sentence
        _scene(shows=[["clients", 1]]),  # not from the first sentence
        _scene(shows=[["clients", 0], ["today", 0]]),  # two at one sentence
        _scene(narration=["Café."]),  # not ASCII, which Piper's input on Windows needs
        _scene(narration=[" "]),
        _scene(narration=[]),  # nothing said and no seconds
        _scene(card=["A card"]),  # a card and screenshots
        _scene(shows=[]),  # neither
        _scene(id="../video"),
    ],
)
def test_a_script_the_build_cannot_use_is_refused(tmp_path, scene):
    """A wrong scene stops the build with a ValueError before anything runs."""
    with pytest.raises(ValueError):
        make_video.load_script(_write_script(tmp_path, scene))


def test_two_scenes_with_one_id_are_refused(tmp_path):
    """Scene ids name the card files, so they must differ."""
    with pytest.raises(ValueError):
        make_video.load_script(_write_script(tmp_path, _scene(), _scene()))


def test_the_capture_must_be_inside_data_capture(monkeypatch, tmp_path):
    """Only a folder inside data/capture/ is used; the folder itself or one outside is refused."""
    root = tmp_path / "data" / "capture"
    run = root / "20261109-120000"
    run.mkdir(parents=True)
    monkeypatch.setattr(make_video, "CAPTURE_ROOT", root)
    assert make_video.check_capture(run) == run.resolve()
    for path in (root, tmp_path, run / ".." / "..", root / "missing"):
        with pytest.raises(ValueError):
            make_video.check_capture(path)


def test_the_output_stays_in_the_gitignored_capture_folder():
    """The video and its parts go to data/capture/, which .gitignore names."""
    assert make_video.CAPTURE_ROOT == ROOT / "data" / "capture"
    assert "data/capture/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_a_wrong_capture_or_a_missing_tool_starts_nothing(monkeypatch, tmp_path, capsys):
    """main() stops before Piper or FFmpeg runs, and writes no video folder."""
    root = tmp_path / "capture"
    (root / "run").mkdir(parents=True)
    monkeypatch.setattr(make_video, "CAPTURE_ROOT", root)
    monkeypatch.setattr(make_video.subprocess, "run", lambda *a, **k: pytest.fail("ran a tool"))
    tool = tmp_path / "tool.exe"
    tool.write_bytes(b"")
    common = ["--piper", str(tool), "--voice", str(tool), "--ffmpeg", str(tool)]
    assert make_video.main(["--capture", str(tmp_path), *common]) == 2
    missing = ["--piper", str(tmp_path / "none.exe"), "--voice", str(tool), "--ffmpeg", str(tool)]
    assert make_video.main(["--capture", str(root / "run"), *missing]) == 2
    # The capture lacks the screenshots.
    assert make_video.main(["--capture", str(root / "run"), *common]) == 2
    assert "missing in the capture" in capsys.readouterr().err
    assert not (root / "run" / "video").exists()


def test_a_piper_failure_shows_its_message_and_stops(monkeypatch, tmp_path, capsys):
    """Piper's stderr is printed and its error raised again; each call has a timeout."""
    root = tmp_path / "capture"
    run = root / "run"
    (run / "frames").mkdir(parents=True)
    (run / "frames" / "0000.png").write_bytes(b"")
    for key in make_video.SHOTS - {make_video.FRAMES}:
        (run / f"{key}.png").write_bytes(b"")
    monkeypatch.setattr(make_video, "CAPTURE_ROOT", root)
    tool = tmp_path / "tool.exe"
    tool.write_bytes(b"")
    calls = []

    def failing_run(command, **kwargs):
        """Fail as Piper does, with a made-up message."""
        calls.append(kwargs)
        raise make_video.subprocess.CalledProcessError(1, command, stderr="voice not loaded")

    monkeypatch.setattr(make_video.subprocess, "run", failing_run)
    args = ["--capture", str(run), "--piper", str(tool), "--voice", str(tool)]
    args += ["--ffmpeg", str(tool)]
    with pytest.raises(make_video.subprocess.CalledProcessError):
        make_video.main(args)
    assert "voice not loaded" in capsys.readouterr().err
    assert calls[0]["timeout"] == make_video.PIPER_TIMEOUT_SECONDS
    assert len(calls) == 1  # nothing else runs after the failure


def test_missing_shots_names_each_screenshot_the_capture_lacks(tmp_path):
    """Every screenshot a scene shows, and the chat's frames, must be in the capture."""
    scenes = [make_video.Scene("chat", (), (("chat-frames", 0), ("chat", 1)), ("a", "b"), 0)]
    assert make_video.missing_shots(tmp_path, scenes) == ["chat.png", "frames/*.png"]
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "0000.png").write_bytes(b"")
    (tmp_path / "chat.png").write_bytes(b"")
    assert make_video.missing_shots(tmp_path, scenes) == []


def test_piper_reads_the_text_from_its_input_with_the_local_voice(tmp_path):
    """Piper gets a list of arguments (no shell): the local voice file and the WAV to write."""
    command = make_video.piper_command(Path("piper.exe"), Path("voice.onnx"), Path("a.wav"))
    assert command == [
        "piper.exe",
        "--model",
        "voice.onnx",
        "--output-file",
        "a.wav",
        "--length-scale",
        f"{make_video.LENGTH_SCALE}",
    ]


def test_a_long_sentence_is_split_at_its_middle_comma():
    """A subtitle over the limit becomes two parts at the comma nearest its middle."""
    short = "Clients have no AI chat."
    assert make_video.subtitle_parts(short) == [short]
    long = (
        "The agent reads the numbers of the week, then the research, and then it stops and waits"
        " for the coach."
    )
    assert len(long) > make_video.MAX_SUBTITLE_CHARS
    assert make_video.subtitle_parts(long) == [
        "The agent reads the numbers of the week, then the research,",
        "and then it stops and waits for the coach.",
    ]


def test_the_timeline_lays_out_sentences_pauses_and_screenshots():
    """Each sentence follows the last after a pause; each screenshot starts with its sentence."""
    scenes = [
        make_video.Scene("opening", ("Title",), (), ("One.",), 0),
        make_video.Scene("review", (), (("review", 0), ("review-approved", 1)), ("A.", "B."), 0),
        make_video.Scene("credits", ("Credits",), (), (), 8),
    ]
    durations = {(0, 0): 2.0, (1, 0): 3.0, (1, 1): 1.0}
    cues, segments, spoken, total = make_video.build_timeline(scenes, durations)
    pause, gap = make_video.SENTENCE_PAUSE, make_video.SCENE_PAUSE
    second = 2.0 + gap
    assert [(cue.start, cue.end, cue.text) for cue in cues] == [
        (0.0, 2.0, "One."),
        (second, second + 3.0, "A."),
        (second + 3.0 + pause, second + 4.0 + pause, "B."),
    ]
    third = second + 4.0 + pause + gap
    assert segments == [
        make_video.Segment("opening", "card", 0.0, second),
        make_video.Segment("review", "review", second, second + 3.0 + pause),
        make_video.Segment("review", "review-approved", second + 3.0 + pause, third),
        make_video.Segment("credits", "card", third, third + 8 + gap),
    ]
    assert [start for _, _, start in spoken] == [0.0, second, second + 3.0 + pause]
    assert total == pytest.approx(third + 8 + gap)


def test_the_subtitles_are_written_as_subrip():
    """Times read hours:minutes:seconds,milliseconds and the cues are numbered from 1."""
    assert make_video.srt_time(62.3456) == "00:01:02,346"
    assert make_video.srt_time(3725.0) == "01:02:05,000"
    text = make_video.srt([make_video.Cue(0.0, 1.5, "One."), make_video.Cue(2.0, 3.0, "Two.")])
    assert text.split("\n") == [
        "1",
        "00:00:00,000 --> 00:00:01,500",
        "One.",
        "",
        "2",
        "00:00:02,000 --> 00:00:03,000",
        "Two.",
        "",
    ]


def test_the_narration_puts_each_clip_at_its_start(tmp_path):
    """The joined WAV has silence before each clip's start and lasts the whole video."""
    first = _wav(tmp_path / "a.wav", 1.0)
    second = _wav(tmp_path / "b.wav", 0.5)
    out = tmp_path / "narration.wav"
    make_video.write_narration([(first, 0.0), (second, 2.0)], 4.0, out)
    assert make_video.wav_seconds(out) == pytest.approx(4.0)


def test_the_chat_frames_play_then_the_last_one_stays():
    """The answer's frames play FRAME_SECONDS each and the last fills the rest of its time."""
    segments = [
        make_video.Segment("opening", "card", 0.0, 5.0),
        make_video.Segment("chat", "chat-frames", 5.0, 15.0),
        make_video.Segment("chat", "chat", 15.0, 20.0),
    ]
    entries = make_video.image_entries(segments, ["0000.png", "0001.png", "0002.png"])
    each = make_video.FRAME_SECONDS
    assert entries == [
        ("cards/opening.png", 5.0),
        ("../frames/0000.png", each),
        ("../frames/0001.png", each),
        ("../frames/0002.png", pytest.approx(10.0 - 2 * each)),
        ("../chat.png", 5.0),
    ]


def test_many_chat_frames_are_sped_up_to_fit():
    """More frames than the time allows share it equally."""
    segments = [make_video.Segment("chat", "chat-frames", 0.0, 2.0)]
    entries = make_video.image_entries(segments, [f"{n:04d}.png" for n in range(8)])
    assert [seconds for _, seconds in entries] == pytest.approx([0.25] * 8)


def test_the_concat_list_names_the_last_image_again():
    """FFmpeg's concat demuxer needs the last file once more to apply its duration."""
    text = make_video.concat_list([("cards/opening.png", 5.0), ("../chat.png", 2.25)])
    assert text.splitlines() == [
        "ffconcat version 1.0",
        "file 'cards/opening.png'",
        "duration 5.000",
        "file '../chat.png'",
        "duration 2.250",
        "file '../chat.png'",
    ]


def test_the_video_command_burns_in_the_subtitles_as_an_mp4():
    """A list of arguments (no shell): H.264 and AAC, the subtitles in DejaVu Sans, the length."""
    command = make_video.video_command(Path("ffmpeg.exe"), 201.5)
    assert command[0] == "ffmpeg.exe" and command[-1] == make_video.VIDEO_NAME
    picture = command[command.index("-vf") + 1]
    assert "subtitles=subtitles.srt:fontsdir=fonts" in picture
    assert "FontName=DejaVu Sans" in picture
    assert command[command.index("-c:v") + 1] == "libopenh264"
    assert command[command.index("-rc_mode") + 1] == "bitrate"  # no faint marks between images
    assert command[command.index("-g") + 1] == str(2 * make_video.FRAME_RATE)
    assert command[command.index("-c:a") + 1] == "aac"
    assert command[command.index("-t") + 1] == "201.500"
    assert make_video.VIDEO_NAME.endswith(".mp4")


def test_a_card_is_drawn_at_the_video_size(tmp_path):
    """A title card is a 1920 by 1080 image, its long lines wrapped."""
    from PIL import Image

    out = tmp_path / "card.png"
    make_video.draw_card(["Credits", "word " * 120, "Title font: DejaVu Sans."], out)
    with Image.open(out) as card:
        assert card.size == make_video.SIZE


def test_the_script_sends_nothing_and_never_reads_the_key_or_secrets():
    """No network module, nothing of the app, and no code that names the key, secrets or store."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    # The module docstring explains these words; the code may not use them.
    tree.body = tree.body[1:]
    banned_modules = {
        "src",
        "scripts",
        "streamlit",
        "tomllib",
        "os",
        "importlib",
        "urllib",
        "http",
        "socket",
        "requests",
        "httpx",
        "ssl",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            modules = [alias.name for alias in node.names] + [getattr(node, "module", "") or ""]
            assert not any(module.split(".")[0] in banned_modules for module in modules)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.lower()
            words = ("secret", "openrouter", "api_key", "data/store", ".sqlite")
            assert not any(word in text for word in words)
        if isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            assert name not in {"environ", "getenv", "secrets", "get_api_key", "__import__"}
