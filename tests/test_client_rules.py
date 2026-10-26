"""The model client rules in code: no call-time model, token cap or URL, no changed clients (T9.2).

`.claude/rules/security-privacy.md` ("Model clients"): call-time arguments override a client's
settings and would get around the model allowlist and the `max_tokens` cap that
`build_chat_model()` checks, and so would changing a built client. This scan reads the app's
source (`src/`, `views/`, `app.py`, `scripts/`) with `ast` and fails on any such call.

What it cannot see: a method reached at run time (`getattr(model, "bind")(...)`), a method kept
in a variable and called later, a client class reached through a module alias, and
`setattr(client, ...)`. Review still checks those. It is strict the other way: assigning
`.model`, `.base_url` or another setting's name on any object is refused, even on an object that
is not a model client; rename such a field.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCANNED = [ROOT / "src", ROOT / "views", ROOT / "scripts", ROOT / "app.py"]
# The one module that builds clients (build_chat_model(), build_embeddings()).
CLIENT_MODULE = ROOT / "src" / "llm.py"

# Methods whose keyword arguments reach the model request or the client's settings.
CALL_TIME_METHODS = {
    "bind",
    "bind_tools",
    "invoke",
    "ainvoke",
    "stream",
    "astream",
    "batch",
    "abatch",
    "batch_as_completed",
    "abatch_as_completed",
    "generate",
    "agenerate",
    "astream_events",
    "astream_log",
    "transform",
    "atransform",
    "with_structured_output",
}
# Settings a call must never set: they pick the model, its budget or where the request goes.
CLIENT_SETTINGS = {
    "model",
    "model_name",
    "max_tokens",
    "max_completion_tokens",
    "base_url",
    "openai_api_base",
    "reasoning_effort",
}
# Keyword arguments that pass anything straight into the request body.
PASS_THROUGH = {"model_kwargs", "extra_body"}
# Methods that make a changed copy of a client or let a caller swap its settings.
RECONFIGURING = {"configurable_fields", "configurable_alternatives"}
# Pydantic's copies that take new field values (`copy` is v1's, still in v2).
COPYING = {"model_copy", "copy"}
# Building a client anywhere but src/llm.py skips the allowlist and the cap.
CLIENT_CLASSES = {
    "ChatOpenAI",
    "OpenAIEmbeddings",
    "CountingEmbeddings",
    "init_chat_model",
    "init_embeddings",
    # The OpenAI SDK itself.
    "OpenAI",
    "AsyncOpenAI",
}
# Agent builders that build their own client when given a model name as text.
AGENT_BUILDERS = {"create_agent", "create_react_agent"}


def _called_name(call: ast.Call) -> str | None:
    """Return the name a call is made through: `f` for f(...) and x.f(...), else None."""
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _client_names(tree: ast.AST) -> set[str]:
    """Return the names a client class is known by in the module: its own and import aliases."""
    names = set(CLIENT_CLASSES)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname for alias in node.names if alias.name in CLIENT_CLASSES)
    return names - {None}


def _names_a_model(call: ast.Call) -> bool:
    """Return True when an agent builder is given a model name as text (first or model=)."""
    model = call.args[0] if call.args else None
    model = next((k.value for k in call.keywords if k.arg == "model"), model)
    return isinstance(model, ast.Constant) and isinstance(model.value, str)


def violations(source: str, *, builds_clients: bool = False) -> list[str]:
    """Return one line per broken client rule in the source, with its line number."""
    found = []
    tree = ast.parse(source)
    clients = _client_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _called_name(node)
            method = name if isinstance(node.func, ast.Attribute) else None
            for keyword in node.keywords:
                if keyword.arg in PASS_THROUGH:
                    found.append(f"{node.lineno}: {keyword.arg}= passed to {name}()")
                elif method in CALL_TIME_METHODS and keyword.arg in CLIENT_SETTINGS:
                    found.append(f"{node.lineno}: call-time {keyword.arg}= in .{method}()")
                elif method in CALL_TIME_METHODS and keyword.arg is None:
                    # **kwargs could carry any setting, so it is refused too.
                    found.append(f"{node.lineno}: **kwargs in .{method}()")
                elif method in COPYING and keyword.arg == "update":
                    found.append(f"{node.lineno}: {method}(update=...)")
            if method in RECONFIGURING:
                found.append(f"{node.lineno}: .{method}()")
            if name in AGENT_BUILDERS and _names_a_model(node):
                found.append(f"{node.lineno}: {name}() builds its own client from a model name")
            if builds_clients:
                continue
            # A client class called, or one of its class methods (model_construct, model_validate).
            owner = node.func.value if isinstance(node.func, ast.Attribute) else None
            if name in clients or (isinstance(owner, ast.Name) and owner.id in clients):
                found.append(f"{node.lineno}: a client built outside src/llm.py")
        elif isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                # Tuple targets too: `chat.max_tokens, x = 1, 2`.
                for part in ast.walk(target):
                    if isinstance(part, ast.Attribute) and part.attr in CLIENT_SETTINGS:
                        found.append(f"{node.lineno}: assigns .{part.attr} of a built client")
    return found


def _scanned_files() -> list[Path]:
    """Return every Python file of the app the rules apply to."""
    files = []
    for path in SCANNED:
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    return files


def test_the_app_source_keeps_the_client_rules():
    """No file of the app passes a call-time model, cap or URL, or changes a built client."""
    problems = []
    for path in _scanned_files():
        source = path.read_text(encoding="utf-8")
        for line in violations(source, builds_clients=path == CLIENT_MODULE):
            problems.append(f"{path.relative_to(ROOT).as_posix()}:{line}")
    assert problems == []


def test_the_scan_reads_the_files_that_use_the_clients():
    """The scan covers the modules that bind tools and ask for structured output."""
    names = {path.relative_to(ROOT).as_posix() for path in _scanned_files()}
    assert {"src/chat.py", "src/llm.py", "src/rag/query_translation.py", "app.py"} <= names
    assert any(name.startswith("views/") for name in names)
    assert any(name.startswith("scripts/") for name in names)


CAUGHT = [
    "model.bind(model='openai/gpt-5')",
    "model.bind(max_tokens=100000)",
    "model.bind(max_completion_tokens=100000)",
    "model.bind(base_url='https://example.com')",
    "model.bind(reasoning_effort='high')",
    "model.bind_tools(tools, model='openai/gpt-5')",
    "model.bind_tools(tools, max_tokens=5)",
    "model.bind_tools(tools, **settings)",
    "model.invoke(messages, max_tokens=100000)",
    "model.invoke(messages, model='openai/gpt-5')",
    "model.stream(messages, max_completion_tokens=100000)",
    "model.batch([messages], reasoning_effort='high')",
    "model.with_structured_output(Plan, model_name='openai/gpt-5')",
    "ChatOpenAI(model='openai/gpt-5', model_kwargs={'max_tokens': 1})",
    "model.invoke(messages, extra_body={'max_tokens': 100000})",
    "model.bind(extra_body={'model': 'x'})",
    "model.model_copy(update={'max_tokens': 100000})",
    "model.configurable_fields(max_tokens=field)",
    "model.configurable_alternatives(which, gpt5=other)",
    "chat.max_tokens = 100000",
    "chat.model_name = 'openai/gpt-5'",
    "chat.max_tokens += 1",
    "ChatOpenAI(model='openai/gpt-5')",
    "langchain_openai.ChatOpenAI(model='openai/gpt-5')",
    "OpenAIEmbeddings(model='other')",
    "init_chat_model('openai:gpt-5')",
    "from langchain_openai import ChatOpenAI as Chat\nChat(model='openai/gpt-5')",
    "ChatOpenAI.model_construct(model='openai/gpt-5')",
    "ChatOpenAI.model_validate({'model': 'openai/gpt-5'})",
    "openai.OpenAI(api_key=key)",
    "AsyncOpenAI(base_url='https://example.com')",
    "create_agent('openai:gpt-5', tools)",
    "create_react_agent(model='openai:gpt-5', tools=tools)",
    "model.generate([messages], max_tokens=100000)",
    "model.astream_events(messages, model='openai/gpt-5')",
    "model.batch_as_completed([messages], **settings)",
    "model.copy(update={'max_tokens': 100000})",
    "chat.max_tokens, other = 100000, 1",
]


@pytest.mark.parametrize("source", CAUGHT)
def test_a_broken_rule_is_caught(source):
    """Each call-time setting, pass-through, reconfiguration or stray client is reported."""
    assert violations(source)


ALLOWED = [
    "model.bind_tools(tools)",
    "model.bind_tools(list(tools.values()), tool_choice='none' if last else None)",
    "model.with_structured_output(QueryPlan, method='json_schema', include_raw=True)",
    "model.stream(messages)",
    "graph.invoke({'text': text}, context=context, config={'recursion_limit': 20})",
    "build_chat_model(config.DEFAULT_ANSWER_MODEL, max_tokens=500)",
    "plan.model_copy()",
    "usage.price(model='openai/gpt-5-mini')",
    "record = {'model': name, 'max_tokens': 5}",
    "def f(chat_model: ChatOpenAI) -> ChatOpenAI: return chat_model",
    "create_agent(build_chat_model(), tools)",
    "settings.copy()",
]


@pytest.mark.parametrize("source", ALLOWED)
def test_an_allowed_call_passes(source):
    """Binding the tools alone, structured output with no setting, and plain calls pass."""
    assert violations(source) == []


def test_the_client_module_may_build_clients_but_not_bind_settings():
    """src/llm.py builds ChatOpenAI, yet a call-time setting there is still caught."""
    assert violations("ChatOpenAI(model=m, max_tokens=n)", builds_clients=True) == []
    assert violations("client.bind(max_tokens=n)", builds_clients=True)
