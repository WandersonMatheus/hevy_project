from datetime import datetime, timezone

import pandas as pd

from hevy_analytics.analytics.formulas import is_hard_set, tonnage
from hevy_analytics.analytics.time_utils import week_start
from hevy_analytics.config.landmarks import Landmarks
from hevy_analytics.insights.models import Insight


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


def _compare_to_trailing_average(
    weekly_df: pd.DataFrame, value_col: str, trailing_weeks: int = 4
) -> dict | None:
    """Compares the most recent week's value against the average of the
    `trailing_weeks` weeks before it. Returns None if there isn't enough
    history yet. Flags `is_partial_week` when the latest week hasn't fully
    elapsed, since a low number there can just mean "not done yet"."""
    if len(weekly_df) < 2:
        return None
    df = weekly_df.sort_values("week")
    current_row = df.iloc[-1]
    trailing = df.iloc[-(trailing_weeks + 1) : -1]
    if trailing.empty:
        return None
    trailing_avg = trailing[value_col].mean()
    current_value = current_row[value_col]
    pct_change = ((current_value - trailing_avg) / trailing_avg * 100) if trailing_avg > 0 else None
    today = datetime.now(timezone.utc).date()
    is_partial_week = (today - current_row["week"]).days < 7
    return {
        "week": current_row["week"],
        "current_value": current_value,
        "trailing_avg": trailing_avg,
        "pct_change": pct_change,
        "is_partial_week": is_partial_week,
    }


def generate_descriptive_insights(
    workouts_df: pd.DataFrame,
    sets_df: pd.DataFrame,
    volume_df: pd.DataFrame,
    landmarks: Landmarks,
) -> list[Insight]:
    """Narrative descriptive insights: what happened, stated in plain
    language with the comparison that explains why it matters (vs. your own
    recent trailing average) -- not just raw numbers on a chart."""
    insights: list[Insight] = []
    now = datetime.now(timezone.utc).isoformat()

    partial_note = (
        " (semana ainda em andamento, então esse número tende a subir até domingo)"
    )

    freq_cmp = _compare_to_trailing_average(session_frequency(workouts_df), "sessions")
    if freq_cmp:
        body = f"Você treinou {freq_cmp['current_value']:.0f}x na semana de {freq_cmp['week']}"
        if freq_cmp["pct_change"] is not None:
            body += (
                f", contra uma média de {freq_cmp['trailing_avg']:.1f}x nas semanas "
                f"anteriores ({freq_cmp['pct_change']:+.0f}%)."
            )
        else:
            body += "."
        if freq_cmp["is_partial_week"]:
            body += partial_note
        insights.append(
            Insight(
                id="desc-frequency",
                type="descriptive",
                title="Frequência de treino",
                body=body,
                metrics={k: v for k, v in freq_cmp.items() if k != "is_partial_week"},
                severity="info",
                created_at=now,
            )
        )

    tonnage_cmp = _compare_to_trailing_average(tonnage_trend(sets_df), "tonnage")
    if tonnage_cmp:
        body = f"O tonnage (peso x reps somado) da semana de {tonnage_cmp['week']} foi {tonnage_cmp['current_value']:,.0f} kg"
        if tonnage_cmp["pct_change"] is not None:
            body += (
                f", {abs(tonnage_cmp['pct_change']):.0f}% "
                f"{'acima' if tonnage_cmp['pct_change'] >= 0 else 'abaixo'} "
                f"da média das semanas anteriores ({tonnage_cmp['trailing_avg']:,.0f} kg)."
            )
        else:
            body += "."
        if tonnage_cmp["is_partial_week"]:
            body += partial_note
        is_meaningful_increase = (
            not tonnage_cmp["is_partial_week"]
            and tonnage_cmp["pct_change"] is not None
            and tonnage_cmp["pct_change"] >= 15
        )
        insights.append(
            Insight(
                id="desc-tonnage",
                type="descriptive",
                title="Tonnage semanal",
                body=body,
                metrics={k: v for k, v in tonnage_cmp.items() if k != "is_partial_week"},
                severity="positive" if is_meaningful_increase else "info",
                created_at=now,
            )
        )

    variety_cmp = _compare_to_trailing_average(exercise_variety(sets_df), "distinct_exercises")
    if variety_cmp and variety_cmp["pct_change"] is not None and variety_cmp["pct_change"] <= -30:
        body = (
            f"Você usou {variety_cmp['current_value']:.0f} exercícios distintos na semana de "
            f"{variety_cmp['week']}, bem menos que a média recente de {variety_cmp['trailing_avg']:.1f}. "
            "Pode ser normal (rotina mais enxuta) ou sinal de menos sessões/menos variação de estímulo."
        )
        if variety_cmp["is_partial_week"]:
            body += partial_note
        insights.append(
            Insight(
                id="desc-variety",
                type="descriptive",
                title="Queda na variedade de exercícios",
                body=body,
                metrics={k: v for k, v in variety_cmp.items() if k != "is_partial_week"},
                severity="info",
                created_at=now,
            )
        )

    if not volume_df.empty:
        latest_week = volume_df["week"].max()
        latest = volume_df[volume_df["week"] == latest_week].sort_values("hard_sets")
        if len(latest) >= 2:
            lowest = latest.iloc[0]
            highest = latest.iloc[-1]
            body = (
                f"Na semana de {latest_week}, {highest['muscle_group']} recebeu o maior volume "
                f"({highest['hard_sets']:.1f} hard sets) e {lowest['muscle_group']} o menor "
                f"({lowest['hard_sets']:.1f}). Isso reflete o foco real da sua rotina nessa semana, "
                "não necessariamente o que você planejou."
            )
            insights.append(
                Insight(
                    id=f"desc-distribution-{latest_week}",
                    type="descriptive",
                    title="Distribuição de volume entre grupos musculares",
                    body=body,
                    metrics={
                        "highest_muscle_group": highest["muscle_group"],
                        "highest_hard_sets": round(highest["hard_sets"], 1),
                        "lowest_muscle_group": lowest["muscle_group"],
                        "lowest_hard_sets": round(lowest["hard_sets"], 1),
                    },
                    severity="info",
                    created_at=now,
                )
            )

    return insights
