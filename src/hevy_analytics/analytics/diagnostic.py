from datetime import datetime, timezone

import pandas as pd

from hevy_analytics.analytics.formulas import is_hard_set
from hevy_analytics.config.context import ExternalActivity, note_for_muscle_group
from hevy_analytics.config.landmarks import Landmarks
from hevy_analytics.insights.models import Insight


def classify_volume(weekly_volume_df: pd.DataFrame, landmarks: Landmarks) -> pd.DataFrame:
    """Adds a `classification` column: below_mev | mev_to_mav | mav_to_mrv | above_mrv."""
    if weekly_volume_df.empty:
        return weekly_volume_df.assign(classification=pd.Series(dtype="object"))

    def classify(row) -> str:
        lm = landmarks.landmark_for(row["muscle_group"])
        sets = row["hard_sets"]
        if sets < lm.mev:
            return "below_mev"
        if sets < lm.mav:
            return "mev_to_mav"
        if sets < lm.mrv:
            return "mav_to_mrv"
        return "above_mrv"

    df = weekly_volume_df.copy()
    df["classification"] = df.apply(classify, axis=1)
    return df


def detect_plateau(e1rm_df: pd.DataFrame, landmarks: Landmarks) -> pd.DataFrame:
    """Flags exercises whose best e1RM has not improved by more than
    `min_e1rm_improvement_pct` over the last `window_sessions` sessions.

    Compares the best e1RM of the first half of the window against the best
    e1RM of the second half (rather than single first/last data points) so a
    single light or high-rep session doesn't read as a huge "plateau" purely
    from session-to-session noise.

    Exercises whose most recent session is older than `landmarks.inactive_days`
    are skipped entirely -- an exercise you haven't touched in months isn't
    "stuck", you just moved on to something else."""
    rule = landmarks.plateau_rule
    today = datetime.now(timezone.utc).date()
    flags = []
    for exercise_id, group in e1rm_df.groupby("exercise_template_id"):
        group = group.sort_values("workout_date")
        if len(group) < rule.window_sessions:
            continue
        if (today - group.iloc[-1]["workout_date"]).days > landmarks.inactive_days:
            continue
        window = group.tail(rule.window_sessions)
        midpoint = len(window) // 2
        first_half = window.iloc[: max(midpoint, 1)]
        second_half = window.iloc[max(midpoint, 1):]
        if second_half.empty:
            continue
        first_e1rm = first_half["e1rm"].max()
        last_e1rm = second_half["e1rm"].max()
        if first_e1rm <= 0:
            continue
        pct_change = (last_e1rm - first_e1rm) / first_e1rm * 100
        if pct_change < rule.min_e1rm_improvement_pct:
            flags.append(
                {
                    "exercise_template_id": exercise_id,
                    "window_sessions": rule.window_sessions,
                    "first_e1rm": first_e1rm,
                    "last_e1rm": last_e1rm,
                    "pct_change": pct_change,
                }
            )
    return pd.DataFrame(flags)


def _session_summary(sets_df: pd.DataFrame, landmarks: Landmarks) -> pd.DataFrame:
    df = sets_df[sets_df["set_type"].apply(lambda t: is_hard_set(t, landmarks.hard_set_types))].copy()
    df = df.dropna(subset=["exercise_template_id", "weight_kg"])
    df["workout_date"] = df["start_time"].dt.date
    return (
        df.groupby(["exercise_template_id", "workout_date"])
        .agg(avg_weight=("weight_kg", "mean"), avg_reps=("reps", "mean"), avg_rpe=("rpe", "mean"))
        .reset_index()
        .sort_values(["exercise_template_id", "workout_date"])
    )


def detect_fatigue_signals(sets_df: pd.DataFrame, landmarks: Landmarks) -> pd.DataFrame:
    """Flags exercises where, at roughly constant load, RPE has risen or reps
    have declined over the configured window. Sessions with no RPE recorded
    are skipped for the RPE-based rule (older history is often RPE-less).

    Same staleness guard as `detect_plateau`: an exercise last touched more
    than `landmarks.inactive_days` ago is skipped, not flagged."""
    rule = landmarks.deload_rule
    today = datetime.now(timezone.utc).date()
    summary = _session_summary(sets_df, landmarks)
    flags = []

    for exercise_id, group in summary.groupby("exercise_template_id"):
        group = group.sort_values("workout_date")
        if len(group) < rule.window_sessions:
            continue
        if (today - group.iloc[-1]["workout_date"]).days > landmarks.inactive_days:
            continue
        window = group.tail(rule.window_sessions)

        mean_weight = window["avg_weight"].mean()
        if mean_weight <= 0:
            continue
        weight_spread_pct = (window["avg_weight"].max() - window["avg_weight"].min()) / mean_weight * 100
        if weight_spread_pct > rule.weight_tolerance_pct:
            continue

        rpe_window = window.dropna(subset=["avg_rpe"])
        if len(rpe_window) >= 2:
            rpe_delta = rpe_window.iloc[-1]["avg_rpe"] - rpe_window.iloc[0]["avg_rpe"]
            if rpe_delta >= rule.rpe_increase_threshold:
                flags.append(
                    {
                        "exercise_template_id": exercise_id,
                        "signal": "rising_rpe_at_constant_load",
                        "window_sessions": rule.window_sessions,
                        "rpe_delta": rpe_delta,
                        "avg_weight": mean_weight,
                    }
                )
                continue

        reps_delta = window.iloc[-1]["avg_reps"] - window.iloc[0]["avg_reps"]
        if reps_delta <= -1:
            flags.append(
                {
                    "exercise_template_id": exercise_id,
                    "signal": "declining_reps_at_constant_load",
                    "window_sessions": rule.window_sessions,
                    "reps_delta": reps_delta,
                    "avg_weight": mean_weight,
                }
            )

    return pd.DataFrame(flags)


def _exercise_title(templates_df: pd.DataFrame, exercise_template_id: str) -> str:
    row = templates_df[templates_df["id"] == exercise_template_id]
    return row.iloc[0]["title"] if not row.empty else exercise_template_id


def generate_diagnostic_insights(
    classified_volume_df: pd.DataFrame,
    plateau_df: pd.DataFrame,
    fatigue_df: pd.DataFrame,
    templates_df: pd.DataFrame,
    landmarks: Landmarks,
    activities: list[ExternalActivity] = (),
) -> list[Insight]:
    """Narrative diagnostic insights: not just *what* was flagged, but the
    reasoning/threshold math behind *why* -- distinct from the Prescritivo
    page, which focuses on *what to do about it*. `activities` are external,
    non-Hevy-tracked training (e.g. another sport) that can plausibly explain
    fatigue in the muscle groups they involve."""
    insights: list[Insight] = []
    now = datetime.now(timezone.utc).isoformat()

    if not classified_volume_df.empty:
        latest_week = classified_volume_df["week"].max()
        latest = classified_volume_df[classified_volume_df["week"] == latest_week]
        counts = latest["classification"].value_counts().to_dict()
        below = counts.get("below_mev", 0)
        above = counts.get("above_mrv", 0)
        productive = counts.get("mev_to_mav", 0) + counts.get("mav_to_mrv", 0)

        body = (
            f"Dos {len(latest)} grupos musculares treinados na semana de {latest_week}, "
            f"{productive} estão numa faixa produtiva de volume (entre MEV e MRV), "
            f"{below} abaixo do MEV (volume mínimo efetivo) e {above} acima do MRV "
            "(volume máximo recuperável)."
        )
        all_productive = below == 0 and above == 0
        insights.append(
            Insight(
                id=f"diag-summary-{latest_week}",
                type="diagnostic",
                title="Panorama de volume da semana",
                body=body,
                metrics={"below_mev": below, "productive": productive, "above_mrv": above},
                severity="positive" if all_productive else "warning",
                created_at=now,
            )
        )

        # One consolidated card per category (not one per muscle group) --
        # these follow an identical template per row, so a bulleted list
        # reads just as clearly with far less vertical stacking.
        below_rows = latest[latest["classification"] == "below_mev"]
        if not below_rows.empty:
            lines = []
            for _, row in below_rows.iterrows():
                lm = landmarks.landmark_for(row["muscle_group"])
                line = f"• {row['muscle_group']}: {row['hard_sets']:.1f} sets (MEV {lm.mev})"
                note = note_for_muscle_group(activities, row["muscle_group"])
                if note:
                    line += f" — {note}"
                lines.append(line)
            body = (
                "Volume abaixo do MEV geralmente é insuficiente para gerar um estímulo "
                "consistente de adaptação/hipertrofia, segundo a literatura de volume de treino.\n"
                + "\n".join(lines)
            )
            insights.append(
                Insight(
                    id=f"diag-below-mev-{latest_week}",
                    type="diagnostic",
                    title=f"{len(below_rows)} grupo(s) abaixo do MEV",
                    body=body,
                    metrics={"count": len(below_rows)},
                    severity="warning",
                    created_at=now,
                )
            )

        above_rows = latest[latest["classification"] == "above_mrv"]
        if not above_rows.empty:
            lines = []
            for _, row in above_rows.iterrows():
                lm = landmarks.landmark_for(row["muscle_group"])
                line = f"• {row['muscle_group']}: {row['hard_sets']:.1f} sets (MRV {lm.mrv})"
                note = note_for_muscle_group(activities, row["muscle_group"])
                if note:
                    line += f" — {note}"
                lines.append(line)
            body = (
                "Acima do MRV, a fadiga desse grupo provavelmente acumula mais rápido do que "
                "a recuperação entre sessões, o que tende a prejudicar a qualidade dos próximos treinos.\n"
                + "\n".join(lines)
            )
            insights.append(
                Insight(
                    id=f"diag-above-mrv-{latest_week}",
                    type="diagnostic",
                    title=f"{len(above_rows)} grupo(s) acima do MRV",
                    body=body,
                    metrics={"count": len(above_rows)},
                    severity="warning",
                    created_at=now,
                )
            )

    if not fatigue_df.empty:
        exercise_to_muscle = dict(zip(templates_df["id"], templates_df["primary_muscle_group"]))
        max_fatigue_cards = 8
        overflow = len(fatigue_df) - max_fatigue_cards
        for _, row in fatigue_df.head(max_fatigue_cards).iterrows():
            exercise_title = _exercise_title(templates_df, row["exercise_template_id"])
            if row["signal"] == "rising_rpe_at_constant_load":
                body = (
                    f"Nas últimas {row['window_sessions']} sessões de {exercise_title}, o RPE médio "
                    f"subiu {row['rpe_delta']:.1f} pontos mantendo a carga em ~{row['avg_weight']:.1f}kg. "
                    "Ou seja: o mesmo peso está exigindo cada vez mais esforço -- um sinal clássico de "
                    "fadiga acumulando, mesmo sem a carga ter mudado."
                )
            else:
                body = (
                    f"Nas últimas {row['window_sessions']} sessões de {exercise_title}, as repetições "
                    f"médias caíram {abs(row['reps_delta']):.1f} mantendo a carga em ~{row['avg_weight']:.1f}kg. "
                    "Menos repetições com o mesmo peso costuma indicar que a capacidade de produzir "
                    "força/resistência naquele exercício está temporariamente reduzida."
                )
            context_note = note_for_muscle_group(
                activities, exercise_to_muscle.get(row["exercise_template_id"])
            )
            if context_note:
                body += f" {context_note}"
            insights.append(
                Insight(
                    id=f"diag-fatigue-{row['exercise_template_id']}-{row['signal']}",
                    type="diagnostic",
                    title=f"Por que {exercise_title} está sinalizando fadiga",
                    body=body,
                    metrics=row.drop("signal").to_dict(),
                    exercise=exercise_title,
                    severity="warning",
                    created_at=now,
                )
            )
        if overflow > 0:
            insights.append(
                Insight(
                    id="diag-fatigue-overflow",
                    type="diagnostic",
                    title=f"+{overflow} outro(s) exercício(s) também sinalizando fadiga",
                    body="Muitos sinais de fadiga ao mesmo tempo -- vale considerar uma semana de deload geral.",
                    metrics={"count": overflow},
                    severity="warning",
                    created_at=now,
                )
            )

    if not plateau_df.empty:
        with_titles = plateau_df.copy()
        with_titles["exercise_title"] = with_titles["exercise_template_id"].apply(
            lambda eid: _exercise_title(templates_df, eid)
        )
        declines = with_titles[with_titles["pct_change"] < -10.0].sort_values("pct_change")
        true_plateaus = with_titles[with_titles["pct_change"] >= -10.0]

        # Real declines are individually actionable -- one card each, capped so
        # a handful of exercises doesn't turn into dozens of cards.
        max_decline_cards = 6
        for _, row in declines.head(max_decline_cards).iterrows():
            body = (
                f"O 1RM estimado em {row['exercise_title']} caiu {abs(row['pct_change']):.1f}% "
                f"comparando a primeira e a segunda metade das últimas {row['window_sessions']} sessões. "
                "Isso pode ser fadiga acumulada, uma sessão com execução/técnica diferente, ou queda "
                "real de desempenho -- vale olhar o histórico bruto do exercício."
            )
            insights.append(
                Insight(
                    id=f"diag-plateau-{row['exercise_template_id']}",
                    type="diagnostic",
                    title=f"Por que {row['exercise_title']} está em queda",
                    body=body,
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
        remaining_declines = len(declines) - max_decline_cards
        extra_note = f" (+{remaining_declines} outros em queda)" if remaining_declines > 0 else ""

        # True plateaus (small variation, not a real drop) are the expected,
        # common case for most exercises in most weeks -- one aggregate card
        # instead of a wall of near-identical "0% de variação" cards.
        if not true_plateaus.empty:
            names = ", ".join(true_plateaus["exercise_title"].head(5))
            more = len(true_plateaus) - 5
            if more > 0:
                names += f" e mais {more}"
            body = (
                f"{len(true_plateaus)} exercícios não avançaram mais que "
                f"{landmarks.plateau_rule.min_e1rm_improvement_pct:.0f}% de 1RM estimado nas últimas "
                f"{landmarks.plateau_rule.window_sessions} sessões: {names}{extra_note}. Isso é normal "
                "para boa parte dos exercícios em qualquer janela curta -- só vira problema se persistir "
                "por várias semanas seguidas no mesmo exercício."
            )
            insights.append(
                Insight(
                    id="diag-plateau-summary",
                    type="diagnostic",
                    title="Exercícios sem progresso recente de 1RM",
                    body=body,
                    metrics={"count": len(true_plateaus)},
                    severity="info",
                    created_at=now,
                )
            )

    return insights
