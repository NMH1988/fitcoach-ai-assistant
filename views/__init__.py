"""The Streamlit UI, one module per concern; app.py only composes them (T8.1).

Modules that build chart specs and table rows (`charts`, `tables`) import no streamlit, so they are
unit-tested without AppTest. The logic stays in src/.
"""
