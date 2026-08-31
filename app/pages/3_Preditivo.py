import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from _shared import get_db_connection, get_landmarks, get_latest_bodyweight, get_sets_df, render_insight_cards
from hevy_analytics.analytics.predictive import (
    best_e1rm_per_session,
    generate_overview_insight,
    generate_predictive_insight,
    project_trend,
)
from hevy_analytics.data_access import load_exercise_templates

st.set_page_config(page_title="Preditivo — Hevy Analytics", layout="wide")
st.title("Preditivo — para onde a força está indo")

sets_df = get_sets_df()
templates_df = load_exercise_templates(get_db_connection())
landmarks = get_landmarks()

if sets_df.empty:
    st.info("Sem dados ainda. Sincronize na página inicial primeiro.")
    st.stop()

formula = st.radio("Fórmula de 1RM", ["epley", "brzycki"], horizontal=True)
landmarks_for_formula = landmarks.__class__(**{**landmarks.__dict__, "one_rm_formula": formula})

e1rm_df = best_e1rm_per_session(sets_df, landmarks_for_formula)
if e1rm_df.empty:
    st.info("Sem sets suficientes para estimar 1RM ainda.")
    st.stop()

id_to_title = dict(zip(templates_df["id"], templates_df["title"]))
exercise_ids = sorted(e1rm_df["exercise_template_id"].unique(), key=lambda x: id_to_title.get(x, x))
exercise_labels = {eid: id_to_title.get(eid, eid) for eid in exercise_ids}

overview_insight = generate_overview_insight(e1rm_df, templates_df)
if overview_insight:
    st.subheader("Visão geral")
    render_insight_cards([overview_insight])
    st.divider()

selected = st.selectbox(
    "Exercício", exercise_ids, format_func=lambda eid: exercise_labels[eid]
)
selected_title = exercise_labels[selected]

exercise_data = e1rm_df[e1rm_df["exercise_template_id"] == selected].sort_values("workout_date")
trend = project_trend(exercise_data)

exercise_insight = generate_predictive_insight(exercise_data, trend, selected_title)
render_insight_cards(
    [exercise_insight] if exercise_insight else [],
    empty_message="Poucas sessões registradas ainda para estimar uma tendência confiável.",
)

bodyweight = get_latest_bodyweight()
if bodyweight:
    current_e1rm = exercise_data.iloc[-1]["e1rm"]
    st.caption(
        f"Força relativa: {current_e1rm / bodyweight:.2f}x seu peso corporal "
        f"({current_e1rm:.1f}kg / {bodyweight:.1f}kg). Se você registrou peso corporal só "
        "recentemente, essa razão usa o valor mais recente para todo o histórico -- não é o "
        "peso real que você tinha em cada sessão."
    )

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=exercise_data["workout_date"],
        y=exercise_data["e1rm"],
        mode="markers+lines",
        name="e1RM registrado",
    )
)
if trend["projected_points"]:
    proj_df = pd.DataFrame(trend["projected_points"])
    fig.add_trace(
        go.Scatter(
            x=proj_df["date"],
            y=proj_df["e1rm"],
            mode="lines+markers",
            name="Projeção (linear)",
            line=dict(dash="dash"),
        )
    )
st.plotly_chart(fig, use_container_width=True)
