"""The pages each kind of user may open, with st.navigation (T9.5, D20).

Only the pages listed for the user's role are registered in a run, so a page of another role (or a
signed-in user's page for a guest) cannot be opened even by its URL: Streamlit shows the role's
home instead. A new session sees only the start page (sign in, or in demo mode a made-up user; no
guest) when sign-in is set up or in demo mode. A guest (a copy with no [auth]) has one page, the
chat with today's tabs, so no menu shows. A user signed in with Google who has no account yet
("pending") sees only the welcome page. A coach has the chat and My data; a gymer My profile, Today
(the food and weight diary, T9.13), Workouts (T9.14) and My data, no chat (owner's choice).
"""

import streamlit as st

from views import account, my_data, pages, today, workouts
from views.text import t

CHAT = "chat"
PROFILE = pages.PROFILE_URL_PATH
TODAY = today.URL_PATH
MY_DATA = my_data.URL_PATH
WORKOUTS = workouts.URL_PATH
WELCOME = "welcome"
START = "start"
PENDING = "pending"
# The first page of each list is the role's home (AC-18). Later tickets add their pages here.
PAGES_BY_ROLE: dict[str | None, tuple[str, ...]] = {
    None: (CHAT,),
    START: (START,),
    PENDING: (WELCOME,),
    "coach": (CHAT, MY_DATA),
    # No chat for a gymer (owner's choice, 2026-11-02): the profile, the diary (T9.13; the
    # profile stays the home, owner's choice, 2026-11-03), the workouts (T9.14) and their data.
    "gymer": (PROFILE, TODAY, WORKOUTS, MY_DATA),
}
_PAGES = {
    CHAT: (pages.chat_page, "page.chat", ":material/chat:"),
    PROFILE: (pages.profile_page, "page.profile", ":material/person:"),
    TODAY: (today.page, "page.today", ":material/restaurant:"),
    WORKOUTS: (workouts.page, "page.workouts", ":material/fitness_center:"),
    MY_DATA: (my_data.page, "page.my_data", ":material/folder_shared:"),
    WELCOME: (account.welcome_page, "page.welcome", ":material/waving_hand:"),
    START: (account.start_page, "page.start", ":material/login:"),
}


def role_key(user: dict | None) -> str | None:
    """Return the key of PAGES_BY_ROLE for the session's user (None for a guest)."""
    if account.needs_start(user):
        return START
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
