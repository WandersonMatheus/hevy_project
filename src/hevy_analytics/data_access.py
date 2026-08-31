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


def log_bodyweight(conn: sqlite3.Connection, log_date: str, weight_kg: float) -> None:
    conn.execute(
        """
        INSERT INTO bodyweight_logs (log_date, weight_kg) VALUES (?, ?)
        ON CONFLICT(log_date) DO UPDATE SET weight_kg = excluded.weight_kg
        """,
        (log_date, weight_kg),
    )
    conn.commit()


def load_bodyweight_logs(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT log_date, weight_kg FROM bodyweight_logs ORDER BY log_date",
        conn,
        parse_dates=["log_date"],
    )


def latest_bodyweight(conn: sqlite3.Connection) -> float | None:
    row = conn.execute(
        "SELECT weight_kg FROM bodyweight_logs ORDER BY log_date DESC LIMIT 1"
    ).fetchone()
    return row["weight_kg"] if row else None


def create_goal(
    conn: sqlite3.Connection,
    label: str,
    goal_type: str,
    target_value: float,
    exercise_template_id: str | None = None,
    muscle_groups: list[str] | None = None,
    baseline: dict | None = None,
    body_part: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO goals (label, goal_type, exercise_template_id, muscle_groups, target_value, baseline_json, body_part)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            label,
            goal_type,
            exercise_template_id,
            json.dumps(muscle_groups) if muscle_groups else None,
            target_value,
            json.dumps(baseline) if baseline else None,
            body_part,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def load_goals(conn: sqlite3.Connection, active_only: bool = True) -> pd.DataFrame:
    query = "SELECT * FROM goals"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY created_at"
    df = pd.read_sql_query(query, conn)
    if df.empty:
        return df
    df["muscle_groups"] = df["muscle_groups"].apply(lambda x: json.loads(x) if pd.notna(x) else [])
    df["baseline_json"] = df["baseline_json"].apply(lambda x: json.loads(x) if pd.notna(x) else {})
    return df


def deactivate_goal(conn: sqlite3.Connection, goal_id: int) -> None:
    conn.execute("UPDATE goals SET active = 0 WHERE id = ?", (goal_id,))
    conn.commit()


def log_pain(conn: sqlite3.Connection, log_date: str, body_part: str, pain_score: float, notes: str = "") -> None:
    conn.execute(
        """
        INSERT INTO pain_logs (log_date, body_part, pain_score, notes) VALUES (?, ?, ?, ?)
        ON CONFLICT(log_date, body_part) DO UPDATE SET pain_score = excluded.pain_score, notes = excluded.notes
        """,
        (log_date, body_part, pain_score, notes),
    )
    conn.commit()


def load_pain_logs(conn: sqlite3.Connection, body_part: str | None = None) -> pd.DataFrame:
    query = "SELECT log_date, body_part, pain_score, notes FROM pain_logs"
    params = ()
    if body_part:
        query += " WHERE body_part = ?"
        params = (body_part,)
    query += " ORDER BY log_date"
    return pd.read_sql_query(query, conn, params=params, parse_dates=["log_date"])
