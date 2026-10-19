"""Streamlit entry point: page layout only; the logic lives in src/."""

import streamlit as st

from src import config

st.set_page_config(page_title=config.APP_TITLE, page_icon=":material/fitness_center:")

st.title(config.APP_TITLE)
st.write(config.APP_INTRO)
st.info(config.DISCLAIMER, icon=":material/info:")
