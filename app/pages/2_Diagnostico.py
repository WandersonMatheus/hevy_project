import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import plotly.express as px
import streamlit as st

from _shared import get_db_connection, get_landmarks, get_sets_df
from hevy_analytics.analytics.descriptive import weekly_muscle_group_volume
from hevy_analytics.analytics.diagnostic import classify_volume, detect_fatigue_signals, detect_plateau
from hevy_analytics.analytics.predictive import best_e1rm_per_session
from hevy_analytics.data_access import load_exercise_templates

st.set_page_config(page_title="Diagnóstico — Hevy Analytics", page_icon="🩺", layout="wide")
st.title("🩺 Diagnóstico — o que isso significa")

sets_df = get_sets_df()
templates_df = load_exercise_templates(get_db_connection())
landmarks = get_landmarks()

if sets_df.empty:
    st.info("Sem dados ainda. Sincronize na página inicial primeiro.")
    st.stop()

st.subheader("Volume da última semana vs. MEV/MAV/MRV")
volume_df = weekly_muscle_group_volume(sets_df, templates_df, landmarks)
classified = classify_volume(volume_df, landmarks)

if classified.empty:
    st.info("Sem volume classificado ainda.")
else:
    latest_week = classified["week"].max()
    latest = classified[classified["week"] == latest_week].sort_values("muscle_group")

    fig = px.bar(latest, x="muscle_group", y="hard_sets", color="classification")
    for _, row in latest.iterrows():
        lm = landmarks.landmark_for(row["muscle_group"])
        fig.add_hline(y=lm.mev, line_dash="dot", line_color="gray")
        fig.add_hline(y=lm.mrv, line_dash="dot", line_color="red")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(latest, use_container_width=True)

st.divider()
st.subheader("Alertas de platô e fadiga")

e1rm_df = best_e1rm_per_session(sets_df, landmarks)
plateau_df = detect_plateau(e1rm_df, landmarks)
fatigue_df = detect_fatigue_signals(sets_df, landmarks)

id_to_title = dict(zip(templates_df["id"], templates_df["title"]))

if plateau_df.empty and fatigue_df.empty:
    st.success("Nenhum sinal de platô ou fadiga detectado com os parâmetros atuais.")
else:
    if not fatigue_df.empty:
        st.markdown("**Sinais de fadiga**")
        display = fatigue_df.copy()
        display["exercise"] = display["exercise_template_id"].map(id_to_title)
        st.dataframe(display, use_container_width=True)

    if not plateau_df.empty:
        st.markdown("**Platôs de força**")
        display = plateau_df.copy()
        display["exercise"] = display["exercise_template_id"].map(id_to_title)
        st.dataframe(display, use_container_width=True)
