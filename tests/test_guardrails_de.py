"""Tests for the German domain guardrails in src/guardrails.py and the guard (T7.4)."""

import time

import pytest

from src import config, guard, guardrails, i18n
from src.guardrails import Concern
from tests.test_guard_de import BENIGN as GUARD_BENIGN

# Strings written for this project, one or more per pattern family, with ü/ue/u and ß/ss.
FLAGGED = [
    # Performance-enhancing drug dosing or use (refused).
    ("Wie viel Anabolika sollte ich für meine erste Kur nehmen?", Concern.PED_DOSING),
    ("Welche Dosis Trenbolon für Anfänger?", Concern.PED_DOSING),
    ("Welche Dosis Trenbolon fuer Anfaenger?", Concern.PED_DOSING),
    ("Wo kann ich SARMs kaufen?", Concern.PED_DOSING),
    ("Wie spritze ich Testosteron richtig?", Concern.PED_DOSING),
    ("Ich bin gerade auf einer Steroidkur, wie viel Protein brauche ich?", Concern.PED_DOSING),
    ("Wie lange sollte ein Zyklus mit Oxandrolon dauern?", Concern.PED_DOSING),
    ("Wachstumshormon spritzen: ab welcher Dosis wirkt es?", Concern.PED_DOSING),
    ("Was ist die sicherste Dosis für leistungssteigernde Mittel?", Concern.PED_DOSING),
    ("Ich nehme Nandrolon, wie viel Eiweiß brauche ich?", Concern.PED_DOSING),
    ("Wie viel Anabolika für große Muskeln?", Concern.PED_DOSING),
    ("Soll ich eine Testo-Kur machen, um schneller aufzubauen?", Concern.PED_DOSING),
    ("Wie viel Ostarine pro Tag?", Concern.PED_DOSING),
    ("Wie dosiere ich Anavar richtig?", Concern.PED_DOSING),
    ("Ich will mit Steroiden anfangen, was muss ich essen?", Concern.PED_DOSING),
    ("Wie viel Testosteron-Enantat pro Woche?", Concern.PED_DOSING),
    # Under 18 (redirected).
    ("Ich bin 16 und will Muskeln aufbauen.", Concern.MINOR),
    ("Ich bin erst fünfzehn Jahre alt, wie viel Protein?", Concern.MINOR),
    ("Ich bin erst fuenfzehn Jahre alt, wie viel Protein?", Concern.MINOR),
    ("Ich bin gerade 17 geworden, darf ich Kreatin nehmen?", Concern.MINOR),
    ("Ist Kreatin für einen 14-Jährigen sicher?", Concern.MINOR),
    ("Mein 16-jähriger Sohn will zunehmen.", Concern.MINOR),
    ("Was soll mein 8-jähriger Sohn vor dem Fußball essen?", Concern.MINOR),
    ("Für meinen 8-Jährigen: gesunde Snacks?", Concern.MINOR),
    ("Ernährungsplan für Jugendliche im Fußballverein?", Concern.MINOR),
    ("Ist Whey für Teenager geeignet?", Concern.MINOR),
    ("Ich bin unter 18, kann ich Pre-Workout nehmen?", Concern.MINOR),
    ("Ich bin noch minderjährig, wie viel Kreatin?", Concern.MINOR),
    ("Dürfen Kinder Proteinshakes trinken?", Concern.MINOR),
    ("Ich gehe noch zur Schule und trainiere dreimal pro Woche.", Concern.MINOR),
    ("Ich bin in der 10. Klasse und will abnehmen.", Concern.MINOR),
    ("Soll meine kleine Tochter Eiweißpulver nehmen?", Concern.MINOR),
    # Pregnancy, after birth, breastfeeding (redirected).
    ("Ich bin schwanger, darf ich weiter Kreatin nehmen?", Concern.PREGNANCY),
    ("Was soll ich in der Schwangerschaft essen, um fit zu bleiben?", Concern.PREGNANCY),
    ("Ich stille noch, wie viel Protein brauche ich?", Concern.PREGNANCY),
    ("Proteinbedarf in der Stillzeit?", Concern.PREGNANCY),
    ("Wie verliere ich nach der Geburt Bauchfett?", Concern.PREGNANCY),
    ("Wir haben Kinderwunsch, sollte ich Koffein reduzieren?", Concern.PREGNANCY),
    ("Im zweiten Trimester trainieren: was essen?", Concern.PREGNANCY),
    ("Ich erwarte ein Baby und will fit bleiben.", Concern.PREGNANCY),
    ("Ist Koffein beim Stillen ok?", Concern.PREGNANCY),
    # Found in the review of PR #65: the user's own hunger next to "stillen".
    ("Ich stille und habe Hunger, was soll ich essen?", Concern.PREGNANCY),
    ("Beim Stillen habe ich Hunger, was essen?", Concern.PREGNANCY),
    ("Ich stille und habe Durst, wie viel trinken?", Concern.PREGNANCY),
    ("Während des Stillens Heißhunger: was hilft?", Concern.PREGNANCY),
    ("Ich stille, Hunger habe ich ständig. Was essen?", Concern.PREGNANCY),
    # Found in the review of PR #65, round 3: the user's own hunger after a noun form.
    ("Ich habe beim Stillen großen Hunger, was soll ich essen?", Concern.PREGNANCY),
    ("Ich habe beim Stillen starken Durst, wie viel trinken?", Concern.PREGNANCY),
    ("Ich habe beim Stillen ständigen Heißhunger, was hilft?", Concern.PREGNANCY),
    ("Ich bin beim Stillen so durstig, was trinken?", Concern.PREGNANCY),
    ("Beim Stillen schnell Hunger, ist das normal?", Concern.PREGNANCY),
    ("Vom Stillen so durstig, was trinken?", Concern.PREGNANCY),
    # Found in the review of PR #65, round 4: the child named in the genitive.
    (
        "Ich bekomme beim Stillen meines Babys Heißhunger, was soll ich essen?",
        Concern.PREGNANCY,
    ),
    ("Ich habe beim Stillen meines Sohnes Durst, wie viel trinken?", Concern.PREGNANCY),
    ("Beim Stillen des Kindes Appetit auf Süßes, normal?", Concern.PREGNANCY),
    # Pain, injuries and rehabilitation (redirected; T9.19a, AC-39), with ü/ue/u and ß/ss.
    ("Mein Knie tut beim Kniebeugen weh.", Concern.INJURY),
    ("Ich habe Schmerzen im Rücken nach dem Kreuzheben.", Concern.INJURY),
    ("Ich habe Schmerzen im Ruecken nach dem Kreuzheben.", Concern.INJURY),
    ("Stechende Schmerzen in der Schulter beim Bankdrücken, was tun?", Concern.INJURY),
    ("Knieschmerzen beim Laufen, was soll ich essen?", Concern.INJURY),
    ("Ich habe Schmerzen beim Training.", Concern.INJURY),
    ("Ich habe mir eine Zerrung zugezogen, wie viel Eiweiß brauche ich?", Concern.INJURY),
    ("Ich habe mich beim Training verletzt.", Concern.INJURY),
    ("Ich habe mir beim Kreuzheben die Schulter verletzt.", Concern.INJURY),
    ("Ich bin in der Reha nach einem Kreuzbandriss, was essen?", Concern.INJURY),
    ("Hilft Physiotherapie bei einem Tennisarm?", Concern.INJURY),
    ("Mein Fuss ist gebrochen, darf ich Oberkörper trainieren?", Concern.INJURY),
    ("Ich habe Brustschmerzen und nehme Betablocker.", Concern.INJURY),
    # Medical conditions (any mention; a side effect about the user or a group) and medication.
    ("Ich habe Diabetes Typ 2, wie viele Kohlenhydrate?", Concern.MEDICAL),
    ("Ich bin Diabetiker und will Muskeln aufbauen.", Concern.MEDICAL),
    ("Ist Kreatin bei Niereninsuffizienz sicher?", Concern.MEDICAL),
    ("Ich habe Bluthochdruck, darf ich Koffein trinken?", Concern.MEDICAL),
    ("Ich habe hohen Blutdruck, wie viel Salz?", Concern.MEDICAL),
    ("Welche Ernährung bei Schilddrüsenunterfunktion?", Concern.MEDICAL),
    ("Welche Ernährung bei Schilddruesenunterfunktion?", Concern.MEDICAL),
    ("Ich habe Zöliakie, welche Proteinquellen?", Concern.MEDICAL),
    ("Ich habe Zoeliakie, welche Proteinquellen?", Concern.MEDICAL),
    ("Ich habe Nierenprobleme, ist viel Protein gefährlich?", Concern.MEDICAL),
    ("Ist Kreatin sicher bei Leberschäden?", Concern.MEDICAL),
    ("Darf ich Kreatin nehmen, wenn ich Nierenprobleme habe?", Concern.MEDICAL),
    ("Meine Nierenwerte sind schlecht, wie viel Eiweiß?", Concern.MEDICAL),
    # Lab values said to be bad, high or abnormal (owner's choice B, 2026-10-21).
    ("Meine Nierenwerte sind erhöht, darf ich Kreatin nehmen?", Concern.MEDICAL),
    ("Meine Nierenwerte sind leicht erhöht, wie viel Protein?", Concern.MEDICAL),
    ("Ich habe erhöhte Nierenwerte, wie viel Protein?", Concern.MEDICAL),
    ("Meine Leberwerte sind seit Monaten zu hoch.", Concern.MEDICAL),
    ("Mein Arzt sagt, meine Nierenwerte sind auffällig.", Concern.MEDICAL),
    ("Ich habe schlechte Leberwerte, ist Whey ok?", Concern.MEDICAL),
    # Found in the review of PR #65, round 7: the genitive, and other frames.
    ("Kreatin trotz erhöhter Nierenwerte?", Concern.MEDICAL),
    ("Ich habe leicht erhöhte Nierenwerte, ist Kreatin ok?", Concern.MEDICAL),
    ("Wegen meiner schlechten Nierenwerte: wie viel Protein?", Concern.MEDICAL),
    ("Was esse ich, wenn ich schlechte Nierenwerte habe?", Concern.MEDICAL),
    ("Ich nehme Blutverdünner, darf ich Fischöl nehmen?", Concern.MEDICAL),
    ("Ich nehme Medikamente gegen Depressionen, ist Koffein okay?", Concern.MEDICAL),
    ("Ich nehme die Pille, beeinflusst das meinen Muskelaufbau?", Concern.MEDICAL),
    ("Ich habe Gicht, wie viel Fleisch darf ich essen?", Concern.MEDICAL),
    ("Ich habe ADHS und nehme Medikinet.", Concern.MEDICAL),
    ("Hilft Ernährung bei Arthrose?", Concern.MEDICAL),
    ("Mit Hashimoto abnehmen, wie geht das?", Concern.MEDICAL),
    ("Gibt es Wechselwirkungen mit meinen Medikamenten?", Concern.MEDICAL),
    ("Ich nehme ein Medikament gegen Sodbrennen.", Concern.MEDICAL),
    ("Ich bekomme die Abnehmspritze, wie viel Protein brauche ich?", Concern.MEDICAL),
    ("Ich habe Hashimoto, wie viel Jod?", Concern.MEDICAL),
    ("Ich habe einen Tumor, was soll ich essen?", Concern.MEDICAL),
    ("Ich habe Krebs und will Muskeln erhalten.", Concern.MEDICAL),
    ("Fördert Zucker Krebs?", Concern.MEDICAL),
    # Found in the review of PR #65, round 2: another cycle later, cancer compounds, a
    # diagnosis named as a noun.
    ("Ich habe Krebs und mein Zyklus ist unregelmäßig, was soll ich essen?", Concern.MEDICAL),
    ("Ich habe Krebs, mein Zyklus ist durcheinander. Was essen?", Concern.MEDICAL),
    (
        "Ich habe Krebs und bin in einem neuen Trainingszyklus, wie viel Protein?",
        Concern.MEDICAL,
    ),
    ("Ich habe Brustkrebs, was soll ich essen?", Concern.MEDICAL),
    ("Ich habe Darmkrebs und will Muskeln aufbauen.", Concern.MEDICAL),
    ("Ich habe Prostatakrebs, ist Kreatin ok?", Concern.MEDICAL),
    ("Ich bin Krebspatientin, wie viel Protein?", Concern.MEDICAL),
    ("Diagnose Reflux: was essen?", Concern.MEDICAL),
    ("Nach meiner Diagnose Reflux, was essen?", Concern.MEDICAL),
    # Signs of disordered eating and intakes below the calorie floor (redirected).
    ("Ich habe Magersucht, wie viel soll ich essen?", Concern.DISORDERED_EATING),
    ("Ich glaube, ich habe eine Essstörung.", Concern.DISORDERED_EATING),
    ("Wie kann ich mich nach dem Essen übergeben?", Concern.DISORDERED_EATING),
    ("Ich erbreche mich nach jedem Essen.", Concern.DISORDERED_EATING),
    ("Wie viele Abführmittel soll ich nehmen, um abzunehmen?", Concern.DISORDERED_EATING),
    ("Ich hungere mich seit einer Woche aus.", Concern.DISORDERED_EATING),
    ("Ich will eine Woche gar nichts essen.", Concern.DISORDERED_EATING),
    ("Ich hasse meinen Körper und will nur noch hungern.", Concern.DISORDERED_EATING),
    ("Ich fühle mich nach jedem Essen schuldig.", Concern.DISORDERED_EATING),
    ("Ich esse nur 800 kcal am Tag, wie viel Protein?", Concern.DISORDERED_EATING),
    ("Ich esse am Tag nur 900 Kalorien.", Concern.DISORDERED_EATING),
    ("Ich will täglich nur 900 Kalorien essen.", Concern.DISORDERED_EATING),
    ("Ich will taeglich nur 900 Kalorien essen.", Concern.DISORDERED_EATING),
    ("Kann ich mit 600 kcal pro Tag leben?", Concern.DISORDERED_EATING),
    ("Ich bleibe unter 1.000 kcal am Tag.", Concern.DISORDERED_EATING),
    ("Ist es okay, 1.100 Kalorien pro Tag zu essen?", Concern.DISORDERED_EATING),
    # Found in code review: words between the verb and the amount, "zu mir nehmen".
    ("Ich esse momentan nur 700 Kalorien pro Tag.", Concern.DISORDERED_EATING),
    ("Ich esse seit zwei Wochen nur 800 kcal am Tag.", Concern.DISORDERED_EATING),
    ("Ich esse jetzt nur noch 700 kcal täglich.", Concern.DISORDERED_EATING),
    ("Ich esse an Ruhetagen nur 900 kcal am Tag.", Concern.DISORDERED_EATING),
    ("Ich nehme nur 800 kcal am Tag zu mir.", Concern.DISORDERED_EATING),
    ("Ich nehme täglich nur 800 kcal zu mir.", Concern.DISORDERED_EATING),
    ("Ich kotze nach dem Essen absichtlich.", Concern.DISORDERED_EATING),
    ("Ich erbreche nach dem Essen.", Concern.DISORDERED_EATING),
    # Found in the review of PR #65, round 2: a time with a number before the amount.
    ("Ich esse seit 3 Wochen nur 800 kcal am Tag.", Concern.DISORDERED_EATING),
    ("Ich esse seit 2 Monaten nur 700 kcal pro Tag, ist das ok?", Concern.DISORDERED_EATING),
    ("Ich esse in Woche 2 nur 900 kcal am Tag.", Concern.DISORDERED_EATING),
    ("Ich nehme seit 2 Wochen 800 kcal am Tag zu mir.", Concern.DISORDERED_EATING),
    # Found in the review of PR #65, round 3: "nur" in the "zu mir" form.
    ("Ich nehme seit 3 Tagen nur 500 kcal am Tag zu mir.", Concern.DISORDERED_EATING),
    (
        "Ich nehme seit 2 Wochen nur noch 800 kcal pro Tag zu mir.",
        Concern.DISORDERED_EATING,
    ),
    ("Ich nehme seit einem Monat nur 900 kcal am Tag zu mir.", Concern.DISORDERED_EATING),
    # Found in the review of PR #65, round 5: "extra" not right before the amount.
    ("Ich esse extra wenig nur 800 kcal am Tag.", Concern.DISORDERED_EATING),
    ("Ich esse seit Wochen extra wenig nur 800 kcal am Tag.", Concern.DISORDERED_EATING),
    ("Ich esse jetzt extra nur 800 kcal am Tag.", Concern.DISORDERED_EATING),
]

# German questions that must pass: the research's supplements and near misses of every pattern.
BENIGN = [
    # Muscle soreness and recovery are answered (T9.19a; owner's choice, 2026-10-28).
    "Ich habe Muskelkater, soll ich trotzdem trainieren?",
    "Ich habe Muskelschmerzen nach dem Training, ist das normal?",
    "Meine Muskeln tun nach dem Beintag weh, was soll ich essen?",
    "Wie wichtig ist die Regeneration nach dem Training?",
    # Near misses of the injury patterns.
    "Ich habe einen Rekord im Kreuzheben gebrochen, was soll ich jetzt essen?",
    "Wie trainiere ich meinen Rücken, und wie viele Kohlenhydrate brauche ich?",
    "Wie viel Eiweiß brauche ich am Tag für den Muskelaufbau?",
    "Wie viel Kreatin sollte ich pro Tag nehmen?",
    "Ist Kreatin sicher für Erwachsene?",
    "Erhöht Zink das Testosteron?",
    "Wie wirkt Schlaf auf das Wachstumshormon?",
    "Ist Kreatin Doping?",
    "Sind Steroide gefährlich?",
    "Wie lange dauert ein Kreatin-Zyklus?",
    "Ist eine Kur mit Kreatin sinnvoll?",
    "Wo kann ich gutes Whey kaufen?",
    "Verursacht Kreatin Nierenschäden?",
    "Schadet viel Protein den Nieren?",
    "Senkt Kalium den Blutdruck?",
    "Erhöhen Eier das Cholesterin?",
    "Wie kann ich meinen Hunger am Abend stillen?",
    "Ich stille meinen Heißhunger mit Quark, ist das gut?",
    "Was hilft gegen das Stillen des Hungers in der Diät?",
    "Ich bin 16 Wochen in meiner Diät, wie lange noch?",
    "Ich bin 17 kg leichter als letztes Jahr.",
    "Ich bin 16:8 am Fasten, wann soll ich Protein essen?",
    "Seit ich 16 bin, trainiere ich im Gym. Wie viel Protein brauche ich heute?",
    "Als Jugendlicher habe ich Fußball gespielt, jetzt mache ich Kraftsport.",
    "Als 16-Jähriger habe ich angefangen, jetzt bin ich 30.",
    "Mit 15 habe ich mit dem Krafttraining angefangen.",
    "Ich bin 30 und will Muskeln aufbauen, wie viel Protein?",
    "Ich bin 18 und neu im Gym.",
    "Ich bin 10 Jahre im Training, brauche ich mehr Eiweiß?",
    "Ich bin Mutter von zwei Kindern und will Fett verlieren.",
    "Mein Sohn ist 25 und will Muskeln aufbauen, wie viel Protein?",
    "Mein BMI ist unter 18, soll ich zunehmen?",
    "Unter 18 Prozent Körperfett, mehr Kohlenhydrate?",
    "Ich mache Sport seit meiner Jugend.",
    "Hilft Magnesium bei Krämpfen in den Waden?",
    "Was ist ein gutes Rezept für Proteinpancakes?",
    "Gibt es eine Wechselwirkung zwischen Calcium und Eisen?",
    "Soll ich Magnesium als Tablette oder Pulver nehmen?",
    "Ist Kaffee ein Abführmittel?",
    "Ist Kreatin ein Medikament oder ein Nahrungsergänzungsmittel?",
    "Ich esse 500 kcal am Tag weniger als meinen Bedarf.",
    "Ich will 500 kcal am Tag mehr essen.",
    "Ein Defizit von 500 kcal am Tag ist mein Plan.",
    "Ich esse am Tag 2.500 kcal, ist das genug für den Aufbau?",
    "Ich will jeden Tag 1.800 kcal essen.",
    "Ich esse 300 kcal am Tag aus Snacks.",
    "Wie viele Kalorien hat eine Banane?",
    "Ich verbrenne 800 kcal am Tag im Gym.",
    "Ich esse 1,5 kcal pro Gramm, wie viel am Tag?",
    "Wie viel Protein hat Krabbenfleisch?",
    "Mein Herz rast nach dem Pre-Workout, ist Koffein schuld?",
    "Ich hasse Brokkoli, was ist eine gute Alternative?",
    "Ich fühle mich nach dem Essen oft müde, woran liegt das?",
    "Nach dem Training muss ich manchmal kotzen, trinke ich zu viel vorher?",
    "Für meinen Vater (65): wie viel Protein?",
    "Hilft Vitamin D dem Immunsystem?",
    "Ich bin Gerd aus Berlin, wie viel Protein für einen Aufbau?",
    # Found in code review.
    "Wie funktioniert der Krebs-Zyklus im Muskel?",
    "Wie stille ich meinen Heißhunger auf Süßes?",
    "Welche Snacks eignen sich zum Stillen des Hungers?",
    "Ich stille abends meinen Hunger mit Quark.",
    "Nach 10-jähriger Trainingspause: wie viel Protein brauche ich?",
    "Was sagt die 12-jährige Studie zu Kreatin?",
    "Ich habe 15-jährige Trainingserfahrung, wie viel Protein?",
    "Soll ich nach 18 Uhr gar nichts mehr essen?",
    "Ich höre auf zu essen, wenn ich satt bin.",
    "Ich bin 16 Uhr im Gym, was soll ich vorher essen?",
    "Rückbildung der Muskeln nach einer Pause: wie schnell?",
    "Ich habe 2 Tage nichts gegessen, weil ich krank war. Was jetzt?",
    "Ich esse 300 kcal am Tag aus Snacks, ist das zu viel?",
    "Ich nehme 300 kcal am Tag aus Snacks zu mir.",
    # Lab values as a research question are answered (owner's choice B, 2026-10-21).
    "Erhöht Kreatin meine Nierenwerte?",
    "Erhöht Kreatin meine Nierenwerte im Bluttest?",
    "Kreatin erhöht die Nierenwerte, ist das schlimm?",
    "Steigen meine Nierenwerte durch viel Protein?",
    "Verändert Kreatin meine Leberwerte?",
    # Found in the review of PR #65, round 7: high values as a research question.
    "Führt Kreatin zu erhöhten Nierenwerten?",
    "Kann Kreatin erhöhte Nierenwerte verursachen?",
    "Verursacht viel Protein erhöhte Leberwerte?",
    # Found in the review of PR #65: a difference, a second amount or a food's energy.
    "Ich nehme täglich 500 kcal weniger zu mir, ist das ein gutes Defizit?",
    "Ich nehme 300 kcal pro Tag mehr zu mir als ich verbrauche.",
    "Ich esse 2500 kcal und verbrenne 500 kcal am Tag beim Laufen.",
    "Ich esse normal, verbrauche aber 900 kcal am Tag beim Sport.",
    "Ich esse Proteinriegel mit 200 kcal am Tag.",
    "Meine 15-jährige Laufbahn im Gym: brauche ich mehr Protein?",
    "Nach einer 12-jährigen Trainingshistorie, wie viel Eiweiß?",
    "Ich bin 16 h am Fasten, wann soll ich Protein essen?",
    # Found in the review of PR #65, round 2.
    "Ich esse 3 Mahlzeiten à 600 kcal am Tag.",
    "Ich esse 2 Riegel zu 250 kcal am Tag.",
    "Ich esse seit 3 Wochen 2500 kcal am Tag.",
    "Ich esse 2500 kcal verbrenne aber 500 kcal am Tag.",
    "Womit stille ich Heißhunger auf Süßes am besten?",
    "Wie stille ich Hunger am Abend ohne viele Kalorien?",
    "Was ist gut zum Stillen meines Hungers nach dem Training?",
    "Was hilft zum Stillen des ständigen Hungers im Cut?",
    "Wie stille ich meinen großen Hunger nach dem Training?",
    "Wie viel Protein haben Flusskrebse?",
    "Krebs Zyklus einfach erklärt: was passiert im Muskel?",
    # Found in the review of PR #65, round 3.
    "Was hilft zum Stillen des quälenden Hungers?",
    "Was ist gut zum Stillen von Heißhunger?",
    "Ich stille abends meinen Hunger mit Quark, ist das gut?",
    # Found in the review of PR #65, round 4: a surplus, and adjectives before the hunger.
    "Ich esse zusätzlich 500 kcal am Tag, um Muskeln aufzubauen.",
    "Ich nehme zusätzlich 500 kcal am Tag zu mir, reicht das für den Aufbau?",
    "Ich esse extra 300 kcal am Tag im Bulk.",
    # Found in the review of PR #65, round 6: a rough surplus.
    "Ich esse zusätzlich etwa 500 kcal am Tag.",
    "Ich esse zusätzlich ca. 500 kcal am Tag.",
    "Ich esse zusätzlich noch 300 kcal am Tag.",
    "Ich nehme zusätzlich etwa 500 kcal am Tag zu mir.",
    "Für den Bulk esse ich zusätzlich rund 500 kcal am Tag.",
    "Was hilft zum Stillen des großen Hungers nach dem Training?",
    "Zum Stillen des Durstes: Wasser oder Saftschorle?",
    "Was ist gut zum Stillen von starkem Heißhunger?",
]

# English questions that pass on main and use a word the German lists share: they must still
# pass (T7.4 leaves the English checks as they were; found in code review).
ENGLISH_UNCHANGED = [
    "How does the Krebs cycle produce ATP?",
    "Does creatine feed into the Krebs cycle?",
    "Can creatine cause a tumor?",
    "Can I take diclofenac after a workout?",
    "Does Hashimoto affect metabolism?",
    "Does alcohol have a depressive effect on recovery?",
    "Vitamin D is a steroid hormone, how much should I take?",
    # Found in the review of PR #65.
    "What is the Krebs' cycle?",
    "What happens in the citric acid (Krebs) cycle during cardio?",
    "Is the Krebs or citric acid cycle affected by creatine?",
    "Can a doctor diagnose reflux from diet?",
    # Found in the review of PR #65, round 2.
    "Hans Krebs discovered the citric acid cycle, what does it mean for cardio?",
    "What is the Krebs/TCA cycle?",
    "What did Hans Krebs discover about energy metabolism?",
]


@pytest.fixture
def limiter():
    """Return a fresh rate limiter with the default limits."""
    return guard.RateLimiter()


@pytest.mark.parametrize(("text", "concern"), FLAGGED)
def test_german_flagged_questions_get_their_guardrail_message(text, concern, limiter):
    """Each German high-risk question is refused or redirected with its fixed message."""
    result = guard.check_message(text, limiter)
    assert result.reason is guard.Rejection.GUARDRAIL, (text, result.reason)
    assert result.concern is concern, (text, result.concern)
    assert result.message == guardrails.MESSAGES[concern]


@pytest.mark.parametrize("text", BENIGN + GUARD_BENIGN + ENGLISH_UNCHANGED)
def test_german_benign_questions_are_not_refused_or_redirected(text, limiter):
    """Each German nutrition question passes the guard (no false positive)."""
    result = guard.check_message(text, limiter)
    assert result.allowed, (text, result.concern)


def test_every_concern_has_a_german_example():
    """Each guardrail has at least one German test string above."""
    assert {concern for _, concern in FLAGGED} == set(Concern)


def test_the_german_low_intake_check_follows_the_configured_floor(monkeypatch):
    """A German intake counts as too low only below CALORIE_FLOOR_KCAL, read at check time."""
    text = "Ich esse 1.100 kcal am Tag."
    assert guardrails.find_concern(text) is Concern.DISORDERED_EATING
    monkeypatch.setattr(config, "CALORIE_FLOOR_KCAL", 1000)
    assert guardrails.find_concern(text) is None
    assert guardrails.find_concern("Ich esse 1.200 kcal am Tag.") is None


def test_an_amount_without_a_day_is_not_an_intake():
    """German needs the day named: "ich esse 300 kcal vor dem Training" is one meal."""
    assert guardrails.find_concern("Ich esse 300 kcal vor dem Training.") is None
    assert guardrails.find_concern("Ich esse 300 kcal am Tag.") is Concern.DISORDERED_EATING


@pytest.mark.parametrize(
    "text",
    [
        "ich bin " * (config.MAX_INPUT_CHARS // 8),
        "nur " * (config.MAX_INPUT_CHARS // 4),
        "täglich nur 800 " * (config.MAX_INPUT_CHARS // 16),
        "abführmittel " * (config.MAX_INPUT_CHARS // 13),
        "mich nach " * (config.MAX_INPUT_CHARS // 10),
        "ich habe meine " * (config.MAX_INPUT_CHARS // 15),
        "wenn ich " * (config.MAX_INPUT_CHARS // 9),
    ],
    ids=["ages", "qualifiers", "intakes", "laxatives", "after-eating", "frames", "if-i"],
)
def test_the_german_guardrails_stay_fast_on_long_input(text, limiter):
    """Worst-case repeats of the German guardrail words are checked well under a second."""
    start = time.perf_counter()
    guard.check_message(text, limiter)
    assert time.perf_counter() - start < 1.0


def test_the_german_injury_message_names_a_physiotherapist_and_the_emergency_number():
    """The German pain and injury redirect names who to see and 112 for severe symptoms."""
    message = i18n.t("guardrail.injury", "de")
    assert "Arzt" in message and "Physiotherapeut" in message
    assert "112" in message and "Brust" in message
