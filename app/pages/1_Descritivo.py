import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import plotly.express as px
import streamlit as st

from _shared import (
    BLUE,
    CATEGORICAL_PALETTE,
    GREEN,
    get_db_connection,
    get_landmarks,
    get_sets_df,
    get_workouts_df,
    render_insight_cards,
    style_fig,
)
from hevy_analytics.analytics.descriptive import (
    exercise_variety,
    generate_descriptive_insights,
    session_duration,
    session_frequency,
    tonnage_trend,
    weekly_muscle_group_volume,
)
from hevy_analytics.data_access import load_exercise_templates

st.set_page_config(page_title="Descritivo — Hevy Analytics", layout="wide")
st.title("Descritivo — o que aconteceu")

workouts_df = get_workouts_df()
sets_df = get_sets_df()
templates_df = load_exercise_templates(get_db_connection())
landmarks = get_landmarks()

if workouts_df.empty:
    st.info("Sem dados ainda. Sincronize na página inicial primeiro.")
    st.stop()

volume_df = weekly_muscle_group_volume(sets_df, templates_df, landmarks)

st.subheader("Insights da semana")
insights = generate_descriptive_insights(workouts_df, sets_df, volume_df, landmarks)
render_insight_cards(insights, empty_message="Dados insuficientes ainda para gerar insights (histórico curto).")

st.divider()

st.subheader("Tonnage semanal")
fig = px.line(tonnage_trend(sets_df), x="week", y="tonnage", markers=True, color_discrete_sequence=[BLUE])
st.plotly_chart(style_fig(fig), use_container_width=True)

st.subheader("Hard sets por semana e grupo muscular")
if volume_df.empty:
    st.info("Sem sets classificados ainda.")
else:
    fig = px.bar(
        volume_df, x="week", y="hard_sets", color="muscle_group", barmode="group",
        color_discrete_sequence=CATEGORICAL_PALETTE,
    )
    st.plotly_chart(style_fig(fig), use_container_width=True)

col1, col2 = st.columns(2)
with col1:
    st.subheader("Frequência de sessões por semana")
    fig = px.bar(session_frequency(workouts_df), x="week", y="sessions", color_discrete_sequence=[BLUE])
    st.plotly_chart(style_fig(fig), use_container_width=True)
with col2:
    st.subheader("Duração das sessões")
    fig = px.line(session_duration(workouts_df), x="start_time", y="duration_minutes", color_discrete_sequence=[GREEN])
    st.plotly_chart(style_fig(fig), use_container_width=True)

st.subheader("Variedade de exercícios por semana")
fig = px.line(exercise_variety(sets_df), x="week", y="distinct_exercises", markers=True, color_discrete_sequence=[BLUE])
st.plotly_chart(style_fig(fig), use_container_width=True)
