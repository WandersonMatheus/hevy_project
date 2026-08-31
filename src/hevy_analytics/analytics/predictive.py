from datetime import datetime, timezone

import numpy as np
import pandas as pd

from hevy_analytics.analytics.formulas import estimate_1rm, is_hard_set
from hevy_analytics.config.landmarks import Landmarks
from hevy_analytics.insights.models import Insight

# Below this, a slope is treated as noise rather than a real trend.
FLAT_SLOPE_THRESHOLD_KG_PER_WEEK = 0.15


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


def generate_predictive_insight(
    exercise_data: pd.DataFrame, trend: dict, exercise_title: str
) -> Insight | None:
    """Narrative insight for a single exercise's e1RM trend: direction,
    magnitude, plain-language interpretation of *why* it matters, and the
    naive-projection caveat -- not just the chart."""
    if trend["slope_per_week"] is None:
        return None

    slope = trend["slope_per_week"]
    n_sessions = len(exercise_data)

    if slope > FLAT_SLOPE_THRESHOLD_KG_PER_WEEK:
        direction = "subindo"
        interpretation = (
            "um ritmo de progresso consistente com ganhos de força ao longo do tempo"
        )
        severity = "positive"
    elif slope < -FLAT_SLOPE_THRESHOLD_KG_PER_WEEK:
        direction = "caindo"
        interpretation = (
            "vale investigar -- pode ser fadiga acumulada, mudança na execução do "
            "exercício, ou uma fase natural de menor intensidade"
        )
        severity = "warning"
    else:
        direction = "estável"
        interpretation = (
            "força mantida, mas sem progresso claro -- pode ser hora de variar o "
            "estímulo (rep range, intensidade) se seu objetivo for continuar evoluindo aqui"
        )
        severity = "info"

    body = (
        f"Com base em {n_sessions} sessões registradas, o 1RM estimado em {exercise_title} "
        f"está {direction}, a {abs(slope):.2f} kg/semana (regressão linear simples). {interpretation.capitalize()}."
    )
    if trend["projected_points"]:
        horizon_weeks = len(trend["projected_points"])
        projected_e1rm = trend["projected_points"][-1]["e1rm"]
        body += (
            f" Se essa tendência linear se mantiver, a projeção para daqui a {horizon_weeks} "
            f"semanas é de ~{projected_e1rm:.1f} kg -- trate como um sinal aproximado, não uma "
            "previsão garantida."
        )

    return Insight(
        id=f"pred-{exercise_title}",
        type="predictive",
        title=f"Tendência de força em {exercise_title}",
        body=body,
        metrics={
            "slope_per_week_kg": round(slope, 2),
            "sessions": n_sessions,
            "current_e1rm": round(exercise_data.iloc[-1]["e1rm"], 1),
        },
        exercise=exercise_title,
        severity=severity,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def generate_overview_insight(
    e1rm_df: pd.DataFrame, templates_df: pd.DataFrame, min_sessions: int = 4
) -> Insight | None:
    """Aggregate insight across every tracked exercise: how many are trending
    up, flat, or down -- context you can't get from looking at one exercise
    at a time."""
    if e1rm_df.empty:
        return None

    id_to_title = dict(zip(templates_df["id"], templates_df["title"]))
    up, flat, down = [], [], []
    for exercise_id, group in e1rm_df.groupby("exercise_template_id"):
        group = group.sort_values("workout_date")
        if len(group) < min_sessions:
            continue
        trend = project_trend(group)
        slope = trend["slope_per_week"]
        if slope is None:
            continue
        title = id_to_title.get(exercise_id, exercise_id)
        if slope > FLAT_SLOPE_THRESHOLD_KG_PER_WEEK:
            up.append(title)
        elif slope < -FLAT_SLOPE_THRESHOLD_KG_PER_WEEK:
            down.append(title)
        else:
            flat.append(title)

    total = len(up) + len(flat) + len(down)
    if total == 0:
        return None

    body = (
        f"Entre os {total} exercícios com histórico suficiente (>= {min_sessions} sessões), "
        f"{len(up)} estão em tendência de alta, {len(flat)} estáveis e {len(down)} em queda."
    )
    if down:
        shown = ", ".join(down[:5]) + (f" e mais {len(down) - 5}" if len(down) > 5 else "")
        body += f" Em queda: {shown}."
        severity = "warning"
    elif up:
        severity = "positive"
    else:
        severity = "info"

    return Insight(
        id="pred-overview",
        type="predictive",
        title="Visão geral das tendências de força",
        body=body,
        metrics={"up": len(up), "flat": len(flat), "down": len(down)},
        severity=severity,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
