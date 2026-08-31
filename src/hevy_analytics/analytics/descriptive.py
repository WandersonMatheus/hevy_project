import pandas as pd

from hevy_analytics.analytics.formulas import is_hard_set, tonnage
from hevy_analytics.analytics.time_utils import week_start
from hevy_analytics.config.landmarks import Landmarks


def _hard_sets_with_muscle_groups(
    sets_df: pd.DataFrame, templates_df: pd.DataFrame, landmarks: Landmarks
) -> pd.DataFrame:
    hard = sets_df[
        sets_df["set_type"].apply(lambda t: is_hard_set(t, landmarks.hard_set_types))
    ].copy()
    hard["week"] = week_start(hard["start_time"])
    merged = hard.merge(
        templates_df[["id", "primary_muscle_group", "secondary_muscle_groups"]],
        left_on="exercise_template_id",
        right_on="id",
        how="left",
    )
    return merged


def weekly_muscle_group_volume(
    sets_df: pd.DataFrame, templates_df: pd.DataFrame, landmarks: Landmarks
) -> pd.DataFrame:
    """Hard sets per (week, muscle_group), crediting 1.0 for the primary
    mover and `secondary_muscle_credit` for each secondary mover."""
    merged = _hard_sets_with_muscle_groups(sets_df, templates_df, landmarks)
    if merged.empty:
        return pd.DataFrame(columns=["week", "muscle_group", "hard_sets"])

    primary = (
        merged.dropna(subset=["primary_muscle_group"])
        .groupby(["week", "primary_muscle_group"])
        .size()
        .reset_index(name="hard_sets")
        .rename(columns={"primary_muscle_group": "muscle_group"})
    )

    secondary_rows = merged[["week", "secondary_muscle_groups"]].explode(
        "secondary_muscle_groups"
    )
    secondary_rows = secondary_rows.dropna(subset=["secondary_muscle_groups"])
    secondary_rows = secondary_rows[secondary_rows["secondary_muscle_groups"] != ""]
    if not secondary_rows.empty:
        secondary = (
            secondary_rows.groupby(["week", "secondary_muscle_groups"])
            .size()
            .reset_index(name="hard_sets")
            .rename(columns={"secondary_muscle_groups": "muscle_group"})
        )
        secondary["hard_sets"] = secondary["hard_sets"] * landmarks.secondary_muscle_credit
    else:
        secondary = pd.DataFrame(columns=["week", "muscle_group", "hard_sets"])

    combined = pd.concat([primary, secondary], ignore_index=True)
    result = combined.groupby(["week", "muscle_group"], as_index=False)["hard_sets"].sum()
    return result.sort_values(["week", "muscle_group"]).reset_index(drop=True)


def session_frequency(workouts_df: pd.DataFrame) -> pd.DataFrame:
    df = workouts_df.copy()
    df["week"] = week_start(df["start_time"])
    return df.groupby("week").size().reset_index(name="sessions")


def session_duration(workouts_df: pd.DataFrame) -> pd.DataFrame:
    df = workouts_df.dropna(subset=["start_time", "end_time"]).copy()
    df["duration_minutes"] = (df["end_time"] - df["start_time"]).dt.total_seconds() / 60
    return df[["start_time", "title", "duration_minutes"]].sort_values("start_time")


def exercise_variety(sets_df: pd.DataFrame) -> pd.DataFrame:
    df = sets_df.copy()
    df["week"] = week_start(df["start_time"])
    return (
        df.groupby("week")["exercise_template_id"]
        .nunique()
        .reset_index(name="distinct_exercises")
    )


def tonnage_trend(sets_df: pd.DataFrame) -> pd.DataFrame:
    df = sets_df.dropna(subset=["weight_kg", "reps"]).copy()
    df["tonnage"] = df.apply(lambda r: tonnage(r["weight_kg"], r["reps"]), axis=1)
    df["week"] = week_start(df["start_time"])
    return df.groupby("week")["tonnage"].sum().reset_index()
