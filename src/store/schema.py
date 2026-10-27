"""The store's tables as versioned migrations (T9.6; docs/ARCHITECTURE.md section 16).

`MIGRATIONS[n]` takes a database from version n to n + 1 and ends by setting `user_version`;
`db.migrate()` runs the ones a file has not had yet, inside one transaction. Never edit a migration
that has shipped: add a new one, so a file made by an older version is brought up to date.

Every table is STRICT (a value of the wrong type is refused) and every user reference is a foreign
key without ON DELETE CASCADE, so `delete_user_data()` must name each table and a forgotten one
fails instead of leaving rows behind. Timestamps are UTC ISO 8601 text ending in `+00:00` and days
are ISO dates (D21), and both must parse as a real day and time; quantities are checked to be
non-negative, and weights, heights and grams to be above zero. The values of `sex`, `activity` and
`goal` match `src/profile.py` (a test checks it).
Stored records are never changed in place: a trigger refuses any UPDATE on them, so an edit is a
deleted row and a new one (snapshots, profile entries and targets stay as they were written), and
a review, once approved or rejected, is never changed again.
"""

# The GLOB patterns check a UTC timestamp as `values.utc_text()` writes it and a day as
# `values.date_text()` writes it. They are repeated in each CHECK, as SQL is never built from pieces
# (tests/test_store_sql_scan.py).

_V1 = """
CREATE TABLE users (
    id TEXT PRIMARY KEY CHECK (length(id) > 0),
    role TEXT NOT NULL CHECK (role IN ('coach', 'gymer')),
    display_name TEXT NOT NULL CHECK (length(display_name) > 0),
    created_at TEXT NOT NULL
        CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(created_at) IS substr(created_at, 1, 10))
) STRICT;

CREATE TABLE invitations (
    id INTEGER PRIMARY KEY,
    coach_id TEXT NOT NULL REFERENCES users (id),
    code_hash TEXT NOT NULL UNIQUE CHECK (length(code_hash) > 0),
    created_at TEXT NOT NULL
        CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(created_at) IS substr(created_at, 1, 10)),
    expires_at TEXT NOT NULL
        CHECK (expires_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(expires_at) IS substr(expires_at, 1, 10)),
    used_at TEXT CHECK (
        used_at IS NULL OR used_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(used_at) IS substr(used_at, 1, 10)
    )
) STRICT;

CREATE TABLE coach_clients (
    id INTEGER PRIMARY KEY,
    coach_id TEXT NOT NULL REFERENCES users (id),
    client_id TEXT NOT NULL REFERENCES users (id),
    status TEXT NOT NULL CHECK (status IN ('active', 'ended')),
    accepted_at TEXT NOT NULL
        CHECK (accepted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(accepted_at) IS substr(accepted_at, 1, 10)),
    ended_at TEXT CHECK (
        ended_at IS NULL OR ended_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(ended_at) IS substr(ended_at, 1, 10)
    ),
    CHECK (coach_id <> client_id),
    CHECK ((status = 'active') = (ended_at IS NULL))
) STRICT;
CREATE UNIQUE INDEX coach_clients_one_active ON coach_clients (coach_id, client_id)
    WHERE status = 'active';
CREATE INDEX coach_clients_client ON coach_clients (client_id);

CREATE TABLE consents (
    id INTEGER PRIMARY KEY,
    relationship_id INTEGER NOT NULL REFERENCES coach_clients (id),
    scope TEXT NOT NULL CHECK (scope IN ('nutrition', 'training', 'body')),
    granted_at TEXT NOT NULL
        CHECK (granted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(granted_at) IS substr(granted_at, 1, 10)),
    revoked_at TEXT CHECK (
        revoked_at IS NULL OR revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(revoked_at) IS substr(revoked_at, 1, 10)
    )
) STRICT;
CREATE UNIQUE INDEX consents_one_open ON consents (relationship_id, scope)
    WHERE revoked_at IS NULL;

-- The one place the sharing rule lives (D16): a coach may read a client's scope while their
-- relationship is active and the client's consent for it is open. access.authorise_read() and
-- every query that filters by sharing read this view.
CREATE VIEW open_shares AS
SELECT relationship.coach_id, relationship.client_id, consent.scope
FROM coach_clients AS relationship
JOIN consents AS consent ON consent.relationship_id = relationship.id
WHERE relationship.status = 'active' AND consent.revoked_at IS NULL;

CREATE TABLE profile_entries (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users (id),
    height_cm REAL NOT NULL CHECK (height_cm > 0),
    age INTEGER NOT NULL CHECK (age >= 0),
    sex TEXT NOT NULL CHECK (sex IN ('male', 'female')),
    activity TEXT NOT NULL
        CHECK (activity IN ('sedentary', 'light', 'moderate', 'very_active', 'extra_active')),
    goal TEXT NOT NULL CHECK (goal IN ('build_muscle', 'lose_fat', 'maintain')),
    recorded_at TEXT NOT NULL
        CHECK (recorded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(recorded_at) IS substr(recorded_at, 1, 10))
) STRICT;
CREATE INDEX profile_entries_user ON profile_entries (user_id);

CREATE TABLE body_measurements (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users (id),
    weight_kg REAL NOT NULL CHECK (weight_kg > 0),
    measured_on TEXT NOT NULL CHECK (measured_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        AND date(measured_on) IS measured_on),
    recorded_at TEXT NOT NULL
        CHECK (recorded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(recorded_at) IS substr(recorded_at, 1, 10))
) STRICT;
CREATE INDEX body_measurements_user ON body_measurements (user_id);

CREATE TABLE nutrition_targets (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users (id),
    kcal REAL NOT NULL CHECK (kcal >= 0),
    protein_g REAL NOT NULL CHECK (protein_g >= 0),
    carbs_g REAL NOT NULL CHECK (carbs_g >= 0),
    fat_g REAL NOT NULL CHECK (fat_g >= 0),
    set_by TEXT NOT NULL CHECK (set_by IN ('system', 'user', 'coach')),
    calc_version TEXT,
    effective_from TEXT NOT NULL
        CHECK (effective_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND date(effective_from) IS effective_from),
    created_at TEXT NOT NULL
        CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(created_at) IS substr(created_at, 1, 10))
) STRICT;
CREATE INDEX nutrition_targets_user ON nutrition_targets (user_id);

CREATE TABLE meal_items (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users (id),
    consumed_on TEXT NOT NULL CHECK (consumed_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        AND date(consumed_on) IS consumed_on),
    meal TEXT NOT NULL CHECK (meal IN ('breakfast', 'lunch', 'dinner', 'snack')),
    fdc_id INTEGER NOT NULL CHECK (fdc_id > 0),
    food_name TEXT NOT NULL CHECK (length(food_name) > 0),
    grams REAL NOT NULL CHECK (grams > 0),
    kcal REAL NOT NULL CHECK (kcal >= 0),
    protein_g REAL NOT NULL CHECK (protein_g >= 0),
    carbohydrate_g REAL NOT NULL CHECK (carbohydrate_g >= 0),
    fat_g REAL NOT NULL CHECK (fat_g >= 0),
    fiber_g REAL CHECK (fiber_g IS NULL OR fiber_g >= 0),
    recorded_at TEXT NOT NULL
        CHECK (recorded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(recorded_at) IS substr(recorded_at, 1, 10))
) STRICT;
CREATE INDEX meal_items_user_day ON meal_items (user_id, consumed_on);

CREATE TABLE workout_sessions (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users (id),
    performed_on TEXT NOT NULL
        CHECK (performed_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND date(performed_on) IS performed_on),
    recorded_at TEXT NOT NULL
        CHECK (recorded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(recorded_at) IS substr(recorded_at, 1, 10))
) STRICT;
CREATE INDEX workout_sessions_user_day ON workout_sessions (user_id, performed_on);

CREATE TABLE exercise_sets (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES workout_sessions (id),
    exercise_id TEXT NOT NULL CHECK (length(exercise_id) > 0),
    set_no INTEGER NOT NULL CHECK (set_no >= 1),
    reps INTEGER NOT NULL CHECK (reps >= 0),
    weight_kg REAL NOT NULL CHECK (weight_kg >= 0),
    rpe REAL CHECK (rpe IS NULL OR rpe >= 0),
    UNIQUE (session_id, set_no)
) STRICT;

CREATE TABLE preferences (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users (id),
    text TEXT NOT NULL CHECK (length(text) > 0),
    created_at TEXT NOT NULL
        CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(created_at) IS substr(created_at, 1, 10))
) STRICT;
CREATE INDEX preferences_user ON preferences (user_id);

CREATE TABLE ai_reviews (
    id INTEGER PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES users (id),
    coach_id TEXT NOT NULL REFERENCES users (id),
    period_start TEXT NOT NULL
        CHECK (period_start GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND date(period_start) IS period_start),
    metrics TEXT NOT NULL CHECK (json_valid(metrics)),
    data_quality TEXT NOT NULL CHECK (json_valid(data_quality)),
    draft TEXT NOT NULL CHECK (json_valid(draft)),
    final TEXT CHECK (final IS NULL OR json_valid(final)),
    status TEXT NOT NULL CHECK (status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED')),
    edited_by_coach INTEGER NOT NULL DEFAULT 0 CHECK (edited_by_coach IN (0, 1)),
    model_version TEXT NOT NULL CHECK (length(model_version) > 0),
    created_at TEXT NOT NULL
        CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(created_at) IS substr(created_at, 1, 10)),
    reviewed_by TEXT REFERENCES users (id),
    reviewed_at TEXT CHECK (
        reviewed_at IS NULL OR reviewed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(reviewed_at) IS substr(reviewed_at, 1, 10)
    ),
    CHECK ((status = 'PENDING_REVIEW') = (reviewed_by IS NULL AND reviewed_at IS NULL)),
    CHECK ((status = 'APPROVED') = (final IS NOT NULL)),
    CHECK (client_id <> coach_id)
) STRICT;
CREATE INDEX ai_reviews_client ON ai_reviews (client_id);
CREATE INDEX ai_reviews_coach ON ai_reviews (coach_id);

CREATE TABLE ai_evidence_refs (
    id INTEGER PRIMARY KEY,
    review_id INTEGER NOT NULL REFERENCES ai_reviews (id),
    source_id TEXT NOT NULL CHECK (length(source_id) > 0),
    chunk_id TEXT NOT NULL CHECK (length(chunk_id) > 0)
) STRICT;
CREATE INDEX ai_evidence_refs_review ON ai_evidence_refs (review_id);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    actor_id TEXT NOT NULL REFERENCES users (id),
    subject_id TEXT REFERENCES users (id),
    action TEXT NOT NULL
        CHECK (action IN ('read', 'review_approved', 'review_edited', 'review_rejected')),
    resource_type TEXT NOT NULL CHECK (length(resource_type) > 0),
    resource_id INTEGER,
    created_at TEXT NOT NULL
        CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*+00:00'
            AND date(created_at) IS substr(created_at, 1, 10))
) STRICT;
CREATE INDEX audit_log_actor ON audit_log (actor_id);
CREATE INDEX audit_log_subject ON audit_log (subject_id);

CREATE TABLE invite_attempts (
    user_id TEXT NOT NULL REFERENCES users (id),
    day TEXT NOT NULL CHECK (day GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        AND date(day) IS day),
    count INTEGER NOT NULL CHECK (count >= 0),
    PRIMARY KEY (user_id, day)
) STRICT;

CREATE TRIGGER profile_entries_never_changed BEFORE UPDATE ON profile_entries
BEGIN SELECT RAISE(ABORT, 'stored records are never changed in place'); END;
CREATE TRIGGER body_measurements_never_changed BEFORE UPDATE ON body_measurements
BEGIN SELECT RAISE(ABORT, 'stored records are never changed in place'); END;
CREATE TRIGGER nutrition_targets_never_changed BEFORE UPDATE ON nutrition_targets
BEGIN SELECT RAISE(ABORT, 'stored records are never changed in place'); END;
CREATE TRIGGER meal_items_never_changed BEFORE UPDATE ON meal_items
BEGIN SELECT RAISE(ABORT, 'stored records are never changed in place'); END;
CREATE TRIGGER workout_sessions_never_changed BEFORE UPDATE ON workout_sessions
BEGIN SELECT RAISE(ABORT, 'stored records are never changed in place'); END;
CREATE TRIGGER exercise_sets_never_changed BEFORE UPDATE ON exercise_sets
BEGIN SELECT RAISE(ABORT, 'stored records are never changed in place'); END;
CREATE TRIGGER preferences_never_changed BEFORE UPDATE ON preferences
BEGIN SELECT RAISE(ABORT, 'stored records are never changed in place'); END;
CREATE TRIGGER audit_log_never_changed BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'stored records are never changed in place'); END;
CREATE TRIGGER ai_reviews_decided_once BEFORE UPDATE ON ai_reviews
WHEN OLD.status <> 'PENDING_REVIEW'
BEGIN SELECT RAISE(ABORT, 'a decided review is never changed'); END;

PRAGMA user_version = 1;
"""

# In order: MIGRATIONS[0] creates version 1.
MIGRATIONS: tuple[str, ...] = (_V1,)
