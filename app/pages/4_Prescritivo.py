import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import streamlit as st

from _shared import get_db_connection, get_landmarks, get_sets_df, render_insight_cards
from hevy_analytics.analytics.descriptive import weekly_muscle_group_volume
from hevy_analytics.analytics.diagnostic import classify_volume, detect_fatigue_signals, detect_plateau
from hevy_analytics.analytics.predictive import best_e1rm_per_session
from hevy_analytics.analytics.prescriptive import generate_recommendations
from hevy_analytics.data_access import load_exercise_templates

st.set_page_config(page_title="Prescritivo — Hevy Analytics", layout="wide")
st.title("Prescritivo — o que fazer a respeito")

sets_df = get_sets_df()
templates_df = load_exercise_templates(get_db_connection())
landmarks = get_landmarks()

if sets_df.empty:
    st.info("Sem dados ainda. Sincronize na página inicial primeiro.")
    st.stop()

volume_df = weekly_muscle_group_volume(sets_df, templates_df, landmarks)
classified = classify_volume(volume_df, landmarks)
e1rm_df = best_e1rm_per_session(sets_df, landmarks)
plateau_df = detect_plateau(e1rm_df, landmarks)
fatigue_df = detect_fatigue_signals(sets_df, landmarks)

insights = generate_recommendations(classified, plateau_df, fatigue_df, templates_df, landmarks)
render_insight_cards(insights, empty_message="Nenhuma recomendação no momento — tudo dentro dos parâmetros configurados.")

st.caption(
    "Todas as recomendações são baseadas em regras configuráveis em config/landmarks.yaml, "
    "não em personalização por machine learning."
)
