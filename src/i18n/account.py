"""The texts of the account: sign-in, roles, My data, sharing and its scopes."""

EN: dict[str, str] = {
    "account.guest_note": (
        "You are using the app as a guest: this app stores nothing; your questions (and your "
        "details, when a question needs them) go to the AI model through OpenRouter."
        " Food names from a question may also go to USDA's FoodData Central API (US), when this "
        "copy of the app has its key."
    ),
    "account.secrets_broken": (
        "Sign-in is off: `.streamlit/secrets.toml` could not be read (a TOML syntax error?). Fix "
        "the file and restart the app. Until then this app stores nothing, and the chat answers "
        "only if the API key is set as an environment variable (your questions then go to the AI "
        "model through OpenRouter)."
        " Food names from a question may also go to USDA's FoodData Central API (US), when this "
        "copy of the app has its key."
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
        " Food names from a question may also go to USDA's FoodData Central API (US), when this "
        "copy of the app has its key."
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
    "account.demo_trace_note": (
        "Tracing is on without masking (demo only): what you type here is sent to LangSmith and "
        "can be read there. Enter made-up data only."
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
    "my_data.intro_gymer": (
        "Everything the app stores about you: your account and your records below; your coach "
        "relationships, sharing choices, the foods your coaches suggested to you, your questions "
        "to the coach with the answers, your coach's reads of your data and your notification "
        "read mark (when you last marked your notifications as read) are in the export."
    ),
    "my_data.intro_coach": (
        "Everything the app stores about you: your account, the working preferences you saved in "
        "the chat, your clients, their reviews and the questions and answers under them once you "
        "have some, and your notification read mark (when you last marked your notifications as "
        "read); they are in the export. The foods you suggest to a client are stored as the "
        "client's data: your export holds when you saved each list. Nothing else of your chats "
        "is stored."
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
    "my_data.grams": "{value} g",
    "my_data.set_by.system": "The app",
    "my_data.set_by.user": "You",
    "my_data.set_by.coach": "Your coach",
    "my_data.coach_target_note": (
        "A target your coach set cannot be deleted on its own; Delete everything below removes it."
    ),
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
    "scope.nutrition": "Nutrition",
    "scope.training": "Training",
    "scope.body": "Body",
    # T9.16: what a weekly review sends, as the gymer agrees to it by ticking a scope.
    "scope_help.nutrition": (
        "Food log, daily targets, the foods your coach suggests (and how much you log from them "
        "while you share) and the weekly reviews your coach approves. When your coach "
        "starts a weekly review, this week's figures (averages and totals, not your name or "
        "foods) go to an AI model through OpenRouter, which drafts the review"
    ),
    "scope_help.training": (
        "Workouts. While shared, a weekly review your coach starts also sends this week's "
        "training figures (sessions, and for each exercise its sets, reps, volume and top weight) "
        "to that AI model"
    ),
    "scope_help.body": (
        "Weights and profile entries (height, age, sex, activity, goal). While shared, a weekly "
        "review your coach starts also sends this week's weight figures to that AI model"
    ),
    # T9.17: what the coach's assistant sends, shown once above the scope boxes, so a gymer knows
    # what sharing a scope sends to a model (wording approved by the owner).
    "sharing.assistant": (
        "While a scope is shared, your coach can also ask the app's AI assistant about your "
        "weeks: that scope's figures (each day's totals, averages, your target, weight or "
        "training figures), for any week your coach asks about, go to the AI model through "
        "OpenRouter, under a reference, never your name."
    ),
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
        "and always sees your display name. You can change what you share at any time. Your "
        "coach is told when you start or stop sharing something, and sees these changes and their "
        "times until one of you deletes their data. Your coach is also told when you ask a "
        "question under a weekly review, while they may read it. Your export records it as a "
        "read of your questions when your coach opens their Notifications page, not when the "
        "sidebar count or a pop-up tells them."
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
        "your display name, the dates of the relationship and when you started or stopped sharing "
        "something until one of you deletes their account. Your records stay yours, and you can "
        "accept a new code later."
    ),
    "sharing.confirm_end": "Yes, end the relationship with my coach",
    "sharing.end_button": "End the relationship",
    "sharing.ended": "The relationship has ended.",
    "sharing.changed": (
        "Your coach relationship changed in the meantime; the page shows it as it is now."
    ),
}

DE: dict[str, str] = {
    "account.guest_note": (
        "Sie nutzen die App als Gast: Diese App speichert nichts; Ihre Fragen (und Ihre Angaben, "
        "wenn eine Frage sie braucht) gehen über OpenRouter an das KI-Modell."
        " Lebensmittelnamen aus einer Frage können außerdem an die FoodData Central API des USDA "
        "(USA) gehen, wenn diese Kopie der App ihren Schlüssel hat."
    ),
    "account.secrets_broken": (
        "Die Anmeldung ist aus: `.streamlit/secrets.toml` konnte nicht gelesen werden "
        "(ein TOML-Syntaxfehler?). Korrigieren Sie die Datei und starten Sie die App neu. Bis "
        "dahin speichert diese App nichts, und der Chat antwortet nur, wenn der API-Schlüssel als "
        "Umgebungsvariable gesetzt ist (Ihre Fragen gehen dann über OpenRouter an das KI-Modell)."
        " Lebensmittelnamen aus einer Frage können außerdem an die FoodData Central API des USDA "
        "(USA) gehen, wenn diese Kopie der App ihren Schlüssel hat."
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
        " Lebensmittelnamen aus einer Frage können außerdem an die FoodData Central API des USDA "
        "(USA) gehen, wenn diese Kopie der App ihren Schlüssel hat."
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
    "account.demo_trace_note": (
        "Das Tracing läuft ohne Maskierung (nur Demo): Was Sie hier eingeben, wird an LangSmith "
        "gesendet und ist dort lesbar. Geben Sie nur erfundene Daten ein."
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
    "my_data.intro_gymer": (
        "Alles, was die App über Sie speichert: Ihr Konto und unten Ihre Einträge; Ihre "
        "Coach-Beziehungen, Ihre Freigaben, die Lebensmittel, die Ihre Coachs Ihnen vorgeschlagen "
        "haben, Ihre Fragen an den Coach mit den Antworten, die "
        "Zugriffe Ihres Coachs auf Ihre Daten und Ihre Lesemarkierung der Benachrichtigungen (wann "
        "Sie sie zuletzt als gelesen markiert haben) stehen im Export."
    ),
    "my_data.intro_coach": (
        "Alles, was die App über Sie speichert: Ihr Konto, die Arbeitsvorlieben, die Sie im Chat "
        "gespeichert haben, Ihre Kunden, deren Auswertungen und die Fragen und Antworten darunter, "
        "sobald Sie welche haben, und Ihre Lesemarkierung der Benachrichtigungen (wann Sie sie "
        "zuletzt als gelesen markiert haben); sie stehen im Export. Die Lebensmittel, die Sie "
        "einem Klienten vorschlagen, werden als Daten des Klienten gespeichert: Ihr Export "
        "enthält, wann Sie jede Liste gespeichert haben. Sonst wird von Ihren Chats nichts "
        "gespeichert."
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
    "my_data.grams": "{value} g",
    "my_data.set_by.system": "Die App",
    "my_data.set_by.user": "Sie",
    "my_data.set_by.coach": "Ihr Coach",
    "my_data.coach_target_note": (
        "Ein Ziel, das Ihr Coach gesetzt hat, kann nicht einzeln gelöscht werden; „Alles löschen“ "
        "unten entfernt es."
    ),
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
    "scope.nutrition": "Ernährung",
    "scope.training": "Training",
    "scope.body": "Körper",
    "scope_help.nutrition": (
        "Ernährungstagebuch, Tagesziele, die Lebensmittel, die Ihr Coach vorschlägt (und wie viel "
        "Sie davon erfassen, solange Sie teilen), und die Wochenberichte, die Ihr Coach freigibt. "
        "Wenn Ihr "
        "Coach einen Wochenbericht startet, gehen die Zahlen dieser Woche (Durchschnitte und "
        "Summen, nicht Ihr Name oder Ihre Lebensmittel) über OpenRouter an ein KI-Modell, das "
        "den Bericht entwirft"
    ),
    "scope_help.training": (
        "Trainingseinheiten. Solange geteilt, sendet ein Wochenbericht Ihres Coaches auch die "
        "Trainingszahlen dieser Woche (Einheiten und je Übung Sätze, Wiederholungen, Volumen und "
        "Höchstgewicht) an dieses KI-Modell"
    ),
    "scope_help.body": (
        "Gewichte und Profileinträge (Größe, Alter, Geschlecht, Aktivität, Ziel). Solange "
        "geteilt, sendet ein Wochenbericht Ihres Coaches auch die Gewichtszahlen dieser Woche an "
        "dieses KI-Modell"
    ),
    "sharing.unverified": "Die App prüft die Qualifikationen eines Coaches nicht.",
    "sharing.assistant": (
        "Solange ein Bereich geteilt ist, kann Ihr Coach auch den KI-Assistenten der App nach "
        "Ihren Wochen fragen: Die Zahlen dieses Bereichs (Tagessummen, Durchschnitte, Ihr Ziel, "
        "Gewichts- oder Trainingszahlen) gehen für jede Woche, nach der Ihr Coach fragt, über "
        "OpenRouter an das KI-Modell, unter einer Referenz, nie mit Ihrem Namen."
    ),
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
        "haben, und sieht immer Ihren Anzeigenamen. Sie können jederzeit ändern, was Sie teilen. "
        "Ihr Coach wird benachrichtigt, wenn Sie etwas zu teilen beginnen oder aufhören, und sieht "
        "diese Änderungen mit ihren Zeiten, bis einer von Ihnen seine Daten löscht. Ihr Coach "
        "wird auch benachrichtigt, wenn Sie eine Frage zu einem Wochenbericht stellen, solange er "
        "sie lesen darf. Ihr Export verzeichnet es als Zugriff auf Ihre Fragen, wenn Ihr Coach "
        "seine Benachrichtigungsseite öffnet, nicht wenn die Anzeige in der Seitenleiste oder ein "
        "Hinweisfenster es ihm mitteilt."
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
        "aber weiterhin Ihren Anzeigenamen, Beginn und Ende der Verbindung sowie, wann Sie etwas "
        "zu teilen begonnen oder aufgehört haben, bis einer von Ihnen sein Konto löscht. Ihre "
        "Einträge bleiben Ihre, und Sie können später einen neuen Code annehmen."
    ),
    "sharing.confirm_end": "Ja, die Verbindung mit meinem Coach beenden",
    "sharing.end_button": "Verbindung beenden",
    "sharing.ended": "Die Verbindung ist beendet.",
    "sharing.changed": (
        "Ihre Verbindung mit dem Coach hat sich inzwischen geändert; die Seite zeigt sie, wie sie "
        "jetzt ist."
    ),
}
