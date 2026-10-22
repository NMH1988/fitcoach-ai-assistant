"""UI tests for the session summary download button in the sidebar (T5.2, AC-9)."""

import ast
from pathlib import Path

import pytest
import streamlit as st
from langchain_core.messages import AIMessage
from streamlit.testing.v1 import AppTest

from src import chat, config, llm
from src.rag import store
from tests.fakes import (
    PROFILE,
    ScriptedChatModel,
    ScriptedTranslator,
    build_fixture_index,
    open_fixture_index,
    pdf_text,
)

APP = Path(__file__).resolve().parent.parent / "app.py"

pytestmark = pytest.mark.usefixtures("no_env_key")


@pytest.fixture(scope="module")
def index_path(tmp_path_factory):
    """Build the fixture index once for the module and return its directory."""
    return build_fixture_index(tmp_path_factory.mktemp("index") / "chroma")


@pytest.fixture(autouse=True)
def fakes(tmp_path, monkeypatch, index_path):
    """Give the app the fixture index, test prompts, a scripted model and fresh caches."""
    for name in ("ANSWER_PROMPT_PATH", "QUERY_TRANSLATION_PROMPT_PATH"):
        prompt = tmp_path / f"{name}.md"
        prompt.write_text("Test prompt.", encoding="utf-8")
        monkeypatch.setattr(config, name, prompt)
    monkeypatch.setattr(config, "ANSWER_WORDS_PER_SECOND", 0)
    monkeypatch.setattr(store, "open_index", lambda: open_fixture_index(index_path))
    monkeypatch.setattr(chat, "manifest_by_id", lambda: {})
    model, translator = (
        ScriptedChatModel(replies=[AIMessage("Four meals [S1].")]),
        ScriptedTranslator(),
    )

    def build(name: str = config.DEFAULT_ANSWER_MODEL, *args, **kwargs):
        """Return the fake translator for the query translation model, else the answer fake."""
        return translator if name == config.QUERY_TRANSLATION_MODEL else model

    monkeypatch.setattr(llm, "build_chat_model", build)
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def _start(profile=None) -> AppTest:
    """Run the app once, with this profile in the session (None: no profile)."""
    at = AppTest.from_file(str(APP))
    at.secrets["UNRELATED"] = "x"
    if profile is not None:
        at.session_state["profile"] = profile
    return at.run(timeout=30)


def _button(at: AppTest):
    """Return the sidebar's summary download button."""
    (button,) = at.sidebar.download_button
    return button


def test_the_button_is_in_the_sidebar_and_off_in_an_empty_session():
    """A new session shows the button in the sidebar, switched off with a hint on what to do."""
    at = _start()
    assert not at.exception
    button = _button(at)
    assert button.label == config.PDF_BUTTON_LABEL
    assert button.disabled
    assert button.help == config.PDF_BUTTON_EMPTY_HELP
    assert not at.download_button(key="summary_pdf").value


def test_the_button_is_on_once_a_profile_is_added():
    """With a profile there is something to export: the button is on and says what it gives."""
    button = _button(_start(PROFILE))
    assert not button.disabled
    assert button.help == config.PDF_BUTTON_HELP


def test_the_button_is_on_after_a_question_without_a_profile():
    """After one question, the button is on even without a profile."""
    at = _start()
    at.chat_input(key="chat_input").set_value("How much protein per meal?").run(timeout=30)
    assert not at.exception
    assert not _button(at).disabled


def test_the_button_sits_after_the_theme_hint_and_before_the_last_answer_card():
    """In the sidebar, the button comes after the theme hint and before "Last answer"."""
    source = APP.read_text(encoding="utf-8")
    sidebar = source.split("with st.sidebar:", 1)[1]
    assert sidebar.index('_t("theme.hint")') < sidebar.index("download_slot = st.empty()")
    assert sidebar.index("download_slot = st.empty()") < sidebar.index("last_answer_slot")


def test_the_button_is_drawn_once_per_run_after_the_main_area():
    """The slot is filled once, after the main area, so the PDF holds the turn that just ran."""
    source = APP.read_text(encoding="utf-8")
    assert source.count("download_slot.container()") == 1
    assert "    _main_area()\nwith download_slot.container():" in source


def test_the_pdf_is_built_only_on_click_and_never_written():
    """data= is a function (built on click) and the app writes no file for the PDF."""
    source = APP.read_text(encoding="utf-8")
    body = source.split("def _summary_download", 1)[1].split("\ndef ", 1)[0]
    assert "data=build," in body
    assert 'on_click="ignore"' in body
    for writes in ("open(", ".write_bytes", ".write_text", "tempfile"):
        assert writes not in body


def test_the_pdf_built_on_click_holds_the_turn_that_just_ran(monkeypatch):
    """The button's build function gives a PDF with the profile and the question just asked."""
    built = []
    real_button = st.download_button

    def recording_button(*args, **kwargs):
        """Record the data function the app passes, then draw the real button."""
        built.append(kwargs["data"])
        return real_button(*args, **kwargs)

    monkeypatch.setattr(st, "download_button", recording_button)
    at = _start(PROFILE)
    at.chat_input(key="chat_input").set_value("How much protein per meal?").run(timeout=30)
    assert not at.exception
    text = pdf_text(built[-1]())
    assert "Question 1 How much protein per meal? Answer Four meals [S1]." in text
    assert "Weight 80 kg" in text
    assert config.DISCLAIMER in text


# What would let the app open an image (docs/SECURITY.md: Pillow's advisories need an untrusted
# image, so an image path needs a review). Any call or attribute with these names, on st or on
# any container ("st.sidebar.image", "col.image"), counts.
IMAGE_ATTRIBUTES = frozenset(
    {"image", "logo", "pyplot", "file_uploader", "camera_input", "drawImage", "drawInlineImage"}
)
# reportlab names that open an image file through Pillow.
REPORTLAB_IMAGE_NAMES = frozenset({"Image", "ImageReader", "ImageAndFlowables"})


def _image_inputs(source: str) -> list[str]:
    """Return the image inputs in Python source: widgets, Pillow, reportlab images, <img> tags."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in IMAGE_ATTRIBUTES:
            found.append(f"line {node.lineno}: .{node.attr}")
        elif isinstance(node, ast.Import):
            found += [f"line {node.lineno}: import {a.name}" for a in node.names if _pillow(a.name)]
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names = {alias.name for alias in node.names}
            if _pillow(node.module) or (
                node.module.startswith("reportlab") and names & REPORTLAB_IMAGE_NAMES
            ):
                found.append(f"line {node.lineno}: from {node.module} import {sorted(names)}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "<img" in node.value.lower():
                found.append(f"line {node.lineno}: <img in a string")
    return found


def _pillow(module: str) -> bool:
    """Return True for Pillow's package or one of its modules."""
    return module == "PIL" or module.startswith("PIL.")


@pytest.mark.parametrize(
    "code",
    [
        "st.image(x)",
        "st.sidebar.image(x)",
        "col.image(x)",
        "st.logo(x)",
        "st.pyplot(fig)",
        "st.file_uploader('a')",
        "st.camera_input('a')",
        "import PIL",
        "from PIL import Image",
        "import PIL.Image as I",
        "from reportlab.platypus import (\n    Paragraph,\n    Image,\n)",
        "from reportlab.lib.utils import ImageReader",
        "canvas.drawImage(path, 0, 0)",
        "Paragraph('<img src=\"a.png\"/>')",
    ],
)
def test_the_image_scan_finds_every_way_to_open_an_image(code):
    """The scan flags image widgets on any container, Pillow, reportlab images and <img>."""
    assert _image_inputs(code)


@pytest.mark.parametrize(
    "code",
    ["st.markdown(x)", "from reportlab.platypus import Paragraph, Table", "remove_images(text)"],
)
def test_the_image_scan_ignores_other_code(code):
    """Text, tables and the answer's image remover are not image inputs."""
    assert _image_inputs(code) == []


def test_the_app_opens_no_image_file():
    """No image input in app.py or src/, so no untrusted image reaches Pillow unreviewed."""
    root = APP.parent
    files = [APP, *sorted((root / "src").rglob("*.py"))]
    found = {
        str(path.relative_to(root)): _image_inputs(path.read_text(encoding="utf-8"))
        for path in files
    }
    assert {path: hits for path, hits in found.items() if hits} == {}
