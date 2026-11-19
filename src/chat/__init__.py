"""One chat turn: guard -> the agent and its tools (a knowledge base search among them) -> answer.

`run_turn()` runs the turn as the LangGraph graph in `src/agent/graph.py` (T9.2), whose nodes use
this package's helpers, and turns its errors into fixed messages. The user's question goes only
inside <user_input> in the user message; the chunks a search finds come back only inside <sources>
in that search's tool message (T9.3, `src/agent/search.py`); neither is ever put into the system
prompt (.claude/rules/security-privacy.md). Both are escaped first (`src/prompt_data.py`), so no
text can close or open a block (T3.4). The profile is never in the messages: the tools read it from
the app (T9.3). The rewrites from query translation are used only for the search and shown in the
app. Tool results reach the model only as tool messages (T4.4). Every error a user can cause or meet
ends as a TurnResult with a fixed message, so the app shows it in the answer and keeps the chat
history (AC-13). The answer's language is the app's language control (en or de), passed in as a
fixed value: the code joins that language's part of the owner's prompt to the end of the system
prompt, and nothing the user types picks it (T7.2).

The modules, by concern (T10.10): `results` (the turn's types and errors), `prompts` (the answer
prompt and its version), `retrieval` (`find_chunks()` and its filters), `citations` (the sources
block, the [S#] labels, the source cards, the manifest), `markdown` (escaping, images removed, the
paced writer), `messages` (the model's messages, the history, the fixed texts), `answer`
(`stream_reply()`, `answer_with_tools()`) and `turn` (`run_turn()` and its log lines). Every public
name is re-exported here, so callers keep `chat.X`. A test patches a name where it is read: on the
package for `run_turn`, `manifest_by_id` and `load_system_prompt`, which callers read as `chat.X`;
on the module that uses it for a name a module of the package reads directly (e.g.
`chat.retrieval.embed_queries`), as `tests/test_chat_package.py` checks.
"""

from src.chat.answer import *  # noqa: F403
from src.chat.citations import *  # noqa: F403
from src.chat.markdown import *  # noqa: F403
from src.chat.messages import *  # noqa: F403
from src.chat.prompts import *  # noqa: F403
from src.chat.results import *  # noqa: F403
from src.chat.retrieval import *  # noqa: F403
from src.chat.turn import *  # noqa: F403
