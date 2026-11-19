"""The dashboards' texts: clients, client week and targets, My week, charts, workouts."""

EN: dict[str, str] = {
    "chart.kcal_per_day": "kcal per day",
    "chart.energy": "Energy",
    "chart.bar_alt": "Energy split per day: {parts}",
    "chart.donut_alt": "Daily target {total} kcal, energy split: {parts}",
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
    "clients.intro": (
        "Your clients and what each of them shares with you. A client chooses what you see, and "
        "can change it or end the relationship at any time."
    ),
    "clients.none": "No clients yet. Create an invitation below and give the code to your client.",
    "clients.col.name": "Client",
    "clients.col.since": "Since",
    "clients.col.ended": "Ended",
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
    "clients.unverified": (
        "The app does not check coaches' qualifications, yours included; your clients see the "
        "same note."
    ),
    "clients.this_week": "This week, {start} to {end}.",
    "clients.col.logged": "Days logged",
    "clients.col.kcal": "Avg kcal / target",
    "clients.col.sessions": "Sessions",
    "clients.col.weight": "Latest weight",
    "clients.col.review": "Weekly review",
    # The follow-up flag (T9.17): fewer logged days than config.FOLLOW_UP_MIN_LOGGED_DAYS, or no
    # workout, judged only on the scopes the client shares.
    "clients.col.follow_up": "Follow up",
    "clients.follow_up.none": "No",
    "clients.follow_up.flagged": "Yes: {reasons}",
    "clients.follow_up.few_logged_days": "few days logged",
    "clients.follow_up.no_session": "no workout",
    "clients.open_pick": "Open a client's week",
    "clients.open_placeholder": "Choose a client",
    "clients.open_week": "Open the week",
    "clients.former": "Former clients",
    "clients.former_note": (
        "Relationships that ended: on this page only the name and the days stay, and you can no "
        "longer read their data."
    ),
    "client_week.intro": (
        "One client's week, with only what they share with you. A day with nothing logged shows "
        "as not logged, never as a day without eating."
    ),
    "client_week.pick": "Client",
    "client_week.gone": "This client is no longer your active client.",
    # The coach's target form on Client week (T9.17).
    "client_targets.heading": "Daily targets",
    "client_targets.intro": (
        "Set this client's daily targets from today. The client sees them as set by you and cannot "
        "change them while they share nutrition with you; the energy target is never below "
        "{floor} kcal a day."
    ),
    "client_targets.not_shared": "Targets can be set only while the client shares nutrition.",
    "client_targets.kcal": "Energy (kcal a day)",
    "client_targets.protein": "Protein (g a day)",
    "client_targets.carbohydrate": "Carbohydrate (g a day)",
    "client_targets.fat": "Fat (g a day)",
    "client_targets.save": "Set targets",
    "client_targets.saved": "The new targets apply from {day}.",
    "client_targets.refused": (
        "The targets were not set: you cannot set targets for this client now."
    ),
    "client_targets.invalid": "The targets were not set: fill in every field within its range.",
    "client_week.no_clients": (
        "You have no active clients. Invite one on the Clients page, then open their week here."
    ),
    "my_week.intro": (
        "Your week: what you logged on Today and Workouts, and the weekly reviews a coach "
        "approved. This page only shows them; you log and change entries on those pages."
    ),
    "my_week.reviews": "Weekly reviews",
    "my_week.no_reviews": "No approved weekly review yet.",
    "week.week_of": "Week of",
    # The charts' day labels, Monday first, separated by commas.
    "week.weekdays": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
    "week.range": "{start} to {end}",
    "week.logged_days": "{logged} of {days} days logged",
    "week.nothing_logged": "Nothing logged",
    "week.kcal_vs_target": "{average} / {target} kcal",
    "week.kcal_no_target": "{average} kcal (no target)",
    "week.weight_on": "{weight} ({day})",
    "week.not_shared": "Not shared with you.",
    "week.average_line": (
        "Average over the logged days: {kcal} kcal, protein {protein} g, carbohydrate "
        "{carbohydrate} g, fat {fat} g."
    ),
    "week.target_line": "Daily target: {kcal} kcal, {source}, from {day}.",
    "week.target_by.system": "worked out from the profile",
    "week.target_by.user": "set by hand",
    "week.target_by.coach": "set by the coach",
    "week.no_target": "No daily target yet.",
    "week.kcal_heading": "Kcal per day",
    "week.macros_heading": "Macros: average per logged day against the target",
    "week.weight_heading": "Weight over {weeks} weeks",
    "week.weight_latest": "Latest weight: {weight}.",
    "week.weight_change": "Change since {day}: {change}.",
    "week.no_weight": "No weight logged up to this week.",
    "week.volume_heading": "Training volume per day",
    "chart.not_logged": "not logged",
    # The tooltips' titles (code review round 3), without the unit the value shows (round 4).
    "chart.day": "Day",
    "chart.macro": "Macro",
    "chart.series": "Average or target",
    "chart.per_day": "Per day",
    "chart.weight": "Weight",
    "chart.volume": "Volume",
    "chart.average": "Average",
    "chart.target": "Target",
    "chart.grams_per_day": "g per day",
    "chart.kcal_days_alt": "Kcal per day: {parts}",
    "chart.target_alt": "target {target} kcal",
    "chart.macros_alt": "Average per logged day against the target: {parts}",
    "chart.weight_axis": "Weight ({unit})",
    "chart.weight_alt": "Weights: {parts}",
    "chart.volume_axis": "Volume ({unit})",
    "chart.volume_alt": "Volume per day: {parts}",
    "chart.no_workout": "no workout",
}

DE: dict[str, str] = {
    "chart.kcal_per_day": "kcal pro Tag",
    "chart.energy": "Energie",
    "chart.bar_alt": "Energieaufteilung pro Tag: {parts}",
    "chart.donut_alt": "Tagesziel {total} kcal, Energieaufteilung: {parts}",
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
    "clients.intro": (
        "Ihre Klienten und was jeder von ihnen mit Ihnen teilt. Ein Klient entscheidet, was Sie "
        "sehen, und kann das jederzeit ändern oder die Verbindung beenden."
    ),
    "clients.none": (
        "Noch keine Klienten. Erstellen Sie unten eine Einladung und geben Sie den Code Ihrem "
        "Klienten."
    ),
    "clients.col.name": "Klient",
    "clients.col.since": "Seit",
    "clients.col.ended": "Beendet",
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
    "clients.unverified": (
        "Die App prüft die Qualifikationen von Coaches nicht, auch Ihre nicht; Ihre Klienten sehen "
        "denselben Hinweis."
    ),
    "clients.this_week": "Diese Woche, {start} bis {end}.",
    "clients.col.logged": "Erfasste Tage",
    "clients.col.kcal": "Ø kcal / Ziel",
    "clients.col.sessions": "Einheiten",
    "clients.col.weight": "Letztes Gewicht",
    "clients.col.review": "Wochenbericht",
    "clients.col.follow_up": "Nachfassen",
    "clients.follow_up.none": "Nein",
    "clients.follow_up.flagged": "Ja: {reasons}",
    "clients.follow_up.few_logged_days": "wenige Tage erfasst",
    "clients.follow_up.no_session": "kein Training",
    "clients.open_pick": "Woche eines Klienten öffnen",
    "clients.open_placeholder": "Klient wählen",
    "clients.open_week": "Woche öffnen",
    "clients.former": "Frühere Klienten",
    "clients.former_note": (
        "Beendete Verbindungen: Auf dieser Seite bleiben nur der Name sowie Beginn und Ende, und "
        "Sie können ihre Daten nicht mehr lesen."
    ),
    "client_week.intro": (
        "Die Woche eines Klienten, nur mit dem, was er mit Ihnen teilt. Ein Tag ohne Einträge "
        "erscheint als nicht erfasst, nie als Tag ohne Essen."
    ),
    "client_week.pick": "Klient",
    "client_week.gone": "Diese Person ist nicht mehr Ihr aktiver Klient.",
    "client_targets.heading": "Tagesziele",
    "client_targets.intro": (
        "Legen Sie die Tagesziele dieses Klienten ab heute fest. Der Klient sieht sie als von "
        "Ihnen gesetzt und kann sie nicht ändern, solange er die Ernährung mit Ihnen teilt; das "
        "Energieziel liegt nie unter {floor} kcal pro Tag."
    ),
    "client_targets.not_shared": (
        "Ziele können nur gesetzt werden, solange der Klient die Ernährung teilt."
    ),
    "client_targets.kcal": "Energie (kcal pro Tag)",
    "client_targets.protein": "Protein (g pro Tag)",
    "client_targets.carbohydrate": "Kohlenhydrate (g pro Tag)",
    "client_targets.fat": "Fett (g pro Tag)",
    "client_targets.save": "Ziele setzen",
    "client_targets.saved": "Die neuen Ziele gelten ab {day}.",
    "client_targets.refused": (
        "Die Ziele wurden nicht gesetzt: Sie können für diesen Klienten jetzt keine Ziele setzen."
    ),
    "client_targets.invalid": (
        "Die Ziele wurden nicht gesetzt: Füllen Sie jedes Feld innerhalb seines Bereichs aus."
    ),
    "client_week.no_clients": (
        "Sie haben keine aktiven Klienten. Laden Sie auf der Seite Klienten jemanden ein und "
        "öffnen Sie dann hier seine Woche."
    ),
    "my_week.intro": (
        "Ihre Woche: was Sie unter Heute und Training erfasst haben, und die freigegebenen "
        "Wochenberichte. Diese Seite zeigt sie nur an; Einträge erfassen und ändern Sie auf jenen "
        "Seiten."
    ),
    "my_week.reviews": "Wochenberichte",
    "my_week.no_reviews": "Noch kein freigegebener Wochenbericht.",
    "week.week_of": "Woche vom",
    "week.weekdays": "Mo,Di,Mi,Do,Fr,Sa,So",
    "week.range": "{start} bis {end}",
    "week.logged_days": "{logged} von {days} Tagen erfasst",
    "week.nothing_logged": "Nichts erfasst",
    "week.kcal_vs_target": "{average} / {target} kcal",
    "week.kcal_no_target": "{average} kcal (kein Ziel)",
    "week.weight_on": "{weight} ({day})",
    "week.not_shared": "Nicht mit Ihnen geteilt.",
    "week.average_line": (
        "Durchschnitt über die erfassten Tage: {kcal} kcal, Eiweiß {protein} g, Kohlenhydrate "
        "{carbohydrate} g, Fett {fat} g."
    ),
    "week.target_line": "Tagesziel: {kcal} kcal, {source}, ab {day}.",
    "week.target_by.system": "aus dem Profil berechnet",
    "week.target_by.user": "von Hand gesetzt",
    "week.target_by.coach": "vom Coach gesetzt",
    "week.no_target": "Noch kein Tagesziel.",
    "week.kcal_heading": "Kcal pro Tag",
    "week.macros_heading": "Makronährstoffe: Durchschnitt pro erfasstem Tag gegenüber dem Ziel",
    "week.weight_heading": "Gewicht über {weeks} Wochen",
    "week.weight_latest": "Letztes Gewicht: {weight}.",
    "week.weight_change": "Veränderung seit {day}: {change}.",
    "week.no_weight": "Bis zu dieser Woche ist kein Gewicht erfasst.",
    "week.volume_heading": "Trainingsvolumen pro Tag",
    "chart.not_logged": "nicht erfasst",
    "chart.day": "Tag",
    "chart.macro": "Makronährstoff",
    "chart.series": "Durchschnitt oder Ziel",
    "chart.per_day": "Pro Tag",
    "chart.weight": "Gewicht",
    "chart.volume": "Volumen",
    "chart.average": "Durchschnitt",
    "chart.target": "Ziel",
    "chart.grams_per_day": "g pro Tag",
    "chart.kcal_days_alt": "Kcal pro Tag: {parts}",
    "chart.target_alt": "Ziel {target} kcal",
    "chart.macros_alt": "Durchschnitt pro erfasstem Tag gegenüber dem Ziel: {parts}",
    "chart.weight_axis": "Gewicht ({unit})",
    "chart.weight_alt": "Gewichte: {parts}",
    "chart.volume_axis": "Volumen ({unit})",
    "chart.volume_alt": "Volumen pro Tag: {parts}",
    "chart.no_workout": "kein Training",
}
