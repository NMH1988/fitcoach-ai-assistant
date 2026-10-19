"""Live check O5 for T1.2: one real chat call and one real embedding call through OpenRouter.

Run by the owner from the repo root, with the key set up as in the README:

    python scripts/live_check_llm.py

It costs a fraction of a cent and never prints the key. Record the output in docs/TESTING.md.
"""

import sys

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from src import config, llm

CHAT_PROMPT = "In one short sentence, what is dietary protein?"
EMBEDDING_TEXT = "protein intake for muscle gain"


class LiveCheckError(RuntimeError):
    """A call succeeded but returned nothing usable."""


def run_checks(chat_model: ChatOpenAI, embeddings: OpenAIEmbeddings) -> list[str]:
    """Make one chat call and one embedding call and return one result line for each."""
    with llm.mapped_errors():
        reply = chat_model.invoke(CHAT_PROMPT)
        vector = embeddings.embed_query(EMBEDDING_TEXT)
    if not reply.text.strip():
        raise LiveCheckError("The chat model returned an empty reply (token budget used up?).")
    if not vector:
        raise LiveCheckError("The embedding call returned an empty vector.")
    usage = reply.usage_metadata or {}
    # Evidence that OpenRouter honours the token cap (sent as max_completion_tokens).
    if usage.get("output_tokens", 0) > chat_model.max_tokens:
        raise LiveCheckError("The reply used more tokens than max_tokens allows.")
    reasoning = usage.get("output_token_details", {}).get("reasoning", "n/a")
    return [
        f"chat: {chat_model.model_name} ok, {len(reply.text)} characters, "
        f"tokens in {usage.get('input_tokens', 'n/a')} / out {usage.get('output_tokens', 'n/a')} "
        f"(reasoning {reasoning})",
        f"embedding: {embeddings.model} ok, {len(vector)} dimensions",
    ]


def main() -> int:
    """Run the live check, print the results or the mapped error, and return the exit code."""
    try:
        lines = run_checks(llm.build_chat_model(), llm.build_embeddings())
    except (config.MissingAPIKeyError, llm.LLMError, LiveCheckError) as exc:
        print(f"Live check failed: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
