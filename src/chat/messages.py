"""The model's messages, the history it sees, and the fixed texts a turn can end with."""

from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages

from src import config, i18n, preferences
from src.chat.citations import strip_citations
from src.chat.results import TurnResult
from src.prompt_data import escape_prompt_data


def user_message(question: str) -> HumanMessage:
    """Return the user message of a question: <user_input> holding the escaped question only."""
    # Plain string content, never a prompt template: braces in the question stay as typed.
    return HumanMessage(f"<user_input>\n{escape_prompt_data(question)}\n</user_input>")


def build_messages(
    question: str,
    system_prompt: str,
    history: Sequence[BaseMessage] = (),
    memories: Sequence[str] = (),
) -> list[BaseMessage]:
    """Return the system prompt, the conversation's earlier messages, then the question."""
    # The chunks come only in a search's tool message (T9.3); the profile is never sent: the tools
    # read it from the app (T9.3). history: the earlier questions and answers the model may see
    # (T9.4, trim_history()). memories: a coach's saved preferences (T9.7), inside <memories> before
    # the question in the user message, never in the system prompt; the conversation keeps the
    # question alone (exchange_messages()).
    question_message = user_message(question)
    if memories:
        block = preferences.memories_block(memories)
        question_message = HumanMessage(f"{block}\n{question_message.text}")
    return [SystemMessage(system_prompt), *history, question_message]


def exchange_messages(question: str, answer: str) -> list[BaseMessage]:
    """Return what the conversation keeps of an answered turn: the question and the answer."""
    # The same <user_input> the model got, and the shown answer without its citations; never the
    # turn's tool calls, tool results or <sources> (T9.4).
    return [user_message(question), AIMessage(strip_citations(answer))]


def trim_history(history: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Return the latest earlier messages that fit HISTORY_MAX_TOKENS, starting on a question."""
    # Counted approximately (about four characters a token), with no network call. What the
    # conversation stores is capped apart, by HISTORY_MAX_MESSAGES (src/agent/memory.py).
    return trim_messages(
        list(history),
        max_tokens=config.HISTORY_MAX_TOKENS,
        token_counter=count_tokens_approximately,
        strategy="last",
        start_on="human",
    )


def fixed_text(result: TurnResult, lang: i18n.Language) -> str:
    """Return a turn's fixed message in the language, or the model's own answer as written."""
    # Shared by the chat and the summary PDF (T7.2), so the two cannot word a message differently.
    # An unknown key falls back to the English text rather than breaking every later run.
    if result.code is not None and result.code in i18n.TEXT[lang]:
        if result.kind == "memory":
            return memory_text(result.code, lang)
        return i18n.t(result.code, lang, **result.params)
    return result.text


def memory_text(code: str, lang: i18n.Language) -> str:
    """Return a coach's memory line with the reminder to ask anything else again on its own."""
    # The turn had no basis, so a question asked beside the preference went unanswered (T9.7). The
    # card reuses the line without the reminder.
    return f"{i18n.t(code, lang)} {i18n.t('memory.ask_again', lang)}"
