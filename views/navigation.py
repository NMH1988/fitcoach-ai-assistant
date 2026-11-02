"""The pages each kind of user may open, with st.navigation (T9.5, D20).

Only the pages listed for the user's role are registered in a run, so a page of another role (or a
signed-in user's page for a guest) cannot be opened even by its URL: Streamlit shows the role's
home instead. A guest has one page, the chat with today's tabs, so no menu shows. A user signed in
with Google who has no account yet ("pending") sees only the welcome page that creates it.
"""

import streamlit as st

from views import account, my_data, pages
from views.text import t

CHAT = "chat"
MY_DATA = my_data.URL_PATH
WELCOME = "welcome"
PENDING = "pending"
# The first page of each list is the role's home (AC-18). Later tickets add their pages here.
PAGES_BY_ROLE: dict[str | None, tuple[str, ...]] = {
    None: (CHAT,),
    PENDING: (WELCOME,),
    "coach": (CHAT, MY_DATA),
    "gymer": (CHAT, MY_DATA),
}
_PAGES = {
    CHAT: (pages.chat_page, "page.chat", ":material/chat:"),
    MY_DATA: (my_data.page, "page.my_data", ":material/folder_shared:"),
    WELCOME: (account.welcome_page, "page.welcome", ":material/waving_hand:"),
}


def role_key(user: dict | None) -> str | None:
    """Return the key of PAGES_BY_ROLE for the session's user (None for a guest)."""
    return None if user is None else user["role"]


def pages_for(user: dict | None) -> list[st.Page]:
    """Return the st.Page objects of the user's role, its home first and default."""
    found = []
    for index, url_path in enumerate(PAGES_BY_ROLE[role_key(user)]):
        page, title, icon = _PAGES[url_path]
        found.append(
            st.Page(page, title=t(title), icon=icon, url_path=url_path, default=index == 0)
        )
    return found
