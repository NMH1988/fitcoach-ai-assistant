"""Tests for scripts/run_evaluation.py (T6.1) with fake models and a fixture index; no network.

The real run is the owner's live check (O5), recorded in docs/TESTING.md.
"""

import json
from decimal import Decimal

import httpx2
import openai
import pytest
from langchain_core.messages import AIMessage

from scripts import run_evaluation
from src import chat, config, llm, usage
from src.eval_questions import EvalItem
from src.rag import store
from src.tools.registry import MACRO_TOOL
from src.usage import ModelPrice
from tests.fakes import (
    CHUNKS,
    PROFILE,
    TEST_LANGUAGE_PARTS,
    ScriptedChatModel,
    ScriptedTranslator,
    build_fixture_index,
    chunk,
    open_fixture_index,
    plan_json,
    tool_reply,
)

# An obvious fake key (.claude/rules/testing.md).
FAKE_KEY = "sk-test-not-a-real-key"
# Text written for these tests (the guardrail question is the owner's q15).
QUESTION = "How much protein per meal?"
OFF_TOPIC = "What is the offside rule in football?"
TARGETS = "What are my daily calorie, protein, carbohydrate, and fat targets?"
STEROIDS = "What steroid dose should I use to gain muscle as fast as possible?"
ANSWER = "Spread it over four meals [S1]."
# As in tests/test_compare_retrieval.py: the fake embeddings put the HMB chunk far from an HMB
# question, so only keyword search finds it.
NOTES = [chunk("8", n, f"Note {n}: training volume and rest days.") for n in range(7)]
HMB = chunk("9", 0, "HMB: beta-hydroxy-beta-methylbutyrate taken with creatine creatine.")


def _item(id: str, question: str, expected=(), profile=None) -> EvalItem:
    """Return an evaluation question with a made-up good answer."""
    return EvalItem(
        id=id,
        question=question,
        expected_sources=list(expected),
        good_answer=f"A made-up good answer for {id}.",
        profile=profile,
    )


@pytest.fixture(autouse=True)
def test_prompts(tmp_path, monkeypatch):
    """Use test prompts, so no test depends on the owner's text."""
    for name in ("ANSWER_PROMPT_PATH", "QUERY_TRANSLATION_PROMPT_PATH"):
        path = tmp_path / f"{name}.md"
        path.write_text("Test prompt.", encoding="utf-8")
        monkeypatch.setattr(config, name, path)


@pytest.fixture(scope="module")
def index_path(tmp_path_factory):
    """Build the fixture index once for the module and return its directory."""
    return build_fixture_index(tmp_path_factory.mktemp("index") / "chroma")


@pytest.fixture
def index(index_path):
    """Open the fixture index with the keyword embeddings."""
    return open_fixture_index(index_path)


def _evaluate(items, index, model, translator=None, prices=None, repeat=1):
    """Run the evaluation on the fixture index with these fake models."""
    return run_evaluation.evaluate(
        items,
        index=index,
        chat_model=model,
        translation_model=translator or ScriptedTranslator(),
        manifest=chat.manifest_by_id(),
        prices=prices,
        repeat=repeat,
    )


def test_a_profile_question_runs_with_its_profile_then_without():
    """q13-like questions run twice; --repeat numbers every run; others run once with none."""
    items = [_item("q1", QUESTION), _item("q13", TARGETS, profile=PROFILE)]
    assert [
        (label, with_profile) for label, _, with_profile in run_evaluation.planned_runs(items, 1)
    ] == [
        ("q1", False),
        ("q13", True),
        ("q13 (no profile)", False),
    ]
    labels = [label for label, _, _ in run_evaluation.planned_runs(items[:1], 2)]
    assert labels == ["q1 run 1", "q1 run 2"]


def test_a_run_reports_the_sources_found_cited_and_expected(index):
    """The summary lists the chunks found in [S#] order, the cited ones and the expected ones."""
    [run] = _evaluate(
        [_item("q1", QUESTION, expected=["1", "3"])],
        index,
        ScriptedChatModel(replies=[AIMessage(ANSWER)]),
    )
    assert [c.text for c in run.chunks] == [c.page_content for c in CHUNKS[:3]]
    lines = run_evaluation.summary_lines([run])
    assert lines[0].startswith("q1: answer · ")
    assert "  found: #1 #1 #2" in lines
    assert "  cited: #1 (S1)" in lines
    assert "  tools: none" in lines
    assert "  expected #1 #3: found #1, cited #1" in lines
    assert "  plan: needs_tool yes, needs_profile yes; filters: none; profile sent: yes" in lines


def test_with_no_expected_source_the_summary_says_whether_anything_is_cited(index):
    """An off-topic question cites nothing; a cited source is flagged for checking."""
    off_topic = ScriptedTranslator(plans=[plan_json([OFF_TOPIC], needs_tool=False)])
    [skipped] = _evaluate([_item("q11", OFF_TOPIC)], index, ScriptedChatModel(), off_topic)
    assert skipped.result.kind == "no_sources"
    assert skipped.chunks == ()
    lines = run_evaluation.summary_lines([skipped])
    assert lines[0].startswith(f"q11: no_sources - {config.NO_SOURCES_MESSAGE} · ")
    assert "  found: nothing" in lines
    assert "  expected none: cites nothing" in lines
    [cited] = _evaluate(
        [_item("q12", QUESTION)], index, ScriptedChatModel(replies=[AIMessage(ANSWER)])
    )
    assert "  expected none: cites #1: check them" in run_evaluation.summary_lines([cited])


def test_chunks_found_by_keyword_only_are_marked(tmp_path):
    """A chunk with no vector distance is marked '*' in the summary and the report."""
    index = open_fixture_index(build_fixture_index(tmp_path / "chroma", [*CHUNKS, *NOTES, HMB]))
    model = ScriptedChatModel(replies=[AIMessage("HMB [S2].")])
    question = "How much HMB per day?"
    translator = ScriptedTranslator(plans=[plan_json([question])])
    [run] = _evaluate([_item("q9", question, expected=["9"])], index, model, translator)
    lines = run_evaluation.summary_lines([run])
    assert "  found: #8 #9* #8 #8 #8 #8" in lines
    assert "  expected #9: found #9, cited #9" in lines
    assert (
        "**S2** #9 Made-up article 9 (2029) · Results · keyword only"
        in run_evaluation.report_text([run], run_evaluation.datetime(2026, 10, 21))
    )


def test_the_profile_reaches_the_tools_only_in_the_profile_run(index):
    """With its profile the targets tool gives values; without, it asks for the user's details."""
    model = ScriptedChatModel(
        replies=[
            tool_reply((MACRO_TOOL, {})),
            AIMessage("Your targets are in Tool results."),
            tool_reply((MACRO_TOOL, {})),
            AIMessage("Add your details first."),
        ]
    )
    with_profile, without = _evaluate([_item("q13", TARGETS, profile=PROFILE)], index, model)
    assert (with_profile.label, with_profile.with_profile) == ("q13", True)
    assert [run.status for run in with_profile.result.tool_runs] == ["ok"]
    assert with_profile.result.tool_runs[0].result.targets.kcal_target == 3035
    assert (without.label, without.with_profile) == ("q13 (no profile)", False)
    assert [run.status for run in without.result.tool_runs] == ["profile_needed"]
    assert f"  tools: {MACRO_TOOL} (ok)" in run_evaluation.summary_lines([with_profile])
    assert f"  tools: {MACRO_TOOL} (profile_needed)" in run_evaluation.summary_lines([without])


def test_a_guardrail_question_is_reported_with_its_message_and_calls_no_model(index):
    """The owner's steroid question stops at the guardrail, as in the app, and costs nothing."""
    model, translator = ScriptedChatModel(), ScriptedTranslator()
    [run] = _evaluate([_item("q15", STEROIDS)], index, model, translator)
    assert run.result.kind == "guardrail"
    assert model.calls == [] and translator.calls == []
    assert run.chunks == ()
    [line, total] = run_evaluation.summary_lines([run])
    assert line.startswith(f"q15: guardrail - {run.result.text} · 0 tokens")
    assert total.startswith("1 runs, 0 ended with an error · 0 tokens")


def test_each_run_shows_its_tokens_and_cost_and_the_total(index):
    """Tokens and cost come from the turn's calls, priced with the prices read once."""
    calls = {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}
    model = ScriptedChatModel(replies=[AIMessage(ANSWER, usage_metadata=calls)] * 2)
    translator = ScriptedTranslator(
        usage={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}
    )
    price = ModelPrice(prompt=Decimal("0.000001"), completion=Decimal("0.000002"))
    prices = {config.DEFAULT_ANSWER_MODEL: price, config.QUERY_TRANSLATION_MODEL: price}
    runs = _evaluate([_item("q1", QUESTION)], index, model, translator, prices, repeat=2)
    lines = run_evaluation.summary_lines(runs)
    # 1,100 answer + 110 rewrite tokens: $0.0012 + $0.00012 per run.
    assert lines[0] == "q1 run 1: answer · 1,210 tokens · $0.0013"
    assert lines[-1] == "2 runs, 0 ended with an error · 2,420 tokens · $0.0026"


@pytest.fixture
def real_pieces(index, tmp_path, monkeypatch):
    """Make main() open the fixture index, build fake models, read no prices and write to tmp."""
    calls = {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}
    model = ScriptedChatModel(replies=[AIMessage(ANSWER, usage_metadata=calls)])
    translator = ScriptedTranslator()
    monkeypatch.setattr(store, "open_index", lambda: index)
    monkeypatch.setattr(
        llm,
        "build_chat_model",
        lambda name=config.DEFAULT_ANSWER_MODEL, *_: (
            translator if name == config.QUERY_TRANSLATION_MODEL else model
        ),
    )

    def no_prices():
        """Fail as an unreadable price list does."""
        raise usage.PriceError("price list not read")

    monkeypatch.setattr(usage, "fetch_prices", no_prices)
    monkeypatch.setattr(config, "EVAL_RUNS_DIR", tmp_path / "eval_runs")
    return model


def _questions_file(tmp_path, items) -> str:
    """Write the questions to a JSON file and return its path."""
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(items), encoding="utf-8")
    return str(path)


def test_main_prints_the_summary_and_writes_the_full_report(real_pieces, tmp_path, capsys):
    """The report holds the question, good answer, answer and every chunk's text; exit code 0."""
    item = {
        "id": "q1",
        "question": QUESTION,
        "expected_sources": ["1"],
        "good_answer": "Says to spread protein over the day.",
    }
    assert run_evaluation.main([_questions_file(tmp_path, [item])]) == 0
    out = capsys.readouterr().out
    # The prices could not be read, so the cost is unknown, not $0.
    assert f"q1: answer · 1,100 tokens · {config.PRICE_UNKNOWN_LABEL}" in out
    assert "  expected #1: found #1, cited #1" in out
    [report] = (tmp_path / "eval_runs").glob("run-*.md")
    assert f"Full report: {report}" in out
    text = report.read_text(encoding="utf-8")
    for part in (QUESTION, item["good_answer"], ANSWER, "**Session profile:** none"):
        assert part in text
    for found in CHUNKS[:3]:
        assert found.page_content in text
    assert "**S1** #1 Made-up article 1 (2021) · Results · distance " in text


def test_main_stops_before_any_question_without_a_key(real_pieces, tmp_path, monkeypatch, capsys):
    """A missing key stops the run with the app's message, before any call or report."""

    def no_key(*_args):
        """Fail as building a client with no key does."""
        raise config.MissingAPIKeyError

    monkeypatch.setattr(llm, "build_chat_model", no_key)
    path = _questions_file(
        tmp_path, [{"id": "q1", "question": QUESTION, "expected_sources": [], "good_answer": "x"}]
    )
    assert run_evaluation.main([path]) == 1
    assert config.MISSING_KEY_MESSAGE in capsys.readouterr().err
    assert real_pieces.calls == []
    assert not (tmp_path / "eval_runs").exists()


def test_a_turn_that_ends_in_an_error_still_writes_the_report_and_exits_1(
    real_pieces, tmp_path, capsys
):
    """A model error is recorded as the app shows it; the exit code tells the owner."""
    real_pieces.error = llm.LLMError(diagnostic="test")
    item = {"id": "q1", "question": QUESTION, "expected_sources": [], "good_answer": "x"}
    assert run_evaluation.main([_questions_file(tmp_path, [item])]) == 1
    out = capsys.readouterr().out
    assert f"q1: error - {llm.LLMError.user_message}" in out
    assert "1 runs, 1 ended with an error" in out
    assert list((tmp_path / "eval_runs").glob("run-*.md"))


def test_a_key_echoed_in_a_provider_error_is_never_printed_or_written(
    real_pieces, tmp_path, monkeypatch, capsys
):
    """A provider error that repeats the key shows only the fixed message, never the key."""
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    request = httpx2.Request("POST", f"{config.OPENROUTER_BASE_URL}/chat/completions")
    response = httpx2.Response(429, request=request)
    real_pieces.error = openai.RateLimitError(f"echo {FAKE_KEY}", response=response, body=None)
    item = {"id": "q1", "question": QUESTION, "expected_sources": [], "good_answer": "x"}
    assert run_evaluation.main([_questions_file(tmp_path, [item])]) == 1
    out, err = capsys.readouterr()
    [report] = (tmp_path / "eval_runs").glob("run-*.md")
    assert "q1: error - " in out
    for text in (out, err, report.read_text(encoding="utf-8")):
        assert FAKE_KEY not in text


@pytest.mark.parametrize(
    "args",
    [["--repeat", "0"], ["missing-file.json"]],
    ids=["repeat below 1", "no questions file"],
)
def test_main_refuses_bad_arguments(real_pieces, tmp_path, monkeypatch, capsys, args):
    """A repeat below 1 or a missing file gives exit code 2 and asks no question."""
    monkeypatch.chdir(tmp_path)
    assert run_evaluation.main(args) == 2
    assert capsys.readouterr().err
    assert real_pieces.calls == []


@pytest.mark.parametrize("language", ["en", "de"])
def test_each_run_asks_in_the_answer_language_given(index, language):
    """The language reaches the app's turn as the EN | DE control would set it (T7.2)."""
    model = ScriptedChatModel(replies=[AIMessage(ANSWER)])
    run_evaluation.evaluate(
        [_item("de1", "Wie viel Protein pro Mahlzeit?")],
        index=index,
        chat_model=model,
        translation_model=ScriptedTranslator(),
        manifest=chat.manifest_by_id(),
        prices=None,
        language=language,
    )
    [[system, _]] = model.calls
    assert system.content.endswith(TEST_LANGUAGE_PARTS[language])


@pytest.mark.parametrize(("args", "language"), [([], "en"), (["--language", "de"], "de")])
def test_main_runs_in_the_language_asked_and_says_so(real_pieces, tmp_path, capsys, args, language):
    """English by default, German with --language de; the summary and the report name it."""
    item = {"id": "de1", "question": QUESTION, "expected_sources": [], "good_answer": "x"}
    assert run_evaluation.main([*args, _questions_file(tmp_path, [item])]) == 0
    [[system, _]] = real_pieces.calls
    assert system.content.endswith(TEST_LANGUAGE_PARTS[language])
    assert f"Answer language: {language}" in capsys.readouterr().out
    [report] = (tmp_path / "eval_runs").glob("run-*.md")
    assert f"**Answer language:** {language}" in report.read_text(encoding="utf-8")


def test_main_refuses_a_language_the_app_does_not_offer(real_pieces, tmp_path, capsys):
    """--language fr stops before any question, with argparse's usage error (exit code 2)."""
    item = {"id": "q1", "question": QUESTION, "expected_sources": [], "good_answer": "x"}
    with pytest.raises(SystemExit) as stopped:
        run_evaluation.main(["--language", "fr", _questions_file(tmp_path, [item])])
    assert stopped.value.code == 2
    assert "--language" in capsys.readouterr().err
    assert real_pieces.calls == []


def test_a_good_answer_is_required(tmp_path, capsys, real_pieces):
    """A question without a good answer cannot be judged, so the file is refused."""
    path = _questions_file(tmp_path, [{"id": "q1", "question": QUESTION, "expected_sources": []}])
    assert run_evaluation.main([path]) == 2
    assert "wrong format" in capsys.readouterr().err


# --- The results file (T8.4) ------------------------------------------------------------


def _records(items, index, model, translator=None, repeat=1):
    """Run the evaluation on the fixture index and return the runs' result records."""
    runs = _evaluate(items, index, model, translator, repeat=repeat)
    return run_evaluation.run_records(runs)


def test_a_record_holds_what_was_expected_found_and_cited(index):
    """The record lists the expected sources found among the chunks and cited, and the rest."""
    model = ScriptedChatModel(replies=[AIMessage(ANSWER)])
    [record] = _records([_item("q1", QUESTION, expected=["1", "3"])], index, model)
    assert (record.id, record.run, record.with_profile) == ("q1", 1, False)
    assert (record.kind, record.code) == ("answer", None)
    assert record.expected == ("1", "3")
    assert record.expected_found == ("1",)
    assert record.expected_cited == ("1",)
    assert record.unexpected_citations == ()
    assert record.tools == ()
    # The fake model reported no tokens, so the turn cost nothing (a price is not needed for 0).
    assert (record.tokens, record.cost_usd) == (0, "0")


def test_a_source_cited_that_was_not_expected_is_unexpected(index):
    """Citing #1 when only #3 is expected: nothing expected found or cited, #1 unexpected."""
    model = ScriptedChatModel(replies=[AIMessage(ANSWER)])
    [record] = _records([_item("q1", QUESTION, expected=["3"])], index, model)
    assert record.expected_found == () and record.expected_cited == ()
    assert record.unexpected_citations == ("1",)


def test_with_no_expected_source_every_citation_is_unexpected(index):
    """A question that should cite nothing counts what it cites, as the summary's check says."""
    model = ScriptedChatModel(replies=[AIMessage(ANSWER)])
    [record] = _records([_item("q12", QUESTION)], index, model)
    assert record.expected == () and record.expected_found == ()
    assert record.unexpected_citations == ("1",)


def test_a_turn_that_made_no_search_has_nothing_found_or_cited(index):
    """A guardrail refusal gives its kind and code, and every expected source is missed."""
    [record] = _records(
        [_item("q15", STEROIDS, expected=["1"])], index, ScriptedChatModel(), ScriptedTranslator()
    )
    assert record.kind == "guardrail"
    assert record.code
    assert record.expected_found == () and record.expected_cited == ()
    assert record.tokens == 0


def test_tokens_cost_and_tools_come_from_the_turn(index):
    """Tokens and cost are the turn's totals; each tool is its name and status."""
    calls = {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}
    # The question runs twice, with its profile and without: a tool call and an answer each time.
    model = ScriptedChatModel(
        replies=[tool_reply((MACRO_TOOL, {})), AIMessage(ANSWER, usage_metadata=calls)] * 2
    )
    price = ModelPrice(prompt=Decimal("0.000001"), completion=Decimal("0.000002"))
    prices = {config.DEFAULT_ANSWER_MODEL: price, config.QUERY_TRANSLATION_MODEL: price}
    runs = _evaluate([_item("q13", TARGETS, profile=PROFILE)], index, model, prices=prices)
    with_profile, without = run_evaluation.run_records(runs)
    assert with_profile.tools == ((MACRO_TOOL, "ok"),)
    assert with_profile.with_profile and not without.with_profile
    assert with_profile.cost_usd is not None
    assert Decimal(with_profile.cost_usd) == runs[0].cost.cost


def test_a_tool_the_model_made_up_is_recorded_as_unknown(index):
    """A name that is not a tool never reaches the file: it is written as 'unknown'."""
    made_up = "CANARY_NOT_A_TOOL"
    model = ScriptedChatModel(replies=[tool_reply((made_up, {})), AIMessage(ANSWER)])
    runs = _evaluate([_item("q1", QUESTION, expected=["1"])], index, model)
    assert runs[0].result.tool_runs[0].name is None
    [record] = run_evaluation.run_records(runs)
    assert record.tools == (("unknown", runs[0].result.tool_runs[0].status),)
    assert made_up not in json.dumps(record.as_dict())


def test_repeats_are_numbered_per_question_and_profile_variant(index):
    """--repeat 2 gives each question runs 1 and 2; q13's two variants are numbered apart."""
    model = ScriptedChatModel(replies=[AIMessage(ANSWER)] * 6)
    items = [_item("q1", QUESTION, expected=["1"]), _item("q13", TARGETS, profile=PROFILE)]
    records = _records(items, index, model, repeat=2)
    assert [(r.id, r.with_profile, r.run) for r in records] == [
        ("q1", False, 1),
        ("q1", False, 2),
        ("q13", True, 1),
        ("q13", True, 2),
        ("q13", False, 1),
        ("q13", False, 2),
    ]


def _results_file(tmp_path):
    """Return the one results file the run wrote next to its report, read as JSON."""
    [results] = (tmp_path / "eval_runs").glob("run-*.json")
    return results, json.loads(results.read_text(encoding="utf-8"))


def test_main_writes_the_results_file_next_to_the_report(real_pieces, tmp_path, capsys):
    """The file has the run's details and a record per run, and the output names its path."""
    item = {
        "id": "q1",
        "question": QUESTION,
        "expected_sources": ["1"],
        "good_answer": "Says to spread protein over the day.",
    }
    path = _questions_file(tmp_path, [item])
    real_pieces.replies *= 2
    assert run_evaluation.main(["--repeat", "2", path]) == 0
    results, document = _results_file(tmp_path)
    [report] = (tmp_path / "eval_runs").glob("run-*.md")
    assert results.stem == report.stem
    assert f"Results file: {results}" in capsys.readouterr().out
    assert document["schema_version"] == config.EVAL_RESULTS_SCHEMA_VERSION
    assert (document["language"], document["repeat"]) == ("en", 2)
    assert document["questions_file"] == "questions.json"
    assert document["models"] == {
        "answer": config.DEFAULT_ANSWER_MODEL,
        "query_translation": config.QUERY_TRANSLATION_MODEL,
        "embedding": config.EMBEDDING_MODEL,
    }
    assert [(r["id"], r["run"], r["kind"]) for r in document["runs"]] == [
        ("q1", 1, "answer"),
        ("q1", 2, "answer"),
    ]
    assert document["runs"][0]["expected_found"] == ["1"]
    assert document["runs"][0]["tokens"] == 1100
    # The prices could not be read, so the cost is unknown, not 0.
    assert document["runs"][0]["cost_usd"] is None


def test_the_commit_is_read_from_the_code_that_ran_not_the_working_folder(
    real_pieces, tmp_path, monkeypatch
):
    """The git state is asked for the project folder (where `src` was loaded from)."""
    seen = []

    def fake_state(folder):
        """Record the folder asked about and answer like a clean checkout."""
        seen.append(folder)
        return run_evaluation.eval_results.GitState("e" * 40, False)

    monkeypatch.setattr(run_evaluation.eval_results, "git_state", fake_state)
    monkeypatch.chdir(tmp_path)
    item = {"id": "q1", "question": QUESTION, "expected_sources": [], "good_answer": "x"}
    assert run_evaluation.main([_questions_file(tmp_path, [item])]) == 0
    assert seen == [config.PROJECT_ROOT]
    _, document = _results_file(tmp_path)
    assert (document["commit"], document["dirty"]) == ("e" * 40, False)


def test_the_results_file_holds_no_text_from_the_answer_the_chunks_or_the_key(
    tmp_path, monkeypatch, capsys
):
    """Canary text in the answer, a chunk, the good answer and the key never reaches the file."""
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    canary_chunk = chunk("1", 0, "CANARY-CHUNK protein per meal.")
    index = open_fixture_index(build_fixture_index(tmp_path / "chroma", [canary_chunk]))
    model = ScriptedChatModel(replies=[AIMessage("CANARY-ANSWER [S1].")])
    translator = ScriptedTranslator()
    monkeypatch.setattr(store, "open_index", lambda: index)
    monkeypatch.setattr(
        llm,
        "build_chat_model",
        lambda name=config.DEFAULT_ANSWER_MODEL, *_: (
            translator if name == config.QUERY_TRANSLATION_MODEL else model
        ),
    )
    monkeypatch.setattr(usage, "fetch_prices", lambda: {})
    monkeypatch.setattr(config, "EVAL_RUNS_DIR", tmp_path / "eval_runs")
    item = {
        "id": "q1",
        "question": "CANARY-QUESTION how much protein per meal?",
        "expected_sources": ["1"],
        "good_answer": "CANARY-GOOD-ANSWER",
    }
    assert run_evaluation.main([_questions_file(tmp_path, [item])]) == 0
    capsys.readouterr()
    results, document = _results_file(tmp_path)
    assert document["runs"][0]["expected_cited"] == ["1"]
    text = results.read_text(encoding="utf-8")
    for canary in ("CANARY", FAKE_KEY, "protein per meal"):
        assert canary not in text
    # The report next to it does hold them: the canaries can reach a file, so the check can fail.
    [report] = (tmp_path / "eval_runs").glob("run-*.md")
    assert "CANARY-ANSWER" in report.read_text(encoding="utf-8")


def test_a_turn_that_ends_in_an_error_is_in_the_results_file(real_pieces, tmp_path):
    """An error ending is recorded with its kind and code, and the exit code stays 1."""
    real_pieces.error = llm.LLMError(diagnostic="test")
    item = {"id": "q1", "question": QUESTION, "expected_sources": ["1"], "good_answer": "x"}
    assert run_evaluation.main([_questions_file(tmp_path, [item])]) == 1
    _, document = _results_file(tmp_path)
    [record] = document["runs"]
    assert record["kind"] == "error"
    assert record["code"]
    # The chunks were found before the answer call failed; nothing was cited.
    assert record["expected_found"] == ["1"]
    assert record["expected_cited"] == []
    assert "test" not in json.dumps(record)


def test_the_summary_lines_are_the_same_with_the_data_split_out(index):
    """Printing the expectation still gives the lines the owner already reads."""
    model = ScriptedChatModel(replies=[AIMessage(ANSWER)])
    [run] = _evaluate([_item("q1", QUESTION, expected=["1", "3"])], index, model)
    assert run_evaluation.expectation_line(run) == "expected #1 #3: found #1, cited #1"
