"""UI text in English and German (T7.1): one lookup function and number formats per language.

Every string the app shows is here under a key, in both languages; `t(key, lang)` returns it.
The English text of messages that also go to the model or into the summary PDF (guard and
guardrail messages, model errors, profile labels, status labels) keeps living in its module, and
tests check that the English entries here are the same (tests/test_i18n.py). The German texts are
our own writing, in the formal "Sie", and the owner reviews them before merge (T7.1, AC-5).
"""

from typing import Literal

from src import config

Language = Literal["en", "de"]
LANGUAGES: tuple[Language, ...] = ("en", "de")
# What the sidebar's language control shows for each language, the same in both UIs (T9.23).
LANGUAGE_LABELS: dict[Language, str] = {"en": "English", "de": "Deutsch"}
# Key of the chosen language in st.session_state (docs/UI_DESIGN.md, "Language").
SESSION_KEY = "language"

# German swaps the thousands and decimal marks: 2,500.5 (en) is 2.500,5 (de).
_DE_MARKS = str.maketrans({",": ".", ".": ","})


def number(value: float, lang: Language) -> str:
    """Show a number with thousands marks in the language's style: 2,500.5 or 2.500,5."""
    if isinstance(value, int):
        text = f"{value:,}"
    else:
        text = f"{value:,g}"
    return text.translate(_DE_MARKS) if lang == "de" else text


def percent(value: int, lang: Language) -> str:
    """Show a percentage as the language writes it: "20%" or "20 %"."""
    return f"{value} %" if lang == "de" else f"{value}%"


def plain(value: float, lang: Language) -> str:
    """Show a number without thousands marks, with the language's decimal mark: 1.5 or 1,5."""
    text = f"{value:g}"
    return text.replace(".", ",") if lang == "de" else text


def t(key: str, lang: Language, **params: object) -> str:
    """Return the UI text of a key in a language, with its {placeholders} filled in."""
    # Numbers are shown without thousands marks in the language's decimal style (a limit of 2000
    # characters, 18 years, 2.5 s); callers pass a formatted string where marks are wanted.
    filled = {
        name: plain(value, lang)
        if isinstance(value, int | float) and not isinstance(value, bool)
        else value
        for name, value in params.items()
    }
    return TEXT[lang][key].format(**filled)


def _de_number(value: int) -> str:
    """Return a whole number with German thousands marks, for texts built at import."""
    return number(value, "de")


# Values put into the texts once, at import.
_REWRITES = config.QUERY_REWRITES
_MAX_CHARS = config.MAX_INPUT_CHARS
_ADULT = config.PROFILE_AGE_RANGE[0]
_FLOOR = config.CALORIE_FLOOR_KCAL
_KEY = config.API_KEY_NAME
_BUILD = config.BUILD_INDEX_COMMAND

_EN: dict[str, str] = {
    # Header, disclaimer and tabs.
    "app.title": config.APP_TITLE,
    "app.intro": config.APP_INTRO,
    "app.not_medical_advice": "Not medical advice",
    "app.disclaimer": config.DISCLAIMER,
    "language.label": "Language",
    "tab.ask": "Ask",
    "tab.targets": "My targets",
    "tab.food": "Food lookup",
    "tab.details": "Details",
    "theme.hint": config.THEME_HINT,
    # The steps of a turn and what each does.
    "step.check": "Checking your question",
    "step.plan": "Planning the answer",
    "step.search": "Searching the research",
    "step.answer": "Writing the answer",
    "step.tools": "Using the tools",
    "step.check.detail": (
        "Length, prompt-injection patterns, safety topics and the question limit."
    ),
    "step.plan.detail": "The model decides whether to search the research, use a tool, or both.",
    "step.search.detail": (
        f"A small model rephrases the model's search {_REWRITES} ways and picks filters; then a "
        "search by meaning and by keyword over the approved research, merged into one ranking."
    ),
    "step.answer.detail": (
        "The model answers from the passages found and the tool results, citing the passages."
    ),
    "step.tools.detail": "Calculations from your profile and the USDA food table.",
    # How a turn's status box ends (config.STATUS_LABELS).
    "status.answer": "Answered from the research",
    "status.answer_uncited": "Answered without citing the research",
    "status.no_sources": "No matching research found",
    "status.rejected": "Question not accepted",
    "status.guardrail": "Not something this assistant can advise on",
    "status.error": "Something went wrong",
    # The profile form and the sidebar.
    "profile.dialog_title": "Your details",
    "profile.form_hint": config.PROFILE_FORM_HINT,
    "profile.units": "Units",
    "units.metric": "Metric (kg, cm)",
    "units.imperial": "Imperial (lb, ft/in)",
    "profile.goal": "Goal",
    "goal.build_muscle": "Build muscle",
    "goal.lose_fat": "Lose fat",
    "goal.maintain": "Maintain",
    "profile.weight_unit": "Weight ({unit})",
    "profile.age_years": "Age (years)",
    "profile.height_cm": "Height (cm)",
    "profile.height_ft": "Height (ft)",
    "profile.height_in": "Height (in)",
    "profile.sex": "Sex",
    "profile.sex_help": "Used by the energy equation, which has a male and a female form.",
    "sex.male": "Male",
    "sex.female": "Female",
    "profile.activity": "Activity",
    "profile.activity_placeholder": "Choose your activity level",
    "activity.sedentary": "Sedentary · exercise less than once a week",
    "activity.light": "Light · exercise 1-3 times a week",
    "activity.moderate": "Moderate · exercise 4-5 times a week",
    "activity.very_active": "Very active · exercise 6-7 times a week",
    "activity.extra_active": (
        "Extra active · exercise more than 7 times a week, extra heavy workouts"
    ),
    "activity_short.sedentary": "Sedentary",
    "activity_short.light": "Light · 1-3 times",
    "activity_short.moderate": "Moderate · 4-5 times",
    "activity_short.very_active": "Very active · 6-7 times",
    "activity_short.extra_active": "Extra active",
    "profile.save": "Save",
    "profile.check_these": "Check these",
    "profile.kept_never_stored": (
        "Kept for this session only, never stored; sent to the AI model through OpenRouter when a "
        "question needs it."
    ),
    "profile.kept": (
        "Kept for this session only; sent to the AI model through OpenRouter when a question "
        "needs it"
    ),
    "profile.your_profile": "Your profile",
    "profile.add_caption": "Add your details to get personal targets.",
    "profile.add": "Add your details",
    "profile.edit": "Edit details",
    "profile.weight": "Weight",
    "profile.height": "Height",
    "profile.age": "Age",
    # Profile validation (profile.ProfileError codes).
    "profile.err.units": "Choose metric or imperial units.",
    "profile.err.weight_missing": "Enter your weight in {unit}.",
    "profile.err.weight_range": "Weight must be between {low} and {high} {unit}.",
    "profile.err.height_cm_missing": "Enter your height in cm.",
    "profile.err.height_cm_range": "Height must be between {low} and {high} cm.",
    "profile.err.height_ft_missing": "Enter your height in feet and inches.",
    "profile.err.height_ft_format": "Enter the height as whole feet and 0 to 11 inches.",
    "profile.err.height_ft_range": "Height must be between {low} and {high}.",
    "profile.err.age_missing": "Enter your age in whole years.",
    "profile.err.age_minor": (
        "This app is for adults aged {min} and over, so it cannot give personal targets for "
        "younger users."
    ),
    "profile.err.age_range": "Age must be between {min} and {max}.",
    "profile.err.sex": "Choose the sex for the energy equation.",
    "profile.err.activity": "Choose your activity level.",
    "profile.err.goal": "Choose your goal.",
    # Daily targets: sidebar card, My targets tab, charts.
    "targets.daily_target": "Daily target",
    "targets.my_targets": "My targets",
    "macro.protein": "Protein",
    "macro.carbohydrate": "Carbohydrate",
    "macro.fat": "Fat",
    "targets.protein_lowered": "Protein was lowered to fit the target: see My targets.",
    "targets.more": "More under My targets.",
    "targets.at_maintenance": "{goal}: at maintenance",
    "targets.above_maintenance": "{goal}: {kcal} kcal above maintenance",
    "targets.below_maintenance": "{goal}: {kcal} kcal below maintenance",
    "targets.empty": "Add your details to get your daily energy and macro targets.",
    "targets.share": "{percent}% of kcal · {per_weight}",
    "targets.protein_warning": "{note} The sources' protein range for your weight: {range}.",
    "targets.protein_range": "{low}-{high} g a day ({per_low} to {per_high})",
    "targets.maintenance": "Maintenance (daily energy needs): about {kcal} kcal/day. {method}",
    "targets.sources": "Sources:",
    "chart.kcal_per_day": "kcal per day",
    "chart.energy": "Energy",
    "chart.bar_alt": "Energy split per day: {parts}",
    "chart.donut_alt": "Daily target {total} kcal, energy split: {parts}",
    # Tool results.
    "tool.results": "Tool results ({count})",
    "tool.profile_needed": config.PROFILE_NEEDED_HINT,
    "tool.title.calculate_tdee": "Daily energy needs",
    "tool.title.calculate_macro_targets": "Daily targets",
    "tool.title.lookup_food_nutrition": "Food lookup",
    "tool.title.evaluate_meal_plan": "Meal plan check",
    "tool.title.none": "Tool call not run",
    "table.item": "Item",
    "table.value": "Value",
    "tdee.bmr": "Resting energy (BMR)",
    "tdee.factor": "Activity factor",
    "tdee.tdee": "Daily energy needs (TDEE)",
    "unit.kcal_per_day": "kcal/day",
    "macros.range": "Range for the goal",
    "macros.needs": "Daily energy needs",
    "macros.protein_range": "Protein range",
    "macros.macro": "Macro",
    "macros.per_day": "Per day",
    "macros.share": "Share of kcal",
    "macros.per_weight": "Per {unit} of body weight",
    # Food lookup (tab and tool result) and the meal plan check.
    "food.title": "Food lookup",
    "food.food": "Food",
    "food.placeholder": "Choose a food or type to search",
    "food.grams": "Grams",
    "food.look_up": "Look up",
    "food.caption": (
        "Pick a food from the list, or type a few letters to search it. Single, unprocessed foods "
        "from the USDA FoodData Central Foundation Foods table, named in English."
    ),
    # The Food lookup tab's own messages (no model call there; owner's choice in the review of
    # PR #74). The English tab shows the lookup's own fixed text (`lookup_chosen_food()`, T4.8).
    "food.tab.invalid": (
        "Invalid food lookup: choose one food from the list; the amount must be a number of "
        "grams from 0.1 to 2000."
    ),
    "food.tab.error": config.TOOL_FAILED_MESSAGE,
    "food.did_you_mean": "Did you mean",
    "food.matched": "Matched USDA food, {grams} g:",
    "food.fiber_line": "Fiber: {fiber}",
    "food.not_reported": "not reported",
    "food.close_alternatives": "Close alternatives",
    "food.usda_food": "USDA food",
    "food.amount": "Amount",
    "nutrient.energy": "Energy",
    "nutrient.protein": "Protein",
    "nutrient.carbohydrate": "Carbohydrate",
    "nutrient.fat": "Fat",
    "nutrient.fiber": "Fiber",
    "usda.source_line": config.USDA_SOURCE_LINE,
    "meal.source_line": config.MEAL_PLAN_SOURCE_LINE,
    "meal.food_asked": "Food asked",
    "meal.other_names": "Other close USDA names",
    "meal.not_found": "Not found",
    "meal.nutrient": "Nutrient",
    "meal.plan_total": "Plan total",
    "meal.daily_target": "Daily target",
    "meal.difference": "Difference",
    "meal.range": "Range from the sources",
    "meal.below_target": "{amount} below the target",
    "meal.above_target": "{amount} above the target",
    "meal.on_target": "On the target",
    "meal.range.below": "Below {span} {unit}",
    "meal.range.within": "Within {span} {unit}",
    "meal.range.above": "Above {span} {unit}",
    "meal.no_target": "No target",
    # The answer, its sources and their cards.
    "sources.count": "Sources ({count})",
    "tier.1": "ISSN position stand",
    "tier.2": "Peer-reviewed review",
    "tier.unknown": "Review",
    "card.cited_as": "cited as {labels}",
    "card.open_article": "Open article",
    "correction.corrected_by": "A correction to this article was published",
    "correction.corrects": "This notice corrects",
    # Tokens and cost (T5.1).
    "usage.token": "token",
    "usage.tokens": "tokens",
    "usage.price_unknown": config.PRICE_UNKNOWN_LABEL,
    "usage.col.step": "Step",
    "usage.col.model": "Model",
    "usage.col.input": "Input tokens",
    "usage.col.cached": "Cached input",
    "usage.col.output": "Output tokens",
    "usage.col.reasoning": "Reasoning",
    "usage.col.cost": "Cost",
    "usage.step.rewrite": config.USAGE_STEP_REWRITE,
    "usage.step.search": config.USAGE_STEP_SEARCH,
    "usage.step.answer": config.USAGE_STEP_ANSWER,
    "usage.title": "Tokens and cost",
    "usage.this_answer": "This answer: {usage}",
    "usage.this_session": "This session: {usage}",
    "usage.session": "Session: {usage}",
    "usage.no_calls": "This answer made no model call that reported its tokens.",
    "usage.explain": (
        "Costs are priced on the input and output tokens, with OpenRouter's prices per token, "
        "read once a day. Reasoning is shown as OpenRouter reports it and is not priced again; "
        'it can be higher than the output count. "price unknown" means the prices could not be '
        "read when the answer ended."
    ),
    # How the answer was found (Details tab) and the sidebar's last answer card.
    "details.title": "How this answer was found",
    "details.empty": (
        "Ask a question in the Ask tab to see how its answer was found: the searches run and "
        "the filters used."
    ),
    "details.question": "Your question: {question}",
    "details.no_search": (
        "The model did not search the research for this answer, so no passage was sent to it."
    ),
    "details.search": "Search {number}",
    "details.searched_for": "Searched for",
    "details.model_query": "(the model's query)",
    "details.found": "{count} passages found, labelled {labels}.",
    "details.found_one": "1 passage found, labelled {labels}.",
    "details.found_none": "No passage close enough: the sources do not cover this query.",
    "details.filters": "Filters",
    "filter.none": "No filters",
    "filter.from_year": "From {year}",
    "topic.protein": "Protein",
    "topic.carbohydrate": "Carbohydrate",
    "topic.fat": "Fat",
    "topic.energy_balance": "Energy balance",
    "topic.nutrient_timing": "Nutrient timing",
    "topic.supplements": "Supplements",
    "topic.resistance_training": "Resistance training",
    "tier_filter.1": "ISSN position stands only",
    "tier_filter.2": "Peer-reviewed reviews only",
    "search.fell_back": (
        "The rewrite step gave no usable result, so only the model's query was searched, with no "
        "filters."
    ),
    "search.filter_dropped": (
        "No passage close enough matched all these filters, so they were relaxed (a training or "
        "nutrition topic, if named, is kept)."
    ),
    "card.last_answer": "Last answer",
    "card.for": "For: {question}",
    "card.no_search": "No search of the research.",
    "card.searches_one": "1 search of the research, {queries} queries in all.",
    "card.searches_many": "{count} searches of the research, {queries} queries in all.",
    "card.filters_dropped": "No match with these filters, so they were relaxed.",
    "card.more": "More in the Details tab.",
    # The Ask tab.
    "ask.invitation": (
        "Ask a question about nutrition for strength training. Answers cite the research they use."
    ),
    "ask.placeholder": "Ask about nutrition for your training",
    # The button that starts a new conversation (T9.4, AC-31).
    "ask.new_chat": "New chat",
    "ask.new_chat_help": (
        "Start a new conversation. The assistant forgets this one, and the summary and the session "
        "cost start again."
    ),
    # What the answers are based on, and the credits (the sidebar button's dialog).
    "about.title": "About the answers",
    "about.articles": (
        "**{articles} open-access research articles**: {stands} ISSN position stands and "
        "{reviews} peer-reviewed reviews ({licenses})."
    ),
    "about.scope": (
        "The assistant explains nutrition and resistance training principles from these articles "
        "and cites them. It does not write training programs or coach exercise technique, and it "
        "does not replace a coach, a doctor or a physiotherapist."
    ),
    "about.method": (
        "The model decides whether to search the research; a search is rephrased "
        f"{_REWRITES} ways, passages are found by meaning and by keyword and ranked together, "
        "and the answer cites them as [S1], [S2]..."
    ),
    "about.models": (
        "Searches rephrased by `{rewrite_model}`, answers written by `{answer_model}`, through "
        "OpenRouter."
    ),
    "about.ai": (
        "Answers are generated by an AI model and can be wrong: check them against the cited "
        "sources."
    ),
    "about.and": " and ",
    "about.credits": "Sources and credits",
    "about.article": "Article",
    "about.changes": (
        "Changes made to every article: text extracted and split into chunks. No endorsement by "
        "the authors, the journals or the publishers is implied."
    ),
    "about.full_credits": (
        "Full credits, with each article's copyright notice, are in ATTRIBUTION.md in the "
        "repository."
    ),
    # The summary PDF button, then the PDF's own headings and fixed labels (T7.2). The PDF also
    # uses the UI's texts for what the app shows the same way (tables, labels, fixed messages).
    "pdf.label": config.PDF_BUTTON_LABEL,
    "pdf.help": config.PDF_BUTTON_HELP,
    "pdf.empty_help": config.PDF_BUTTON_EMPTY_HELP,
    "pdf.title": f"{config.APP_TITLE}: session summary",
    "pdf.created": "Created on {date}",
    "pdf.disclaimer": "Not medical advice.",
    "pdf.profile": "Your profile",
    "pdf.no_profile": "No details were added in this session.",
    "pdf.age": "{age} years",
    "pdf.targets": "Your daily targets",
    "pdf.targets_note": "Calculated by the app from the profile above, with no AI model.",
    "pdf.no_targets": "Add your details in the app to get personal targets.",
    "pdf.turns": "Questions and answers",
    "pdf.no_turns": "No questions were asked in this session.",
    "pdf.question": "Question {number}",
    "pdf.answer": "Answer",
    "pdf.sources": "Sources",
    "pdf.tool_results": "Tool results",
    "pdf.credits": "Credits",
    "pdf.credits_intro": (
        "The answers and targets draw on the open access articles below; each is used under its "
        "own licence. The full list of the app's sources, with every article's copyright notice, "
        "is in ATTRIBUTION.md in the repository."
    ),
    "pdf.formula_sources": (
        "Formula sources (the energy calculations use their equation or factors)"
    ),
    "pdf.food_data": "Food data",
    "pdf.font": "Font",
    # Every PDF embeds subsets of the font, and its licence asks for its notices with every copy,
    # so the licence follows this line word for word (owner's choices in T5.2's review, 2026-10-20).
    "pdf.font_credit": (
        "Set in DejaVu Sans 2.37 "
        "(https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37). Its licence, "
        "as published with the fonts:"
    ),
    "pdf.footer": f"{config.APP_TITLE} · Not medical advice · Page {{page}}",
    # Messages from src/ (TurnResult.code): the guard, the guardrails, errors.
    "guard.empty": "Please type a question first.",
    "guard.too_long": (
        f"Your message is too long. Please keep it to at most {_MAX_CHARS} characters."
    ),
    "guard.injection": (
        "Your message looks like it tries to change how the assistant works, so it was not sent. "
        "If it is a nutrition question, please rephrase it."
    ),
    "guard.rate_window": (
        "You are sending questions too fast. Please wait {seconds} s and try again."
    ),
    "guard.rate_session": "This session has reached its limit of {limit} questions.",
    "guardrail.ped_dosing": (
        "This assistant does not give dosing or use advice for steroids, SARMs or other "
        "performance-enhancing drugs. For questions about them, please talk to a doctor. I can "
        "help with nutrition and with supplements covered by the research, such as creatine or "
        "caffeine."
    ),
    "guardrail.minor": (
        f"This assistant is made for adults ({_ADULT}+). For nutrition advice for someone under "
        f"{_ADULT}, please talk to a doctor, a paediatric dietitian or another qualified "
        "professional."
    ),
    "guardrail.pregnancy": (
        "This assistant is not made for pregnancy, the time after giving birth or breastfeeding. "
        "Please ask your doctor, midwife or a registered dietitian for advice that fits you."
    ),
    "guardrail.injury": (
        "This assistant cannot advise on pain, injuries or rehabilitation. Please see a doctor or "
        "a physiotherapist. If the pain is sudden or severe, or you have chest pain, call the "
        "emergency number (112 in Germany and the EU)."
    ),
    "guardrail.medical": (
        "This assistant is made for healthy adults and cannot advise on medical conditions or "
        "medication, as they can change what is safe to eat or take. Please ask your doctor, "
        "pharmacist or a registered dietitian."
    ),
    "guardrail.disordered_eating": (
        f"This assistant does not advise on eating below {_FLOOR:,} kcal a day or on ways of "
        "eating that may harm your health. If food, eating or your weight feel hard to manage, "
        "please talk to a doctor or a registered dietitian; eating disorder support services can "
        "help too."
    ),
    "answer.no_sources": config.NO_SOURCES_MESSAGE,
    "llm.error": "Something went wrong while calling the model service. Please try again.",
    "llm.invalid_key": (
        "The OpenRouter API key was rejected. Check the key in .streamlit/secrets.toml or the "
        f"{_KEY} environment variable."
    ),
    "llm.out_of_credit": "The OpenRouter account is out of credit. Add credit, then try again.",
    "llm.rate_limited": (
        "The model service is getting too many requests. Wait a minute and try again."
    ),
    "llm.timeout": "The model service took too long to answer. Please try again.",
    "llm.unavailable": (
        "The model service is temporarily unavailable. Try again in a few minutes."
    ),
    "llm.connection": (
        "Could not reach the model service. Check the internet connection and try again."
    ),
    "llm.cut_off": "The answer was cut off before it was finished. Please try again.",
    "llm.invalid_reply": "The model's answer was not in the expected format. Please try again.",
    "llm.tool_loop": "The answer could not be finished. Please try again.",
    "index.missing": f"The knowledge base index is missing. Run `{_BUILD}` to build it.",
    "index.unreadable": (
        f"The knowledge base index could not be read. Run `{_BUILD}` to build it."
    ),
    "index.empty": f"The knowledge base index is empty. Run `{_BUILD}` to build it.",
    "index.other_model": (
        "The knowledge base index was built with a different embedding model. "
        f"Run `{_BUILD}` to build it."
    ),
    "prompt.answer_missing": config.PROMPT_MISSING_MESSAGE,
    "prompt.query_missing": config.QUERY_PROMPT_MISSING_MESSAGE,
    "prompt.language_missing": config.LANGUAGE_PROMPT_MISSING_MESSAGE,
    "key.missing": config.MISSING_KEY_MESSAGE,
    "key.secrets_file": config.SECRETS_FILE_MESSAGE,
    "turn.error": config.TURN_ERROR_MESSAGE,
    # Pages, the account block, the welcome page and My data (T9.5).
    "page.chat": "Chat",
    "page.my_data": "My data",
    "page.profile": "My profile",
    "page.today": "Today",
    "page.workouts": "Workouts",
    "page.welcome": "Welcome",
    "page.start": "Start",
    "start.title": "Sign in to continue",
    "start.text": (
        "Sign in with Google to keep your profile, daily targets, food log and workouts (as a "
        "gymer) or to use the app's AI assistant (as a coach). A coach's questions (and the "
        "coach's own details, when a question needs them) go to the AI model through OpenRouter."
    ),
    "start.demo_title": "Try a made-up user",
    "start.demo": (
        "Demo mode: pick a made-up user below to try a coach's or a gymer's pages (what they save "
        "is deleted when the app stops). A coach's questions (and the coach's own details, when a "
        "question needs them) go to the AI model through OpenRouter."
    ),
    "start.demo_placeholder": "Choose a demo user",
    "account.guest_note": (
        "You are using the app as a guest: this app stores nothing; your questions (and your "
        "details, when a question needs them) go to the AI model through OpenRouter."
    ),
    "account.secrets_broken": (
        "Sign-in is off: `.streamlit/secrets.toml` could not be read (a TOML syntax error?). Fix "
        "the file and restart the app. Until then this app stores nothing, and the chat answers "
        "only if the API key is set as an environment variable (your questions then go to the AI "
        "model through OpenRouter)."
    ),
    "role.coach": "Coach",
    "role.gymer": "Gymer",
    "role_choice.coach": "Coach · I follow clients' nutrition and training",
    "role_choice.gymer": "Gymer · I log my own nutrition and training",
    "account.sign_in": "Sign in with Google",
    "account.sign_out": "Sign out",
    "account.signed_in_google": "Signed in with Google",
    "account.sign_in_off": (
        "Sign-in is off: this copy of the app has no Google sign-in set up. "
        "You can use the chat as a guest: this app stores nothing, and your questions (and your "
        "details, when a question needs them) go to the AI model through OpenRouter."
    ),
    "account.not_set_up": (
        "Sign-in is not fully set up: a secret in `.streamlit/secrets.toml` is missing, shorter "
        "than 32 characters or still the example's. Fix the file and restart the app."
    ),
    "account.demo_user": "Demo user",
    "account.demo_none": "None (back to the start page)",
    "account.demo_note": (
        "Demo mode: made-up users on a temporary database that is deleted when the app stops."
    ),
    "account.store_unavailable": (
        "Your saved data cannot be opened right now, so nothing is read or saved. Try again "
        "later, or restart the app."
    ),
    "account.welcome_title": "Set up your account",
    "account.welcome_text": (
        "Choose your role and the name the app shows (a made-up one is fine). The app's data file "
        "stores only an ID made from your Google account (never its name, e-mail address or "
        "picture), your role and this name. The sign-in cookie in your browser keeps your Google "
        "name, e-mail address and picture link until you sign out (at most 30 days)."
    ),
    "account.role": "Your role",
    "account.role_once": "The role is chosen once and cannot be changed in the app.",
    "account.display_name": "Display name",
    "account.display_name_help": (
        "{low} to {high} characters: letters, digits, spaces, dots, hyphens and apostrophes. "
        "Shown in the app only, never sent to the AI model."
    ),
    "account.create": "Create account",
    "account.role_needed": "Choose a role.",
    "account.name_length": "The display name needs {low} to {high} characters.",
    "account.name_characters": (
        "Use only letters, digits, spaces, dots, hyphens and apostrophes, starting with a letter "
        "or digit."
    ),
    "account.name_refused": "This display name cannot be used. Choose another one.",
    "account.exists": "This account exists already. Reload the page.",
    "account.gone": "Your account no longer exists (it was deleted). Reload the page.",
    "account.no_identity": "The sign-in did not give an account ID. Sign out and sign in again.",
    "account.no_target": "No daily target could be worked out from these details.",
    # The privacy notes of the sidebar and the profile form for signed-in users (T9.5).
    "profile.note_gymer": (
        "Saved for your account: when you press Save (or change the goal), your details, weight "
        "and daily targets are stored in this app's data file on this computer, and so are the "
        "food and weights you log on Today and the workouts you log on Workouts. Use made-up data "
        "only: do not enter real health data."
    ),
    "profile.note_coach": (
        "Kept for this session only: a coach's details are not stored, but they go to the AI "
        "model, through OpenRouter, when a question needs them. Your account (an ID, your role and "
        "display name) is stored in this app's data file on this computer. Chats are never stored, "
        "but this chat's earlier questions and answers go to the AI model with each new question. "
        "Use made-up data only: do not enter real health data."
    ),
    "profile.my_data_link": "See, export or delete it in My data",
    "profile.saved_on_save": "Saved to your account when you press Save (My data lists it).",
    "profile.opt_in": (
        "I understand that my details, the food and weights I log on Today and the workouts I "
        "log on Workouts are stored in this app's data file on this computer, and I enter made-up "
        "data only."
    ),
    "profile.opt_in_needed": "Tick the box above to save your details to your account.",
    "profile.goal_not_saved": (
        "The goal is kept for this session only: save your details with Edit details first "
        "(ticking the box there)."
    ),
    "my_data.intro_gymer": (
        "Everything the app stores about you: your account and your records below; your coach "
        "relationships, sharing choices and your coach's reads of your data are in the export."
    ),
    "my_data.intro_coach": (
        "Everything the app stores about you: your account, and your clients and their reviews "
        "once you have some (they are in the export). A coach keeps no records of their own, and "
        "nothing of your chats is stored."
    ),
    "my_data.account": "**Account:** {name} · {role} · created {created}",
    "my_data.count": "{count} stored",
    "my_data.kind.profile_entries": "Profile entries",
    "my_data.kind.body_measurements": "Weights",
    "my_data.kind.nutrition_targets": "Daily targets",
    "my_data.kind.meal_items": "Food log",
    "my_data.kind.workout_sessions": "Workouts",
    "my_data.kind.preferences": "Preferences",
    "my_data.col.saved": "Saved",
    "my_data.col.height": "Height",
    "my_data.col.age": "Age",
    "my_data.col.sex": "Sex",
    "my_data.col.activity": "Activity",
    "my_data.col.goal": "Goal",
    "my_data.col.day": "Day",
    "my_data.col.weight": "Weight",
    "my_data.col.from": "From",
    "my_data.col.kcal": "kcal",
    "my_data.col.protein": "Protein (g)",
    "my_data.col.carbohydrate": "Carbohydrate (g)",
    "my_data.col.fat": "Fat (g)",
    "my_data.col.set_by": "Set by",
    "my_data.col.meal": "Meal",
    "my_data.col.food": "Food",
    "my_data.col.grams": "Amount",
    "my_data.col.sets": "Sets",
    "my_data.col.text": "Text",
    "my_data.col.volume": "Volume",
    # The workout log (T9.14): facts only, no advice (config.TRAINING_ADVICE_WORDS, tested).
    "workouts.intro": (
        "Log a workout: pick the day, add each set with the exercise, reps, weight and, if you "
        "like, the RPE, then save it. Below, your week's sessions and totals."
    ),
    "workouts.stored_note": (
        "Saved for your account: your workouts are stored in this app's data file on this "
        "computer, and a coach sees them only while you share training with them. Use made-up "
        "data only: do not enter real health data."
    ),
    "workouts.profile_first": (
        "Workouts are saved once your details are: save them in My profile first, with the tick "
        "that you understand they are stored."
    ),
    "workouts.profile_link": "Go to My profile",
    "workouts.my_data_link": "See, export or delete them in My data",
    "workouts.log": "Log a workout",
    "workouts.editing": "Edit the workout of {day}",
    "workouts.day": "Day",
    "workouts.exercise": "Exercise",
    "workouts.reps": "Reps",
    "workouts.weight": "Weight ({unit})",
    "workouts.weight_help": "The weight lifted; 0 for a body-weight set with no added weight.",
    "workouts.rpe": "RPE (optional)",
    "workouts.rpe_help": "How hard the set felt, from 1 (very easy) to 10 (maximal effort).",
    "workouts.add_set": "Add set",
    "workouts.remove_last": "Remove the last set",
    "workouts.save": "Save workout",
    "workouts.save_edit": "Save changes",
    "workouts.cancel_edit": "Cancel editing",
    "workouts.discard": "Discard the draft",
    "workouts.edit_blocked": "Save, cancel or discard the workout above first.",
    "workouts.no_sets_yet": "No sets yet: add the first set above.",
    "workouts.max_sets": "A workout holds at most {count} sets.",
    "workouts.saved": "Workout saved.",
    "workouts.not_saved": "The workout could not be saved: check the values and try again.",
    "workouts.gone": "This workout no longer exists (it was deleted). Log it as a new one.",
    "workouts.week": "Your week",
    "workouts.week_of": "Week of",
    "workouts.week_line": (
        "{start} to {end} · Sessions: {sessions} · Sets: {sets} · Volume: {volume}"
    ),
    "workouts.volume_note": (
        "Volume is reps × weight, so a body-weight set with no added weight adds none."
    ),
    "workouts.none_this_week": "No workout logged in this week.",
    "workouts.session_line": "**{day}** · Sets: {sets} · Volume: {volume}",
    "workouts.edit": "Edit",
    "workouts.delete": "Delete",
    "workouts.col.set": "Set",
    "workouts.col.exercise": "Exercise",
    "workouts.col.reps": "Reps",
    "workouts.col.weight": "Weight",
    "workouts.col.rpe": "RPE",
    "workouts.col.sets": "Sets",
    "workouts.col.volume": "Volume",
    "workouts.col.top_weight": "Top weight",
    "muscle.chest": "Chest",
    "muscle.back": "Back",
    "muscle.legs": "Legs",
    "muscle.shoulders": "Shoulders",
    "muscle.arms": "Arms",
    "muscle.core": "Core",
    "my_data.grams": "{value} g",
    "my_data.set_by.system": "The app",
    "my_data.set_by.user": "You",
    "my_data.meal.breakfast": "Breakfast",
    "my_data.meal.lunch": "Lunch",
    "my_data.meal.dinner": "Dinner",
    "my_data.meal.snack": "Snack",
    "my_data.delete_one": "Delete one entry",
    "my_data.entry": "Entry",
    "my_data.entry_placeholder": "Choose an entry",
    "my_data.delete_entry": "Delete this entry",
    "my_data.export": "Export",
    "my_data.export_note": "All your data as one JSON file, built when you ask for it.",
    "my_data.prepare_export": "Prepare the export",
    "my_data.download": "Download my data (JSON)",
    "my_data.delete_all": "Delete everything",
    "my_data.delete_all_note": (
        "Deletes your account and every row about you, then signs you out. This cannot be undone."
    ),
    "my_data.confirm_delete_all": "Yes, delete my account and all my data",
    "my_data.delete_all_button": "Delete everything",
    # Invitations and sharing (T9.12).
    "page.clients": "Clients",
    "page.sharing": "Coach and sharing",
    "scope.nutrition": "Nutrition",
    "scope.training": "Training",
    "scope.body": "Body",
    "scope_help.nutrition": (
        "Food log, daily targets and the weekly reviews your coach approves (drafted by an AI "
        "model)"
    ),
    "scope_help.training": "Workouts",
    "scope_help.body": "Weights and profile entries (height, age, sex, activity, goal)",
    "relationship.active": "Active",
    "relationship.ended": "Ended",
    "clients.intro": (
        "Your clients and what each of them shares with you. A client chooses what you see, and "
        "can change it or end the relationship at any time."
    ),
    "clients.none": "No clients yet. Create an invitation below and give the code to your client.",
    "clients.col.name": "Client",
    "clients.col.status": "Status",
    "clients.col.since": "Since",
    "clients.col.ended": "Ended",
    "clients.shared": "Shared",
    "clients.not_shared": "Not shared",
    "clients.invitations": "Invitations",
    "clients.invitations_note": (
        "A code works once and expires after {days} days. Pass it on yourself, in person or by "
        "message: the app sends no email."
    ),
    "clients.create": "Create an invitation",
    "clients.new_code": (
        "Your new code, shown only now: note it or pass it on. It expires on {expires} (UTC)."
    ),
    "clients.noted": "I have noted the code",
    "clients.open_codes": "Unused codes",
    "clients.no_codes": "No unused codes.",
    "clients.col.created": "Created",
    "clients.col.expires": "Expires",
    "clients.col.state": "State",
    "clients.code_open": "Open",
    "clients.code_expired": "Expired",
    "clients.code_label": "Created {created} · expires {expires}",
    "clients.cancel_pick": "Code to cancel",
    "clients.cancel_placeholder": "Choose a code",
    "clients.cancel": "Cancel this invitation",
    "sharing.unverified": "The app does not check a coach's qualifications.",
    "sharing.no_coach": (
        "You have no coach. Enter the code your coach gave you and choose what they may see."
    ),
    "sharing.code": "Invitation code",
    "sharing.code_help": (
        "{length} letters and digits, e.g. ABCD-EFGH-JKLM; the hyphens are optional."
    ),
    "sharing.choose": (
        "Your coach sees what you share here, the days you logged before you shared it included, "
        "and always sees your display name. You can change what you share at any time."
    ),
    "sharing.accept": "Accept the invitation",
    "sharing.accepted": "You are now connected with your coach.",
    "sharing.refused.not_valid": (
        "This code cannot be used. Check it with your coach, or ask them for a new one."
    ),
    "sharing.refused.limit": "You have tried {attempts} codes today. Please try again tomorrow.",
    "sharing.refused.has_coach": "You have a coach already. End that relationship first.",
    "sharing.coach": "**Your coach:** {name} · since {since}",
    "sharing.what": "What your coach sees",
    "sharing.save": "Save sharing",
    "sharing.saved": "Your sharing choices are saved.",
    "sharing.end": "End the relationship",
    "sharing.end_note": (
        "Your coach can then read none of your records (nutrition, training, body), but still sees "
        "your display name and the dates of the relationship until one of you deletes their "
        "account. Your records stay yours, and you can accept a new code later."
    ),
    "sharing.confirm_end": "Yes, end the relationship with my coach",
    "sharing.end_button": "End the relationship",
    "sharing.ended": "The relationship has ended.",
    "sharing.changed": (
        "Your coach relationship changed in the meantime; the page shows it as it is now."
    ),
    # The Today page: the food and weight diary (T9.13).
    "today.intro": (
        "Log what you ate and your weight. A day with nothing logged shows as not logged, never "
        "as a day without food."
    ),
    "today.made_up_only": "Use made-up data only: do not enter real health data.",
    "today.profile_first": (
        "Save your details on My profile first (with the box ticked that you understand they are "
        "stored). Then you can log food and weight here."
    ),
    "today.day": "Day",
    "today.day_help": f"Today or up to {config.DIARY_MAX_DAYS_BACK} days back.",
    "today.add_food": "Add a food",
    "today.food": "Food",
    "today.food_placeholder": "Choose a food",
    "today.grams": "Amount (g)",
    "today.meal": "Meal",
    "today.add": "Add",
    "today.food_caption": (
        "Foods from the USDA table, in English. Each entry keeps the nutrients for the amount you "
        "logged."
    ),
    "today.day_title": "Logged on {day}",
    "today.nothing_logged": "Nothing logged on this day.",
    "today.meal_total": "**{meal}** · {kcal} kcal",
    "today.day_total": (
        "**Day total:** {kcal} kcal · protein {protein} g · carbohydrate {carbohydrate} g · "
        "fat {fat} g · fiber {fiber}"
    ),
    "today.fiber_partial": "{value} g or more (not reported for some foods)",
    "today.col.food": "Food",
    "today.col.grams": "Amount (g)",
    "today.col.kcal": "kcal",
    "today.col.protein": "Protein (g)",
    "today.col.carbohydrate": "Carbohydrate (g)",
    "today.col.fat": "Fat (g)",
    "today.col.fiber": "Fiber (g)",
    "today.edit_title": "Change or delete an entry",
    "today.entry": "Entry",
    "today.entry_placeholder": "Choose an entry",
    "today.save_changes": "Save changes",
    "today.delete": "Delete entry",
    "today.weight_title": "Weight",
    "today.weight_unit": "Weight ({unit})",
    "today.save_weight": "Save weight",
    "today.weights_logged": "Logged on this day: {weights}",
    "today.added": "Food added.",
    "today.changed": "Entry changed.",
    "today.deleted": "Entry deleted.",
    "today.weight_saved": "Weight saved.",
    "today.gone": "This entry no longer exists. The list below is up to date.",
    "today.stored_note": (
        "Saved in this app's database. You can export or delete it on My data; a coach sees "
        "it only while you share nutrition (food) or body (weight) with them."
    ),
    "diary.grams_range": (
        f"Enter an amount from {plain(config.FOOD_MIN_GRAMS, 'en')} to {config.FOOD_MAX_GRAMS} g."
    ),
    "diary.meal_needed": "Choose a meal: breakfast, lunch, dinner or snack.",
    "diary.profile_first": "Save your details on My profile first; nothing was saved here.",
    "diary.food_needed": "Choose a food from the list.",
    "diary.food_table": "The food table could not be read, so nothing was saved.",
    "diary.day_range": f"Choose today or a day up to {config.DIARY_MAX_DAYS_BACK} days back.",
    "diary.weight_range": (
        f"Enter a weight from {plain(config.PROFILE_WEIGHT_KG_RANGE[0], 'en')} to "
        f"{plain(config.PROFILE_WEIGHT_KG_RANGE[1], 'en')} kg (or the same in lb)."
    ),
}

_DE: dict[str, str] = {
    # A name is not translated: the German UI and PDF show the English one (T9.22).
    "app.title": config.APP_TITLE,
    "app.intro": (
        "Evidenzbasierte Antworten zur Ernährung für Erwachsene, die Krafttraining machen, mit "
        "der Forschung dahinter."
    ),
    "app.not_medical_advice": "Keine medizinische Beratung",
    "app.disclaimer": (
        "Diese App gibt allgemeine Informationen für gesunde Erwachsene. Sie ist keine "
        "medizinische Beratung und ersetzt weder eine Ärztin oder einen Arzt noch eine "
        "Ernährungsfachkraft, ein Coaching oder eine Physiotherapie. Sie erklärt "
        "Trainingsprinzipien aus der Forschung, erstellt aber keine Trainingspläne. Ihre "
        "Antworten erzeugt ein KI-Modell: Prüfen Sie sie anhand der Quellen."
    ),
    "language.label": "Sprache",
    "tab.ask": "Fragen",
    "tab.targets": "Meine Ziele",
    "tab.food": "Lebensmittel",
    "tab.details": "Details",
    "theme.hint": (
        ":material/dark_mode: Hell oder dunkel: Menü :material/more_vert: oben rechts "
        "(Light, Dark, System)"
    ),
    "step.check": "Frage wird geprüft",
    "step.plan": "Antwort wird geplant",
    "step.search": "Forschung wird durchsucht",
    "step.answer": "Antwort wird geschrieben",
    "step.tools": "Werkzeuge werden genutzt",
    "step.check.detail": "Länge, Muster für Prompt-Injection, Sicherheitsthemen und Fragenlimit.",
    "step.plan.detail": (
        "Das Modell entscheidet, ob es die Forschung durchsucht, ein Werkzeug nutzt oder beides."
    ),
    "step.search.detail": (
        f"Ein kleines Modell formuliert die Suche des Modells auf {_REWRITES} Arten um und wählt "
        "Filter; dann Suche nach Bedeutung und nach Stichwort in der geprüften Forschung, zu einer "
        "Rangfolge zusammengeführt."
    ),
    "step.answer.detail": (
        "Das Modell antwortet aus den gefundenen Textstellen und den Werkzeugergebnissen und "
        "zitiert die Textstellen."
    ),
    "step.tools.detail": "Berechnungen aus Ihrem Profil und der USDA-Lebensmitteltabelle.",
    "status.answer": "Aus der Forschung beantwortet",
    "status.answer_uncited": "Ohne Zitat aus der Forschung beantwortet",
    "status.no_sources": "Keine passende Forschung gefunden",
    "status.rejected": "Frage nicht angenommen",
    "status.guardrail": "Dazu kann dieser Assistent nicht beraten",
    "status.error": "Etwas ist schiefgelaufen",
    "profile.dialog_title": "Ihre Angaben",
    "profile.form_hint": (
        "Geben Sie Ihre Werte ein und klicken Sie dann auf Speichern. Die Werte werden beim "
        "Speichern geprüft."
    ),
    "profile.units": "Einheiten",
    "units.metric": "Metrisch (kg, cm)",
    "units.imperial": "Imperial (lb, ft/in)",
    "profile.goal": "Ziel",
    "goal.build_muscle": "Muskeln aufbauen",
    "goal.lose_fat": "Fett verlieren",
    "goal.maintain": "Gewicht halten",
    "profile.weight_unit": "Gewicht ({unit})",
    "profile.age_years": "Alter (Jahre)",
    "profile.height_cm": "Größe (cm)",
    "profile.height_ft": "Größe (ft)",
    "profile.height_in": "Größe (in)",
    "profile.sex": "Geschlecht",
    "profile.sex_help": (
        "Wird für die Energieformel gebraucht, die eine Form für Männer und eine für Frauen hat."
    ),
    "sex.male": "Männlich",
    "sex.female": "Weiblich",
    "profile.activity": "Aktivität",
    "profile.activity_placeholder": "Aktivitätsniveau wählen",
    "activity.sedentary": "Sitzend · Sport seltener als einmal pro Woche",
    "activity.light": "Leicht · Sport 1-3 Mal pro Woche",
    "activity.moderate": "Mäßig · Sport 4-5 Mal pro Woche",
    "activity.very_active": "Sehr aktiv · Sport 6-7 Mal pro Woche",
    "activity.extra_active": (
        "Extrem aktiv · Sport mehr als 7 Mal pro Woche, besonders harte Einheiten"
    ),
    "activity_short.sedentary": "Sitzend",
    "activity_short.light": "Leicht · 1-3 Mal",
    "activity_short.moderate": "Mäßig · 4-5 Mal",
    "activity_short.very_active": "Sehr aktiv · 6-7 Mal",
    "activity_short.extra_active": "Extrem aktiv",
    "profile.save": "Speichern",
    "profile.check_these": "Zu prüfen",
    "profile.kept_never_stored": (
        "Nur für diese Sitzung behalten, nie gespeichert; geht über OpenRouter an das KI-Modell, "
        "wenn eine Frage es braucht."
    ),
    "profile.kept": (
        "Nur für diese Sitzung; geht über OpenRouter an das KI-Modell, wenn eine Frage es braucht"
    ),
    "profile.your_profile": "Ihr Profil",
    "profile.add_caption": "Geben Sie Ihre Angaben ein, um persönliche Ziele zu erhalten.",
    "profile.add": "Angaben eingeben",
    "profile.edit": "Angaben bearbeiten",
    "profile.weight": "Gewicht",
    "profile.height": "Größe",
    "profile.age": "Alter",
    "profile.err.units": "Wählen Sie metrische oder imperiale Einheiten.",
    "profile.err.weight_missing": "Geben Sie Ihr Gewicht in {unit} ein.",
    "profile.err.weight_range": "Das Gewicht muss zwischen {low} und {high} {unit} liegen.",
    "profile.err.height_cm_missing": "Geben Sie Ihre Größe in cm ein.",
    "profile.err.height_cm_range": "Die Größe muss zwischen {low} und {high} cm liegen.",
    "profile.err.height_ft_missing": "Geben Sie Ihre Größe in Fuß und Zoll ein.",
    "profile.err.height_ft_format": "Geben Sie die Größe in ganzen Fuß und 0 bis 11 Zoll ein.",
    "profile.err.height_ft_range": "Die Größe muss zwischen {low} und {high} liegen.",
    "profile.err.age_missing": "Geben Sie Ihr Alter in ganzen Jahren ein.",
    "profile.err.age_minor": (
        "Diese App ist für Erwachsene ab {min} Jahren und kann jüngeren Menschen keine "
        "persönlichen Ziele geben."
    ),
    "profile.err.age_range": "Das Alter muss zwischen {min} und {max} liegen.",
    "profile.err.sex": "Wählen Sie das Geschlecht für die Energieformel.",
    "profile.err.activity": "Wählen Sie Ihr Aktivitätsniveau.",
    "profile.err.goal": "Wählen Sie Ihr Ziel.",
    "targets.daily_target": "Tagesziel",
    "targets.my_targets": "Meine Ziele",
    "macro.protein": "Protein",
    "macro.carbohydrate": "Kohlenhydrate",
    "macro.fat": "Fett",
    "targets.protein_lowered": (
        "Protein wurde gesenkt, damit es zum Ziel passt: siehe „Meine Ziele“."
    ),
    "targets.more": "Mehr unter „Meine Ziele“.",
    "targets.at_maintenance": "{goal}: auf Erhaltungsbedarf",
    "targets.above_maintenance": "{goal}: {kcal} kcal über dem Erhaltungsbedarf",
    "targets.below_maintenance": "{goal}: {kcal} kcal unter dem Erhaltungsbedarf",
    "targets.empty": (
        "Geben Sie Ihre Angaben ein, um Ihre täglichen Ziele für Energie und Makronährstoffe zu "
        "erhalten."
    ),
    "targets.share": "{percent} % der kcal · {per_weight}",
    "targets.protein_warning": "{note} Proteinbereich der Quellen für Ihr Gewicht: {range}.",
    "targets.protein_range": "{low}-{high} g pro Tag ({per_low} bis {per_high})",
    "targets.maintenance": (
        "Erhaltungsbedarf (täglicher Energiebedarf): etwa {kcal} kcal/Tag. {method}"
    ),
    "targets.sources": "Quellen:",
    "chart.kcal_per_day": "kcal pro Tag",
    "chart.energy": "Energie",
    "chart.bar_alt": "Energieaufteilung pro Tag: {parts}",
    "chart.donut_alt": "Tagesziel {total} kcal, Energieaufteilung: {parts}",
    "tool.results": "Werkzeugergebnisse ({count})",
    "tool.profile_needed": (
        "Diese Berechnung braucht Ihre Angaben. Geben Sie sie ein und fragen Sie dann noch einmal."
    ),
    "tool.title.calculate_tdee": "Täglicher Energiebedarf",
    "tool.title.calculate_macro_targets": "Tagesziele",
    "tool.title.lookup_food_nutrition": "Lebensmittelsuche",
    "tool.title.evaluate_meal_plan": "Essensplan-Check",
    "tool.title.none": "Werkzeugaufruf nicht ausgeführt",
    "table.item": "Angabe",
    "table.value": "Wert",
    "tdee.bmr": "Ruheenergiebedarf (BMR)",
    "tdee.factor": "Aktivitätsfaktor",
    "tdee.tdee": "Täglicher Energiebedarf (TDEE)",
    "unit.kcal_per_day": "kcal/Tag",
    "macros.range": "Bereich für das Ziel",
    "macros.needs": "Täglicher Energiebedarf",
    "macros.protein_range": "Proteinbereich",
    "macros.macro": "Makronährstoff",
    "macros.per_day": "Pro Tag",
    "macros.share": "Anteil an kcal",
    "macros.per_weight": "Pro {unit} Körpergewicht",
    "food.title": "Lebensmittelsuche",
    "food.food": "Lebensmittel",
    "food.placeholder": "Wählen Sie ein Lebensmittel oder tippen Sie zum Suchen",
    "food.grams": "Gramm",
    "food.look_up": "Suchen",
    "food.caption": (
        "Wählen Sie ein Lebensmittel aus der Liste oder geben Sie einige Buchstaben ein, um danach "
        "zu suchen. Verfügbar sind einzelne, unverarbeitete Lebensmittel aus der "
        "Foundation-Foods-Tabelle von USDA FoodData Central; die Bezeichnungen sind auf Englisch."
    ),
    "food.tab.invalid": (
        "Wählen Sie ein Lebensmittel aus der Liste und geben Sie eine Menge von 0,1 bis 2000 "
        "Gramm an."
    ),
    "food.tab.error": (
        "Die Lebensmittelsuche ist gerade nicht verfügbar: Die Lebensmitteltabelle konnte nicht "
        "gelesen werden."
    ),
    "food.did_you_mean": "Meinten Sie",
    "food.matched": "Gefundenes USDA-Lebensmittel, {grams} g:",
    "food.fiber_line": "Ballaststoffe: {fiber}",
    "food.not_reported": "nicht angegeben",
    "food.close_alternatives": "Ähnliche Einträge",
    "food.usda_food": "USDA-Lebensmittel",
    "food.amount": "Menge",
    "nutrient.energy": "Energie",
    "nutrient.protein": "Protein",
    "nutrient.carbohydrate": "Kohlenhydrate",
    "nutrient.fat": "Fett",
    "nutrient.fiber": "Ballaststoffe",
    "usda.source_line": (
        "Quelle: USDA FoodData Central, Foundation Foods (CC0). Werte pro 100 g, umgerechnet."
    ),
    "meal.source_line": (
        "Quelle: USDA FoodData Central, Foundation Foods (CC0). Werte pro 100 g, umgerechnet. "
        "Ziele: die Tagesziele aus Ihren Angaben."
    ),
    "meal.food_asked": "Angefragtes Lebensmittel",
    "meal.other_names": "Weitere ähnliche USDA-Namen",
    "meal.not_found": "Nicht gefunden",
    "meal.nutrient": "Nährstoff",
    "meal.plan_total": "Summe im Plan",
    "meal.daily_target": "Tagesziel",
    "meal.difference": "Differenz",
    "meal.range": "Bereich aus den Quellen",
    "meal.below_target": "{amount} unter dem Ziel",
    "meal.above_target": "{amount} über dem Ziel",
    "meal.on_target": "Ziel erreicht",
    "meal.range.below": "Unter {span} {unit}",
    "meal.range.within": "Im Bereich {span} {unit}",
    "meal.range.above": "Über {span} {unit}",
    "meal.no_target": "Kein Ziel",
    "sources.count": "Quellen ({count})",
    "tier.1": "ISSN-Positionspapier",
    "tier.2": "Begutachtete Übersichtsarbeit",
    "tier.unknown": "Übersichtsarbeit",
    "card.cited_as": "zitiert als {labels}",
    "card.open_article": "Artikel öffnen",
    "correction.corrected_by": "Zu diesem Artikel wurde eine Korrektur veröffentlicht",
    "correction.corrects": "Diese Mitteilung korrigiert",
    "usage.token": "Token",
    "usage.tokens": "Token",
    "usage.price_unknown": "Preis unbekannt",
    "usage.col.step": "Schritt",
    "usage.col.model": "Modell",
    "usage.col.input": "Eingabe-Token",
    "usage.col.cached": "Eingabe aus Cache",
    "usage.col.output": "Ausgabe-Token",
    "usage.col.reasoning": "Reasoning",
    "usage.col.cost": "Kosten",
    "usage.step.rewrite": "Frage umformulieren",
    "usage.step.search": "Suchanfragen einbetten",
    "usage.step.answer": "Antwort, Runde {round}",
    "usage.title": "Token und Kosten",
    "usage.this_answer": "Diese Antwort: {usage}",
    "usage.this_session": "Diese Sitzung: {usage}",
    "usage.session": "Sitzung: {usage}",
    "usage.no_calls": "Diese Antwort hat keinen Modellaufruf gemacht, der seine Token meldet.",
    "usage.explain": (
        "Die Kosten werden aus den Eingabe- und Ausgabe-Token berechnet, mit den Preisen pro "
        "Token von OpenRouter, die einmal am Tag gelesen werden. Reasoning wird gezeigt, wie "
        "OpenRouter es meldet, und nicht noch einmal berechnet; es kann höher sein als die "
        'Ausgabe. "Preis unbekannt" heißt, dass die Preise am Ende der Antwort nicht gelesen '
        "werden konnten."
    ),
    "details.title": "Wie diese Antwort gefunden wurde",
    "details.empty": (
        "Stellen Sie im Tab „Fragen“ eine Frage, um zu sehen, wie ihre Antwort gefunden wurde: die "
        "Suchen und die Filter."
    ),
    "details.question": "Ihre Frage: {question}",
    "details.no_search": (
        "Das Modell hat für diese Antwort nicht in der Forschung gesucht, daher wurde ihm keine "
        "Textstelle gesendet."
    ),
    "details.search": "Suche {number}",
    "details.searched_for": "Gesucht nach",
    "details.model_query": "(die Suchanfrage des Modells)",
    "details.found": "{count} Textstellen gefunden, bezeichnet als {labels}.",
    "details.found_one": "1 Textstelle gefunden, bezeichnet als {labels}.",
    "details.found_none": (
        "Keine Textstelle nah genug: Die Quellen decken diese Suchanfrage nicht ab."
    ),
    "details.filters": "Filter",
    "filter.none": "Keine Filter",
    "filter.from_year": "Ab {year}",
    "topic.protein": "Protein",
    "topic.carbohydrate": "Kohlenhydrate",
    "topic.fat": "Fett",
    "topic.energy_balance": "Energiebilanz",
    "topic.nutrient_timing": "Nährstoff-Timing",
    "topic.supplements": "Nahrungsergänzung",
    "topic.resistance_training": "Krafttraining",
    "tier_filter.1": "Nur ISSN-Positionspapiere",
    "tier_filter.2": "Nur begutachtete Übersichtsarbeiten",
    "search.fell_back": (
        "Die Umformulierung gab kein brauchbares Ergebnis, daher wurde nur die Suchanfrage des "
        "Modells gesucht, ohne Filter."
    ),
    "search.filter_dropped": (
        "Keine Textstelle passte nah genug zu allen diesen Filtern, daher wurden sie gelockert "
        "(ein genanntes Trainings- oder Ernährungsthema bleibt)."
    ),
    "card.last_answer": "Letzte Antwort",
    "card.for": "Zu: {question}",
    "card.no_search": "Keine Suche in der Forschung.",
    "card.searches_one": "1 Suche in der Forschung, insgesamt {queries} Suchanfragen.",
    "card.searches_many": "{count} Suchen in der Forschung, insgesamt {queries} Suchanfragen.",
    "card.filters_dropped": "Nichts passte zu diesen Filtern, daher wurden sie gelockert.",
    "card.more": "Mehr im Tab „Details“.",
    "ask.invitation": (
        "Stellen Sie eine Frage zur Ernährung für Krafttraining. Die Antworten zitieren die "
        "Forschung, die sie nutzen."
    ),
    "ask.placeholder": "Fragen Sie zur Ernährung für Ihr Training",
    "ask.new_chat": "Neuer Chat",
    "ask.new_chat_help": (
        "Ein neues Gespräch beginnen. Der Assistent vergisst dieses, und die Zusammenfassung und "
        "die Kosten der Sitzung beginnen neu."
    ),
    "about.title": "Über die Antworten",
    "about.articles": (
        "**{articles} frei zugängliche Forschungsartikel**: {stands} ISSN-Positionspapiere und "
        "{reviews} begutachtete Übersichtsarbeiten ({licenses})."
    ),
    "about.scope": (
        "Der Assistent erklärt Grundsätze der Ernährung und des Krafttrainings aus diesen "
        "Artikeln und zitiert sie. Er erstellt keine Trainingspläne, leitet keine Übungstechnik "
        "an und ersetzt weder ein Coaching noch eine ärztliche oder physiotherapeutische "
        "Behandlung."
    ),
    "about.method": (
        "Das Modell entscheidet, ob es in der Forschung sucht; eine Suche wird auf "
        f"{_REWRITES} Arten umformuliert, Textstellen werden nach Bedeutung und nach Stichwort "
        "gefunden und in eine gemeinsame Rangfolge gebracht, und die Antwort zitiert sie als "
        "[S1], [S2]..."
    ),
    "about.models": (
        "Suchen umformuliert von `{rewrite_model}`, Antworten geschrieben von `{answer_model}`, "
        "über OpenRouter."
    ),
    "about.ai": (
        "Die Antworten erzeugt ein KI-Modell, und sie können falsch sein: Prüfen Sie sie anhand "
        "der zitierten Quellen."
    ),
    "about.and": " und ",
    "about.credits": "Quellen und Nachweise",
    "about.article": "Artikel",
    "about.changes": (
        "An jedem Artikel geändert: Text extrahiert und in Abschnitte aufgeteilt. Das bedeutet "
        "keine Billigung durch die Autorinnen und Autoren, die Zeitschriften oder die Verlage."
    ),
    "about.full_credits": (
        "Vollständige Nachweise mit dem Urheberrechtshinweis jedes Artikels stehen in "
        "ATTRIBUTION.md im Repository."
    ),
    "pdf.label": "Zusammenfassung herunterladen (PDF)",
    "pdf.help": (
        "Ihr Profil, Ihre Ziele, Fragen und Antworten mit ihren Quellen als PDF. Wird beim Klick "
        "erstellt; nicht auf dem Server gespeichert."
    ),
    "pdf.empty_help": "Geben Sie zuerst Ihre Angaben ein oder stellen Sie eine Frage.",
    "pdf.title": f"{config.APP_TITLE}: Zusammenfassung der Sitzung",
    "pdf.created": "Erstellt am {date}",
    "pdf.disclaimer": "Keine medizinische Beratung.",
    "pdf.profile": "Ihr Profil",
    "pdf.no_profile": "In dieser Sitzung wurden keine Angaben gemacht.",
    "pdf.age": "{age} Jahre",
    "pdf.targets": "Ihre Tagesziele",
    "pdf.targets_note": "Von der App aus dem Profil oben berechnet, ohne KI-Modell.",
    "pdf.no_targets": "Geben Sie Ihre Angaben in der App ein, um persönliche Ziele zu erhalten.",
    "pdf.turns": "Fragen und Antworten",
    "pdf.no_turns": "In dieser Sitzung wurden keine Fragen gestellt.",
    "pdf.question": "Frage {number}",
    "pdf.answer": "Antwort",
    "pdf.sources": "Quellen",
    "pdf.tool_results": "Werkzeugergebnisse",
    "pdf.credits": "Nachweise",
    "pdf.credits_intro": (
        "Die Antworten und Ziele stützen sich auf die unten genannten Open-Access-Artikel; jeder "
        "wird unter seiner eigenen Lizenz verwendet. Die Nachweise stehen auf Englisch, wie in "
        "ATTRIBUTION.md im Repository, wo die vollständige Liste der Quellen der App mit dem "
        "Urheberrechtshinweis jedes Artikels steht."
    ),
    "pdf.formula_sources": (
        "Quellen der Formeln (die Energieberechnungen verwenden ihre Gleichung oder Faktoren)"
    ),
    "pdf.food_data": "Lebensmitteldaten",
    "pdf.font": "Schrift",
    "pdf.font_credit": (
        "Gesetzt in DejaVu Sans 2.37 "
        "(https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37). Ihre Lizenz, "
        "wie sie mit den Schriften veröffentlicht wurde:"
    ),
    "pdf.footer": f"{config.APP_TITLE} · Keine medizinische Beratung · Seite {{page}}",
    "guard.empty": "Geben Sie zuerst eine Frage ein.",
    "guard.too_long": (
        f"Ihre Nachricht ist zu lang. Sie darf höchstens {_MAX_CHARS} Zeichen haben."
    ),
    "guard.injection": (
        "Ihre Nachricht sieht so aus, als wolle sie ändern, wie der Assistent arbeitet, daher "
        "wurde sie nicht gesendet. Wenn es eine Frage zur Ernährung ist, formulieren Sie sie "
        "bitte um."
    ),
    "guard.rate_window": (
        "Sie senden Fragen zu schnell. Warten Sie bitte {seconds} s und versuchen Sie es erneut."
    ),
    "guard.rate_session": "Diese Sitzung hat ihr Limit von {limit} Fragen erreicht.",
    "guardrail.ped_dosing": (
        "Dieser Assistent gibt keine Ratschläge zur Dosierung oder Anwendung von Steroiden, "
        "SARMs oder anderen leistungssteigernden Mitteln. Sprechen Sie bei Fragen dazu bitte "
        "mit einer Ärztin oder einem Arzt. Ich helfe gern bei der Ernährung und bei "
        "Nahrungsergänzungsmitteln, die die Forschung abdeckt, etwa Kreatin oder Koffein."
    ),
    "guardrail.minor": (
        f"Dieser Assistent ist für Erwachsene ({_ADULT}+) gedacht. Für eine Ernährungsberatung "
        f"für Menschen unter {_ADULT} sprechen Sie bitte mit einer Ärztin oder einem Arzt, einer "
        "Ernährungsfachkraft für Kinder oder einer anderen qualifizierten Fachperson."
    ),
    "guardrail.pregnancy": (
        "Dieser Assistent ist nicht für die Schwangerschaft, die Zeit nach der Geburt oder die "
        "Stillzeit gedacht. Fragen Sie bitte Ihre Ärztin oder Ihren Arzt, Ihre Hebamme oder eine "
        "Ernährungsfachkraft nach einem Rat, der zu Ihnen passt."
    ),
    "guardrail.injury": (
        "Dieser Assistent kann nicht zu Schmerzen, Verletzungen oder Rehabilitation beraten. "
        "Wenden Sie sich bitte an eine Ärztin oder einen Arzt oder an eine Physiotherapeutin "
        "oder einen Physiotherapeuten. Bei plötzlichen oder starken Schmerzen oder Schmerzen in "
        "der Brust rufen Sie den Notruf 112 an."
    ),
    "guardrail.medical": (
        "Dieser Assistent ist für gesunde Erwachsene gedacht und kann nicht zu Erkrankungen oder "
        "Medikamenten beraten, da sie verändern können, was Sie sicher essen oder einnehmen "
        "können. Fragen Sie bitte Ihre Ärztin oder Ihren Arzt, Ihre Apotheke oder eine "
        "Ernährungsfachkraft."
    ),
    "guardrail.disordered_eating": (
        f"Dieser Assistent berät nicht dazu, weniger als {_de_number(_FLOOR)} kcal am Tag zu "
        "essen, und nicht zu Essweisen, die Ihrer Gesundheit schaden können. Wenn Essen, "
        "Ernährung oder Ihr Gewicht schwer zu bewältigen sind, sprechen Sie bitte mit einer "
        "Ärztin oder einem Arzt oder einer Ernährungsfachkraft; auch Beratungsstellen für "
        "Essstörungen können helfen."
    ),
    "answer.no_sources": (
        "Unsere Quellen decken diese Frage nicht ab, daher gibt es keine Antwort aus der "
        "Forschung. Versuchen Sie eine Frage zu Protein, Kohlenhydraten, Fett, Energiebilanz, "
        "Nährstoff-Timing oder Nahrungsergänzung für Krafttraining oder zu Grundsätzen des "
        "Krafttrainings (Volumen, Last, Häufigkeit, Pausen, Progression)."
    ),
    "llm.error": (
        "Beim Aufruf des Modelldienstes ist etwas schiefgelaufen. Versuchen Sie es bitte erneut."
    ),
    "llm.invalid_key": (
        "Der OpenRouter-API-Schlüssel wurde abgelehnt. Prüfen Sie den Schlüssel in "
        f".streamlit/secrets.toml oder die Umgebungsvariable {_KEY}."
    ),
    "llm.out_of_credit": (
        "Das OpenRouter-Konto hat kein Guthaben mehr. Laden Sie Guthaben auf und versuchen Sie es "
        "dann erneut."
    ),
    "llm.rate_limited": (
        "Der Modelldienst bekommt zu viele Anfragen. Warten Sie eine Minute und versuchen Sie es "
        "erneut."
    ),
    "llm.timeout": (
        "Der Modelldienst hat zu lange für die Antwort gebraucht. Versuchen Sie es bitte erneut."
    ),
    "llm.unavailable": (
        "Der Modelldienst ist vorübergehend nicht erreichbar. Versuchen Sie es in ein paar "
        "Minuten erneut."
    ),
    "llm.connection": (
        "Der Modelldienst war nicht erreichbar. Prüfen Sie die Internetverbindung und versuchen "
        "Sie es erneut."
    ),
    "llm.cut_off": (
        "Die Antwort wurde abgeschnitten, bevor sie fertig war. Versuchen Sie es bitte erneut."
    ),
    "llm.invalid_reply": (
        "Die Antwort des Modells hatte nicht das erwartete Format. Versuchen Sie es bitte erneut."
    ),
    "llm.tool_loop": (
        "Die Antwort konnte nicht fertiggestellt werden. Versuchen Sie es bitte erneut."
    ),
    "index.missing": (
        f"Der Index der Wissensbasis fehlt. Führen Sie `{_BUILD}` aus, um ihn zu erstellen."
    ),
    "index.unreadable": (
        "Der Index der Wissensbasis konnte nicht gelesen werden. Führen Sie "
        f"`{_BUILD}` aus, um ihn zu erstellen."
    ),
    "index.empty": (
        f"Der Index der Wissensbasis ist leer. Führen Sie `{_BUILD}` aus, um ihn zu erstellen."
    ),
    "index.other_model": (
        "Der Index der Wissensbasis wurde mit einem anderen Embedding-Modell erstellt. Führen "
        f"Sie `{_BUILD}` aus, um ihn zu erstellen."
    ),
    "prompt.answer_missing": (
        "Der Antwort-Prompt `src/prompts/answer_system.md` fehlt oder ist leer, daher kann keine "
        "Antwort geschrieben werden. Stellen Sie die Datei wieder her und fragen Sie erneut."
    ),
    "prompt.query_missing": (
        "Der Prompt für die Umformulierung `src/prompts/query_translation_system.md` fehlt oder "
        "ist leer, daher kann die Frage nicht gesucht werden. Stellen Sie die Datei wieder her "
        "und fragen Sie erneut."
    ),
    "prompt.language_missing": (
        "Der Sprach-Prompt für die Antwort (`src/prompts/answer_language_en.md` oder "
        "`answer_language_de.md`) fehlt oder ist leer, daher kann keine Antwort geschrieben "
        "werden. Stellen Sie die Datei wieder her und fragen Sie erneut."
    ),
    "key.missing": (
        "Der OpenRouter-API-Schlüssel fehlt. Tragen Sie ihn in `.streamlit/secrets.toml` ein oder "
        f"setzen Sie die Umgebungsvariable {_KEY} und starten Sie die App dann neu."
    ),
    "key.secrets_file": (
        "`.streamlit/secrets.toml` konnte nicht gelesen werden. Korrigieren Sie die Datei oder "
        f"setzen Sie die Umgebungsvariable {_KEY} und starten Sie die App dann neu."
    ),
    "turn.error": (
        "Beim Beantworten Ihrer Frage ist etwas schiefgelaufen. Versuchen Sie es bitte erneut."
    ),
    # Seiten, Kontobereich, Willkommensseite und Meine Daten (T9.5).
    "page.chat": "Chat",
    "page.my_data": "Meine Daten",
    "page.profile": "Mein Profil",
    "page.today": "Heute",
    "page.workouts": "Training",
    "page.welcome": "Willkommen",
    "page.start": "Start",
    "start.title": "Melden Sie sich an, um fortzufahren",
    "start.text": (
        "Melden Sie sich mit Google an, um Ihr Profil, Ihre Tagesziele, Ihr Ernährungstagebuch "
        "und Ihre Trainingseinheiten zu behalten (als Gymer) oder den KI-Assistenten der App zu "
        "nutzen (als Coach). Die Fragen eines Coachs (und seine eigenen Angaben, wenn eine Frage "
        "sie braucht) gehen über OpenRouter an das KI-Modell."
    ),
    "start.demo_title": "Einen erfundenen Nutzer ausprobieren",
    "start.demo": (
        "Demo-Modus: Wählen Sie unten einen erfundenen Nutzer, um die Seiten eines Coachs oder "
        "Gymers auszuprobieren (was sie speichern, wird beim Beenden der App gelöscht). Die Fragen "
        "eines Coachs (und seine eigenen Angaben, wenn eine Frage sie braucht) gehen über "
        "OpenRouter an das KI-Modell."
    ),
    "start.demo_placeholder": "Demo-Nutzer wählen",
    "account.guest_note": (
        "Sie nutzen die App als Gast: Diese App speichert nichts; Ihre Fragen (und Ihre Angaben, "
        "wenn eine Frage sie braucht) gehen über OpenRouter an das KI-Modell."
    ),
    "account.secrets_broken": (
        "Die Anmeldung ist aus: `.streamlit/secrets.toml` konnte nicht gelesen werden "
        "(ein TOML-Syntaxfehler?). Korrigieren Sie die Datei und starten Sie die App neu. Bis "
        "dahin speichert diese App nichts, und der Chat antwortet nur, wenn der API-Schlüssel als "
        "Umgebungsvariable gesetzt ist (Ihre Fragen gehen dann über OpenRouter an das KI-Modell)."
    ),
    "role.coach": "Coach",
    "role.gymer": "Gymer",
    "role_choice.coach": "Coach · Ich begleite Ernährung und Training meiner Kunden",
    "role_choice.gymer": "Gymer · Ich erfasse meine eigene Ernährung und mein Training",
    "account.sign_in": "Mit Google anmelden",
    "account.sign_out": "Abmelden",
    "account.signed_in_google": "Mit Google angemeldet",
    "account.sign_in_off": (
        "Die Anmeldung ist aus: In dieser Kopie der App ist keine Google-Anmeldung eingerichtet. "
        "Sie können den Chat als Gast nutzen: Diese App speichert nichts, und Ihre Fragen (und "
        "Ihre Angaben, wenn eine Frage sie braucht) gehen über OpenRouter an das KI-Modell."
    ),
    "account.not_set_up": (
        "Die Anmeldung ist nicht vollständig eingerichtet: Ein Geheimnis in "
        "`.streamlit/secrets.toml` fehlt, ist kürzer als 32 Zeichen oder ist noch das aus dem "
        "Beispiel. Korrigieren Sie die Datei und starten Sie die App neu."
    ),
    "account.demo_user": "Demo-Nutzer",
    "account.demo_none": "Keiner (zurück zur Startseite)",
    "account.demo_note": (
        "Demo-Modus: erfundene Nutzer in einer temporären Datenbank, die beim Beenden der App "
        "gelöscht wird."
    ),
    "account.store_unavailable": (
        "Ihre gespeicherten Daten können gerade nicht geöffnet werden, daher wird nichts gelesen "
        "oder gespeichert. Versuchen Sie es später erneut oder starten Sie die App neu."
    ),
    "account.welcome_title": "Konto einrichten",
    "account.welcome_text": (
        "Wählen Sie Ihre Rolle und den Namen, den die App anzeigt (ein erfundener genügt). Die "
        "Datendatei der App speichert nur eine aus Ihrem Google-Konto gebildete ID (nie dessen "
        "Namen, E-Mail-Adresse oder Bild), Ihre Rolle und diesen Namen. Das Anmelde-Cookie in "
        "Ihrem Browser behält Ihren Google-Namen, Ihre E-Mail-Adresse und den Link zu Ihrem Bild, "
        "bis Sie sich abmelden (höchstens 30 Tage)."
    ),
    "account.role": "Ihre Rolle",
    "account.role_once": "Die Rolle wird einmal gewählt und kann in der App nicht geändert werden.",
    "account.display_name": "Anzeigename",
    "account.display_name_help": (
        "{low} bis {high} Zeichen: Buchstaben, Ziffern, Leerzeichen, Punkte, Bindestriche und "
        "Apostrophe. Nur in der App angezeigt, nie an das KI-Modell gesendet."
    ),
    "account.create": "Konto anlegen",
    "account.role_needed": "Wählen Sie eine Rolle.",
    "account.name_length": "Der Anzeigename braucht {low} bis {high} Zeichen.",
    "account.name_characters": (
        "Verwenden Sie nur Buchstaben, Ziffern, Leerzeichen, Punkte, Bindestriche und Apostrophe, "
        "beginnend mit einem Buchstaben oder einer Ziffer."
    ),
    "account.name_refused": (
        "Dieser Anzeigename kann nicht verwendet werden. Wählen Sie einen anderen."
    ),
    "account.exists": "Dieses Konto gibt es schon. Laden Sie die Seite neu.",
    "account.gone": "Ihr Konto gibt es nicht mehr (es wurde gelöscht). Laden Sie die Seite neu.",
    "account.no_identity": (
        "Die Anmeldung hat keine Konto-ID geliefert. Melden Sie sich ab und wieder an."
    ),
    "account.no_target": "Aus diesen Angaben ließ sich kein Tagesziel berechnen.",
    "profile.note_gymer": (
        "Für Ihr Konto gespeichert: Wenn Sie auf Speichern klicken (oder das Ziel ändern), werden "
        "Ihre Angaben, Ihr Gewicht und Ihre Tagesziele in der Datendatei dieser App auf diesem "
        "Computer gespeichert, ebenso das Essen und die Gewichte, die Sie unter Heute eintragen, "
        "und die Trainingseinheiten, die Sie unter Training eintragen. Verwenden Sie nur erfundene "
        "Daten: Geben Sie keine echten Gesundheitsdaten ein."
    ),
    "profile.note_coach": (
        "Nur für diese Sitzung: Die Angaben eines Coachs werden nicht gespeichert, gehen aber über "
        "OpenRouter an das KI-Modell, wenn eine Frage sie braucht. Ihr Konto (eine ID, Ihre Rolle "
        "und Ihr Anzeigename) wird in der Datendatei dieser App auf diesem Computer gespeichert. "
        "Chats werden nie gespeichert, aber die früheren Fragen und Antworten dieses Chats gehen "
        "mit jeder neuen Frage an das KI-Modell. Verwenden Sie nur erfundene Daten: Geben Sie "
        "keine echten Gesundheitsdaten ein."
    ),
    "profile.my_data_link": "Unter Meine Daten ansehen, exportieren oder löschen",
    "profile.saved_on_save": (
        "Wird beim Klick auf Speichern in Ihrem Konto gespeichert (Meine Daten listet es auf)."
    ),
    "profile.opt_in": (
        "Ich verstehe, dass meine Angaben, das Essen und die Gewichte, die ich unter Heute "
        "eintrage, und die Trainingseinheiten, die ich unter Training eintrage, in der Datendatei "
        "dieser App auf diesem Computer gespeichert werden, und ich gebe nur erfundene Daten ein."
    ),
    "profile.goal_not_saved": (
        "Das Ziel gilt nur für diese Sitzung: Speichern Sie zuerst Ihre Angaben unter "
        "Angaben bearbeiten (mit dem Häkchen dort)."
    ),
    "profile.opt_in_needed": (
        "Setzen Sie oben das Häkchen, um Ihre Angaben in Ihrem Konto zu speichern."
    ),
    "my_data.intro_gymer": (
        "Alles, was die App über Sie speichert: Ihr Konto und unten Ihre Einträge; Ihre "
        "Coach-Beziehungen, Ihre Freigaben und die Zugriffe Ihres Coachs auf Ihre Daten stehen im "
        "Export."
    ),
    "my_data.intro_coach": (
        "Alles, was die App über Sie speichert: Ihr Konto und, sobald Sie welche haben, Ihre "
        "Kunden und deren Auswertungen (sie stehen im Export). Ein Coach hat keine eigenen "
        "Einträge, und von Ihren Chats wird nichts gespeichert."
    ),
    "my_data.account": "**Konto:** {name} · {role} · angelegt am {created}",
    "my_data.count": "{count} gespeichert",
    "my_data.kind.profile_entries": "Profileinträge",
    "my_data.kind.body_measurements": "Gewichte",
    "my_data.kind.nutrition_targets": "Tagesziele",
    "my_data.kind.meal_items": "Ernährungstagebuch",
    "my_data.kind.workout_sessions": "Trainingseinheiten",
    "my_data.kind.preferences": "Vorlieben",
    "my_data.col.saved": "Gespeichert",
    "my_data.col.height": "Größe",
    "my_data.col.age": "Alter",
    "my_data.col.sex": "Geschlecht",
    "my_data.col.activity": "Aktivität",
    "my_data.col.goal": "Ziel",
    "my_data.col.day": "Tag",
    "my_data.col.weight": "Gewicht",
    "my_data.col.from": "Ab",
    "my_data.col.kcal": "kcal",
    "my_data.col.protein": "Eiweiß (g)",
    "my_data.col.carbohydrate": "Kohlenhydrate (g)",
    "my_data.col.fat": "Fett (g)",
    "my_data.col.set_by": "Festgelegt von",
    "my_data.col.meal": "Mahlzeit",
    "my_data.col.food": "Lebensmittel",
    "my_data.col.grams": "Menge",
    "my_data.col.sets": "Sätze",
    "my_data.col.text": "Text",
    "my_data.col.volume": "Volumen",
    "workouts.intro": (
        "Erfassen Sie eine Trainingseinheit: Wählen Sie den Tag, fügen Sie jeden Satz mit Übung, "
        "Wiederholungen, Gewicht und auf Wunsch dem RPE hinzu und speichern Sie sie. Darunter "
        "stehen die Einheiten und Summen Ihrer Woche."
    ),
    "workouts.stored_note": (
        "Für Ihr Konto gespeichert: Ihre Trainingseinheiten werden in der Datendatei dieser App "
        "auf diesem Computer gespeichert, und ein Coach sieht sie nur, solange Sie den "
        "Bereich Training freigeben. Verwenden Sie nur erfundene Daten: Geben Sie keine echten "
        "Gesundheitsdaten ein."
    ),
    "workouts.profile_first": (
        "Trainingseinheiten werden gespeichert, sobald Ihre Angaben gespeichert sind: Speichern "
        "Sie diese zuerst unter Mein Profil, mit dem Häkchen, dass Sie die Speicherung verstehen."
    ),
    "workouts.profile_link": "Zu Mein Profil",
    "workouts.my_data_link": "Unter Meine Daten ansehen, exportieren oder löschen",
    "workouts.log": "Trainingseinheit erfassen",
    "workouts.editing": "Trainingseinheit vom {day} bearbeiten",
    "workouts.day": "Tag",
    "workouts.exercise": "Übung",
    "workouts.reps": "Wiederholungen",
    "workouts.weight": "Gewicht ({unit})",
    "workouts.weight_help": (
        "Das bewegte Gewicht; 0 für einen Satz mit dem eigenen Körpergewicht ohne Zusatzgewicht."
    ),
    "workouts.rpe": "RPE (optional)",
    "workouts.rpe_help": (
        "Wie anstrengend sich der Satz anfühlte, von 1 (sehr leicht) bis 10 (maximale Anstrengung)."
    ),
    "workouts.add_set": "Satz hinzufügen",
    "workouts.remove_last": "Letzten Satz entfernen",
    "workouts.save": "Trainingseinheit speichern",
    "workouts.save_edit": "Änderungen speichern",
    "workouts.cancel_edit": "Bearbeiten abbrechen",
    "workouts.discard": "Entwurf verwerfen",
    "workouts.edit_blocked": (
        "Speichern, verwerfen oder brechen Sie zuerst die Trainingseinheit oben ab."
    ),
    "workouts.no_sets_yet": "Noch keine Sätze: Fügen Sie oben den ersten Satz hinzu.",
    "workouts.max_sets": "Eine Trainingseinheit hat höchstens {count} Sätze.",
    "workouts.saved": "Trainingseinheit gespeichert.",
    "workouts.not_saved": (
        "Die Trainingseinheit konnte nicht gespeichert werden: Prüfen Sie die Werte und "
        "speichern Sie erneut."
    ),
    "workouts.gone": (
        "Diese Trainingseinheit gibt es nicht mehr (sie wurde gelöscht). Erfassen Sie sie neu."
    ),
    "workouts.week": "Ihre Woche",
    "workouts.week_of": "Woche vom",
    "workouts.week_line": (
        "{start} bis {end} · Einheiten: {sessions} · Sätze: {sets} · Volumen: {volume}"
    ),
    "workouts.volume_note": (
        "Volumen ist Wiederholungen × Gewicht; ein Satz mit dem eigenen Körpergewicht ohne "
        "Zusatzgewicht zählt daher nicht mit."
    ),
    "workouts.none_this_week": "In dieser Woche ist kein Training erfasst.",
    "workouts.session_line": "**{day}** · Sätze: {sets} · Volumen: {volume}",
    "workouts.edit": "Bearbeiten",
    "workouts.delete": "Löschen",
    "workouts.col.set": "Satz",
    "workouts.col.exercise": "Übung",
    "workouts.col.reps": "Wiederholungen",
    "workouts.col.weight": "Gewicht",
    "workouts.col.rpe": "RPE",
    "workouts.col.sets": "Sätze",
    "workouts.col.volume": "Volumen",
    "workouts.col.top_weight": "Höchstes Gewicht",
    "muscle.chest": "Brust",
    "muscle.back": "Rücken",
    "muscle.legs": "Beine",
    "muscle.shoulders": "Schultern",
    "muscle.arms": "Arme",
    "muscle.core": "Rumpf",
    "my_data.grams": "{value} g",
    "my_data.set_by.system": "Die App",
    "my_data.set_by.user": "Sie",
    "my_data.meal.breakfast": "Frühstück",
    "my_data.meal.lunch": "Mittagessen",
    "my_data.meal.dinner": "Abendessen",
    "my_data.meal.snack": "Snack",
    "my_data.delete_one": "Einen Eintrag löschen",
    "my_data.entry": "Eintrag",
    "my_data.entry_placeholder": "Eintrag wählen",
    "my_data.delete_entry": "Diesen Eintrag löschen",
    "my_data.export": "Export",
    "my_data.export_note": "Alle Ihre Daten als eine JSON-Datei, erstellt, wenn Sie darum bitten.",
    "my_data.prepare_export": "Export vorbereiten",
    "my_data.download": "Meine Daten herunterladen (JSON)",
    "my_data.delete_all": "Alles löschen",
    "my_data.delete_all_note": (
        "Löscht Ihr Konto und jede Zeile über Sie und meldet Sie dann ab. Das kann nicht "
        "rückgängig gemacht werden."
    ),
    "my_data.confirm_delete_all": "Ja, mein Konto und alle meine Daten löschen",
    "my_data.delete_all_button": "Alles löschen",
    # Einladungen und Freigaben (T9.12).
    "page.clients": "Klienten",
    "page.sharing": "Coach und Freigaben",
    "scope.nutrition": "Ernährung",
    "scope.training": "Training",
    "scope.body": "Körper",
    "scope_help.nutrition": (
        "Ernährungstagebuch, Tagesziele und die Wochenberichte, die Ihr Coach freigibt (von "
        "einem KI-Modell entworfen)"
    ),
    "scope_help.training": "Trainingseinheiten",
    "scope_help.body": "Gewichte und Profileinträge (Größe, Alter, Geschlecht, Aktivität, Ziel)",
    "relationship.active": "Aktiv",
    "relationship.ended": "Beendet",
    "clients.intro": (
        "Ihre Klienten und was jeder von ihnen mit Ihnen teilt. Ein Klient entscheidet, was Sie "
        "sehen, und kann das jederzeit ändern oder die Verbindung beenden."
    ),
    "clients.none": (
        "Noch keine Klienten. Erstellen Sie unten eine Einladung und geben Sie den Code Ihrem "
        "Klienten."
    ),
    "clients.col.name": "Klient",
    "clients.col.status": "Status",
    "clients.col.since": "Seit",
    "clients.col.ended": "Beendet",
    "clients.shared": "Geteilt",
    "clients.not_shared": "Nicht geteilt",
    "clients.invitations": "Einladungen",
    "clients.invitations_note": (
        "Ein Code gilt einmal und läuft nach {days} Tagen ab. Geben Sie ihn selbst weiter, "
        "persönlich oder per Nachricht: Die App versendet keine E-Mails."
    ),
    "clients.create": "Einladung erstellen",
    "clients.new_code": (
        "Ihr neuer Code, nur jetzt angezeigt: Notieren Sie ihn oder geben Sie ihn weiter. Er läuft "
        "am {expires} (UTC) ab."
    ),
    "clients.noted": "Ich habe den Code notiert",
    "clients.open_codes": "Unbenutzte Codes",
    "clients.no_codes": "Keine unbenutzten Codes.",
    "clients.col.created": "Erstellt",
    "clients.col.expires": "Läuft ab",
    "clients.col.state": "Zustand",
    "clients.code_open": "Offen",
    "clients.code_expired": "Abgelaufen",
    "clients.code_label": "Erstellt {created} · läuft ab {expires}",
    "clients.cancel_pick": "Code zum Zurückziehen",
    "clients.cancel_placeholder": "Code wählen",
    "clients.cancel": "Diese Einladung zurückziehen",
    "sharing.unverified": "Die App prüft die Qualifikationen eines Coaches nicht.",
    "sharing.no_coach": (
        "Sie haben keinen Coach. Geben Sie den Code ein, den Ihr Coach Ihnen gegeben hat, und "
        "wählen Sie, was er sehen darf."
    ),
    "sharing.code": "Einladungscode",
    "sharing.code_help": (
        "{length} Buchstaben und Ziffern, z. B. ABCD-EFGH-JKLM; die Bindestriche sind optional."
    ),
    "sharing.choose": (
        "Ihr Coach sieht, was Sie hier teilen, auch die Tage, die Sie vor dem Teilen erfasst "
        "haben, und sieht immer Ihren Anzeigenamen. Sie können jederzeit ändern, was Sie teilen."
    ),
    "sharing.accept": "Einladung annehmen",
    "sharing.accepted": "Sie sind jetzt mit Ihrem Coach verbunden.",
    "sharing.refused.not_valid": (
        "Dieser Code kann nicht verwendet werden. Prüfen Sie ihn mit Ihrem Coach oder bitten Sie "
        "um einen neuen."
    ),
    "sharing.refused.limit": (
        "Sie haben heute {attempts} Codes versucht. Bitte versuchen Sie es morgen wieder."
    ),
    "sharing.refused.has_coach": (
        "Sie haben bereits einen Coach. Beenden Sie zuerst diese Verbindung."
    ),
    "sharing.coach": "**Ihr Coach:** {name} · seit {since}",
    "sharing.what": "Was Ihr Coach sieht",
    "sharing.save": "Freigaben speichern",
    "sharing.saved": "Ihre Freigaben sind gespeichert.",
    "sharing.end": "Verbindung beenden",
    "sharing.end_note": (
        "Ihr Coach kann dann keine Ihrer Einträge (Ernährung, Training, Körper) mehr lesen, sieht "
        "aber weiterhin Ihren Anzeigenamen sowie Beginn und Ende der Verbindung, bis einer von "
        "Ihnen sein Konto löscht. Ihre Einträge bleiben Ihre, und Sie können später einen neuen "
        "Code annehmen."
    ),
    "sharing.confirm_end": "Ja, die Verbindung mit meinem Coach beenden",
    "sharing.end_button": "Verbindung beenden",
    "sharing.ended": "Die Verbindung ist beendet.",
    "sharing.changed": (
        "Ihre Verbindung mit dem Coach hat sich inzwischen geändert; die Seite zeigt sie, wie sie "
        "jetzt ist."
    ),
    # Die Seite Heute: das Ernährungs- und Gewichtstagebuch (T9.13).
    "today.intro": (
        "Tragen Sie ein, was Sie gegessen haben, und Ihr Gewicht. Ein Tag ohne Einträge gilt als "
        "nicht eingetragen, nie als Tag ohne Essen."
    ),
    "today.made_up_only": (
        "Verwenden Sie nur erfundene Daten: Geben Sie keine echten Gesundheitsdaten ein."
    ),
    "today.profile_first": (
        "Speichern Sie zuerst Ihre Angaben unter Mein Profil (mit dem Häkchen, dass Sie verstehen, "
        "dass sie gespeichert werden). Danach können Sie hier Essen und Gewicht eintragen."
    ),
    "today.day": "Tag",
    "today.day_help": f"Heute oder bis zu {config.DIARY_MAX_DAYS_BACK} Tage zurück.",
    "today.add_food": "Lebensmittel hinzufügen",
    "today.food": "Lebensmittel",
    "today.food_placeholder": "Lebensmittel wählen",
    "today.grams": "Menge (g)",
    "today.meal": "Mahlzeit",
    "today.add": "Hinzufügen",
    "today.food_caption": (
        "Lebensmittel aus der USDA-Tabelle, auf Englisch. Jeder Eintrag behält die Nährwerte für "
        "die eingetragene Menge."
    ),
    "today.day_title": "Eingetragen am {day}",
    "today.nothing_logged": "An diesem Tag ist nichts eingetragen.",
    "today.meal_total": "**{meal}** · {kcal} kcal",
    "today.day_total": (
        "**Tagessumme:** {kcal} kcal · Protein {protein} g · Kohlenhydrate {carbohydrate} g · "
        "Fett {fat} g · Ballaststoffe {fiber}"
    ),
    "today.fiber_partial": "{value} g oder mehr (bei einigen Lebensmitteln nicht angegeben)",
    "today.col.food": "Lebensmittel",
    "today.col.grams": "Menge (g)",
    "today.col.kcal": "kcal",
    "today.col.protein": "Protein (g)",
    "today.col.carbohydrate": "Kohlenhydrate (g)",
    "today.col.fat": "Fett (g)",
    "today.col.fiber": "Ballaststoffe (g)",
    "today.edit_title": "Eintrag ändern oder löschen",
    "today.entry": "Eintrag",
    "today.entry_placeholder": "Eintrag wählen",
    "today.save_changes": "Änderungen speichern",
    "today.delete": "Eintrag löschen",
    "today.weight_title": "Gewicht",
    "today.weight_unit": "Gewicht ({unit})",
    "today.save_weight": "Gewicht speichern",
    "today.weights_logged": "An diesem Tag eingetragen: {weights}",
    "today.added": "Lebensmittel hinzugefügt.",
    "today.changed": "Eintrag geändert.",
    "today.deleted": "Eintrag gelöscht.",
    "today.weight_saved": "Gewicht gespeichert.",
    "today.gone": "Diesen Eintrag gibt es nicht mehr. Die Liste unten ist aktuell.",
    "today.stored_note": (
        "In der Datenbank dieser App gespeichert. Sie können es unter Meine Daten exportieren oder "
        "löschen; ein Coach sieht es nur, solange Sie Ernährung (Essen) oder Körper (Gewicht) mit "
        "dem Coach teilen."
    ),
    "diary.grams_range": (
        f"Geben Sie eine Menge von {plain(config.FOOD_MIN_GRAMS, 'de')} bis "
        f"{config.FOOD_MAX_GRAMS} g ein."
    ),
    "diary.meal_needed": "Wählen Sie eine Mahlzeit: Frühstück, Mittagessen, Abendessen oder Snack.",
    "diary.food_needed": "Wählen Sie ein Lebensmittel aus der Liste.",
    "diary.profile_first": (
        "Speichern Sie zuerst Ihre Angaben unter Mein Profil; hier wurde nichts gespeichert."
    ),
    "diary.food_table": (
        "Die Lebensmitteltabelle konnte nicht gelesen werden, daher wurde nichts gespeichert."
    ),
    "diary.day_range": (
        f"Wählen Sie heute oder einen Tag bis zu {config.DIARY_MAX_DAYS_BACK} Tage zurück."
    ),
    "diary.weight_range": (
        f"Geben Sie ein Gewicht von {plain(config.PROFILE_WEIGHT_KG_RANGE[0], 'de')} bis "
        f"{plain(config.PROFILE_WEIGHT_KG_RANGE[1], 'de')} kg ein (oder dasselbe in lb)."
    ),
}

TEXT: dict[Language, dict[str, str]] = {"en": _EN, "de": _DE}
