import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import plotly.express as px
import streamlit as st

from _shared import get_context, get_db_connection, get_landmarks, get_sets_df, render_insight_cards
from hevy_analytics.analytics.descriptive import weekly_muscle_group_volume
from hevy_analytics.analytics.diagnostic import (
    classify_volume,
    detect_fatigue_signals,
    detect_plateau,
    generate_diagnostic_insights,
)
from hevy_analytics.analytics.predictive import best_e1rm_per_session
from hevy_analytics.analytics.responsiveness import generate_responsiveness_insights, volume_responsiveness
from hevy_analytics.data_access import load_exercise_templates

st.set_page_config(page_title="Diagnóstico — Hevy Analytics", layout="wide")
st.title("Diagnóstico — o que isso significa")

sets_df = get_sets_df()
templates_df = load_exercise_templates(get_db_connection())
landmarks = get_landmarks()
activities = get_context()

if sets_df.empty:
    st.info("Sem dados ainda. Sincronize na página inicial primeiro.")
    st.stop()

volume_df = weekly_muscle_group_volume(sets_df, templates_df, landmarks)
classified = classify_volume(volume_df, landmarks)
e1rm_df = best_e1rm_per_session(sets_df, landmarks)
plateau_df = detect_plateau(e1rm_df, landmarks)
fatigue_df = detect_fatigue_signals(sets_df, landmarks)

tab_summary, tab_responsiveness, tab_chart = st.tabs(
    ["Por que isso está acontecendo", "Você reage melhor a mais volume?", "Volume vs. MEV/MAV/MRV"]
)

with tab_summary:
    insights = generate_diagnostic_insights(classified, plateau_df, fatigue_df, templates_df, landmarks, activities)
    render_insight_cards(insights, empty_message="Nada fora do esperado com os parâmetros atuais.")

with tab_responsiveness:
    responsiveness_df = volume_responsiveness(sets_df, templates_df, landmarks)
    responsiveness_insights = generate_responsiveness_insights(responsiveness_df, landmarks)
    render_insight_cards(
        responsiveness_insights,
        empty_message="Ainda sem histórico suficiente pra essa análise (precisa de várias semanas treinando o mesmo grupo com volume variando).",
    )

with tab_chart:
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
        st.caption("Linhas pontilhadas: cinza = MEV, vermelha = MRV, por grupo muscular.")
        with st.expander("Ver tabela"):
            st.dataframe(latest, use_container_width=True)
