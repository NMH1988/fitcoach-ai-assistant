"""The texts of the weekly review, the questions to the coach under it, and notifications."""

from src import config

EN: dict[str, str] = {
    # In-app notifications (T9.29): the kind, the other side's name, the scope and the week only.
    "notifications.bell": "Notifications · {count} unread",
    "notifications.intro_coach": (
        "What changed with your clients: who connected, started or stopped sharing, which "
        "relationships ended, and the questions they asked under your weekly reviews. A "
        "notification shows a name, what is shared, a week and a time, never a client's values "
        "or the text of a question. Each time this page loads with notifications of your "
        "clients' questions, it counts as a read of those clients' questions, which each client "
        "sees in their export. New ones appear the next time a page loads."
    ),
    "notifications.intro_gymer": (
        "What changed with your coach: when you connected, when a coach approved a weekly review "
        "about you or answered your question under one, when your coach updated the foods they "
        "suggest, and when a relationship ended. A notification never shows the text of a review, "
        "a question or an answer, or a food. New ones appear the next time a page loads."
    ),
    "notifications.read_note": (
        "Mark all as read stores one mark with the time this list was loaded. Only you see it; "
        "it is in your export and deleted with your data."
    ),
    "notifications.none": "No notifications yet.",
    "notifications.new": "New",
    "notifications.mark_all": "Mark all as read",
    "notifications.unavailable": "Notifications could not be loaded just now.",
    "notifications.more": "Unread notifications not shown here: {count}. See Notifications.",
    "notifications.connected_coach": "{name} connected and shares: {scopes}.",
    "notifications.connected_coach_none": "{name} connected and shares nothing yet.",
    "notifications.connected_gymer": "You are connected with {name}.",
    "notifications.scope_started": "{name} started sharing {scopes}.",
    "notifications.scope_stopped": "{name} stopped sharing {scopes}.",
    "notifications.ended": "Your relationship with {name} ended.",
    "notifications.review_approved": "{name} approved your weekly review for the week of {week}.",
    # T9.30: the week only, never the question's or the answer's text.
    "notifications.question_asked": (
        "{name} asked a question under the weekly review for the week of {week}."
    ),
    "notifications.question_answered": (
        "{name} answered your question under the weekly review for the week of {week}."
    ),
    # T9.34: never a food or an amount.
    "notifications.suggestions_updated": "{name} updated the foods they suggest to you.",
    # Questions to the coach under an approved review (T9.25): never sent to a model.
    "questions.heading": "Questions to the coach",
    "questions.note": (
        "Your coach answers here, not an AI model, and your question is not sent to one. The "
        "answer is not medical advice, and the app does not check coaches' qualifications. For "
        "pain or an injury, see a doctor; in an emergency, call 112. Your question is stored in "
        "this app's data file on this computer until you delete everything on My data. Use "
        "made-up data only: do not enter real health data."
    ),
    "questions.ask_label": "Your question to the coach",
    "questions.ask": "Send question",
    "questions.sent": "Your question was sent. The coach sees it under this review.",
    "questions.waiting": "Your question is waiting for the coach's answer.",
    "questions.used_up": "You have asked {max} questions under this review, the most it takes.",
    # One fixed message for every refusal by the store (an ended relationship, a scope turned off),
    # for both sides; it names no scope, as the store gives the same NotFound for every refusal
    # (T9.25).
    "questions.closed": "Questions can no longer be asked or answered under this review.",
    "questions.refused": "This question was not sent.",
    "questions.empty": "Please type some text first.",
    "questions.too_long": "Please keep it to at most {max} characters.",
    "questions.none": "The client has not asked a question under this review.",
    "questions.answer_label": "Your answer",
    "questions.answer": "Send answer",
    "questions.answer_note": (
        "Your client reads your answer under this review. It is not sent to an AI model. Keep it "
        "to general guidance, and refer pain, injuries and medical questions to a doctor."
    ),
    "questions.answered": "Your answer was sent.",
    "questions.answered_already": "This question has an answer already.",
    "questions.open_weeks": (
        "Unanswered questions from this client under the reviews of the weeks of {weeks}. Pick the "
        "week to answer."
    ),
    "questions.label.my_question": "Your question · {time}",
    "questions.label.client_question": "The client's question · {time}",
    "questions.label.coach_answer": "Written by the coach, not by AI · {time}",
    "questions.label.my_answer": "Your answer · {time}",
    "review.none": "None",
    "review.status.PENDING_REVIEW": "Pending",
    "review.status.APPROVED": "Approved",
    "review.status.REJECTED": "Rejected",
    "review.status_line": "{status} · week of {week}",
    "review.heading": "Week of {week} · approved on {day}",
    "review.ai_label": "AI draft, approved by the coach",
    "review.ai_label_edited": "AI draft, edited and approved by the coach",
    # The weekly review on the coach's Client week page and the gymer's My week (T9.16).
    "review.section": "Weekly review",
    "review.intro": (
        "An AI model, reached through OpenRouter, drafts a review of a finished week from the "
        "numbers this client shares with you and the app's research sources. It gets the numbers "
        "for 'the client', never a name. You approve, edit or reject the draft; the client reads "
        "it only once you approve it. The app's checks do not catch every wording: check every "
        "figure, especially calories, before you approve."
    ),
    "review.not_finished": "A week can be reviewed once it is over, from the Monday after it.",
    "review.needs_nutrition": "A weekly review needs the client to share Nutrition.",
    "review.start": "Draft weekly review",
    "review.running": "Drafting the review. This can take a minute.",
    "review.pending": "Draft for the week of {week}, waiting for your decision",
    "review.rejected_note": "You rejected the draft for this week. You can draft a new one.",
    "review.approve": "Approve",
    "review.edit": "Edit",
    "review.reject": "Reject",
    "review.save_edit": "Approve my edit",
    "review.cancel_edit": "Cancel",
    "review.edit_help": (
        "Change the texts, or empty one to leave it out. The kind of each recommendation, its "
        "sources and the range quoted from a source stay as drafted."
    ),
    "review.observations": "Observations",
    "review.hypotheses": "Possible reasons",
    "review.recommendations": "Recommendations",
    "review.kind.nutrition": "Nutrition",
    "review.kind.training": "Training",
    "review.suggestion": "The model's suggestion, no source cited",
    "review.direction": "Direction",
    "review.source_range": "Range in the source",
    "review.population": "Studied in",
    # A recommendation's kcal fields (T10.2): shown beside its text, and in the edit form.
    # "Proposed", so the client does not read the figure as their current target.
    "review.target_kcal": "Proposed target",
    "review.kcal_change": "Proposed change",
    "review.kcal_per_day": "{value} kcal a day",
    "review.target_kcal_input": "Daily target (kcal)",
    "review.kcal_change_input": "Change to the current target (kcal a day)",
    "review.kcal_input_help": "Leave empty for none. A change is negative for a reduction.",
    "review.sources": "Sources",
    "review.source_line": "[S{number}] {title} ({year})",
    "review.outcome.pending": "The draft is ready below for your decision.",
    "review.outcome.not_found": (
        "This client does not share everything this review needs right now (or is no longer "
        "your client), so it cannot be drafted or decided."
    ),
    "review.outcome.exists": "A review of this week is already waiting or approved.",
    "review.outcome.not_finished": (
        "A week can be reviewed once it is over, from the Monday after it."
    ),
    "review.outcome.invalid": (
        "The model's draft did not pass the app's checks twice, so no review was saved. You can "
        "try again."
    ),
    "review.outcome.edit_invalid": "Your edit was not saved: {checks}",
    "review.outcome.approve_invalid": (
        "The draft was not approved: checked against the client's target today, {checks} Edit "
        "the figure or reject the draft."
    ),
    "review.outcome.approved": "Approved: the client can now read the review.",
    "review.outcome.edited": "Your edited review was approved: the client can now read it.",
    "review.outcome.rejected": "Rejected: the client will not see this draft.",
    "review.outcome.gone": (
        "This draft can no longer be approved or edited here: it was decided in another tab, "
        "or its run was lost. If it still shows as waiting, reject it, then draft the week again."
    ),
    "review.rate_window": (
        "You are starting reviews too fast. Please wait {seconds} s and try again."
    ),
    "review.rate_session": (
        "This session has reached its limit of {limit} requests to the AI model (questions and "
        "reviews)."
    ),
    "review.check.schema": "a section is empty or too long, or Observations has no text.",
    "review.check.calorie_floor": (
        "a recommendation, or a possible reason that cites a source, names a kcal figure below "
        f"{config.CALORIE_FLOOR_KCAL} kcal a day, or a recommendation's daily target, or the "
        f"current target plus its change, is below {config.CALORIE_FLOOR_KCAL} kcal a day; put "
        "the client's current intake in an "
        "observation and describe only the direction of the change, or write a change as "
        "'reduce intake by 300 kcal' or 'a 300 kcal deficit'."
    ),
    "review.check.observation_evidence": (
        "an observation cites a source; observations come from the week's figures only."
    ),
    "review.check.kcal_change_no_target": (
        "a recommendation changes the kcal target, but the client has no current target."
    ),
    "review.check.diagnosis": "a text names a medical condition or a diagnosis.",
    "review.check.training_uncited": "a training recommendation does not cite a training source.",
    "review.check.training_fields": (
        "a training recommendation needs its direction and the population studied."
    ),
    "review.check.source_range": "a training recommendation's range is not the source's.",
    "review.check.program": (
        "a training recommendation reads as a program (sets and reps, days, a plan)."
    ),
    "review.check.client_volume": (
        "a training recommendation gives the client's own sets or volume; that number is yours to "
        "set with the client."
    ),
    "review.check.number": "a number is not in the week's figures or the cited source.",
    "review.check.suggestion_label": "a recommendation's source label does not match its sources.",
    "review.check.unknown_evidence": "a text cites a source that was not found for this review.",
}

DE: dict[str, str] = {
    "notifications.bell": "Benachrichtigungen · {count} ungelesen",
    "notifications.intro_coach": (
        "Was sich bei Ihren Kunden geändert hat: wer sich verbunden hat, etwas zu teilen begonnen "
        "oder aufgehört hat, welche Verbindungen beendet sind und welche Fragen sie zu Ihren "
        "Wochenberichten gestellt haben. Eine Benachrichtigung zeigt einen Namen, was geteilt "
        "wird, eine Woche und eine Zeit, nie die Werte eines Kunden oder den Text einer Frage. "
        "Jedes Mal, wenn diese Seite mit Benachrichtigungen über Fragen Ihrer Kunden lädt, gilt "
        "das als Zugriff auf die Fragen dieser Kunden, den jeder Kunde in seinem Export sieht. "
        "Neue erscheinen, wenn eine Seite das nächste Mal lädt."
    ),
    "notifications.intro_gymer": (
        "Was sich bei Ihrem Coach geändert hat: wann Sie sich verbunden haben, wann ein Coach "
        "einen Wochenbericht über Sie freigegeben oder Ihre Frage dazu beantwortet hat, wann Ihr "
        "Coach die vorgeschlagenen Lebensmittel geändert hat und wann eine Verbindung beendet "
        "wurde. Eine Benachrichtigung zeigt nie den Text eines Berichts, einer Frage oder einer "
        "Antwort und kein Lebensmittel. Neue erscheinen, wenn eine Seite das nächste Mal lädt."
    ),
    "notifications.read_note": (
        "„Alle als gelesen markieren“ speichert eine Markierung mit der Zeit, zu der diese Liste "
        "geladen wurde. Nur Sie sehen sie; sie steht in Ihrem Export und wird mit Ihren Daten "
        "gelöscht."
    ),
    "notifications.none": "Noch keine Benachrichtigungen.",
    "notifications.new": "Neu",
    "notifications.mark_all": "Alle als gelesen markieren",
    "notifications.unavailable": "Die Benachrichtigungen konnten gerade nicht geladen werden.",
    "notifications.more": (
        "Hier nicht gezeigte ungelesene Benachrichtigungen: {count}. Siehe Benachrichtigungen."
    ),
    "notifications.connected_coach": "{name} hat sich verbunden und teilt: {scopes}.",
    "notifications.connected_coach_none": "{name} hat sich verbunden und teilt noch nichts.",
    "notifications.connected_gymer": "Sie sind mit {name} verbunden.",
    "notifications.scope_started": "{name} teilt jetzt {scopes}.",
    "notifications.scope_stopped": "{name} teilt {scopes} nicht mehr.",
    "notifications.ended": "Ihre Verbindung mit {name} ist beendet.",
    "notifications.review_approved": (
        "{name} hat Ihren Wochenbericht für die Woche vom {week} freigegeben."
    ),
    "notifications.question_asked": (
        "{name} hat eine Frage zum Wochenbericht für die Woche vom {week} gestellt."
    ),
    "notifications.question_answered": (
        "{name} hat Ihre Frage zum Wochenbericht für die Woche vom {week} beantwortet."
    ),
    "notifications.suggestions_updated": "{name} hat die vorgeschlagenen Lebensmittel geändert.",
    "questions.heading": "Fragen an den Coach",
    "questions.note": (
        "Ihr Coach antwortet hier, kein KI-Modell, und Ihre Frage wird an keines gesendet. Die "
        "Antwort ist keine medizinische Beratung, und die App prüft die Qualifikationen von "
        "Coaches nicht. Bei Schmerzen oder einer Verletzung wenden Sie sich an eine Ärztin oder "
        "einen Arzt; im Notfall rufen Sie 112 an. Ihre Frage wird in der Datendatei dieser App "
        "auf diesem Computer gespeichert, bis Sie unter Meine Daten alles löschen. Verwenden Sie "
        "nur erfundene Daten: Geben Sie keine echten Gesundheitsdaten ein."
    ),
    "questions.ask_label": "Ihre Frage an den Coach",
    "questions.ask": "Frage senden",
    "questions.sent": "Ihre Frage wurde gesendet. Der Coach sieht sie unter diesem Wochenbericht.",
    "questions.waiting": "Ihre Frage wartet auf die Antwort des Coachs.",
    "questions.used_up": (
        "Sie haben unter diesem Wochenbericht {max} Fragen gestellt, mehr sind nicht möglich."
    ),
    "questions.closed": (
        "Unter diesem Wochenbericht können keine Fragen mehr gestellt oder beantwortet werden."
    ),
    "questions.refused": "Diese Frage wurde nicht gesendet.",
    "questions.empty": "Geben Sie zuerst einen Text ein.",
    "questions.too_long": "Bitte schreiben Sie höchstens {max} Zeichen.",
    "questions.none": "Ihr Klient hat unter diesem Wochenbericht noch keine Frage gestellt.",
    "questions.answer_label": "Ihre Antwort",
    "questions.answer": "Antwort senden",
    "questions.answer_note": (
        "Ihr Klient liest Ihre Antwort unter diesem Wochenbericht. Sie wird an kein KI-Modell "
        "gesendet. Bleiben Sie bei allgemeinen Hinweisen und verweisen Sie bei Schmerzen, "
        "Verletzungen und medizinischen Fragen an eine Ärztin oder einen Arzt."
    ),
    "questions.answered": "Ihre Antwort wurde gesendet.",
    "questions.answered_already": "Diese Frage ist schon beantwortet.",
    "questions.open_weeks": (
        "Unbeantwortete Fragen dieses Klienten unter den Wochenberichten der Wochen ab {weeks}. "
        "Wählen Sie die Woche, um zu antworten."
    ),
    "questions.label.my_question": "Ihre Frage · {time}",
    "questions.label.client_question": "Frage Ihres Klienten · {time}",
    "questions.label.coach_answer": "Vom Coach geschrieben, nicht von der KI · {time}",
    "questions.label.my_answer": "Ihre Antwort · {time}",
    "review.none": "Keiner",
    "review.status.PENDING_REVIEW": "Offen",
    "review.status.APPROVED": "Freigegeben",
    "review.status.REJECTED": "Abgelehnt",
    "review.status_line": "{status} · Woche vom {week}",
    "review.heading": "Woche vom {week} · freigegeben am {day}",
    "review.ai_label": "KI-Entwurf, vom Coach freigegeben",
    "review.ai_label_edited": "KI-Entwurf, vom Coach bearbeitet und freigegeben",
    "review.section": "Wochenbericht",
    "review.intro": (
        "Ein KI-Modell, angebunden über OpenRouter, entwirft einen Bericht über eine "
        "abgeschlossene Woche aus den Zahlen, die dieser Klient mit Ihnen teilt, und den "
        "Forschungsquellen der App. Es erhält die Zahlen für 'den Klienten', nie einen Namen. Sie "
        "geben den Entwurf frei, bearbeiten oder verwerfen ihn; der Klient liest ihn erst nach "
        "Ihrer Freigabe. Die Prüfungen der App erkennen nicht jede Formulierung: Prüfen "
        "Sie vor der Freigabe jede Zahl, besonders die Kalorien."
    ),
    "review.not_finished": (
        "Eine Woche kann ausgewertet werden, wenn sie vorbei ist, ab dem Montag danach."
    ),
    "review.needs_nutrition": "Für einen Wochenbericht muss der Klient Ernährung teilen.",
    "review.start": "Wochenbericht entwerfen",
    "review.running": "Der Bericht wird entworfen. Das kann eine Minute dauern.",
    "review.pending": "Entwurf für die Woche vom {week}, wartet auf Ihre Entscheidung",
    "review.rejected_note": (
        "Sie haben den Entwurf für diese Woche verworfen. Sie können einen neuen entwerfen."
    ),
    "review.approve": "Freigeben",
    "review.edit": "Bearbeiten",
    "review.reject": "Verwerfen",
    "review.save_edit": "Meine Bearbeitung freigeben",
    "review.cancel_edit": "Abbrechen",
    "review.edit_help": (
        "Ändern Sie die Texte oder leeren Sie einen, um ihn wegzulassen. Die Art jeder "
        "Empfehlung, ihre Quellen und der aus einer Quelle zitierte Bereich bleiben wie entworfen."
    ),
    "review.observations": "Beobachtungen",
    "review.hypotheses": "Mögliche Gründe",
    "review.recommendations": "Empfehlungen",
    "review.kind.nutrition": "Ernährung",
    "review.kind.training": "Training",
    "review.suggestion": "Vorschlag des Modells, ohne Quelle",
    "review.direction": "Richtung",
    "review.source_range": "Bereich in der Quelle",
    "review.population": "Untersucht bei",
    "review.target_kcal": "Vorgeschlagenes Ziel",
    "review.kcal_change": "Vorgeschlagene Änderung",
    "review.kcal_per_day": "{value} kcal pro Tag",
    "review.target_kcal_input": "Tagesziel (kcal)",
    "review.kcal_change_input": "Änderung des aktuellen Ziels (kcal pro Tag)",
    "review.kcal_input_help": "Leer lassen, wenn keine. Eine Senkung ist negativ.",
    "review.sources": "Quellen",
    "review.source_line": "[S{number}] {title} ({year})",
    "review.outcome.pending": "Der Entwurf steht unten zu Ihrer Entscheidung bereit.",
    "review.outcome.not_found": (
        "Dieser Klient teilt derzeit nicht alles, was dieser Bericht braucht (oder ist nicht mehr "
        "Ihr Klient), daher kann er nicht entworfen oder entschieden werden."
    ),
    "review.outcome.exists": "Ein Bericht für diese Woche wartet bereits oder ist freigegeben.",
    "review.outcome.not_finished": (
        "Eine Woche kann ausgewertet werden, wenn sie vorbei ist, ab dem Montag danach."
    ),
    "review.outcome.invalid": (
        "Der Entwurf des Modells hat die Prüfungen der App zweimal nicht bestanden, daher wurde "
        "kein Bericht gespeichert. Sie können es erneut versuchen."
    ),
    "review.outcome.edit_invalid": "Ihre Bearbeitung wurde nicht gespeichert: {checks}",
    "review.outcome.approve_invalid": (
        "Der Entwurf wurde nicht freigegeben: geprüft am heutigen Ziel des Klienten, {checks} "
        "Ändern Sie die Zahl oder verwerfen Sie den Entwurf."
    ),
    "review.outcome.approved": "Freigegeben: Der Klient kann den Bericht jetzt lesen.",
    "review.outcome.edited": (
        "Ihr bearbeiteter Bericht wurde freigegeben: Der Klient kann ihn jetzt lesen."
    ),
    "review.outcome.rejected": "Verworfen: Der Klient sieht diesen Entwurf nicht.",
    "review.outcome.gone": (
        "Dieser Entwurf kann hier nicht mehr freigegeben oder bearbeitet werden: Er wurde in "
        "einem anderen Tab entschieden, oder sein Ablauf ging verloren. Wenn er noch als wartend "
        "erscheint, verwerfen Sie ihn und entwerfen Sie die Woche erneut."
    ),
    "review.rate_window": (
        "Sie starten Berichte zu schnell. Bitte warten Sie {seconds} s und versuchen Sie es erneut."
    ),
    "review.rate_session": (
        "Diese Sitzung hat ihr Limit von {limit} Anfragen an das KI-Modell erreicht (Fragen und "
        "Berichte)."
    ),
    "review.check.schema": (
        "ein Abschnitt ist leer oder zu lang, oder Beobachtungen hat keinen Text."
    ),
    "review.check.calorie_floor": (
        "eine Empfehlung oder ein möglicher Grund mit Quelle nennt eine kcal-Zahl unter "
        f"{config.CALORIE_FLOOR_KCAL} kcal pro Tag, oder das Tagesziel einer Empfehlung oder das "
        f"aktuelle Ziel plus ihre Änderung liegt unter {config.CALORIE_FLOOR_KCAL} kcal pro Tag; "
        "nennen Sie die aktuelle Zufuhr des Klienten in "
        "einer Beobachtung und beschreiben Sie nur die Richtung der Änderung, oder schreiben Sie "
        "eine Änderung als 'die Zufuhr um 300 kcal senken' oder '300 kcal weniger'."
    ),
    "review.check.observation_evidence": (
        "eine Beobachtung zitiert eine Quelle; Beobachtungen stammen nur aus den Zahlen der Woche."
    ),
    "review.check.kcal_change_no_target": (
        "eine Empfehlung ändert das kcal-Ziel, aber es gibt kein aktuelles Ziel."
    ),
    "review.check.diagnosis": "ein Text nennt eine Erkrankung oder eine Diagnose.",
    "review.check.training_uncited": "eine Trainingsempfehlung zitiert keine Trainingsquelle.",
    "review.check.training_fields": (
        "eine Trainingsempfehlung braucht ihre Richtung und die untersuchte Gruppe."
    ),
    "review.check.source_range": "der Bereich einer Trainingsempfehlung ist nicht der der Quelle.",
    "review.check.program": (
        "eine Trainingsempfehlung liest sich wie ein Trainingsplan (Sätze und Wiederholungen, "
        "Tage, ein Plan)."
    ),
    "review.check.client_volume": (
        "eine Trainingsempfehlung nennt eigene Sätze oder ein eigenes Volumen des Klienten; diese "
        "Zahl legen Sie mit dem Klienten fest."
    ),
    "review.check.number": "eine Zahl steht weder in den Zahlen der Woche noch in der Quelle.",
    "review.check.suggestion_label": (
        "die Quellenangabe einer Empfehlung passt nicht zu ihren Quellen."
    ),
    "review.check.unknown_evidence": (
        "ein Text zitiert eine Quelle, die für diesen Bericht nicht gefunden wurde."
    ),
}
