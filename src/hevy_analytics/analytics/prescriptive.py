from datetime import datetime, timezone

import pandas as pd

from hevy_analytics.analytics.diagnostic import _exercise_title
from hevy_analytics.config.landmarks import Landmarks
from hevy_analytics.insights.models import Insight


def generate_recommendations(
    classified_volume_df: pd.DataFrame,
    plateau_df: pd.DataFrame,
    fatigue_df: pd.DataFrame,
    templates_df: pd.DataFrame,
    landmarks: Landmarks,
) -> list[Insight]:
    """Pure rule-based translation of diagnostic/predictive outputs into
    actionable insights. No ML/personalization in v1 -- purely threshold
    driven off config/landmarks.yaml."""
    insights: list[Insight] = []
    now = datetime.now(timezone.utc).isoformat()

    if not classified_volume_df.empty:
        latest_week = classified_volume_df["week"].max()
        latest = classified_volume_df[classified_volume_df["week"] == latest_week]

        # One consolidated card per category instead of one per muscle group
        # -- keeps the page scannable even when several groups need the same action.
        below_rows = latest[latest["classification"] == "below_mev"]
        if not below_rows.empty:
            lines = [
                f"• {row['muscle_group']}: {row['hard_sets']:.1f} sets "
                f"(MEV {landmarks.landmark_for(row['muscle_group']).mev}-"
                f"{landmarks.landmark_for(row['muscle_group']).mav})"
                for _, row in below_rows.iterrows()
            ]
            insights.append(
                Insight(
                    id=f"vol-below-{latest_week}",
                    type="prescriptive",
                    title=f"Adicionar volume em {len(below_rows)} grupo(s)",
                    body="Abaixo do MEV nessa semana, considere adicionar sets:\n" + "\n".join(lines),
                    metrics={"count": len(below_rows)},
                    severity="warning",
                    created_at=now,
                )
            )

        above_rows = latest[latest["classification"] == "above_mrv"]
        if not above_rows.empty:
            lines = [
                f"• {row['muscle_group']}: {row['hard_sets']:.1f} sets "
                f"(MRV {landmarks.landmark_for(row['muscle_group']).mrv})"
                for _, row in above_rows.iterrows()
            ]
            insights.append(
                Insight(
                    id=f"vol-above-{latest_week}",
                    type="prescriptive",
                    title=f"Reduzir volume em {len(above_rows)} grupo(s)",
                    body="Acima do MRV nessa semana, risco de fadiga excessiva -- considere reduzir:\n"
                    + "\n".join(lines),
                    metrics={"count": len(above_rows)},
                    severity="warning",
                    created_at=now,
                )
            )

    plateau_exercises = set(plateau_df["exercise_template_id"]) if not plateau_df.empty else set()

    if not fatigue_df.empty:
        for _, row in fatigue_df.iterrows():
            exercise_title = _exercise_title(templates_df, row["exercise_template_id"])
            has_plateau = row["exercise_template_id"] in plateau_exercises
            if row["signal"] == "rising_rpe_at_constant_load":
                body = (
                    f"RPE médio subiu {row['rpe_delta']:.1f} pontos na mesma carga "
                    f"(~{row['avg_weight']:.1f}kg) nas últimas {row['window_sessions']} sessões."
                )
            else:
                body = (
                    f"Repetições médias caíram {abs(row['reps_delta']):.1f} na mesma carga "
                    f"(~{row['avg_weight']:.1f}kg) nas últimas {row['window_sessions']} sessões."
                )
            if has_plateau:
                body += " Combinado com estagnação de 1RM — considere um deload."
            insights.append(
                Insight(
                    id=f"fatigue-{row['exercise_template_id']}-{row['signal']}",
                    type="prescriptive",
                    title=f"Sinal de fadiga em {exercise_title}",
                    body=body,
                    metrics=row.drop("signal").to_dict(),
                    exercise=exercise_title,
                    severity="critical" if has_plateau else "warning",
                    created_at=now,
                )
            )

    if not plateau_df.empty:
        fatigue_exercises = set(fatigue_df["exercise_template_id"]) if not fatigue_df.empty else set()
        remaining = plateau_df[~plateau_df["exercise_template_id"].isin(fatigue_exercises)].copy()
        remaining["exercise_title"] = remaining["exercise_template_id"].apply(
            lambda eid: _exercise_title(templates_df, eid)
        )
        declines = remaining[remaining["pct_change"] < -10.0].sort_values("pct_change")
        true_plateaus = remaining[remaining["pct_change"] >= -10.0]

        # Real declines are individually actionable -- capped so a handful of
        # exercises doesn't turn into dozens of near-identical cards.
        max_decline_cards = 6
        for _, row in declines.head(max_decline_cards).iterrows():
            insights.append(
                Insight(
                    id=f"plateau-{row['exercise_template_id']}",
                    type="prescriptive",
                    title=f"Queda de desempenho em {row['exercise_title']}",
                    body=(
                        f"1RM estimado caiu {abs(row['pct_change']):.1f}% nas últimas "
                        f"{row['window_sessions']} sessões — pode ser fadiga, uma variação de "
                        "exercício diferente sob o mesmo nome, ou queda real de desempenho. Vale conferir."
                    ),
                    metrics={
                        "first_e1rm": round(row["first_e1rm"], 1),
                        "last_e1rm": round(row["last_e1rm"], 1),
                        "pct_change": round(row["pct_change"], 1),
                    },
                    exercise=row["exercise_title"],
                    severity="warning",
                    created_at=now,
                )
            )

        # True plateaus (small variation) are the common case for most
        # exercises most weeks -- one consolidated card, not one each.
        if not true_plateaus.empty:
            names = ", ".join(true_plateaus["exercise_title"].head(6))
            more = len(true_plateaus) - 6
            if more > 0:
                names += f" e mais {more}"
            insights.append(
                Insight(
                    id="plateau-summary",
                    type="prescriptive",
                    title=f"{len(true_plateaus)} exercício(s) sem progresso -- considere variar estímulo",
                    body=(
                        f"1RM estimado sem melhora clara nas últimas sessões: {names}. Considere variar "
                        "rep range, exercício ou intensidade nesses movimentos."
                    ),
                    metrics={"count": len(true_plateaus)},
                    severity="info",
                    created_at=now,
                )
            )

    return insights
