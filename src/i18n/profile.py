"""The texts of the profile: the form, the sidebar, its validation, and the daily targets."""

from src import config

EN: dict[str, str] = {
    "language.label": "Language",
    "theme.hint": config.THEME_HINT,
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
    # A gymer's active target when their coach set it (T9.17): read-only for the gymer.
    "targets.coach_set": (
        "Your coach set your daily target from {day}: {kcal} kcal, {protein} g protein, "
        "{carbohydrate} g carbohydrate and {fat} g fat. While you share nutrition with your coach, "
        "only they can change it, and saving your details does not replace it. The targets below "
        "are worked out from your details, for comparison."
    ),
    "targets.computed_not_active": (
        "Worked out from your details. Your active target is the one your coach set (My profile)."
    ),
    "profile.coach_target_kept": (
        "Your details are saved. Your daily target stays the one your coach set."
    ),
    "targets.at_maintenance": "{goal}: at maintenance",
    "targets.above_maintenance": "{goal}: {kcal} kcal above maintenance",
    "targets.below_maintenance": "{goal}: {kcal} kcal below maintenance",
    "targets.empty": "Add your details to get your daily energy and macro targets.",
    "targets.share": "{percent}% of kcal · {per_weight}",
    "targets.protein_warning": "{note} The sources' protein range for your weight: {range}.",
    "targets.protein_range": "{low}-{high} g a day ({per_low} to {per_high})",
    "targets.maintenance": "Maintenance (daily energy needs): about {kcal} kcal/day. {method}",
    "targets.sources": "Sources:",
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
    "nutrient.energy": "Energy",
    "nutrient.protein": "Protein",
    "nutrient.carbohydrate": "Carbohydrate",
    "nutrient.fat": "Fat",
    "nutrient.fiber": "Fiber",
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
        "display name) and the working preferences you save in the chat are stored in this app's "
        "data file on this computer; your newest preferences go to the AI model, through "
        "OpenRouter, with each question. Chats are never stored, but this chat's earlier "
        "questions and answers go to the AI model with each new question. Food names from a "
        "question may also go to USDA's FoodData Central API (US), when this copy of the app has "
        "its key. When you ask about your clients, the figures they share go to the AI model "
        "through OpenRouter, under a reference, never their names. Use made-up data only: "
        "do not enter real health data."
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
}

DE: dict[str, str] = {
    "language.label": "Sprache",
    "theme.hint": (
        ":material/dark_mode: Hell oder dunkel: Menü :material/more_vert: oben rechts "
        "(Light, Dark, System)"
    ),
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
    "targets.coach_set": (
        "Ihr Coach hat Ihr Tagesziel ab {day} gesetzt: {kcal} kcal, {protein} g Protein, "
        "{carbohydrate} g Kohlenhydrate und {fat} g Fett. Solange Sie die Ernährung mit Ihrem "
        "Coach teilen, kann nur er es ändern, und das Speichern Ihrer Angaben ersetzt es nicht. "
        "Die Ziele unten sind aus Ihren Angaben berechnet, zum Vergleich."
    ),
    "targets.computed_not_active": (
        "Aus Ihren Angaben berechnet. Ihr aktives Ziel ist das von Ihrem Coach gesetzte "
        "(Mein Profil)."
    ),
    "profile.coach_target_kept": (
        "Ihre Angaben sind gespeichert. Ihr Tagesziel bleibt das von Ihrem Coach gesetzte."
    ),
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
    "nutrient.energy": "Energie",
    "nutrient.protein": "Protein",
    "nutrient.carbohydrate": "Kohlenhydrate",
    "nutrient.fat": "Fett",
    "nutrient.fiber": "Ballaststoffe",
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
        "und Ihr Anzeigename) und die Arbeitsvorlieben, die Sie im Chat speichern, werden in der "
        "Datendatei dieser App auf diesem Computer gespeichert; Ihre neuesten Vorlieben gehen mit "
        "jeder Frage über OpenRouter an das KI-Modell. Chats werden nie gespeichert, aber die "
        "früheren Fragen und Antworten dieses Chats gehen mit jeder neuen Frage an das KI-Modell. "
        "Lebensmittelnamen aus einer Frage können außerdem an die FoodData Central API des USDA "
        "(USA) gehen, wenn diese Kopie der App ihren Schlüssel hat. Wenn Sie nach Ihren Klienten "
        "fragen, gehen die Zahlen, die sie teilen, über OpenRouter an das KI-Modell, unter einer "
        "Referenz, nie mit ihrem Namen. "
        "Verwenden Sie nur erfundene Daten: Geben Sie keine echten Gesundheitsdaten ein."
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
}
