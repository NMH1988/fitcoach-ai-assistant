"""The fixed messages of src/: the guard, the guardrails, model errors, the key."""

from src import config
from src.i18n.core import de_number

# Values put into the texts once, at import.
_MAX_CHARS = config.MAX_INPUT_CHARS
_ADULT = config.PROFILE_AGE_RANGE[0]
_FLOOR = config.CALORIE_FLOOR_KCAL
_KEY = config.API_KEY_NAME

EN: dict[str, str] = {
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
    "key.missing": config.MISSING_KEY_MESSAGE,
    "key.secrets_file": config.SECRETS_FILE_MESSAGE,
}

DE: dict[str, str] = {
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
        f"Dieser Assistent berät nicht dazu, weniger als {de_number(_FLOOR)} kcal am Tag zu "
        "essen, und nicht zu Essweisen, die Ihrer Gesundheit schaden können. Wenn Essen, "
        "Ernährung oder Ihr Gewicht schwer zu bewältigen sind, sprechen Sie bitte mit einer "
        "Ärztin oder einem Arzt oder einer Ernährungsfachkraft; auch Beratungsstellen für "
        "Essstörungen können helfen."
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
    "key.missing": (
        "Der OpenRouter-API-Schlüssel fehlt. Tragen Sie ihn in `.streamlit/secrets.toml` ein oder "
        f"setzen Sie die Umgebungsvariable {_KEY} und starten Sie die App dann neu."
    ),
    "key.secrets_file": (
        "`.streamlit/secrets.toml` konnte nicht gelesen werden. Korrigieren Sie die Datei oder "
        f"setzen Sie die Umgebungsvariable {_KEY} und starten Sie die App dann neu."
    ),
}
