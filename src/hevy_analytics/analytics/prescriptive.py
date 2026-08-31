from datetime import datetime, timezone

import pandas as pd

from hevy_analytics.config.landmarks import Landmarks
from hevy_analytics.insights.models import Insight


def _exercise_title(templates_df: pd.DataFrame, exercise_template_id: str) -> str:
    row = templates_df[templates_df["id"] == exercise_template_id]
    if row.empty:
        return exercise_template_id
    return row.iloc[0]["title"]


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

        for _, row in latest.iterrows():
            lm = landmarks.landmark_for(row["muscle_group"])
            if row["classification"] == "below_mev":
                insights.append(
                    Insight(
                        id=f"vol-{row['muscle_group']}-{latest_week}",
                        type="prescriptive",
                        title=f"Volume de {row['muscle_group']} abaixo do MEV",
                        body=(
                            f"{row['hard_sets']:.1f} hard sets/semana, abaixo do MEV "
                            f"estimado de {lm.mev}-{lm.mav}. Considere adicionar sets."
                        ),
                        metrics={
                            "hard_sets": round(row["hard_sets"], 1),
                            "mev": lm.mev,
                            "mav": lm.mav,
                        },
                        muscle_group=row["muscle_group"],
                        severity="warning",
                        created_at=now,
                    )
                )
            elif row["classification"] == "above_mrv":
                insights.append(
                    Insight(
                        id=f"vol-{row['muscle_group']}-{latest_week}",
                        type="prescriptive",
                        title=f"Volume de {row['muscle_group']} acima do MRV",
                        body=(
                            f"{row['hard_sets']:.1f} hard sets/semana, acima do MRV "
                            f"estimado de {lm.mrv}. Risco de fadiga excessiva — considere reduzir volume."
                        ),
                        metrics={"hard_sets": round(row["hard_sets"], 1), "mrv": lm.mrv},
                        muscle_group=row["muscle_group"],
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
        for _, row in plateau_df.iterrows():
            if row["exercise_template_id"] in fatigue_exercises:
                continue  # already covered above with the combined message
            exercise_title = _exercise_title(templates_df, row["exercise_template_id"])
            is_decline = row["pct_change"] < -10.0
            title = f"{'Queda de desempenho' if is_decline else 'Platô'} em {exercise_title}"
            body = (
                f"1RM estimado caiu {abs(row['pct_change']):.1f}% nas últimas "
                f"{row['window_sessions']} sessões — pode ser fadiga, uma variação de "
                f"exercício diferente sob o mesmo nome, ou queda real de desempenho. Vale conferir."
                if is_decline
                else (
                    f"1RM estimado variou {row['pct_change']:.1f}% nas últimas "
                    f"{row['window_sessions']} sessões — considere variar estímulo "
                    f"(rep range, exercício, intensidade)."
                )
            )
            insights.append(
                Insight(
                    id=f"plateau-{row['exercise_template_id']}",
                    type="prescriptive",
                    title=title,
                    body=body,
                    metrics={
                        "first_e1rm": round(row["first_e1rm"], 1),
                        "last_e1rm": round(row["last_e1rm"], 1),
                        "pct_change": round(row["pct_change"], 1),
                    },
                    exercise=exercise_title,
                    severity="info",
                    created_at=now,
                )
            )

    return insights
