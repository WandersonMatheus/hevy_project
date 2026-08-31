import json
import sqlite3

import pandas as pd


def load_workouts(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT * FROM workouts WHERE deleted = 0",
        conn,
        parse_dates=["start_time", "end_time", "updated_at", "created_at"],
    )
    return df


def load_sets(conn: sqlite3.Connection) -> pd.DataFrame:
    """One row per set, joined with its parent workout_exercise and workout,
    ready for volume/tonnage/1RM aggregation."""
    query = """
        SELECT
            w.id AS workout_id,
            w.start_time,
            w.title AS workout_title,
            we.id AS workout_exercise_id,
            we.title AS exercise_title,
            we.exercise_template_id,
            s.id AS set_id,
            s.set_index,
            s.type AS set_type,
            s.weight_kg,
            s.reps,
            s.rpe
        FROM sets s
        JOIN workout_exercises we ON we.id = s.workout_exercise_id
        JOIN workouts w ON w.id = we.workout_id
        WHERE w.deleted = 0
    """
    df = pd.read_sql_query(query, conn, parse_dates=["start_time"])
    return df


def load_exercise_templates(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM exercise_templates", conn)
    df["secondary_muscle_groups"] = df["secondary_muscle_groups"].apply(
        lambda x: json.loads(x) if x else []
    )
    return df


def load_sync_state(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT key, value FROM sync_state").fetchall()
    return {row["key"]: row["value"] for row in rows}


def load_last_sync_log(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT * FROM sync_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None
