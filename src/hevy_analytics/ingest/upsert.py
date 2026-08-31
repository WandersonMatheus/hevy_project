import json
import sqlite3
from datetime import datetime, timezone


def upsert_exercise_template(conn: sqlite3.Connection, template: dict) -> None:
    conn.execute(
        """
        INSERT INTO exercise_templates
            (id, title, type, primary_muscle_group, secondary_muscle_groups, equipment, is_custom, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            type=excluded.type,
            primary_muscle_group=excluded.primary_muscle_group,
            secondary_muscle_groups=excluded.secondary_muscle_groups,
            equipment=excluded.equipment,
            is_custom=excluded.is_custom,
            synced_at=excluded.synced_at
        """,
        (
            template["id"],
            template.get("title"),
            template.get("type"),
            template.get("primary_muscle_group"),
            json.dumps(template.get("secondary_muscle_groups") or []),
            template.get("equipment"),
            int(bool(template.get("is_custom"))),
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def upsert_routine(conn: sqlite3.Connection, routine: dict) -> None:
    conn.execute(
        """
        INSERT INTO routines (id, title, notes, updated_at, created_at, raw_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            notes=excluded.notes,
            updated_at=excluded.updated_at,
            created_at=excluded.created_at,
            raw_json=excluded.raw_json
        """,
        (
            routine["id"],
            routine.get("title"),
            routine.get("notes"),
            routine.get("updated_at"),
            routine.get("created_at"),
            json.dumps(routine),
        ),
    )


def upsert_workout(conn: sqlite3.Connection, workout: dict) -> None:
    workout_id = workout["id"]

    conn.execute(
        """
        INSERT INTO workouts
            (id, title, description, routine_id, start_time, end_time, updated_at, created_at, deleted, deleted_at, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            description=excluded.description,
            routine_id=excluded.routine_id,
            start_time=excluded.start_time,
            end_time=excluded.end_time,
            updated_at=excluded.updated_at,
            created_at=excluded.created_at,
            deleted=0,
            deleted_at=NULL,
            synced_at=excluded.synced_at
        """,
        (
            workout_id,
            workout.get("title"),
            workout.get("description"),
            workout.get("routine_id"),
            workout["start_time"],
            workout.get("end_time"),
            workout["updated_at"],
            workout.get("created_at"),
            datetime.now(timezone.utc).isoformat(),
        ),
    )

    existing_exercise_ids = [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM workout_exercises WHERE workout_id = ?", (workout_id,)
        )
    ]
    if existing_exercise_ids:
        placeholders = ",".join("?" * len(existing_exercise_ids))
        conn.execute(
            f"DELETE FROM sets WHERE workout_exercise_id IN ({placeholders})",
            existing_exercise_ids,
        )
    conn.execute("DELETE FROM workout_exercises WHERE workout_id = ?", (workout_id,))

    for exercise in workout.get("exercises", []):
        cursor = conn.execute(
            """
            INSERT INTO workout_exercises
                (workout_id, exercise_index, title, notes, exercise_template_id, superset_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                workout_id,
                exercise["index"],
                exercise.get("title"),
                exercise.get("notes"),
                exercise.get("exercise_template_id"),
                exercise.get("superset_id"),
            ),
        )
        workout_exercise_id = cursor.lastrowid

        for s in exercise.get("sets", []):
            conn.execute(
                """
                INSERT INTO sets
                    (workout_exercise_id, set_index, type, weight_kg, reps, distance_meters, duration_seconds, rpe, custom_metric)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workout_exercise_id,
                    s["index"],
                    s.get("type"),
                    s.get("weight_kg"),
                    s.get("reps"),
                    s.get("distance_meters"),
                    s.get("duration_seconds"),
                    s.get("rpe"),
                    json.dumps(s.get("custom_metric")) if s.get("custom_metric") is not None else None,
                ),
            )


def delete_workout(conn: sqlite3.Connection, workout_id: str) -> None:
    conn.execute(
        "UPDATE workouts SET deleted = 1, deleted_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), workout_id),
    )
