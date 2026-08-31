import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from hevy_analytics.api.client import HevyClient
from hevy_analytics.ingest.upsert import (
    delete_workout,
    upsert_exercise_template,
    upsert_routine,
    upsert_workout,
)
from hevy_analytics.settings import EPOCH_CURSOR, PAGE_SIZE


@dataclass
class SyncResult:
    workouts_upserted: int
    workouts_deleted: int
    templates_upserted: int
    routines_upserted: int
    events_processed: int
    duration_seconds: float
    new_cursor: str


def _get_cursor(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT value FROM sync_state WHERE key = 'last_sync_since'"
    ).fetchone()
    return row["value"] if row else EPOCH_CURSOR


def _set_cursor(conn: sqlite3.Connection, value: str) -> None:
    conn.execute(
        """
        INSERT INTO sync_state (key, value, updated_at)
        VALUES ('last_sync_since', ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (value, datetime.now(timezone.utc).isoformat()),
    )


def run_sync(conn: sqlite3.Connection, client: HevyClient) -> SyncResult:
    started_at = datetime.now(timezone.utc)
    start_perf = time.perf_counter()
    since = _get_cursor(conn)

    templates_upserted = 0
    routines_upserted = 0
    workouts_upserted = 0
    workouts_deleted = 0
    events_processed = 0
    max_updated_at = since

    try:
        for template in client.iter_exercise_templates():
            upsert_exercise_template(conn, template)
            templates_upserted += 1

        for routine in client.iter_routines():
            upsert_routine(conn, routine)
            routines_upserted += 1

        for event in client.iter_workout_events(since=since, page_size=PAGE_SIZE):
            events_processed += 1
            event_type = event.get("type")
            workout = event.get("workout")
            if workout is None:
                continue

            if event_type == "updated":
                upsert_workout(conn, workout)
                workouts_upserted += 1
            elif event_type == "deleted":
                delete_workout(conn, workout["id"])
                workouts_deleted += 1
            else:
                continue

            workout_updated_at = workout.get("updated_at")
            if workout_updated_at and workout_updated_at > max_updated_at:
                max_updated_at = workout_updated_at

        _set_cursor(conn, max_updated_at)

        duration = time.perf_counter() - start_perf
        conn.execute(
            """
            INSERT INTO sync_log
                (started_at, finished_at, since_cursor, events_processed, workouts_upserted, workouts_deleted, templates_upserted, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'success', NULL)
            """,
            (
                started_at.isoformat(),
                datetime.now(timezone.utc).isoformat(),
                since,
                events_processed,
                workouts_upserted,
                workouts_deleted,
                templates_upserted,
            ),
        )
        conn.commit()

        return SyncResult(
            workouts_upserted=workouts_upserted,
            workouts_deleted=workouts_deleted,
            templates_upserted=templates_upserted,
            routines_upserted=routines_upserted,
            events_processed=events_processed,
            duration_seconds=duration,
            new_cursor=max_updated_at,
        )

    except Exception as exc:
        conn.rollback()
        conn.execute(
            """
            INSERT INTO sync_log
                (started_at, finished_at, since_cursor, events_processed, workouts_upserted, workouts_deleted, templates_upserted, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'failed', ?)
            """,
            (
                started_at.isoformat(),
                datetime.now(timezone.utc).isoformat(),
                since,
                events_processed,
                workouts_upserted,
                workouts_deleted,
                templates_upserted,
                str(exc),
            ),
        )
        conn.commit()
        raise
