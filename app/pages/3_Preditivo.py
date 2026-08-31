import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from _shared import get_db_connection, get_landmarks, get_sets_df
from hevy_analytics.analytics.predictive import best_e1rm_per_session, project_trend
from hevy_analytics.data_access import load_exercise_templates

st.set_page_config(page_title="Preditivo — Hevy Analytics", page_icon="🔮", layout="wide")
st.title("🔮 Preditivo — para onde a força está indo")

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

selected = st.selectbox(
    "Exercício", exercise_ids, format_func=lambda eid: exercise_labels[eid]
)

exercise_data = e1rm_df[e1rm_df["exercise_template_id"] == selected].sort_values("workout_date")
trend = project_trend(exercise_data)

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

if trend["slope_per_week"] is not None:
    st.caption(
        f"Tendência: {trend['slope_per_week']:+.2f} kg de 1RM estimado por semana "
        "(regressão linear simples — não é um modelo de forecasting, apenas um sinal aproximado)."
    )
else:
    st.caption("Dados insuficientes para calcular tendência.")
