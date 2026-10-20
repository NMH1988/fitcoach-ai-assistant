"""Domain guardrails: questions the assistant refuses or redirects before any model call.

The input guard runs `find_concern()` on each message after its injection checks (AC-12,
docs/PRD.md "Domain guardrails"). Performance-enhancing drug dosing is refused; minors,
pregnancy, medical conditions and medication, and signs of disordered eating are redirected to a
professional. The owner's system prompt holds the same rules as the second line of defence. The
patterns are English only and catch common phrasings, not all of them (docs/SECURITY.md).
"""

import re
from enum import StrEnum

from src import config


class Concern(StrEnum):
    """Why a question is refused or redirected."""

    PED_DOSING = "ped_dosing"
    MINOR = "minor"
    PREGNANCY = "pregnancy"
    MEDICAL = "medical"
    DISORDERED_EATING = "disordered_eating"


# The youngest age the profile accepts; the minor patterns below are written for 18 (ages 10-17,
# "under 18"), and a test checks the two agree.
ADULT_AGE = config.PROFILE_AGE_RANGE[0]

# Fixed messages: they never quote the user's text back.
MESSAGES = {
    Concern.PED_DOSING: (
        "This assistant does not give dosing or use advice for steroids, SARMs or other "
        "performance-enhancing drugs. For questions about them, please talk to a doctor. I can "
        "help with nutrition and with supplements covered by the research, such as creatine or "
        "caffeine."
    ),
    Concern.MINOR: (
        f"This assistant is made for adults ({ADULT_AGE}+). For nutrition advice for someone "
        f"under {ADULT_AGE}, please talk to a doctor, a paediatric dietitian or another qualified "
        "professional."
    ),
    Concern.PREGNANCY: (
        "This assistant is not made for pregnancy, the time after giving birth or breastfeeding. "
        "Please ask your doctor, midwife or a registered dietitian for advice that fits you."
    ),
    Concern.MEDICAL: (
        "This assistant is made for healthy adults and cannot advise on medical conditions or "
        "medication, as they can change what is safe to eat or take. Please ask your doctor, "
        "pharmacist or a registered dietitian."
    ),
    Concern.DISORDERED_EATING: (
        f"This assistant does not advise on eating below {config.CALORIE_FLOOR_KCAL:,} kcal a "
        "day or on ways of eating that may harm your health. If food, eating or your weight feel "
        "hard to manage, please talk to a doctor or a registered dietitian; eating disorder "
        "support services can help too."
    ),
}

# All patterns run on casefolded text with whitespace collapsed to single spaces.

# --- Performance-enhancing drugs: a drug named together with a dose or use request -------------
# "Testosterone", "growth hormone", "insulin" and "steroid hormones" are physiology ("does zinc
# raise testosterone?", "vitamin D is a steroid hormone"), so only their drug forms count;
# "corticosteroid" is a medication (MEDICAL).
_PED_TERMS = (
    r"\b(?:(?:anabolic[- ])?steroids?(?! hormones?\b)|aas|roids?|peds|sarms?|prohormones?"
    r"|performance[- ]enhancing (?:drugs?|substances?)"
    r"|ostarine|enobosarm|mk[- ]?2866|ligandrol|lgd[- ]?4033|rad[- ]?140|testolone"
    r"|mk[- ]?677|ibutamoren|cardarine|gw[- ]?501516|andarine|yk[- ]?11"
    r"|trenbolone|tren|nandrolone|deca(?:[- ]durabolin)?|dianabol|d[- ]?bol|methandrostenolone"
    r"|anavar|oxandrolone|winstrol|winny|stanozolol|anadrol|oxymetholone|primobolan|masteron"
    r"|boldenone|equipoise|turinabol|superdrol|halotestin"
    r"|testosterone (?:cypionate|enanthate|propionate|undecanoate|esters?|injections?|shots?"
    # "Test e", but not "a blood test e.g. ...".
    r"|cycles?|boosters? cycle)|test (?:cyp|e(?!\.\w)|enanthate|prop)"
    r"|hgh|growth hormone (?:injections?|shots?|peptides?)|bpc[- ]?157|tb[- ]?500"
    r"|clenbuterol|clen|dnp|dinitrophenol|epo)\b"
)
_PED_USE = (
    r"\b(?:doses?|dosages?|dosing|dose it|mg|milligrams?|mcg|iu|ml|cc"
    r"|cycles?|cycling|stack|stacks|stacking|inject|injecting|injection|injections|pin|pinning"
    r"|blast|cruise|pct|post[- ]cycle|protocol|kickstart"
    r"|how (?:much|many|often|long)|when (?:to|should i|do i) (?:take|use|run|start|inject)"
    r"|(?:should|can|could|do|would) i (?:take|use|try|start|run|inject|hop on|get on|add)"
    r"|how (?:do|should|can|would) (?:i|you) (?:take|use|run|start|inject)"
    r"|how to (?:take|use|run|start|inject|get)"
    r"|where (?:to|can i|do i|should i) (?:buy|get|order|find|source)"
    r"|buy|first time|beginners?"
    r"|safest (?:way|dose|amount)|safe (?:dose|amount)"
    r"|i(?:'m| am|m) (?:on|taking|using|running|starting)"
    r"|i (?:take|use|run|inject|started|want to (?:take|use|try|run|start))"
    r"|i(?:'m| am|m) (?:going|planning) to (?:take|use|try|run|start|hop on))\b"
)
# The drug and the use word must be in the same sentence: "I run 5k a day; are steroids common
# among runners?" is not a use request.
_SENTENCE_END = re.compile(r"[.?!;]+(?: |$)")

# --- Minors ---------------------------------------------------------------------------------------
# "I'm 16" is an age unless a unit follows ("I'm 16 kg over", "I'm 16 weeks in", "I'm 5'10",
# "I'm 16:8 fasting", "I'm 12-weeks out", "I'm 13 and a half stone").
_NOT_A_UNIT = (
    r"(?![\w'\"%]|[.,:/]\d| %|(?: and a half| and a bit)?[ -]?(?:kgs?|kilos?|lbs?|pounds?|stone"
    r"|st|cm|ft|feet|foot|in|inch|inches|percent|weeks?|days?|months?|hours?|hrs?|minutes?|mins?|times?|sets?|reps?|meals?|g|grams?"
    r"|k?cals?|calories|servings?|scoops?|eggs?|x|sessions?|workouts?|miles?|km|steps|down"
    r"|over|under|pounds|plates?)\b)"
)
_MINOR_AGE = r"(?:1[0-7]|[1-9]|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen)"
_MINOR_PATTERNS = [
    rf"\b(?:i(?:'m| am|m)|i (?:just )?turned|i(?:'ll| will) be) (?:only |just |almost |nearly )?"
    # "I'm 16 years old" is an age, "I'm 10 years into lifting" is not.
    rf"(?:1[0-7](?! (?:years?|yrs?)\b(?! old\b)){_NOT_A_UNIT}"
    rf"|{_MINOR_AGE} (?:years?|yrs?) old\b|{_MINOR_AGE} ?(?:yo|y/o)\b)",
    # A teenager named ("a 16-year-old"), not the past ("since I was 15 years old"); a younger
    # child only as the subject ("for my 8-year-old"), so a parent saying "I have a 2-year-old"
    # asks about their own diet.
    r"(?<!was )(?<!was a )(?<!were )(?<!at )(?<!since )(?<!from )"
    r"\b1[0-7][- ](?:years?|yrs?)[- ]old\b",
    rf"\b(?:for|can|should|does|is|will|may) (?:my|a|an|our) {_MINOR_AGE}[- ](?:years?|yrs?)"
    r"[- ]old\b",
    # Not cheese "aged 2 years" or "aged 12+ months".
    rf"\baged {_MINOR_AGE}\b(?! ?(?:weeks?|months?|days?|years?|yrs?)\b|\+)",
    # Not a BMI ("my BMI is under 18").
    rf"(?<!bmi )(?<!bmi is )(?<!bmi of )(?<!bmi's )\bunder[- ]18{_NOT_A_UNIT}",
    # "Since my teens" and "in my teens" are the past.
    r"(?<!since my )(?<!in my )(?<!my late )(?<!my early )\b(?:teens?|teenagers?|teenage"
    r"|adolescents?|underage|minors|pre-?teens?)\b",
    # Children as the subject: "is creatine safe for kids?", "can children take whey?".
    r"\b(?:for|can|should|do|may) (?:a |young |small )?(?:kids?|child|children)\b",
    rf"\b(?:for|can|should|does|is|will|may) my (?:{_MINOR_AGE}|young|teenage|little)"
    r" (?:son|daughter|kid|child|boy|girl)\b",
    r"\b(?:i(?:'m| am|m)|as) an? (?:minor|high school(?:er| student)"
    r"|middle school(?:er| student))\b",
    # Only the present ("I'm in high school", "I go to middle school"), not the past ("I played
    # football in high school").
    r"\b(?:i(?:'m| am|m)|i'm still|i am still|still|currently|i go to|i attend|i'm at|i am at)"
    r" (?:in )?(?:high|middle|secondary|junior high) school\b",
]

# --- Pregnancy, after birth, breastfeeding --------------------------------------------------------
_PREGNANCY_PATTERNS = [
    r"\b(?:pregnan(?:t|cy|cies)|trimester|prenatal|antenatal|postpartum|post-partum|postnatal"
    r"|breast-?feeding|breast feeding|breastfeed|lactating|lactation)\b",
    r"\bexpecting (?:a baby|twins|my (?:first|second|third) (?:baby|child))\b",
    r"\b(?:trying to (?:conceive|get pregnant)|nursing (?:mother|mom|mum|my baby|a baby))\b",
    r"\b(?:i(?:'m| am|m)|she(?:'s| is)) (?:a )?(?:new )?(?:nursing|breastfeeding)"
    r" (?:mother|mom|mum)\b",
]

# --- Medical conditions (said about the user or a group) and medication (any mention) -------------
_CONDITIONS = (
    r"(?:(?:pre-?)?diabetes|type [12] diabetes|t[12]d|kidney (?:disease|failure|stones?|problems?"
    r"|issues?|damage)|renal (?:disease|failure|insufficiency)|ckd|liver (?:disease|damage"
    r"|problems?|issues?)|fatty liver|cirrhosis|hepatitis|heart (?:disease|failure|condition"
    r"|problems?|issues?|attack)|cardiovascular disease|coronary artery disease"
    r"|(?:high|low) blood pressure|hypertension|high cholesterol|hypercholesterolaemia"
    r"|hypercholesterolemia|cancer|leukaemia|leukemia|pcos|polycystic ovar(?:y|ian) syndrome"
    r"|(?:hypo|hyper)thyroid(?:ism)?|an? (?:under|over)active thyroid|hashimoto's|graves' disease"
    r"|thyroid (?:condition|problems?|disease|issues?)|gout|crohn's|crohns|ulcerative colitis"
    r"|ibd|ibs|irritable bowel syndrome|celiac(?: disease)?|coeliac(?: disease)?|epilepsy"
    r"|seizures|anaemia|anemia|osteoporosis|arthritis|asthma|copd|hiv|lupus|multiple sclerosis"
    r"|an autoimmune (?:disease|condition)|arrhythmia|afib|atrial fibrillation|gallstones"
    r"|pancreatitis|gerd|sleep apnoea|sleep apnea|depression|bipolar(?: disorder)?|adhd"
    r"|an? (?:medical|health|chronic|heart|kidney|liver|thyroid) (?:condition|illness|disease"
    r"|problem))"
)
# Who has it: the user, someone named, or a group ("people with ...").
_CONDITION_FRAME = (
    r"\b(?:i have|i've got|ive got|i've|ive|i got|i had|i've had|i was diagnosed with"
    r"|i've been diagnosed with|i'm diagnosed with|diagnosed with|i suffer from|suffering from"
    r"|i(?:'m| am|m) living with|living with|recovering from|history of|my"
    # "Safe with ...", not a link in research ("is red meat associated with heart disease?").
    r"|(?:he|she|they|we|my \w+) (?:has|have|had|got)"
    r"|(?:safe|ok|okay|fine|good|bad|healthy|dangerous|risky) (?:for|with)|with my"
    r"|(?:people|someone|anyone|those"
    r"|patients|a person|persons|men|women|lifters|athletes|adults) with|if you have)"
    # Not a healthy user's prevention question ("how can I lower my diabetes risk?").
    rf" (?:a |an |my |mild |severe |chronic |early |stage \d )?{_CONDITIONS}\b(?! risks?\b)"
)
_MEDICAL_PATTERNS = [
    _CONDITION_FRAME,
    r"\b(?:diabetics?|pre-?diabetic|hypertensives?|epileptics?|asthmatics?)\b",
    r"\bi(?:'m| am|m) (?:a )?(?:type [12] )?(?:diabetic|hypothyroid|hyperthyroid|anaemic|anemic"
    r"|epileptic|asthmatic|bipolar|celiac|coeliac)\b",
    # Medication, named or not. "Medicine" alone is left out ("sports medicine", "a medicine
    # ball"), and so is "prescribed" alone ("my program prescribed 5x5").
    r"\b(?:medications?|meds|medicines|prescriptions?|drug interactions?"
    r"|prescribed (?:me |to me )?(?:a |an |some )?(?:medication|medicine|pills?|drugs?|tablets?)"
    # Not "a medicine" or "the medicine": "is creatine a medicine?", "the Medicine and Science in
    # Sports and Exercise paper".
    r"|(?:my|any|this|these|some|other|prescription|blood pressure|heart|thyroid|diabetes)"
    r" medicine(?! balls?\b)|metformin|insulin (?:shots?|injections?|pumps?|therapy|pens?)"
    r"|(?:i|i(?:'m| am|m)) (?:on|taking|take|inject|injecting|using|use) insulin"
    r"|statins?|atorvastatin|rosuvastatin|simvastatin|warfarin|blood thinners?|anticoagulants?"
    r"|antidepressants?|ssris?|sertraline|fluoxetine|citalopram|escitalopram|levothyroxine"
    r"|synthroid|beta[- ]blockers?|ace inhibitors?|lisinopril|amlodipine|contraceptives?"
    r"|birth control|accutane|isotretinoin|adderall|ritalin|vyvanse|methylphenidate"
    r"|corticosteroids?|prednisone|prednisolone|immunosuppressants?|chemo(?:therapy)?"
    r"|antibiotics?|ibuprofen|nsaids?|painkillers?|paracetamol|acetaminophen|aspirin"
    r"|ozempic|wegovy|semaglutide|mounjaro|zepbound|tirzepatide|saxenda|liraglutide"
    r"|glp-?1 (?:agonists?|medications?|drugs?|injections?|shots?|meds)|on (?:a )?glp-?1|trt"
    r"|testosterone replacement(?: therapy)?|hrt|hormone replacement(?: therapy)?)\b",
]

# --- Disordered eating ------------------------------------------------------------------------
_DISORDERED_PATTERNS = [
    r"\b(?:anorexi[ac]|anorexia nervosa|bulimi[ac]|bulimia nervosa|binge[- ]eating disorder"
    r"|eating disorders?|disordered eating|ednos|osfed|arfid|orthorexi[ac]|pro-?ana|pro-?mia"
    r"|thinspo|thinspiration|purg(?:e|es|ed|ing)|binge and purge|chew and spit"
    r"|self[- ]induced vomiting)\b",
    r"\b(?:(?:take|taking|took|use|using|used|abuse|abusing) laxatives?"
    r"|laxatives? (?:to|for) (?:lose|losing|drop|cut|weight))\b",
    r"\b(?:make|made|making) myself (?:throw up|vomit|sick|puke)\b",
    r"\b(?:throw(?:ing)? up|vomit(?:ing)?|puk(?:e|ing)) after (?:eating|meals?|i eat|food)\b",
    r"\bstarv(?:e|ing|ed) myself\b",
    r"\b(?:stop|quit) eating (?:completely|entirely|altogether|for (?:days|a week|\d+ days))\b",
    r"\bnot eat(?:ing)? (?:anything|at all) for (?:days|a week|\d+ days)\b",
    r"\b(?:hate|disgusted by|ashamed of) my body\b",
    r"\bfeel (?:so |really |very )?(?:guilty|disgusted|ashamed) (?:after|when|about) "
    r"(?:eating|i eat|food|every meal)\b",
    r"\bpunish myself\b",
    r"\bdiuretics? to (?:lose|drop|cut) weight\b",
]
# An intake per day below the calorie floor, after an eating verb: "eat 800 kcal a day", "live on
# 900 calories daily". A deficit or surplus ("a 500 kcal a day deficit", "eat 500 calories a day
# more") or a part of the intake ("snacks add just 300 calories a day", "eat 400 calories a day
# from snacks") does not count.
_LOW_INTAKE = re.compile(
    # "My fat intake is 600 kcal a day" is one macro, not the whole day.
    r"\b(?:eat|eats|eating|ate|consume|consuming|consumed|diet of"
    r"|(?<!protein )(?<!fat )(?<!carb )(?<!carbs )(?<!carbohydrate )(?<!sugar )(?<!alcohol )"
    r"(?<!snack )(?<!fibre )(?<!fiber )(?<!caffeine )(?<!drink )"
    r"intake (?:of|at|to|is)"
    r"|live on|living on|survive on|surviving on|stay (?:under|below|at)|keep (?:it |myself )?"
    r"(?:under|below|at)|(?:cut|drop|go|get|come) (?:down )?to|limit (?:myself|me|it) to)"
    r"(?: (?:only|just|about|around|roughly|like|approximately|maybe|barely|under|below|less than"
    r"|fewer than|at most|no more than|~)){0,2}"
    # Bounded, so int() never meets a huge number.
    r" ~?(\d{1,2}(?:,\d{3}){1,2}|\d{1,7}) ?(?:k?cals?|kilocalories|calories)"
    r"(?: (?:a|per|each|every) day|/ ?day| daily| per 24 ?h)\b"
    r"(?! (?:less|fewer|more|extra|over|under|below|above|deficit|surplus|lower|higher|from|of"
    r"|in)\b)"
)

_PED_TERMS_RE = re.compile(_PED_TERMS)
_PED_USE_RE = re.compile(_PED_USE)
_REDIRECTS = [
    (Concern.MINOR, [re.compile(p) for p in _MINOR_PATTERNS]),
    (Concern.PREGNANCY, [re.compile(p) for p in _PREGNANCY_PATTERNS]),
    (Concern.MEDICAL, [re.compile(p) for p in _MEDICAL_PATTERNS]),
    (Concern.DISORDERED_EATING, [re.compile(p) for p in _DISORDERED_PATTERNS]),
]


def _below_floor(folded: str) -> bool:
    """Return True if the text names a daily intake below the calorie floor."""
    for match in _LOW_INTAKE.finditer(folded):
        kcal = int(match.group(1).replace(",", ""))
        # 0 counts too: "eat 0 calories a day for a week" is a fast, below the floor.
        if kcal < config.CALORIE_FLOOR_KCAL:
            return True
    return False


def find_concern(text: str) -> Concern | None:
    """Return the first guardrail the text falls under (drug dosing first), or None."""
    folded = " ".join(text.casefold().split())
    for sentence in _SENTENCE_END.split(folded):
        if _PED_TERMS_RE.search(sentence) and _PED_USE_RE.search(sentence):
            return Concern.PED_DOSING
    for concern, patterns in _REDIRECTS:
        if any(p.search(folded) for p in patterns):
            return concern
    if _below_floor(folded):
        return Concern.DISORDERED_EATING
    return None
