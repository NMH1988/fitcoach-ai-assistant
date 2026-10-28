"""Domain guardrails: questions the assistant refuses or redirects before any model call.

The input guard runs `find_concern()` on each message after its injection checks (AC-12,
docs/PRD.md "Domain guardrails"). Performance-enhancing drug dosing is refused; minors,
pregnancy, pain and injuries (T9.19a, AC-39), medical conditions and medication, and signs of
disordered eating are redirected to a professional. The owner's system prompt holds the same
rules as the second line of defence. The patterns cover English and German (T7.4) and catch
common phrasings, not all of them (docs/SECURITY.md).
"""

import re
from enum import StrEnum

from src import config
from src.german import german


class Concern(StrEnum):
    """Why a question is refused or redirected."""

    PED_DOSING = "ped_dosing"
    MINOR = "minor"
    PREGNANCY = "pregnancy"
    # Before MEDICAL, here and in _REDIRECTS: its message names the emergency number, so "chest
    # pain on my blood pressure medication" gets it.
    INJURY = "injury"
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
    Concern.INJURY: (
        "This assistant cannot advise on pain, injuries or rehabilitation. Please see a doctor or "
        "a physiotherapist. If the pain is sudden or severe, or you have chest pain, call the "
        "emergency number (112 in Germany and the EU)."
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
    r"|st|cm|ft|feet|foot|in|inch|inches|percent|weeks?|days?|months?|hours?|hrs?|minutes?"
    r"|mins?|times?|sets?|reps?|meals?|g|grams?"
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

# --- Medical conditions and medication (any mention) --------------------------------------
# A disease named anywhere is redirected, research questions too ("does sugar cause diabetes?"):
# owner's choice in the review of PR #46, as diseases are out of scope (docs/PRD.md).
_DISEASES = (
    r"(?:(?:pre-?)?diabetes|type [12] diabetes|t[12]d|kidney (?:failure|stones?)"
    r"|renal (?:disease|failure|insufficiency)|ckd|fatty liver|cirrhosis|hepatitis"
    r"|heart (?:failure|attacks?)|cardiovascular disease"
    r"|coronary artery disease|(?:high|low) blood pressure|hypertension|high cholesterol"
    r"|hypercholesterolaemia|hypercholesterolemia|cancer|leukaemia|leukemia|pcos"
    r"|polycystic ovar(?:y|ian) syndrome|(?:hypo|hyper)thyroid(?:ism)?|(?:under|over)active thyroid"
    r"|hashimoto's|graves' disease|gout|crohn's|crohns"
    r"|ulcerative colitis|ibd|ibs|irritable bowel syndrome|celiac|coeliac|epilepsy|seizures"
    r"|anaemia|anemia|osteoporosis|arthritis|asthma|copd|hiv|lupus|multiple sclerosis"
    r"|autoimmune (?:disease|condition)|arrhythmia|afib|atrial fibrillation|gallstones"
    r"|pancreatitis|sleep apnoea|sleep apnea|bipolar(?: disorder)?|adhd"
    # Not "glycogen depression" or "depression of appetite".
    r"|(?<!glycogen )depression(?! of\b)"
    r"|(?:medical|health|chronic|heart|kidney|liver|thyroid) (?:condition|illness|disease))"
)
# Side effects a supplement question names about healthy people ("does creatine cause kidney
# damage?", which the research covers) count only when said about the user or a group, and so
# does "GERD", which is also a German first name ("I'm Gerd from Berlin").
_SIDE_EFFECTS = (
    r"(?:(?:kidney|liver|heart|thyroid)[- ](?:damage|problems?|issues?)|gerd|acid reflux)"
)
# Who has it: the user, someone named, or a group ("people with ...").
_CONDITION_FRAME = (
    r"\b(?:i have|i've got|ive got|i've|ive|i got|i had|i've had|i have had|i was diagnosed with"
    r"|i've been diagnosed with|i'm diagnosed with|diagnosed with|i suffer from|suffering from"
    r"|i(?:'m| am|m) living with|living with|recovering from|history of|my"
    # "Safe with ...", not a link in research ("is creatine linked with kidney damage?").
    r"|(?:he|she|they|we|my \w+) (?:has|have|had|got)"
    r"|(?:safe|ok|okay|fine|good|bad|healthy|dangerous|risky) (?:for|with)|with my"
    # "Can I take creatine with kidney problems?": the user's own condition.
    r"|(?:take|taking|use|using|drink|drinking|eat|eating) \w+(?: \w+)? with"
    r"|(?:people|someone|anyone|those"
    r"|patients|a person|persons|men|women|lifters|athletes|adults) with|if you have)"
    rf" (?:a |an |my |mild |severe |chronic |early )?{_SIDE_EFFECTS}\b"
)
_MEDICAL_PATTERNS = [
    rf"\b{_DISEASES}\b",
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

# --- Pain, injuries, rehabilitation (T9.19a) ---------------------------------------------------
# An injury, rehabilitation or physiotherapy named anywhere (as a disease is), joint pain, and
# pain the user has during or after training. Muscle soreness is answered: "DOMS", "sore muscles
# after leg day", "muscle damage" (a research term) and muscle pain after training pass (owner's
# choice, 2026-10-28), so the general pain patterns count only in a sentence that names no muscle
# (_outside_muscle_talk); joint pain and named injuries count in any sentence.
_BODY_PARTS = (
    r"(?:joints?|knees?|(?:lower |upper )?back|shoulders?|elbows?|wrists?|hips?|ankles?|neck"
    r"|chest|feet|foot|heels?|achilles|spine|groin|rotator cuff)"
)
# Muscle words in either language, as the sentence check runs on the same folded text.
_MUSCLE_WORDS = (
    r"(?:muscles?|muscular|doms|soreness|muskeln?|muskulatur|muskelkater|muskelschmerz\w*)"
)


def _outside_muscle_talk(pattern: str) -> str:
    """Return the pattern matched only in a sentence that names no muscle (soreness passes)."""
    # From a sentence start: no muscle word anywhere in the sentence, then the pattern in it.
    return rf"(?:^|[.?!;] )(?![^.?!;]*\b{_MUSCLE_WORDS}\b)[^.?!;]*?{pattern}"


_TRAINING = (
    r"(?:training|lifting|working out|workouts?|squats?|squatting|bench(?:ing)?"
    r"|bench press(?:ing)?|deadlifts?|deadlifting|overhead press(?:ing)?|curls?|curling|rows?"
    r"|rowing|pull-?ups?|push-?ups?|running|leg day|the gym)"
)
_INJURY_PATTERNS = [
    # "Injury" and rehabilitation anywhere: "does creatine help an injury heal?" is redirected too.
    r"\b(?:injur(?:y|ies|ed|ing)|re-?injur\w*|injures?)\b",
    r"\b(?:rehab(?:ilitation|bing)?|physio(?:therapy|therapists?)?|physical therap(?:y|ists?))\b",
    r"\b(?:sprain(?:s|ed)?|tendinitis|tendonitis|tendinopathy|tendinosis|bursitis|impingement"
    r"|herniated (?:disc|disk)|slipped (?:disc|disk)|bulging (?:disc|disk)|sciatica|tennis elbow"
    r"|golfer'?s elbow|shin splints|plantar fasciitis|stress fractures?|fractured?|fractures"
    r"|dislocat(?:ed|ion|ions)|concussions?|whiplash)\b",
    # A body part after "my", "a" or "an": not "torn between cutting and bulking", "strained
    # yogurt", "pulled back on carbs" or "does lifting tear muscle fibres?".
    r"\b(?:torn|tore|tear|tearing|ruptured?|pulled|strained|tweaked|hurt) (?:my|a|an)"
    r" (?:(?:left|right|lower|upper) )?(?:muscle|hamstrings?|groin|calf|calves|pecs?|biceps?"
    r"|triceps|quads?|ligaments?|tendons?|acl|mcl|meniscus|labrum|rotator cuff|back|neck"
    r"|shoulders?|knees?|wrists?|elbows?|ankles?|hips?|foot|feet)\b",
    # A torn ligament or tendon named without "my": "heal my torn hamstring", "a torn ACL".
    r"\b(?:torn|ruptured|pulled|strained) (?:(?:left|right) )?(?:hamstrings?|groin|calf"
    r"|pecs?|biceps?|triceps|quads?|ligaments?|tendons?|acl|mcl|meniscus|labrum|rotator cuff)\b",
    r"\b(?:i|i've|ive|i have) hurt (?:myself|my\w*)\b",
    r"\b(?:broken|broke (?:my|a)) (?:arm|leg|wrist|ankle|foot|hand|ribs?|bone|fingers?|toes?"
    r"|collarbone)\b",
    # Joint pain, said either way round: "knee pain", "pain in my knee", "my knee hurts".
    rf"\b{_BODY_PARTS} (?:pain|pains|aches?|aching)\b|\bbackaches?\b",
    rf"\b(?:pain|pains|aches?|hurts?|hurting|swelling|clicking|popping) (?:in|on) (?:my|the|both)"
    rf" (?:\w+ )?{_BODY_PARTS}\b",
    rf"\b(?:my|both|the) (?:\w+ )?{_BODY_PARTS} (?:hurts?|is hurting|are hurting|aches?"
    r"|is aching|are aching|is swollen|are swollen|keeps? hurting|gives? out|pops?|clicks?)\b",
    rf"\b(?:swollen|painful|sore) {_BODY_PARTS}\b",
    # Pain with a quality ("sharp", "chest"-like severity) counts in any sentence.
    r"\b(?:sharp|stabbing|shooting|sudden|severe|burning|radiating|nerve|chronic) pains?\b",
    # The user's own pain while training ("I get pain when I squat"), not about the muscles.
    _outside_muscle_talk(
        r"\b(?:i (?:have|get|got|feel|felt|had|keep getting|am getting|am having|still have)"
        r"|i've (?:got|had|been having|been getting)|ive got|i'm (?:getting|having|feeling|in)"
        r"|i am (?:getting|having|feeling|in)) (?:\w+ ){0,3}?pains?\b"
    ),
    _outside_muscle_talk(
        rf"\b(?:pains?|it hurts) (?:during|after|when|while|from) (?:i |my |the )?{_TRAINING}\b"
    ),
    _outside_muscle_talk(r"\b(?:it|this|that) hurts (?:when|if|after|during|to)\b"),
    _outside_muscle_talk(r"\bhurts? when i\b"),
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

# --- German (T7.4) ------------------------------------------------------------------------------
# The same rules for German questions, on the same casefolded text. Written with "ss" for "ß" and
# passed through german(), so "ü" also matches "u" and the typed "ue". Drug names that German
# spells like English (SARMs, Anavar, HGH, Ozempic, Diabetes, PCOS, ...) are already caught above.
# No umlaut inside a lookbehind: german() would make it variable-width.

# "Testosteron" and "Wachstumshormon" alone are physiology, as in English; "Doping" alone is left
# out ("ist Kreatin Doping?").
_DE_PED_TERMS = (
    # Not "steroid hormones" in an English sentence ("vitamin D is a steroid hormone").
    r"\b(?:anabolika|anabolikum|anabole[nr]? steroide?n?|steroide?n?(?! ?hormon)|steroidkur(?:en)?"
    r"|dopingmittel[n]?|leistungssteigernde[nr]? (?:mittel[n]?|substanzen|drogen|präparate)"
    r"|prohormone|trenbolon|nandrolon|oxandrolon|oxymetholon|methandrostenolon|boldenon"
    r"|testosteron[- ]?(?:spritzen|spritze|injektion(?:en)?|kur(?:en)?|enantat|cypionat"
    r"|propionat|undecanoat|ester)|testo[- ]?kur(?:en)?"
    r"|(?:spritze|spritzen|spritzt|injiziere|injizieren) (?:ich |man |du )?(?:\w+ )?testosteron"
    r"|wachstumshormon(?:spritzen|spritze|injektion(?:en)?)|wachstumshormone? (?:spritzen|spritze"
    r"|injektion(?:en)?|peptide))\b"
)
_DE_PED_USE = (
    r"\b(?:dosis|dosen|dosierung(?:en)?|dosieren|dosiere|dosiert|dosierst|milligramm|kur|kuren"
    r"|zyklus|zyklen|absetzen"
    r"|absetzphase|spritzen|spritze|spritzt|injizieren|injiziere|injektion(?:en)?|stacken"
    r"|wie (?:viel|viele|oft|lange)|wann (?:soll|sollte|muss|kann) ich"
    r"|(?:soll|sollte|kann|könnte|darf|würde) ich (?:\w+ ){0,3}?(?:nehmen|einnehmen|probieren"
    r"|anfangen|starten|spritzen|beginnen|kaufen|bestellen)"
    r"|wie (?:nehme|nimmt|nehmen|spritze|beginne|starte) (?:ich|man)"
    r"|wo (?:kaufen|kaufe ich|kauft man|bekomme ich|bekommt man|kriege ich|bestellen"
    r"|bestelle ich)|kaufen|bestellen|anfänger|erste[nrs]? (?:kur|mal|zyklus)"
    r"|sicherste[nr]? (?:dosis|menge|weg)|sichere[nr]? (?:dosis|menge)"
    r"|ich (?:nehme|spritze|benutze|nutze|verwende|starte|beginne|plane)"
    r"|ich bin (?:gerade )?auf|ich (?:will|möchte) (?:\w+ ){0,2}?(?:nehmen|probieren|spritzen"
    r"|starten|anfangen|beginnen))\b"
)

# "Ich bin 16" is an age unless a unit follows ("ich bin 16 kg leichter", "ich bin 16 Wochen in
# der Diät", "ich bin 16:8 am Fasten").
_DE_NOT_A_UNIT = (
    r"(?![\w'\"%]|[.,:/]\d| %| ?(?:kg|kilo|kilos|kilogramm|g|gramm|cm|zentimeter|m|meter|km"
    r"|prozent|wochen?|tage?n?|monate?n?|stunden?|std|minuten?|min|mal|sätze?n?|wiederholungen"
    r"|wdh|kcal|kalorien|portionen?|messlöffel|eier|x|einheiten|trainings?|schritte|pfund|stück"
    r"|scheiben|kilometer|uhr|h)\b)"
)
_DE_MINOR_AGE = r"(?:1[0-7]|[1-9]|zehn|elf|zwölf|dreizehn|vierzehn|fünfzehn|sechzehn|siebzehn)"
_DE_MINOR_PATTERNS = [
    r"\b(?:ich bin|ich werde|ich wurde) (?:erst |gerade |fast |bald |noch |jetzt |knapp )?"
    # "Ich bin 16 Jahre alt" is an age, "ich bin 10 Jahre im Training" is not.
    rf"(?:1[0-7](?! jahre?n?\b(?! alt\b)){_DE_NOT_A_UNIT}|{_DE_MINOR_AGE} jahre alt\b)",
    # A teenager named ("ein 16-Jähriger"), not the past ("als 16-Jähriger", "mit 16 Jahren") or
    # an adjective of a thing, told by the noun's ending ("nach 10-jähriger Trainingspause",
    # "die 12-jährige Studie", "meine 15-jährige Laufbahn").
    r"(?<!als )(?<!mit )(?<!seit )(?<!nach )\b(?:1[0-7][- ]?|dreizehn|vierzehn|fünfzehn|sechzehn"
    r"|siebzehn)jährige?[nmrs]?\b(?! \w*(?:ung|heit|keit|schaft|bahn|historie|pause|zeit"
    r"|erfahrung|praxis|studie|karriere|geschichte|tradition|daten|phase|dauer|ehe|training"
    r"|programm|plan|jubiläum|lauf)\b)",
    # A younger child only as the subject ("für meinen 8-Jährigen"), as in English.
    rf"\b(?:für|kann|soll|sollte|darf|muss) (?:mein|meine|meinen|meinem|ein|eine|einen|unser"
    rf"|unsere|unseren) {_DE_MINOR_AGE}[- ]?jährige[nmrs]?\b",
    # Not a BMI ("mein BMI ist unter 18").
    rf"(?<!bmi )(?<!bmi von )(?<!bmi ist )(?<!bmi liegt )\bunter 18{_DE_NOT_A_UNIT}",
    # "Als Jugendlicher" is the past; "Jugend" alone is not counted ("seit meiner Jugend").
    r"(?<!als )\b(?:teenager|teenagerin|teenies?|jugendliche[nr]?|minderjährige?[nr]?"
    r"|heranwachsende[nr]?|pubertierende[nr]?)\b",
    r"\b(?:für|können|kann|sollen|sollten|dürfen|darf|müssen) (?:ein |kleine |junge |unsere "
    r"|meine )?(?:kinder|kind|kids)\b",
    rf"\b(?:für|kann|soll|sollte|darf|muss) (?:mein|meine|meinen|meinem|unser|unsere|unseren) "
    rf"(?:{_DE_MINOR_AGE}[- ]?jährige[nmrs]?|kleine[nmrs]?|jugendliche[nmrs]?) (?:sohn|tochter"
    r"|kind|junge|jungen|mädchen)\b",
    # Only the present: "ich gehe noch zur Schule", "ich bin in der 10. Klasse".
    r"\bich (?:bin|gehe|geh) (?:noch |gerade |aktuell )?(?:in die|zur|auf die|aufs|auf das"
    r"|in der|auf der|auf dem) (?:schule|gymnasium|realschule|hauptschule|gesamtschule"
    r"|mittelschule|oberstufe|(?:\d{1,2}\. ?)klasse)\b",
    r"\bich bin (?:noch )?(?:schüler|schülerin)\b",
]

# "Stillen" is also "to still": "stille ich (meinen) Heißhunger" or "zum Stillen des Hungers" is
# a nutrition question, so a form of "stillen" whose object is hunger, thirst or appetite does
# not count. After the verb the hunger may come right away or after up to two articles,
# possessives, adverbs or adjectives; after a noun form it needs an article or possessive first
# and at most one adjective ending in -en or -em ("zum Stillen des ständigen Hungers"), so a
# child named in the genitive is not read as the object ("beim Stillen meines Babys Heißhunger"),
# and "beim Stillen großen Hunger" or "beim Stillen schnell Hunger" is the user's own hunger. The
# user's own hunger next to it still counts ("Ich stille und habe Hunger", "Während des Stillens
# Heißhunger").
_DE_HUNGER_LEAD = (
    r"(?:den|des|meinen|meines|deinen|deines|seinen|seines|ihren|ihres|unseren|unseres|euren"
    r"|von|abends|nachts|schnell|damit|so|kurz|gut|am besten|grossen|ständigen|starken|kleinen"
    r"|akuten|abendlichen)"
)
_DE_HUNGER = r"\w*(?:hunger|durst|appetit)\w*\b"
_DE_VERB_NOT_HUNGER = rf"(?! (?:{_DE_HUNGER_LEAD} ){{0,2}}{_DE_HUNGER})"
_DE_HUNGER_ARTICLE = (
    r"(?:den|des|meinen|meines|deinen|deines|seinen|seines|ihren|ihres|unseren|unseres|euren"
    r"|von)"
)
_DE_NOUN_NOT_HUNGER = rf"(?! {_DE_HUNGER_ARTICLE} (?:\w+e[nm] )?{_DE_HUNGER})"
_DE_PREGNANCY_PATTERNS = [
    r"\b(?:schwanger|schwangere[nrs]?|schwangerschaft(?:en)?|schwangerschafts\w*|trimenon"
    r"|pränatal\w*|postpartal\w*|postnatal\w*|wochenbett|stillzeit|stillende[nr]?|kinderwunsch"
    r"|nach der geburt|nach der entbindung|entbindung|frisch entbunden|rückbildungs\w*)\b",
    rf"\b(?:ich stille|stille ich)\b{_DE_VERB_NOT_HUNGER}",
    r"\b(?:beim stillen|während des stillens|während dem stillen|vom stillen|zum stillen"
    rf"|das stillen)\b{_DE_NOUN_NOT_HUNGER}",
    r"\b(?:ich erwarte|wir erwarten|sie erwartet|meine frau erwartet) (?:ein |unser |mein "
    r"|unser erstes |unser zweites |mein erstes |mein zweites )?(?:baby|kind|zwillinge)\b",
]

_DE_DISEASES = (
    r"(?:diabetiker(?:in|innen)?|prädiabet\w*|diabetisch\w*|zuckerkrank\w*|nierenerkrankung(?:en)?"
    r"|nierenkrankheit|niereninsuffizienz|nierenversagen|nierensteine?n?|nierenschwäche"
    r"|fettleber|leberzirrhose|zirrhose|leberentzündung|herzinsuffizienz|herzschwäche"
    r"|herzinfarkts?|herz-kreislauf-erkrankung(?:en)?|koronare herzkrankheit|khk|bluthochdruck"
    r"|(?:hohe[mnr]?|niedrige[mnr]?|erhöhte[mnr]?) blutdruck|hypertonie|hypotonie"
    # Not the Krebs cycle: "Zyklus" right after "Krebs" ("Krebs-Zyklus"), or "cycle" within a few
    # words and no comma ("the Krebs' cycle", "the citric acid (Krebs) cycle", "Krebs or citric
    # acid cycle"), so "Ich habe Krebs und mein Zyklus ..." still counts; not the chemist Hans
    # Krebs. The cancer compounds count ("Brustkrebs", "Krebspatientin"). "Tumor" and "Hashimoto"
    # only in German frames, so the English words keep the English rules above.
    r"|(?:hohe[mnrs]?|erhöhte[mnrs]?) cholesterin\w*|hypercholesterinämie"
    r"|(?<!hans )krebs(?!(?:'|\))?[- ]?(?:zyklus|zyklen)\b|[^.?!;,]{0,30}?\bcycle)|krebserkrankung"
    r"|(?:brust|darm|dickdarm|prostata|lungen|haut|blut|magen|leber|nieren|pankreas|hoden"
    r"|eierstock|gebärmutterhals|schilddrüsen|knochen|blasen)krebs|krebspatient(?:in|innen|en)?"
    r"|(?:einen|ein|meinen|mein|der|den|dem|gutartige[nmr]?|bösartige[nmr]?) tumor|tumore|tumoren"
    r"|tumorerkrankung(?:en)?|leukämie|polyzystische[sn]? ovarsyndrom|schilddrüsenunterfunktion"
    r"|schilddrüsenüberfunktion|hypothyreose|hyperthyreose"
    r"|(?:morbus|mit|bei|habe|hab|hat|wegen) hashimoto|hashimoto-thyreoiditis|morbus basedow|gicht"
    r"|morbus crohn|colitis ulcerosa|chronisch entzündliche darmerkrankung(?:en)?|reizdarm\w*"
    r"|zöliakie|epilepsie|epileptiker\w*|krampfanfälle?n?|anämie|blutarmut|osteoporose|arthrose"
    r"|rheuma\w*|multiple sklerose|autoimmunerkrankung(?:en)?|herzrhythmusstörung(?:en)?"
    r"|vorhofflimmern|gallensteine?n?|bauchspeicheldrüsenentzündung|schlafapnoe"
    # German forms only: "a depressive effect" in English is not counted.
    r"|bipolare?[nr]? störung|adhs|depressionen|depressiv(?:en|er|es|em)?\b|depressive (?:phase"
    r"|episode|verstimmung|störung)"
    r"|(?:chronische[nr]?|ernsthafte[nr]?|schwere[nr]?) (?:krankheit|erkrankung)(?:en)?"
    r"|vorerkrankung(?:en)?|herzerkrankung(?:en)?|herzkrankheit|lebererkrankung(?:en)?"
    r"|schilddrüsenerkrankung(?:en)?|stoffwechselerkrankung(?:en)?)"
)
# As in English, a side effect counts only when said about the user or a group. "Bei" counts too
# ("Kreatin bei Nierenproblemen?" asks about people who have them), so "was hilft bei
# Sodbrennen?" is redirected (docs/SECURITY.md).
_DE_SIDE_EFFECTS = (
    r"(?:(?:nieren|leber|herz|schilddrüsen)(?:schäden|schaden|problemen?|beschwerden)"
    r"|sodbrennen|reflux|saures aufstossen)"
)
# Lab values ("Nierenwerte", "Leberwerte") are a research question on their own ("Erhöht Kreatin
# meine Nierenwerte?" is answered from the sources, as "does creatine raise my creatinine?" is in
# English; owner's choice, 2026-10-21); they count only when said to be bad, high or abnormal
# ("Meine Nierenwerte sind erhöht", "Ich habe schlechte Leberwerte").
_DE_LAB_VALUES = r"(?:nieren|leber|schilddrüsen)werte?n?"
_DE_BAD = (
    r"(?:schlecht|erhöht|zu hoch|hoch|zu niedrig|auffällig|abnormal|abnorm|kritisch"
    r"|nicht (?:gut|in ordnung|ok|okay|normal))"
)
# "Erhöhte Nierenwerte" counts only as the user's or a group's ("ich habe", "trotz", "meine"), so
# "Kann Kreatin erhöhte Nierenwerte verursachen?" is a research question.
_DE_BAD_LAB_VALUES = [
    r"\b(?:ich habe|ich hab|ich hatte|habe ich|hab ich|hatte ich|wenn ich|wenn man|mit|trotz"
    r"|wegen|bei|meine[nr]?)(?: (?:leicht|stark|deutlich|etwas|sehr|zu))? (?:schlechte[nmr]?"
    rf"|erhöhte[nmr]?|hohe[nmr]?|auffällige[nmr]?|abnormale[nmr]?|abnorme[nmr]?|kritische[nmr]?)"
    rf" {_DE_LAB_VALUES}\b",
    rf"\b{_DE_LAB_VALUES} (?:sind|waren|wären|seien|bleiben) (?:\S+ ){{0,2}}?{_DE_BAD}\b",
]
_DE_CONDITION_FRAME = (
    r"\b(?:ich habe|ich hab|ich hatte|hatte ich|ich leide an|ich leide unter|leide an|leide unter"
    r"|leidet an|leidet unter|diagnostiziert mit"
    # The German noun, not the English verb ("can a doctor diagnose reflux").
    r"|(?<!to )(?<!can )(?<!could )(?<!will )(?<!doctor )(?<!doctors )(?<!help )diagnose:?"
    r"|mit meinen|mit meiner"
    r"|mit meinem|meine|meinen|meiner|mein|menschen mit|leute mit|personen mit|patienten mit"
    r"|jemand mit|jemanden mit|sportler mit|männer mit|frauen mit|bei|trotz"
    r"|(?:sicher|unbedenklich|ok|okay|gut|schlecht|gefährlich|riskant|gesund) (?:bei|für|mit))"
    r"(?: (?:leichte[nmr]?|schwere[nmr]?|chronische[nmr]?|starke[nmr]?|starkem|erhöhte[nmr]?"
    rf"|schlechte[nmr]?))? {_DE_SIDE_EFFECTS}\b"
)
_DE_MEDICAL_PATTERNS = [
    rf"\b{_DE_DISEASES}\b",
    _DE_CONDITION_FRAME,
    *_DE_BAD_LAB_VALUES,
    rf"\bwenn (?:ich|man|du|er|sie) (?:\w+ ){{0,2}}?{_DE_SIDE_EFFECTS} (?:habe|hab|hat|hast|hatte"
    r"|haben)\b",
    # "Ist Kreatin ein Medikament?" is not about the user's medication, as in English.
    r"(?<!\bein )(?<!\bkein )(?<!\bals )\bmedikament\b",
    r"\b(?:nehme|nehmen|brauche|bekomme) (?:ein |mein |das |dieses )?medikament\b",
    r"\b(?:medikamente[n]?|medikaments|arzneimittel[n]?|arznei|verschreibungspflichtige[nr]? \w+"
    r"|verschriebene[nr]? (?:medikamente?|tabletten|pillen|mittel)"
    r"|wechselwirkung(?:en)? mit (?:meinen )?(?:medikamenten|arzneimitteln|tabletten)"
    r"|insulin(?:spritzen|spritze|pumpe|therapie|pen)|insulin (?:spritzen|pumpe|therapie)"
    r"|(?:spritze|nehme|brauche) (?:ich )?insulin|statine|blutverdünner[n]?|gerinnungshemmer[n]?"
    r"|antidepressiva|antidepressivum|l-thyroxin|thyroxin|levothyroxin|euthyrox|betablocker[n]?"
    r"|ace-hemmer[n]?|antibabypille|die pille|verhütungsmittel[n]?|hormonelle verhütung"
    r"|roaccutan|methylphenidat|medikinet|elvanse|kortison|cortison|prednisolon"
    r"|kortikosteroide?|immunsuppressiva|chemotherapie|antibiotika|antibiotikum|schmerzmittel[n]?"
    r"|schmerztabletten|novaminsulfon|metamizol|abnehmspritzen?|fettwegspritzen?"
    r"|testosteronersatztherapie|hormonersatztherapie|hormontherapie)\b",
]

# As in English: muscle soreness passes ("Muskelkater", "Muskelschmerzen nach dem Training": the
# compound is one word, so "\bschmerzen" does not match inside it). "Gebrochen" counts only with
# a body part ("einen Rekord gebrochen" passes), "verletzen" only as an injury ("Regeln verletzen"
# passes).
_DE_BODY_PARTS = (
    r"(?:gelenk|knie|rücken|kreuz|schulter|ellenbogen|ellbogen|handgelenk|hüft|hüfte|nacken"
    r"|brust|fuss|fersen|achillessehnen|leisten|wirbelsäulen|sprunggelenk|steissbein)"
)
_DE_TRAINING = (
    r"(?:training|trainieren|heben|kniebeugen|bankdrücken|kreuzheben|schulterdrücken|curls"
    r"|rudern|klimmzügen|liegestützen|laufen|joggen|sport|beintag|workout)"
)
_DE_INJURY_PATTERNS = [
    r"\b(?:verletzung(?:en)?|verletzungsbedingt\w*"
    r"|(?:mich|mir|sich|habe|hab|bin|ist) (?:\w+ ){0,4}?verletzt"
    r"|verletzte[nrms]? (?:knie|schulter|rücken|sehne|band|bänder|muskel|fuss|hand|handgelenk"
    r"|ellenbogen|ellbogen))\b",
    r"\b(?:reha|reha-\w+|rehabilitation|physiotherap\w*|krankengymnastik|physio)\b",
    r"\b(?:zerrung(?:en)?|muskelfaserriss|faserriss|bänderriss|bänderdehnung|sehnenriss"
    r"|sehnenentzündung(?:en)?|sehnenscheidenentzündung|tendinitis|tendinopathie"
    r"|schleimbeutelentzündung|bandscheibenvorfall|hexenschuss|ischias|kreuzbandriss"
    r"|meniskus(?:riss|schaden|verletzung)?|tennisarm|golferarm|ermüdungsbruch|knochenbruch"
    r"|verstaucht\w*|verstauchung(?:en)?|prellung(?:en)?|ausgekugelt\w*|gehirnerschütterung"
    r"|überlastungsschäden|überlastungsschaden|impingement)\b",
    r"\b(?:arm|bein|handgelenk|knöchel|fuss|rippe|finger|zeh|schlüsselbein) (?:\w+ )?gebrochen\b"
    r"|\bgebrochene[nmrs]? (?:arm|bein|handgelenk|knöchel|fuss|rippe|finger|zeh)\b",
    r"\b(?:umgeknickt|gezerrt|verrenkt|(?:knie|knöchel|fuss|handgelenk|rücken|nacken) verdreht"
    r"|verdrehte[nms]? (?:knie|knöchel|fuss|handgelenk))\b",
    # Joint pain, as in English: "Knieschmerzen", "Schmerzen im Knie", "mein Knie tut weh",
    # "mein Knie schmerzt", "tut mir das Knie weh". A body part is needed: "meine Beine tun nach
    # dem Beintag weh" and "mir tun die Muskeln weh" are soreness, like "my legs hurt".
    rf"\b{_DE_BODY_PARTS}schmerz(?:en)?\b",
    rf"\bschmerzen (?:im|in der|in den|am|an der|in meinem|in meiner|in meinen) {_DE_BODY_PARTS}"
    r"\w*\b",
    rf"\b{_DE_BODY_PARTS}\w* (?:\w+ ){{0,3}}?(?:tut|tun|tat|taten) (?:\w+ ){{0,3}}?weh\b",
    rf"\b(?:tut|tun|tat|taten) (?:mir )?(?:der|die|das|mein\w*) {_DE_BODY_PARTS}\w*"
    r" (?:\w+ ){0,3}?weh\b",
    rf"\b{_DE_BODY_PARTS}\w* (?:\w+ ){{0,2}}?(?:schmerzt|schmerzte|schmerzen)\b",
    rf"\bschmerzt (?:mir |mich )?(?:der|die|das|mein\w*) {_DE_BODY_PARTS}",
    r"\b(?:stechende|starke|plötzliche|ziehende|chronische|ausstrahlende)[nr]? schmerzen\b",
    # The user's own pain, or pain while training ("Schmerzen beim Kreuzheben"), not about the
    # muscles ("Schmerzen in den Muskeln").
    _outside_muscle_talk(
        r"\b(?:ich habe|ich hab|ich hatte|habe ich|hab ich|ich bekomme|ich kriege|ich spüre)"
        r" (?:\w+ ){0,3}?schmerzen\b"
    ),
    _outside_muscle_talk(
        rf"\bschmerzen (?:beim|bei|nach dem|nach|während des|während dem|vom) {_DE_TRAINING}\b"
    ),
    _outside_muscle_talk(r"\bwehgetan\b|\b(?:es|das) tut (?:mir )?weh,? (?:wenn|beim|nach)\b"),
]

# Throwing up counts after eating, not after training ("nach dem Training muss ich kotzen").
_DE_DISORDERED_PATTERNS = [
    r"\b(?:magersucht|magersüchtig\w*|anorexie|anorektisch\w*|bulimie|bulimisch\w*"
    r"|ess-brech-sucht|essbrechsucht|binge-eating-störung|essstörung(?:en)?"
    r"|gestörte[ns]? essverhalten|orthorexie)\b",
    r"\b(?:erbreche|übergebe) (?:ich )?mich (?:\w+ ){0,2}?nach (?:dem|jedem) essen\b",
    r"\bmich (?:\w+ ){0,3}?nach (?:dem|jedem) essen (?:übergeben|erbrechen)\b",
    r"\b(?:erbreche|erbrechen|übergeben|kotze|kotzen)(?: (?:ich|mich))? (?:\w+ )?nach (?:dem"
    r"|jedem) essen\b",
    r"\bmich (?:absichtlich |selbst )?zum (?:erbrechen|kotzen|übergeben) (?:bringen|bringe"
    r"|gebracht)\b",
    r"\bfinger in den hals\b",
    r"\b(?:nehme|nehmen|benutze|nutze|genommen|einnehmen|missbrauche|missbrauch von) (?:\w+ )?"
    r"(?:abführmittel|abführtabletten)\b",
    r"\b(?:abführmittel|abführtabletten|entwässerungstabletten|diuretika)\w*\b(?:\W+\w+){0,6}?"
    r"\W+(?:abnehmen|abzunehmen|gewicht|gewichtsverlust)\b",
    r"\b(?:abnehmen|abzunehmen|gewichtsverlust)\b(?:\W+\w+){0,4}?\W+(?:abführmittel"
    r"|abführtabletten|entwässerungstabletten|diuretika)\b",
    r"\b(?:hungere (?:ich )?mich|mich (?:aus)?hungern|mich aushungere)\b",
    r"\b(?:tagelang|eine woche|\d+ tage(?: lang)?) (?:gar |überhaupt )?nichts (?:mehr )?(?:essen"
    r"|zu essen)\b",
    # As in English, stopping counts only completely or for a time.
    r"\b(?:höre|hör) (?:komplett|ganz|vollständig) auf zu essen\b",
    r"\bauf zu essen,? (?:für (?:tage|eine woche|\d+ tage)|tagelang)\b",
    r"\b(?:ich hasse|hasse) meinen körper\b",
    r"\b(?:ekle mich vor|schäme mich für) meinem körper\b|\bschäme mich für meinen körper\b",
    r"\bfühle mich (?:so |total |sehr |extrem )?(?:schuldig|eklig|ekelhaft) nach (?:dem|jedem)"
    r" essen\b",
    r"\bfühle mich (?:\w+ ){0,2}?nach (?:dem|jedem) essen (?:so |total |sehr )?(?:schuldig|eklig"
    r"|ekelhaft)\b",
    r"\bmich (?:selbst )?(?:bestrafen|bestrafe)\b",
]
# An intake per day below the calorie floor: "ich esse nur 800 kcal am Tag", "täglich 800 kcal
# essen", "mit 600 kcal pro Tag leben". The day must be named before or after the amount; a part of
# the intake or a difference ("500 kcal am Tag weniger essen", "300 kcal am Tag aus Snacks") does
# not count. German writes thousands with a dot ("1.100").
# A whole number, not the end of one ("1,5 kcal").
_DE_NUMBER = (
    r"~?(?<![\w.,])(?P<kcal>\d{1,2}(?:[.,]\d{3}){1,2}|\d{1,7}) ?(?:k?cals?|kilokalorien|kalorien)"
)
_DE_DAY = r"(?:(?:am|pro|jeden|je) tag|/ ?tag|täglich|pro 24 ?h)"
_DE_QUALIFIERS = (
    r"(?:nur|noch|etwa|ungefähr|circa|ca\.|knapp|maximal|höchstens|weniger als|unter|so|gerade"
    r"|um die|rund|bloss|max\.)"
)
_DE_NOT_A_PART = (
    r"(?! (?:weniger|mehr|zusätzlich|extra|über|unter|defizit|überschuss|von|aus|durch|im|als"
    r"|an)\b)"
)
# A word between the verb and the amount: no amount of energy, no comma and no joining word, so
# a second verb and amount ("ich esse 2500 kcal und verbrenne 500 kcal am Tag"), a food's own
# energy ("Proteinriegel mit 200 kcal", "3 Mahlzeiten à 600 kcal") or a surplus right before
# the amount ("zusätzlich 500 kcal am Tag") is not read as the day's intake, while a time is
# ("seit 3 Wochen nur 800 kcal am Tag"), and so is "extra" in another sense ("extra wenig, nur
# 800 kcal am Tag" said without the comma).
_DE_INTAKE_GAP = (
    # A surplus may be rough ("zusätzlich etwa 500 kcal"); "extra nur 800 kcal" is not one.
    r"(?: (?!(?:und|oder|aber|mit|je|sowie|plus|à|a|zu)\b"
    r"|(?:zusätzlich|extra)(?: (?:noch|etwa|ungefähr|circa|ca\.|rund|um die))? ~?\d)"
    r"(?![^\s,;]*?\d ?(?:k?cals?|kilokalorien|kalorien)\b)[^\s,;]+)"
)
_DE_LOW_INTAKE_PATTERNS = [
    # The verb first: "ich esse (am Tag) nur 800 kcal (am Tag)".
    r"\b(?:esse|isst|essen|esst|ass|gegessen|lebe von|leben von|komme mit|überlebe mit"
    r"|bleibe unter|bleiben unter|beschränke mich auf|reduziere auf|runter auf"
    r"|ernähre mich von)"
    rf"(?P<pre> {_DE_DAY})?(?: {_DE_QUALIFIERS}){{0,3}} {_DE_NUMBER}(?P<post> {_DE_DAY})?\b"
    rf"{_DE_NOT_A_PART}",
    # The verb first with other words before the amount and the day right after it: "ich esse
    # seit zwei Wochen nur 800 kcal am Tag".
    r"\b(?:esse|isst|essen|esst|ass|lebe von|leben von|komme mit|bleibe unter|bleiben unter)"
    rf"{_DE_INTAKE_GAP}{{1,4}}? (?:{_DE_QUALIFIERS} ){{0,3}}{_DE_NUMBER}(?P<post> {_DE_DAY})\b"
    rf"{_DE_NOT_A_PART}",
    # "Ich nehme (täglich) nur 800 kcal (am Tag) zu mir".
    rf"\b(?:nehme|nimmst|nimmt|nehmen)(?P<pre> {_DE_DAY})?{_DE_INTAKE_GAP}{{0,3}}?"
    rf"(?: {_DE_QUALIFIERS}){{0,3}} {_DE_NUMBER}"
    rf"(?P<post> {_DE_DAY})?(?: (?!(?:weniger|mehr|zusätzlich|extra)\b)[^\s\d,;]+)? zu mir\b",
    # The verb last: "(täglich) nur 800 kcal (am Tag) essen".
    rf"(?P<pre>\b{_DE_DAY} )?(?:{_DE_QUALIFIERS} ){{0,3}}{_DE_NUMBER}(?P<post> {_DE_DAY})? "
    r"(?:zu )?(?:essen|esse|isst|zu mir nehmen|aufnehmen|leben|auskommen|überleben)\b",
]

_PED_TERMS_RE = re.compile(rf"{_PED_TERMS}|{german(_DE_PED_TERMS)}")
_PED_USE_RE = re.compile(rf"{_PED_USE}|{german(_DE_PED_USE)}")


def _compiled(english: list[str], german_patterns: list[str]) -> list[re.Pattern[str]]:
    """Compile the English patterns and the German ones with their umlaut spellings."""
    return [re.compile(p) for p in [*english, *map(german, german_patterns)]]


_REDIRECTS = [
    (Concern.MINOR, _compiled(_MINOR_PATTERNS, _DE_MINOR_PATTERNS)),
    (Concern.PREGNANCY, _compiled(_PREGNANCY_PATTERNS, _DE_PREGNANCY_PATTERNS)),
    # Before MEDICAL, as in Concern: find_concern() returns the first match in this list.
    (Concern.INJURY, _compiled(_INJURY_PATTERNS, _DE_INJURY_PATTERNS)),
    (Concern.MEDICAL, _compiled(_MEDICAL_PATTERNS, _DE_MEDICAL_PATTERNS)),
    (Concern.DISORDERED_EATING, _compiled(_DISORDERED_PATTERNS, _DE_DISORDERED_PATTERNS)),
]
_DE_LOW_INTAKE = [re.compile(german(p)) for p in _DE_LOW_INTAKE_PATTERNS]


def _below_floor(folded: str) -> bool:
    """Return True if the text names a daily intake below the calorie floor."""
    amounts = [match.group(1) for match in _LOW_INTAKE.finditer(folded)]
    # German: the day named before or after the amount.
    for pattern in _DE_LOW_INTAKE:
        for match in pattern.finditer(folded):
            day = match.groupdict()
            if day.get("pre") or day.get("post"):
                amounts.append(match["kcal"])
    # 0 counts too: "eat 0 calories a day for a week" is a fast, below the floor.
    return any(int(re.sub(r"[.,]", "", kcal)) < config.CALORIE_FLOOR_KCAL for kcal in amounts)


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
