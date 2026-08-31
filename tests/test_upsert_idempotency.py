import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hevy_analytics.db.connection import get_connection, init_db
from hevy_analytics.ingest.upsert import delete_workout, upsert_exercise_template, upsert_workout

SAMPLE_TEMPLATE = {
    "id": "TPL1",
    "title": "Bench Press (Barbell)",
    "type": "weight_reps",
    "primary_muscle_group": "chest",
    "secondary_muscle_groups": ["triceps", "shoulders"],
    "equipment": "barbell",
    "is_custom": False,
}

SAMPLE_WORKOUT = {
    "id": "W1",
    "title": "Push",
    "description": "",
    "routine_id": None,
    "start_time": "2026-01-01T10:00:00+00:00",
    "end_time": "2026-01-01T11:00:00+00:00",
    "updated_at": "2026-01-01T11:00:05.000Z",
    "created_at": "2026-01-01T11:00:05.000Z",
    "exercises": [
        {
            "index": 0,
            "title": "Bench Press (Barbell)",
            "notes": "",
            "exercise_template_id": "TPL1",
            "superset_id": None,
            "sets": [
                {"index": 0, "type": "normal", "weight_kg": 80, "reps": 8, "rpe": 8},
                {"index": 1, "type": "normal", "weight_kg": 80, "reps": 7, "rpe": 9},
            ],
        }
    ],
}


def make_db():
    conn = get_connection(Path(":memory:"))
    init_db(conn)
    return conn


def test_upsert_workout_is_idempotent():
    conn = make_db()
    upsert_exercise_template(conn, SAMPLE_TEMPLATE)
    upsert_workout(conn, SAMPLE_WORKOUT)
    upsert_workout(conn, SAMPLE_WORKOUT)
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM workout_exercises").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0] == 2


def test_upsert_workout_replays_edits_correctly():
    conn = make_db()
    upsert_exercise_template(conn, SAMPLE_TEMPLATE)
    upsert_workout(conn, SAMPLE_WORKOUT)

    edited = {**SAMPLE_WORKOUT}
    edited["exercises"] = [
        {
            **SAMPLE_WORKOUT["exercises"][0],
            "sets": [{"index": 0, "type": "normal", "weight_kg": 82.5, "reps": 8, "rpe": 8}],
        }
    ]
    upsert_workout(conn, edited)
    conn.commit()

    rows = conn.execute("SELECT weight_kg, reps FROM sets").fetchall()
    assert len(rows) == 1
    assert rows[0]["weight_kg"] == 82.5


def test_delete_workout_is_soft_delete():
    conn = make_db()
    upsert_exercise_template(conn, SAMPLE_TEMPLATE)
    upsert_workout(conn, SAMPLE_WORKOUT)
    delete_workout(conn, "W1")
    conn.commit()

    row = conn.execute("SELECT deleted FROM workouts WHERE id = 'W1'").fetchone()
    assert row["deleted"] == 1
    assert conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0] == 2
