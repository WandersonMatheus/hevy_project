import numpy as np
import pandas as pd

from hevy_analytics.analytics.formulas import estimate_1rm, is_hard_set
from hevy_analytics.config.landmarks import Landmarks


def best_e1rm_per_session(sets_df: pd.DataFrame, landmarks: Landmarks) -> pd.DataFrame:
    """Best estimated 1RM per (exercise_template_id, session/date), using only
    hard sets with reps <= max_reps_for_estimate (formula accuracy degrades
    past that point)."""
    df = sets_df.dropna(subset=["weight_kg", "reps", "exercise_template_id"]).copy()
    df = df[df["set_type"].apply(lambda t: is_hard_set(t, landmarks.hard_set_types))]
    df = df[df["reps"] <= landmarks.max_reps_for_estimate]
    # weight_kg == 0 (pure bodyweight movements logged without added load)
    # makes every 1RM formula collapse to 0 -- not a meaningful data point.
    df = df[df["weight_kg"] > 0]
    if df.empty:
        return pd.DataFrame(columns=["exercise_template_id", "workout_date", "e1rm"])

    df["e1rm"] = df.apply(
        lambda r: estimate_1rm(r["weight_kg"], int(r["reps"]), landmarks.one_rm_formula),
        axis=1,
    )
    df["workout_date"] = df["start_time"].dt.date

    result = (
        df.groupby(["exercise_template_id", "workout_date"])["e1rm"]
        .max()
        .reset_index()
        .sort_values(["exercise_template_id", "workout_date"])
    )
    return result


def project_trend(e1rm_series: pd.DataFrame, horizon_weeks: int = 3) -> dict:
    """Naive linear projection of e1RM over time for a single exercise.
    `e1rm_series` must have columns `workout_date` and `e1rm`, already
    filtered to one exercise. Not a real forecasting model -- just a trend
    line extrapolated forward; treat the projection as a rough signal only."""
    if len(e1rm_series) < 2:
        return {"slope_per_week": None, "projected_points": []}

    dates = pd.to_datetime(e1rm_series["workout_date"])
    x = (dates - dates.min()).dt.days.to_numpy(dtype=float)
    y = e1rm_series["e1rm"].to_numpy(dtype=float)

    slope, intercept = np.polyfit(x, y, 1)
    slope_per_week = slope * 7

    last_x = x.max()
    last_date = dates.max()
    projected_points = []
    for week in range(1, horizon_weeks + 1):
        proj_x = last_x + week * 7
        proj_y = slope * proj_x + intercept
        proj_date = last_date + pd.Timedelta(days=week * 7)
        projected_points.append({"date": proj_date.date(), "e1rm": proj_y})

    return {"slope_per_week": slope_per_week, "projected_points": projected_points}
