"""The chat's texts: steps, status, answer, sources, Details, tools, memory, usage."""

from src import config

# Values put into the texts once, at import.
_REWRITES = config.QUERY_REWRITES
_BUILD = config.BUILD_INDEX_COMMAND

EN: dict[str, str] = {
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
    "status.memory": "About remembering a preference",
    # Tool results.
    "tool.results": "Tool results ({count})",
    "tool.profile_needed": config.PROFILE_NEEDED_HINT,
    "tool.title.calculate_tdee": "Daily energy needs",
    "tool.title.calculate_macro_targets": "Daily targets",
    "tool.title.lookup_food_nutrition": "Food lookup",
    "tool.title.evaluate_meal_plan": "Meal plan check",
    "tool.title.none": "Tool call not run",
    # The coach's client tools (T9.17); a client's reference shows as their name on the page.
    "tool.title.list_my_clients": "Your clients this week",
    "tool.title.get_client_week": "A client's week",
    "tool.client_week.week": "Week",
    "tool.client_week.range": "{start} to {end}",
    "tool.client_week.kcal": "{average} / {target} kcal",
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
    # The share of the turn's input the provider's prompt cache served (T10.6).
    "usage.cached": (
        "Cached input: {cached} of {total} input tokens ({percent}), which saved {saved} at "
        "today's prices."
    ),
    "usage.cached_unpriced": (
        "Cached input: {cached} of {total} input tokens ({percent}); what it saved is not known, "
        "as a price could not be read."
    ),
    "usage.cached_none": "None of this answer's input came from the provider's prompt cache.",
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
        "Ask a question about nutrition or resistance training principles. Answers cite the "
        "research they use."
    ),
    "ask.placeholder": "Ask about nutrition or training principles",
    # The button that starts a new conversation (T9.4, AC-31).
    "ask.new_chat": "New chat",
    "ask.new_chat_help": (
        "Start a new conversation. The assistant forgets this one, and the summary and the session "
        "cost start again."
    ),
    # Under an answer the chat's memory did not keep (T10.1).
    "ask.not_remembered": (
        "This question and answer will not be remembered in this chat: the answer contains text "
        "that reads like an instruction to the assistant."
    ),
    # The coach's long-term memory (T9.7): the proposal card under the answer, and what follows.
    "memory.remember": "Remember: “{text}”?",
    "memory.note": (
        "A preference is about how you work: it is stored for your account and goes to the AI "
        "model, through OpenRouter, with each question, so your chats follow it. It must not hold "
        "a client's personal or health data: no names, ages, weights or conditions."
    ),
    "memory.save": "Save",
    "memory.edit": "Edit",
    "memory.discard": "Discard",
    "memory.edit_label": "Preference",
    "memory.save_edited": "Save edited",
    "memory.cancel_edit": "Cancel",
    "memory.locked": "Save, edit or discard the proposed preference first.",
    "memory.proposed": "I proposed a preference to remember; you decide whether it is saved.",
    "memory.ask_again": (
        "If you also asked something else, I found no source to answer it from: ask it again on "
        "its own."
    ),
    "memory.saved": "Saved. Your chats follow this preference; see or delete it in My data.",
    "memory.discarded": "Not saved: the preference was discarded.",
    "memory.failed": (
        "The preference could not be saved, as the data store is not available right now."
    ),
    "memory.refused.invalid": (
        "This cannot be saved as a preference: it must be one short text of at most "
        f"{config.PREFERENCE_MAX_CHARS} characters."
    ),
    "memory.refused.injection": (
        "This cannot be saved as a preference: it reads like an instruction to the assistant."
    ),
    "memory.refused.guardrail": (
        "This cannot be saved as a preference: it is about a medical topic, such as a condition, "
        "pregnancy or medication. A preference holds how you work, never a client's health data."
    ),
    "memory.refused.client_name": (
        "This cannot be saved as a preference: it names one of your clients. A preference holds "
        "how you work, never a client's personal data."
    ),
    "memory.refused.client_reference": (
        "This cannot be saved as a preference: it names one of your clients by their reference "
        "(such as client-2). A preference holds how you work, never a client's personal data."
    ),
    "memory.refused.one_per_turn": "Only one preference can be proposed at a time.",
    "answer.no_sources": config.NO_SOURCES_MESSAGE,
    # An answer that read as a written program, replaced in code (T10.5).
    "answer.program": config.NO_PROGRAM_SENTENCE["en"],
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
    "prompt.coach_missing": config.COACH_PROMPT_MISSING_MESSAGE,
    "turn.error": config.TURN_ERROR_MESSAGE,
    "prompt.review_missing": config.REVIEW_PROMPT_MISSING_MESSAGE,
}

DE: dict[str, str] = {
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
    "status.memory": "Zum Merken einer Vorliebe",
    "tool.results": "Werkzeugergebnisse ({count})",
    "tool.profile_needed": (
        "Diese Berechnung braucht Ihre Angaben. Geben Sie sie ein und fragen Sie dann noch einmal."
    ),
    "tool.title.calculate_tdee": "Täglicher Energiebedarf",
    "tool.title.calculate_macro_targets": "Tagesziele",
    "tool.title.lookup_food_nutrition": "Lebensmittelsuche",
    "tool.title.evaluate_meal_plan": "Essensplan-Check",
    "tool.title.none": "Werkzeugaufruf nicht ausgeführt",
    "tool.title.list_my_clients": "Ihre Klienten diese Woche",
    "tool.title.get_client_week": "Die Woche eines Klienten",
    "tool.client_week.week": "Woche",
    "tool.client_week.range": "{start} bis {end}",
    "tool.client_week.kcal": "{average} / {target} kcal",
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
    "usage.cached": (
        "Eingabe aus Cache: {cached} von {total} Eingabe-Token ({percent}), eine Ersparnis von "
        "{saved} zu den heutigen Preisen."
    ),
    "usage.cached_unpriced": (
        "Eingabe aus Cache: {cached} von {total} Eingabe-Token ({percent}); die Ersparnis ist "
        "nicht bekannt, da ein Preis nicht gelesen werden konnte."
    ),
    "usage.cached_none": "Keine Eingabe dieser Antwort kam aus dem Prompt-Cache des Anbieters.",
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
        "Stellen Sie eine Frage zur Ernährung oder zu Trainingsprinzipien im Krafttraining. Die "
        "Antworten zitieren die Forschung, die sie nutzen."
    ),
    "ask.placeholder": "Fragen Sie zu Ernährung oder Trainingsprinzipien",
    "ask.new_chat": "Neuer Chat",
    "ask.new_chat_help": (
        "Ein neues Gespräch beginnen. Der Assistent vergisst dieses, und die Zusammenfassung und "
        "die Kosten der Sitzung beginnen neu."
    ),
    "ask.not_remembered": (
        "Diese Frage und Antwort werden in diesem Chat nicht gemerkt: Die Antwort enthält Text, "
        "der wie eine Anweisung an den Assistenten klingt."
    ),
    "memory.remember": "Merken: „{text}“?",
    "memory.note": (
        "Eine Vorliebe beschreibt, wie Sie arbeiten: Sie wird für Ihr Konto gespeichert und geht "
        "mit jeder Frage über OpenRouter an das KI-Modell, damit Ihre Chats ihr folgen. Sie darf "
        "keine persönlichen oder Gesundheitsdaten von Kundinnen und Kunden enthalten: keine Namen, "
        "kein Alter, kein Gewicht und keine Erkrankungen."
    ),
    "memory.save": "Speichern",
    "memory.edit": "Bearbeiten",
    "memory.discard": "Verwerfen",
    "memory.edit_label": "Vorliebe",
    "memory.save_edited": "Bearbeitet speichern",
    "memory.cancel_edit": "Abbrechen",
    "memory.locked": "Speichern, bearbeiten oder verwerfen Sie zuerst die vorgeschlagene Vorliebe.",
    "memory.proposed": (
        "Ich habe eine Vorliebe zum Merken vorgeschlagen; Sie entscheiden, ob sie gespeichert wird."
    ),
    "memory.ask_again": (
        "Falls Sie noch etwas anderes gefragt haben, habe ich keine Quelle für eine Antwort "
        "gefunden: Stellen Sie diese Frage bitte noch einmal einzeln."
    ),
    "memory.saved": (
        "Gespeichert. Ihre Chats folgen dieser Vorliebe; unter „Meine Daten“ sehen oder löschen "
        "Sie sie."
    ),
    "memory.discarded": "Nicht gespeichert: Die Vorliebe wurde verworfen.",
    "memory.failed": (
        "Die Vorliebe konnte nicht gespeichert werden, da der Datenspeicher gerade nicht "
        "verfügbar ist."
    ),
    "memory.refused.invalid": (
        "Das kann nicht als Vorliebe gespeichert werden: Es muss ein kurzer Text mit höchstens "
        f"{config.PREFERENCE_MAX_CHARS} Zeichen sein."
    ),
    "memory.refused.injection": (
        "Das kann nicht als Vorliebe gespeichert werden: Es liest sich wie eine Anweisung an den "
        "Assistenten."
    ),
    "memory.refused.guardrail": (
        "Das kann nicht als Vorliebe gespeichert werden: Es geht um ein medizinisches Thema, etwa "
        "eine Erkrankung, eine Schwangerschaft oder Medikamente. Eine Vorliebe beschreibt, wie Sie "
        "arbeiten, nie Gesundheitsdaten von Kundinnen und Kunden."
    ),
    "memory.refused.client_name": (
        "Das kann nicht als Vorliebe gespeichert werden: Es nennt eine Ihrer Kundinnen oder einen "
        "Ihrer Kunden. Eine Vorliebe beschreibt, wie Sie arbeiten, nie persönliche Daten von "
        "Kundinnen und Kunden."
    ),
    "memory.refused.client_reference": (
        "Das kann nicht als Vorliebe gespeichert werden: Es nennt eine Ihrer Kundinnen oder einen "
        "Ihrer Kunden über die Referenz (etwa client-2). Eine Vorliebe beschreibt, wie Sie "
        "arbeiten, nie persönliche Daten von Kundinnen und Kunden."
    ),
    "memory.refused.one_per_turn": "Es kann jeweils nur eine Vorliebe vorgeschlagen werden.",
    "answer.program": config.NO_PROGRAM_SENTENCE["de"],
    "answer.no_sources": (
        "Unsere Quellen decken diese Frage nicht ab, daher gibt es keine Antwort aus der "
        "Forschung. Versuchen Sie eine Frage zu Protein, Kohlenhydraten, Fett, Energiebilanz, "
        "Nährstoff-Timing oder Nahrungsergänzung für Krafttraining oder zu Grundsätzen des "
        "Krafttrainings (Volumen, Last, Häufigkeit, Pausen, Progression)."
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
    "prompt.coach_missing": (
        "Der Coach-Teil des Antwort-Prompts (`src/prompts/answer_coach.md`) fehlt oder ist "
        "leer, daher kann keine Antwort geschrieben werden. Stellen Sie die Datei wieder her "
        "und fragen Sie erneut."
    ),
    "turn.error": (
        "Beim Beantworten Ihrer Frage ist etwas schiefgelaufen. Versuchen Sie es bitte erneut."
    ),
    "prompt.review_missing": (
        "Der Prompt für den Wochenbericht (`src/prompts/weekly_review_system.md`) fehlt oder ist "
        "leer, daher kann kein Bericht entworfen werden. Stellen Sie die Datei wieder her und "
        "versuchen Sie es erneut."
    ),
}
