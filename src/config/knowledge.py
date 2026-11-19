"""The knowledge base: topics, chunking, the index, retrieval, query translation, the download."""

# A question whose plan has only this topic is answered from training chunks or not at all: no
# nutrition chunk stands in for a missing training source (T9.20).
TRAINING_TOPIC = "resistance_training"
# The topics a source can be tagged with; query translation filters on them (T3.2).
TOPICS: tuple[str, ...] = (
    "protein",
    "carbohydrate",
    "fat",
    "energy_balance",
    "nutrient_timing",
    "supplements",
    # Training principles (PRD feature 26, T9.19): only on the approved training sources, never on
    # a nutrition source (docs/SOURCES.md, "Training sources").
    TRAINING_TOPIC,
)
# 1 = ISSN position stand, 2 = other peer-reviewed review or meta-analysis (docs/SOURCES.md).
EVIDENCE_TIERS: tuple[int, ...] = (1, 2)

# Chunking of the article text (docs/ARCHITECTURE.md section 4). A chunk is at most CHUNK_SIZE
# characters, its section title included (a chunk joined with a short piece may be up to
# CHUNK_SIZE + CHUNK_MIN_CHARS); neighbouring chunks of a section share CHUNK_OVERLAP.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
# Room always left for the text after a very long section title, so the splitter still works;
# such a chunk may then be longer than CHUNK_SIZE (no approved article comes close). Must stay above
# CHUNK_OVERLAP, or the splitter raises ValueError.
CHUNK_MIN_BODY_CHARS = 400
# A piece of a section shorter than this (title included) is joined to the piece before it, or else
# to the one after it, as long as the result is at most CHUNK_SIZE + CHUNK_MIN_CHARS. The splitter's
# short pieces are often little more than the overlap they repeat, and such chunks were near short,
# generic queries (T3.7). A section that is short as a whole stays one short chunk.
CHUNK_MIN_CHARS = 300
# Section title for paragraphs that sit directly in the body, outside any section (e.g. #18a).
MAIN_TEXT_TITLE = "Main text"
# Back matter that many articles put inside <body>: dropped, as it is not nutrition content (owner's
# choice in T2.2), and so are the registration notes of an abstract, a bare PROSPERO ID that short
# queries matched (T3.7; a Methods "Protocol and registration" section is content and stays).
# Matched on the section's sec-type, or on its title in lower case with numbering and punctuation
# removed; a title starting with "appendix" is dropped too.
INGEST_DROPPED_SEC_TYPES: frozenset[str] = frozenset(
    {
        "ack",
        "ai-statement",
        "app",
        "associated-data",
        "coi-statement",
        "contrib-info",
        "data-availability",
        "data-availability-statement",
        "disclaimer",
        "display-objects",
        "fn-group",
        "history",
        "kwd-group",
        "ref-list",
        "supplementary-material",
        "supplementary-materials",
    }
)
INGEST_DROPPED_SEC_TITLES: frozenset[str] = frozenset(
    {
        "abbreviations",
        "acknowledgement",
        "acknowledgements",
        "acknowledgment",
        "acknowledgments",
        "associated data",
        "author contributions",
        "authors contributions",
        "availability of data and materials",
        "clinical trial registration",
        "competing interests",
        "conflict of interest",
        "conflict of interest statement",
        "conflicts of interest",
        "conflicts of interest statement",
        "consent for publication",
        "contributor information",
        "correction note",
        "data availability",
        "data availability statement",
        "declarations",
        "disclaimer",
        "disclaimer publishers note",
        "disclosure",
        "disclosure statement",
        "ethics approval",
        "ethics approval and consent to participate",
        "ethics approval statement",
        "footnotes",
        "funding",
        "funding statement",
        "generative ai statement",
        "infographic",
        "informed consent statement",
        "institutional review board statement",
        "publishers note",
        "references",
        "supplemental material",
        "supplementary information",
        "supplementary material",
        "supplementary materials",
        "supporting information",
        "systematic review registration",
        "trial registration",
    }
)

# The vector index (docs/ARCHITECTURE.md section 4): a persistent Chroma collection in CHROMA_DIR,
# embedded in the app's process only (never a server; .claude/rules/security-privacy.md),
# rebuilt by BUILD_INDEX_COMMAND (D7). Chroma names need 3-512 characters from [a-zA-Z0-9._-].
CHROMA_COLLECTION = "nutrition-sources"
BUILD_INDEX_COMMAND = "python scripts/build_index.py"
# Chunks sent to the embedding API per request: about 50 KB of text each, so one failed request
# loses little work and the build can show its progress.
EMBEDDING_BATCH_SIZE = 64

# Retrieval and answers for one chat turn (T3.1; query translation and hybrid search extend it in
# T3.2 and T3.3). The best chunks after RRF given to the answer model, labelled [S1]...[S6]; also
# the length of each vector and keyword list that RRF merges.
RETRIEVAL_TOP_K = 6
# Cosine distance (0 = same meaning, up to 2) above which a chunk counts as not relevant to the
# question. Measured on the real index (O5, 2026-10-20, 28 questions; docs/TESTING.md): questions
# the sources cover, short or long, had their nearest chunk at 0.28-0.54; unrelated ones at 0.70
# and above; near-domain ones (a dog's diet, running shoes, insulin) at 0.56-0.70. 0.62 sits midway
# and favours answering: a near-domain question that passes costs one model call, which the
# prompt declines or redirects, while a covered question that is blocked gets no answer at all.
# Measured on questions as asked, so only the question's own nearest chunk decides whether the
# sources cover it; once they do, its rewrites add the chunks within the same limit (T3.8).
RETRIEVAL_MAX_DISTANCE = 0.62
# Reciprocal Rank Fusion (T3.3, Hard 1): a chunk scores the sum of 1 / (RRF_K + rank) over the
# ranked lists it is in (rank 1 is the top). 60 is the constant of the original RRF paper; it
# keeps one list's top rank from outweighing a chunk that several lists rank a little lower.
RRF_K = 60
# The most chunks of one source that come first in the fused list (T8.3): without a cap one article
# filled all six places (q2, q3, q10) and a second source never reached the answer model. Chunks
# over the cap are only used, in fused order, when too few other sources are left to fill the list.
MAX_CHUNKS_PER_SOURCE = 3

# Query translation (T3.2; docs/ARCHITECTURE.md section 5): one QUERY_TRANSLATION_MODEL call
# rewrites the question and picks optional filters. Its system prompt is written by the owner (O7).
# Rewrites per question; the question itself is searched as well (owner's choice in T3.2).
QUERY_REWRITES = 3
# Longest rewrite accepted; a longer one makes the whole reply invalid (fallback to the question).
QUERY_REWRITE_MAX_CHARS = 300
# The years a min_year filter may name; the oldest approved source is from 2014. A year with no
# source after it finds nothing, so the search runs again without filters.
QUERY_MIN_YEAR_RANGE = (2000, 2100)
# The tool results an answer may rest on (T9.3): a calculation, a food found or not found, and
# "profile needed", whose answer points to the "Add your details" button (owner's choice of
# 2026-10-29, after the security review of PR #46). A refused call ("invalid") or a tool that
# failed ("error") is no basis, so a reply after it stays hidden.
BASIS_TOOL_STATUSES = frozenset({"ok", "found", "not_found", "profile_needed"})

# Article XML comes only from the Europe PMC REST API, which allows automated retrieval
# (copyright policy rule 10); the PMC, Europe PMC and publisher websites are never scripted.
EUROPE_PMC_FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
DOWNLOAD_USER_AGENT = (
    "fitcoach-ai-assistant/0.1 (study project; source download; "
    "https://github.com/NMH1988/fitcoach-ai-assistant)"
)
# Wait between two requests, to be polite to the API.
DOWNLOAD_PAUSE_SECONDS = 1.0
DOWNLOAD_TIMEOUT_SECONDS = 30
# The largest approved article is under 1 MB; anything far bigger is not an article.
DOWNLOAD_MAX_BYTES = 10_000_000
