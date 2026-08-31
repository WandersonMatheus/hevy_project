from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from hevy_analytics.analytics.descriptive import weekly_muscle_group_volume
from hevy_analytics.analytics.diagnostic import classify_volume
from hevy_analytics.analytics.predictive import best_e1rm_per_session, project_trend
from hevy_analytics.analytics.responsiveness import volume_responsiveness
from hevy_analytics.config.landmarks import Landmarks
from hevy_analytics.insights.models import Insight

STANDARD_BARBELL_KG = 20.0


@dataclass
class GoalProgress:
    goal_id: int
    label: str
    sublabel: str
    exercise_template_id: str | None
    current_value: float
    target_value: float
    unit: str
    pct_complete: float
    gap: float
    eta_weeks: float | None
    achieved: bool


def bench_target_from_per_side(per_side_kg: float, bar_weight_kg: float = STANDARD_BARBELL_KG) -> float:
    """'50kg cada lado' means 50kg of plates per side of the bar -- the
    actual total lifted is bar + 2x plates, not just the plates."""
    return bar_weight_kg + 2 * per_side_kg


def effective_load_sets(sets_df: pd.DataFrame, templates_df: pd.DataFrame, bodyweight_kg: float) -> pd.DataFrame:
    """Adjusts weight_kg to the true total load for bodyweight-relative
    exercise types. Hevy logs only the ADDED weight for 'bodyweight_weighted'
    exercises (e.g. a weighted pull-up) and only the ASSISTANCE amount for
    'bodyweight_assisted' ones -- comparing those raw numbers against a
    bodyweight-multiple target would wildly understate what's actually being
    lifted."""
    merged = sets_df.merge(
        templates_df[["id", "type"]], left_on="exercise_template_id", right_on="id", how="left"
    )

    def adjust(row):
        if pd.isna(row["weight_kg"]):
            return row["weight_kg"]
        if row["type"] == "bodyweight_weighted":
            return row["weight_kg"] + bodyweight_kg
        if row["type"] == "bodyweight_assisted":
            return max(bodyweight_kg - row["weight_kg"], 0)
        return row["weight_kg"]

    merged = merged.copy()
    merged["weight_kg"] = merged.apply(adjust, axis=1)
    return merged


def _eta_weeks(exercise_e1rm: pd.DataFrame, current: float, target: float) -> float | None:
    if current >= target:
        return 0.0
    trend = project_trend(exercise_e1rm, horizon_weeks=1)
    slope = trend["slope_per_week"]
    if slope is None or slope <= 0:
        return None
    return round((target - current) / slope, 1)


def _progress_for_exercise(
    goal_id: int, label: str, sublabel: str, exercise_template_id: str, target: float, e1rm_df: pd.DataFrame
) -> GoalProgress | None:
    data = e1rm_df[e1rm_df["exercise_template_id"] == exercise_template_id].sort_values("workout_date")
    if data.empty:
        return None
    current = data.iloc[-1]["e1rm"]
    gap = target - current
    return GoalProgress(
        goal_id=goal_id,
        label=label,
        sublabel=sublabel,
        exercise_template_id=exercise_template_id,
        current_value=round(current, 1),
        target_value=round(target, 1),
        unit="kg",
        pct_complete=round(min(current / target, 1.5) * 100, 1) if target > 0 else 0,
        gap=round(gap, 1),
        eta_weeks=_eta_weeks(data, current, target),
        achieved=current >= target,
    )


def evaluate_exercise_weight_goal(goal: pd.Series, e1rm_df: pd.DataFrame) -> GoalProgress | None:
    return _progress_for_exercise(
        goal["id"], goal["label"], goal["label"], goal["exercise_template_id"], goal["target_value"], e1rm_df
    )


def evaluate_bodyweight_multiple_goal(
    goal: pd.Series, e1rm_df: pd.DataFrame, templates_df: pd.DataFrame, bodyweight_kg: float
) -> list[GoalProgress]:
    target = goal["target_value"] * bodyweight_kg
    exercise_ids = templates_df[templates_df["primary_muscle_group"].isin(goal["muscle_groups"])]["id"]
    id_to_title = dict(zip(templates_df["id"], templates_df["title"]))
    results = []
    for eid in exercise_ids:
        p = _progress_for_exercise(goal["id"], goal["label"], id_to_title.get(eid, eid), eid, target, e1rm_df)
        if p:
            results.append(p)
    return sorted(results, key=lambda g: -g.pct_complete)


def evaluate_baseline_multiple_goal(goal: pd.Series, e1rm_df: pd.DataFrame, templates_df: pd.DataFrame) -> list[GoalProgress]:
    id_to_title = dict(zip(templates_df["id"], templates_df["title"]))
    results = []
    for eid, baseline in goal["baseline_json"].items():
        target = goal["target_value"] * baseline
        p = _progress_for_exercise(goal["id"], goal["label"], id_to_title.get(eid, eid), eid, target, e1rm_df)
        if p:
            results.append(p)
    return sorted(results, key=lambda g: -g.pct_complete)


def evaluate_pain_goal(goal: pd.Series, pain_logs_df: pd.DataFrame) -> GoalProgress | None:
    logs = pain_logs_df[pain_logs_df["body_part"] == goal["body_part"]].sort_values("log_date")
    if logs.empty:
        return None
    current = logs.iloc[-1]["pain_score"]
    target = goal["target_value"]
    baseline = logs.iloc[0]["pain_score"]
    span = max(baseline - target, 1)
    pct = max(min((baseline - current) / span, 1.5), 0) * 100
    return GoalProgress(
        goal_id=goal["id"],
        label=goal["label"],
        sublabel=goal["body_part"],
        exercise_template_id=None,
        current_value=current,
        target_value=target,
        unit="dor (0-10)",
        pct_complete=round(pct, 1),
        gap=round(current - target, 1),
        eta_weeks=None,
        achieved=current <= target,
    )


def _volume_lever_note(muscle_group: str, sets_df: pd.DataFrame, templates_df: pd.DataFrame, landmarks: Landmarks) -> str:
    volume_df = weekly_muscle_group_volume(sets_df, templates_df, landmarks)
    classified = classify_volume(volume_df, landmarks)
    if classified.empty:
        return ""
    latest_week = classified["week"].max()
    row = classified[(classified["week"] == latest_week) & (classified["muscle_group"] == muscle_group)]
    if row.empty:
        return ""
    classification = row.iloc[0]["classification"]
    lm = landmarks.landmark_for(muscle_group)
    if classification == "below_mev":
        return (
            f"Seu volume de {muscle_group} está abaixo do MEV ({row.iloc[0]['hard_sets']:.1f} de "
            f"{lm.mev} sets/semana) -- aumentar volume é uma alavanca disponível aqui."
        )
    if classification == "above_mrv":
        return (
            f"Seu volume de {muscle_group} já está acima do MRV -- o limitador provavelmente não é "
            "falta de volume, e sim recuperação/intensidade."
        )
    return (
        f"Seu volume de {muscle_group} está numa faixa produtiva -- o próximo passo tende a ser mais "
        "sobre progressão de carga/intensidade do que adicionar volume."
    )


def _responsiveness_lever_note(muscle_group: str, sets_df: pd.DataFrame, templates_df: pd.DataFrame, landmarks: Landmarks) -> str:
    resp_df = volume_responsiveness(sets_df, templates_df, landmarks)
    row = resp_df[resp_df["muscle_group"] == muscle_group]
    if row.empty:
        return ""
    signal = row.iloc[0]["signal"]
    if signal == "responds_to_volume":
        return "Historicamente, você responde bem a semanas de mais volume nesse grupo."
    if signal == "not_responding":
        return "Historicamente, mais volume não tem se traduzido em mais produção nesse grupo -- foco em técnica/intensidade pode valer mais que só adicionar sets."
    return ""


def _eta_phrase(progress: GoalProgress) -> str:
    if progress.achieved:
        return "Meta já alcançada!"
    if progress.eta_weeks is not None:
        return f"No ritmo atual de progresso, você chegaria lá em ~{progress.eta_weeks:.0f} semanas."
    return "Ainda não dá pra estimar um prazo -- sem tendência de alta clara nas últimas sessões."


def generate_exercise_weight_insight(
    goal: pd.Series, progress: GoalProgress | None, muscle_group: str | None,
    sets_df: pd.DataFrame, templates_df: pd.DataFrame, landmarks: Landmarks,
) -> Insight:
    now = datetime.now(timezone.utc).isoformat()
    if progress is None:
        return Insight(
            id=f"goal-{goal['id']}", type="prescriptive", title=goal["label"],
            body="Ainda sem dados desse exercício para calcular seu progresso.",
            severity="info", created_at=now,
        )
    body = (
        f"Você está em {progress.current_value:.1f}kg, faltam {max(progress.gap, 0):.1f}kg para "
        f"{progress.target_value:.0f}kg ({progress.pct_complete:.0f}% do caminho). {_eta_phrase(progress)}"
    )
    if muscle_group:
        lever = _volume_lever_note(muscle_group, sets_df, templates_df, landmarks)
        if lever:
            body += f"\n{lever}"
        resp = _responsiveness_lever_note(muscle_group, sets_df, templates_df, landmarks)
        if resp:
            body += f"\n{resp}"
    return Insight(
        id=f"goal-{goal['id']}",
        type="prescriptive",
        title=goal["label"],
        body=body,
        metrics={"current": progress.current_value, "target": progress.target_value, "pct": progress.pct_complete},
        muscle_group=muscle_group,
        severity="positive" if progress.achieved else "info",
        created_at=now,
    )


def generate_muscle_group_goal_insight(
    goal: pd.Series, progress_list: list[GoalProgress],
    sets_df: pd.DataFrame, templates_df: pd.DataFrame, landmarks: Landmarks,
) -> Insight:
    now = datetime.now(timezone.utc).isoformat()
    if not progress_list:
        return Insight(
            id=f"goal-{goal['id']}", type="prescriptive", title=goal["label"],
            body="Ainda sem dados suficientes dos exercícios desse grupo para calcular progresso.",
            severity="info", created_at=now,
        )

    lines = [
        f"• {p.sublabel}: {p.current_value:.1f}kg / {p.target_value:.0f}kg ({p.pct_complete:.0f}%)"
        for p in progress_list
    ]
    closest = progress_list[0]
    baseline_note = ""
    if goal["goal_type"] == "baseline_multiple":
        created = str(goal["created_at"])[:10]
        baseline_note = (
            f"O alvo de cada exercício é {goal['target_value']:.1f}x a carga que você levantava em "
            f"{created} (quando a meta foi criada) -- por isso todos começam em torno de "
            f"{100 / goal['target_value']:.0f}%, não é erro.\n\n"
        )
    body = baseline_note + (
        f"Mais perto de chegar lá: {closest.sublabel}, faltam {max(closest.gap, 0):.1f}kg "
        f"({closest.pct_complete:.0f}%). {_eta_phrase(closest)}\n\n"
        "Progresso por exercício (essa meta tende a fazer mais sentido pra movimentos compostos "
        "bilaterais -- variações unilaterais/isoladas dificilmente chegam no mesmo alvo, e tudo bem):\n"
        + "\n".join(lines)
    )
    for mg in goal["muscle_groups"]:
        lever = _volume_lever_note(mg, sets_df, templates_df, landmarks)
        if lever:
            body += f"\n\n{lever}"
        resp = _responsiveness_lever_note(mg, sets_df, templates_df, landmarks)
        if resp:
            body += f" {resp}"

    return Insight(
        id=f"goal-{goal['id']}",
        type="prescriptive",
        title=goal["label"],
        body=body,
        metrics={"n_exercises": len(progress_list), "closest_pct": closest.pct_complete},
        severity="positive" if closest.achieved else "info",
        created_at=now,
    )


def generate_pain_goal_insight(goal: pd.Series, progress: GoalProgress | None) -> Insight:
    now = datetime.now(timezone.utc).isoformat()
    if progress is None:
        body = (
            "Ainda sem nenhum registro de dor. Comece a registrar (mesmo que só 1x/semana) para "
            "acompanhar a tendência ao longo do tempo.\n\n"
            "Nota: isto é acompanhamento, não diagnóstico ou tratamento. Instabilidade patelar "
            "geralmente é discutida na literatura em conjunto com fortalecimento de quadríceps "
            "(especialmente VMO) e da musculatura do quadril/glúteo médio, que ajuda no rastreamento "
            "da patela -- mas avaliação e condução do tratamento são de um fisioterapeuta ou "
            "médico do esporte, não deste app."
        )
        return Insight(
            id=f"goal-{goal['id']}", type="prescriptive", title=goal["label"], body=body,
            severity="info", created_at=now,
        )

    body = (
        f"Última dor registrada: {progress.current_value:.0f}/10 (meta: {progress.target_value:.0f}). "
        f"{'Meta alcançada!' if progress.achieved else f'Faltam {progress.gap:.0f} pontos.'}\n\n"
        "Lembrete: isto é acompanhamento, não diagnóstico. Se a dor/instabilidade persistir ou piorar, "
        "vale conversar com um fisioterapeuta -- ele consegue avaliar rastreamento patelar e força de "
        "quadril de um jeito que este app não consegue."
    )
    return Insight(
        id=f"goal-{goal['id']}",
        type="prescriptive",
        title=goal["label"],
        body=body,
        metrics={"current": progress.current_value, "target": progress.target_value},
        severity="positive" if progress.achieved else "warning",
        created_at=now,
    )
