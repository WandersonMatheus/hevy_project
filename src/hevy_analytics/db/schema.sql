CREATE TABLE IF NOT EXISTS workouts (
    id            TEXT PRIMARY KEY,
    title         TEXT,
    description   TEXT,
    routine_id    TEXT,
    start_time    TEXT NOT NULL,
    end_time      TEXT,
    updated_at    TEXT NOT NULL,
    created_at    TEXT,
    deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    synced_at     TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_workouts_start_time ON workouts(start_time);
CREATE INDEX IF NOT EXISTS idx_workouts_updated_at ON workouts(updated_at);

CREATE TABLE IF NOT EXISTS exercise_templates (
    id                      TEXT PRIMARY KEY,
    title                   TEXT,
    type                    TEXT,
    primary_muscle_group    TEXT,
    secondary_muscle_groups TEXT,
    equipment               TEXT,
    is_custom               INTEGER,
    synced_at               TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_templates_primary_muscle ON exercise_templates(primary_muscle_group);

CREATE TABLE IF NOT EXISTS workout_exercises (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id           TEXT NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
    exercise_index       INTEGER NOT NULL,
    title                TEXT,
    notes                TEXT,
    exercise_template_id TEXT REFERENCES exercise_templates(id),
    superset_id          INTEGER,
    UNIQUE(workout_id, exercise_index)
);
CREATE INDEX IF NOT EXISTS idx_wex_workout_id ON workout_exercises(workout_id);
CREATE INDEX IF NOT EXISTS idx_wex_template_id ON workout_exercises(exercise_template_id);

CREATE TABLE IF NOT EXISTS sets (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_exercise_id  INTEGER NOT NULL REFERENCES workout_exercises(id) ON DELETE CASCADE,
    set_index            INTEGER NOT NULL,
    type                 TEXT,
    weight_kg            REAL,
    reps                 INTEGER,
    distance_meters      REAL,
    duration_seconds     REAL,
    rpe                  REAL,
    custom_metric        TEXT,
    UNIQUE(workout_exercise_id, set_index)
);
CREATE INDEX IF NOT EXISTS idx_sets_wex_id ON sets(workout_exercise_id);

CREATE TABLE IF NOT EXISTS routines (
    id           TEXT PRIMARY KEY,
    title        TEXT,
    notes        TEXT,
    updated_at   TEXT,
    created_at   TEXT,
    raw_json     TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    key          TEXT PRIMARY KEY,
    value        TEXT,
    updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at          TEXT,
    finished_at         TEXT,
    since_cursor        TEXT,
    events_processed    INTEGER,
    workouts_upserted   INTEGER,
    workouts_deleted    INTEGER,
    templates_upserted  INTEGER,
    status              TEXT,
    error_message       TEXT
);

-- Manually logged, since Hevy's API doesn't track bodyweight. One entry per
-- calendar date; logging again on the same date overwrites (upsert).
CREATE TABLE IF NOT EXISTS bodyweight_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date    TEXT NOT NULL UNIQUE,
    weight_kg   REAL NOT NULL,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bodyweight_log_date ON bodyweight_logs(log_date);

-- goal_type: 'exercise_weight' | 'bodyweight_multiple' | 'baseline_multiple' | 'pain'
--   exercise_weight:      target_value = fixed kg total, exercise_template_id set
--   bodyweight_multiple:  target_value = multiplier of current bodyweight, muscle_groups set
--   baseline_multiple:    target_value = multiplier of e1RM captured AT CREATION (baseline_json), muscle_groups set
--   pain:                 target_value = target pain score (usually 0), body_part set
CREATE TABLE IF NOT EXISTS goals (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    label                 TEXT NOT NULL,
    goal_type             TEXT NOT NULL,
    exercise_template_id  TEXT REFERENCES exercise_templates(id),
    muscle_groups         TEXT,      -- JSON array, for muscle-group-scoped goals
    target_value          REAL NOT NULL,
    baseline_json         TEXT,      -- JSON {exercise_template_id: baseline_e1rm}, only for baseline_multiple
    body_part             TEXT,      -- free text, only for pain goals
    active                INTEGER NOT NULL DEFAULT 1,
    created_at            TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pain_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date    TEXT NOT NULL,
    body_part   TEXT NOT NULL,
    pain_score  REAL NOT NULL,
    notes       TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(log_date, body_part)
);
CREATE INDEX IF NOT EXISTS idx_pain_logs_body_part ON pain_logs(body_part);
