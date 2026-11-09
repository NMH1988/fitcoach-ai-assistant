"""Capture the README's screenshots and GIF from the running app in demo mode (T9.27).

The owner's tool, run on the owner's machine only: it drives a browser through the app's demo
mode (synthetic users on a temporary database, T9.5, D18) and writes the screenshots, the GIF and
the frames it is made of into the gitignored `data/capture/<time>/`. It only drives the browser:
it never reads the key, the secrets file or the store, and it refuses any address but the local
app at http://localhost:8501. Every HTTP request the page makes off the local app is aborted and
service workers are blocked; Playwright's routing does not see WebSockets, and the app's only one
is its own, to the same local address.

How to capture the images again when the UI changes:

1. `.streamlit/secrets.toml` has the OpenRouter key (the chat and the weekly review call the model,
   a few cents a run) and no `[auth]` section: demo mode is ignored while one is set
   (`docs/DEPLOYMENT.md`, "Demo mode"). Restart the app after a code or data change, so the demo
   database is seeded again with last week's records (`src/demo.py`).
2. Start the app in demo mode on port 8501, with the toolbar's developer buttons hidden:
   `DEMO_MODE=1 streamlit run app.py --client.toolbarMode minimal` in Git Bash, or
   `$env:DEMO_MODE = "1"; streamlit run app.py --client.toolbarMode minimal` in PowerShell.
3. Install the `media` extra (`pip install -e ".[media]"`) and the Chromium build and FFmpeg named
   in `docs/SOURCES.md`, "Tools used to make media" (downloaded by hand, outside the repo; never
   `playwright install`).
4. In a shell without `OPENROUTER_API_KEY` set (the browser and FFmpeg inherit the shell's
   environment; the app reads the key from `secrets.toml`), run
   `python -m scripts.capture_media --browser <chrome.exe> --ffmpeg <ffmpeg.exe>` (full paths).
   One run drafts and approves one weekly review in the demo database; restart the app before a
   second run, so the review can be drafted again.
5. Look at every image (synthetic data only; no key, account or real person; only `localhost`), then
   copy the chosen files into `docs/media/` and run `python -m pytest tests/test_readme_media.py`
   (sizes and the GIF's length). `docs/TESTING.md`, "README images (T9.27)", has the checklist.
"""

import argparse
import subprocess
import sys
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

APP_URL = "http://localhost:8501/"
# The project's folder, so the output lands in the gitignored data/capture/ wherever it is run from.
ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "data" / "capture"
# The app's own time zone (src/config.py TIME_ZONE, D21), so "last week" is the week the demo
# seeded; the script imports nothing of the app.
TIME_ZONE = ZoneInfo("Europe/Berlin")
# The window the images are taken in; the README shows them at this size or smaller.
VIEWPORT = {"width": 1280, "height": 860}
JPEG_QUALITY = 80
# The demo users' names in the picker (src/demo.py) and the question the coach asks in the chat.
COACH = "Demo coach Alex"
GYMER = "Demo gymer Sam"
QUESTION = "How much protein per day helps build muscle?"
# The GIF: the chat's frames, taken every FRAME_SECONDS while the answer appears, played back in at
# most GIF_SECONDS (the README's limit is 10 seconds and 5 MB, tests/test_readme_media.py).
FRAME_SECONDS = 0.5
GIF_SECONDS = 9.0
GIF_WIDTH = 960
# A frame is kept only when it differs from the last kept one over more than this share of the
# window (the wait's spinner is smaller), and the GIF plays at least this many frames a second.
MIN_CHANGED_SHARE = 0.01
MIN_FRAME_RATE = 1.0
# How long to wait for the model: a chat answer, and a weekly review's draft (several model calls).
ANSWER_TIMEOUT_MS = 180_000
REVIEW_TIMEOUT_MS = 300_000
REVIEW_TRIES = 3
# Run in the page: put an element in the middle of the nearest box that scrolls around it.
CENTRE_IN_SCROLL_BOX = """element => {
    let box = element.parentElement;
    while (box && !(box.scrollHeight > box.clientHeight
            && getComputedStyle(box).overflowY !== 'visible')) {
        box = box.parentElement;
    }
    if (box) {
        const inner = element.getBoundingClientRect();
        const outer = box.getBoundingClientRect();
        box.scrollTop += inner.top - outer.top - outer.height / 2;
    }
}"""


def check_app_url(url: str) -> str:
    """Return the app's address if `url` is the local app at http://localhost:8501, else raise."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ValueError("only http://localhost:8501 may be captured") from exc
    if (
        parts.scheme != "http"
        or parts.hostname != "localhost"
        or port != 8501
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise ValueError("only http://localhost:8501 may be captured")
    return APP_URL


def is_app_request(url: str) -> bool:
    """Return True if an HTTP request the page makes goes to the local app."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "http"
        and parts.hostname == "localhost"
        and port == 8501
        and parts.username is None
    )


def last_monday(today: date) -> date:
    """Return the Monday of the week before `today`'s, the week the review is drafted for."""
    return today - timedelta(days=today.weekday() + 7)


def changed(previous: Path, current: Path) -> bool:
    """Return True if the two screenshots differ over more than MIN_CHANGED_SHARE of the window."""
    from PIL import Image, ImageChops

    with Image.open(previous) as before, Image.open(current) as after:
        box = ImageChops.difference(before.convert("RGB"), after.convert("RGB")).getbbox()
        if box is None:
            return False
        area = (box[2] - box[0]) * (box[3] - box[1])
        return area > MIN_CHANGED_SHARE * after.width * after.height


def gif_command(ffmpeg: Path, frames: Path, frame_count: int, out: Path) -> list[str]:
    """Return FFmpeg's arguments that join the numbered frames into a GIF of at most GIF_SECONDS."""
    # The kept frames share the GIF's seconds, so the whole answer fits; the palette is made from
    # the frames themselves, which keeps the file small and the text sharp.
    rate = max(frame_count / GIF_SECONDS, MIN_FRAME_RATE)
    scale = f"scale={GIF_WIDTH}:-1:flags=lanczos"
    palette = "split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer"
    return [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        f"{rate:.3f}",
        "-i",
        str(frames / "%04d.png"),
        "-vf",
        f"{scale},{palette}",
        "-t",
        f"{GIF_SECONDS}",
        str(out),
    ]


def _parse(args: Sequence[str] | None) -> argparse.Namespace:
    """Read the command line: the app's address, the browser and FFmpeg."""
    parser = argparse.ArgumentParser(description="Capture the README images (T9.27).")
    parser.add_argument("--url", default=APP_URL, help="the app (only http://localhost:8501)")
    parser.add_argument("--browser", type=Path, required=True, help="Chromium's chrome.exe")
    parser.add_argument("--ffmpeg", type=Path, required=True, help="FFmpeg's ffmpeg.exe")
    parser.add_argument("--headed", action="store_true", help="show the browser while it runs")
    return parser.parse_args(args)


def main(args: Sequence[str] | None = None) -> int:
    """Check the address and the tools, then capture into a new folder under data/capture/."""
    # No observability.configure_logging() here, unlike the other scripts (T8.2): it reads the
    # secrets file and puts the key in the environment the browser and FFmpeg would inherit, and
    # this script writes no log lines (owner's decision, 2026-11-09, code review round 2).
    options = _parse(args)
    try:
        url = check_app_url(options.url)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    for tool in (options.browser, options.ffmpeg):
        if not tool.is_file():
            print(f"not found: {tool}", file=sys.stderr)
            return 2
    out = OUTPUT_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / "frames").mkdir(parents=True)
    count = capture(url, options.browser, out, headed=options.headed)
    subprocess.run(gif_command(options.ffmpeg, out / "frames", count, out / "chat.gif"), check=True)
    print(f"written: {out}")
    return 0


def capture(url: str, browser_path: Path, out: Path, *, headed: bool = False) -> int:
    """Drive the app through the coach's and the gymer's pages; return the GIF's frame count."""
    # Imported here, so the address check and its tests run without Playwright (CI installs only
    # the dev extra).
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(browser_path), headless=not headed)
        context = browser.new_context(
            viewport=VIEWPORT, color_scheme="light", locale="en-US", service_workers="block"
        )
        context.route(
            "**/*",
            lambda route: route.continue_() if is_app_request(route.request.url) else route.abort(),
        )
        page = context.new_page()
        page.goto(url)
        _pick(page, "Demo user", COACH)
        count = _chat(page, out)
        _open(page, "Clients")
        # The client table is drawn on a canvas after the run.
        page.locator("[data-testid='stDataFrame'] canvas").first.wait_for()
        page.wait_for_timeout(1500)
        _top(page, "Clients")
        _shot(page, out / "clients.jpg")
        _open(page, "Client week")
        _pick(page, "Client", GYMER)
        _week(page, "Client week")
        _top(page, "Nutrition")
        _shot(page, out / "client-week.jpg")
        _review(page, out)
        _pick(page, "Demo user", GYMER)
        _open(page, "My week")
        _week(page, "My week")
        _top(page, "Weekly reviews")
        _shot(page, out / "my-week.jpg")
        _open(page, "Notifications")
        _top(page, "Notifications")
        _shot(page, out / "notifications.jpg")
        browser.close()
    return count


def _settle(page, timeout_ms: int = 60_000) -> None:
    """Wait until Streamlit has finished its run (its 'Running' status came and went)."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    status = page.locator("[data-testid='stStatusWidget']")
    try:
        # A quick run may end before its status shows; a long one (a model call) shows it.
        status.wait_for(state="attached", timeout=3_000)
    except PlaywrightTimeout:
        pass
    status.wait_for(state="detached", timeout=timeout_ms)
    page.wait_for_timeout(800)


def _pick(page, label: str, option: str) -> None:
    """Choose an option in the select box with this label."""
    page.get_by_label(label, exact=True).first.click()
    page.get_by_role("option", name=option, exact=True).click()
    _settle(page)


def _open(page, title: str) -> None:
    """Open a page from the sidebar's navigation (a click keeps the session's demo user)."""
    page.locator("[data-testid='stSidebarNav']").get_by_text(title, exact=True).click()
    _settle(page)


def _week(page, heading: str) -> None:
    """Set the page's week picker to last week, the finished week the review is about."""
    # Streamlit's date field is three spin buttons (year, month, day), not a text box: each is
    # moved with the arrow keys from its value to the target's, then a click on the page's
    # heading leaves the field, which applies the date and closes its calendar.
    monday = last_monday(datetime.now(TIME_ZONE).date())
    group = page.get_by_role("group", name="Week of").first
    for part, target in (("year", monday.year), ("month", monday.month), ("day", monday.day)):
        segment = group.get_by_role("spinbutton", name=f"{part}, Week of")
        segment.focus()
        now = int(segment.get_attribute("aria-valuenow") or target)
        for _ in range(abs(target - now)):
            segment.press("ArrowUp" if target > now else "ArrowDown")
    page.get_by_role("heading", name=heading, exact=True).first.click()
    _settle(page)
    sunday = monday + timedelta(days=6)
    page.get_by_text(f"{monday.isoformat()} to {sunday.isoformat()}").first.wait_for()


def _top(page, heading: str) -> None:
    """Scroll the main column so this heading is at the top of the window."""
    page.get_by_role("heading", name=heading, exact=True).first.evaluate(
        "element => element.scrollIntoView({block: 'start'})"
    )
    page.wait_for_timeout(600)


def _shot(page, path: Path) -> None:
    """Save the window as a JPEG."""
    page.screenshot(path=str(path), type="jpeg", quality=JPEG_QUALITY)


def _chat(page, out: Path) -> int:
    """Ask the coach's question, keep frames while the answer appears, open its sources."""
    frames = out / "frames"
    box = page.get_by_placeholder("Ask about nutrition or training principles")
    box.fill(QUESTION)
    count = 0
    page.screenshot(path=str(frames / f"{count:04d}.png"))
    count += 1
    box.press("Enter")
    sources = page.get_by_text("Sources (", exact=False).last
    waited = 0
    while not sources.is_visible() and waited < ANSWER_TIMEOUT_MS:
        page.wait_for_timeout(int(FRAME_SECONDS * 1000))
        waited += int(FRAME_SECONDS * 1000)
        frame = frames / f"{count:04d}.png"
        page.screenshot(path=str(frame))
        # A frame like the last kept one (only the spinner moved) is dropped, so the wait does
        # not fill the GIF.
        if changed(frames / f"{count - 1:04d}.png", frame):
            count += 1
        else:
            frame.unlink()
    _settle(page)
    sources.click()
    page.wait_for_timeout(800)
    # The answer's last lines with their [S#] citations above, the first source cards below: the
    # expander's own heading (its <summary>) is put in the middle of the chat's scrolling box.
    # The box keeps itself scrolled to the bottom while its content grows, so this waits for the
    # expander to finish opening, then sets the box's scroll position itself.
    page.wait_for_timeout(1500)
    heading = page.locator("[data-testid='stExpander'] summary").last
    heading.evaluate(CENTRE_IN_SCROLL_BOX)
    page.wait_for_timeout(300)
    for _ in range(4):  # the open sources stay on screen for the GIF's last second
        page.screenshot(path=str(frames / f"{count:04d}.png"))
        count += 1
    _shot(page, out / "chat.jpg")
    return count


def _review(page, out: Path) -> None:
    """Draft the weekly review of last week, shoot it waiting for approval, then approve it."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    approve = page.get_by_role("button", name="Approve", exact=True)
    # A draft the app's checks refuse leaves a warning and the button to draft again: try again,
    # a few times at most (each try is one model run).
    for _ in range(REVIEW_TRIES):
        page.get_by_role("button", name="Draft weekly review").click()
        _settle(page, timeout_ms=REVIEW_TIMEOUT_MS)
        try:
            approve.wait_for(timeout=10_000)
            break
        except PlaywrightTimeout:  # no draft to decide on: the app's checks refused this one
            continue
    else:
        raise RuntimeError(f"no draft passed the app's checks in {REVIEW_TRIES} tries")
    # A taller window for this one image, so the draft and its Approve, Edit and Reject buttons
    # show together; then back to the usual size.
    _top(page, "Weekly review")
    heading = page.get_by_role("heading", name="Weekly review", exact=True).first.bounding_box()
    buttons = approve.bounding_box()
    if heading and buttons:
        height = int(buttons["y"] + buttons["height"] - heading["y"]) + 120
        page.set_viewport_size({"width": VIEWPORT["width"], "height": min(max(height, 860), 2400)})
        _top(page, "Weekly review")
    _shot(page, out / "review.jpg")
    page.set_viewport_size(VIEWPORT)
    approve.click()
    _settle(page)


if __name__ == "__main__":
    sys.exit(main())
