import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import streamlit as st

from _shared import (
    get_context,
    get_db_connection,
    get_goals_df,
    get_landmarks,
    get_latest_bodyweight,
    get_pain_logs_df,
    get_sets_df,
    get_templates_df,
    render_insight_cards,
)
from hevy_analytics.analytics.goals import (
    bench_target_from_per_side,
    effective_load_sets,
    evaluate_baseline_multiple_goal,
    evaluate_bodyweight_multiple_goal,
    evaluate_exercise_weight_goal,
    evaluate_pain_goal,
    generate_exercise_weight_insight,
    generate_muscle_group_goal_insight,
    generate_pain_goal_insight,
)
from hevy_analytics.analytics.predictive import best_e1rm_per_session
from hevy_analytics.data_access import create_goal, log_pain

st.set_page_config(page_title="Metas — Hevy Analytics", layout="wide")
st.title("Metas — o quanto falta e como chegar lá")

conn = get_db_connection()
sets_df = get_sets_df()
templates_df = get_templates_df()
landmarks = get_landmarks()
goals_df = get_goals_df()
bodyweight = get_latest_bodyweight()

if sets_df.empty:
    st.info("Sem dados ainda. Sincronize na página inicial primeiro.")
    st.stop()

if not bodyweight:
    st.warning(
        "Nenhum peso corporal registrado -- metas relativas ao peso corporal e o ajuste de "
        "exercícios com peso adicional (ex: barra com peso) usam seu peso mais recente. "
        "Registre na página inicial para resultados corretos."
    )
    bodyweight = 0.0

adjusted_sets = effective_load_sets(sets_df, templates_df, bodyweight) if bodyweight else sets_df
e1rm_df = best_e1rm_per_session(adjusted_sets, landmarks)
id_to_muscle = dict(zip(templates_df["id"], templates_df["primary_muscle_group"]))

if goals_df.empty:
    st.info("Nenhuma meta cadastrada ainda. Adicione uma abaixo.")
else:
    insights = []
    for _, goal in goals_df.iterrows():
        if goal["goal_type"] == "exercise_weight":
            progress = evaluate_exercise_weight_goal(goal, e1rm_df)
            muscle_group = id_to_muscle.get(goal["exercise_template_id"])
            insights.append(
                generate_exercise_weight_insight(goal, progress, muscle_group, adjusted_sets, templates_df, landmarks)
            )
        elif goal["goal_type"] == "bodyweight_multiple":
            progress_list = evaluate_bodyweight_multiple_goal(goal, e1rm_df, templates_df, bodyweight)
            insights.append(generate_muscle_group_goal_insight(goal, progress_list, adjusted_sets, templates_df, landmarks))
        elif goal["goal_type"] == "baseline_multiple":
            progress_list = evaluate_baseline_multiple_goal(goal, e1rm_df, templates_df)
            insights.append(generate_muscle_group_goal_insight(goal, progress_list, adjusted_sets, templates_df, landmarks))
        elif goal["goal_type"] == "pain":
            pain_logs_df = get_pain_logs_df()
            progress = evaluate_pain_goal(goal, pain_logs_df)
            insights.append(generate_pain_goal_insight(goal, progress))

    render_insight_cards(insights, empty_message="Sem metas ativas.")

st.divider()

col1, col2 = st.columns(2)

with col1:
    with st.expander("Registrar dor (ex: joelho)"):
        with st.form("pain_form"):
            body_part = st.text_input("Local", value="joelho")
            pain_date = st.date_input("Data", value=date.today())
            pain_score = st.slider("Dor (0 = nenhuma, 10 = máxima)", 0, 10, 0)
            if st.form_submit_button("Registrar"):
                log_pain(conn, pain_date.isoformat(), body_part.strip().lower(), float(pain_score))
                st.cache_data.clear()
                st.success(f"Dor registrada: {body_part} = {pain_score}/10 em {pain_date.isoformat()}.")

with col2:
    with st.expander("Nova meta"):
        goal_type_label = st.selectbox(
            "Tipo de meta",
            ["Peso alvo num exercício", "Múltiplo do peso corporal (grupo muscular)",
             "Dobrar carga atual (grupo muscular)", "Reduzir dor"],
        )

        with st.form("goal_form"):
            if goal_type_label == "Peso alvo num exercício":
                id_to_title = dict(zip(templates_df["id"], templates_df["title"]))
                exercise_ids = sorted(templates_df["id"], key=lambda x: id_to_title.get(x, x))
                selected_exercise = st.selectbox(
                    "Exercício", exercise_ids, format_func=lambda eid: id_to_title.get(eid, eid)
                )
                input_mode = st.radio("Como definir o alvo", ["Peso total (kg)", "Peso por lado + barra"], horizontal=True)
                if input_mode == "Peso total (kg)":
                    target = st.number_input("Alvo (kg)", min_value=1.0, value=100.0, step=1.0)
                else:
                    per_side = st.number_input("Peso por lado (kg)", min_value=1.0, value=50.0, step=1.0)
                    bar = st.number_input("Peso da barra (kg)", min_value=0.0, value=20.0, step=1.0)
                    target = bench_target_from_per_side(per_side, bar)
                    st.caption(f"Alvo total: {target:.0f}kg")
                label = st.text_input("Nome da meta", value=f"{id_to_title.get(selected_exercise, '')}: {target:.0f}kg")
                submitted = st.form_submit_button("Criar meta")
                if submitted:
                    create_goal(conn, label, "exercise_weight", target, exercise_template_id=selected_exercise)
                    st.cache_data.clear()
                    st.success("Meta criada.")

            elif goal_type_label == "Múltiplo do peso corporal (grupo muscular)":
                muscle_options = sorted(templates_df["primary_muscle_group"].dropna().unique())
                selected_groups = st.multiselect("Grupo(s) muscular(es)", muscle_options, default=["upper_back", "lats"] if "upper_back" in muscle_options else [])
                multiple = st.number_input("Múltiplo do peso corporal", min_value=0.1, value=2.0, step=0.1)
                label = st.text_input("Nome da meta", value=f"{multiple:.1f}x peso corporal em {', '.join(selected_groups)}")
                submitted = st.form_submit_button("Criar meta")
                if submitted and selected_groups:
                    create_goal(conn, label, "bodyweight_multiple", multiple, muscle_groups=selected_groups)
                    st.cache_data.clear()
                    st.success("Meta criada.")

            elif goal_type_label == "Dobrar carga atual (grupo muscular)":
                muscle_options = sorted(templates_df["primary_muscle_group"].dropna().unique())
                selected_groups = st.multiselect("Grupo(s) muscular(es)", muscle_options, default=["biceps", "triceps"] if "biceps" in muscle_options else [])
                multiple = st.number_input("Multiplicar carga atual por", min_value=1.1, value=2.0, step=0.1)
                label = st.text_input("Nome da meta", value=f"{multiple:.1f}x carga atual em {', '.join(selected_groups)}")
                submitted = st.form_submit_button("Criar meta")
                if submitted and selected_groups:
                    exercise_ids = templates_df[templates_df["primary_muscle_group"].isin(selected_groups)]["id"]
                    baseline = {}
                    for eid in exercise_ids:
                        data = e1rm_df[e1rm_df["exercise_template_id"] == eid]
                        if not data.empty:
                            baseline[eid] = float(data.sort_values("workout_date").iloc[-1]["e1rm"])
                    create_goal(conn, label, "baseline_multiple", multiple, muscle_groups=selected_groups, baseline=baseline)
                    st.cache_data.clear()
                    st.success(f"Meta criada com baseline capturado agora ({len(baseline)} exercícios).")

            else:
                body_part = st.text_input("Local da dor", value="joelho")
                target_pain = st.number_input("Alvo de dor (0-10)", min_value=0.0, max_value=10.0, value=0.0, step=1.0)
                label = st.text_input("Nome da meta", value=f"Zerar dor em {body_part}")
                submitted = st.form_submit_button("Criar meta")
                if submitted:
                    create_goal(conn, label, "pain", target_pain, body_part=body_part.strip().lower())
                    st.cache_data.clear()
                    st.success("Meta criada.")

st.caption(
    "Metas de exercício usam 1RM estimado (mesma metodologia da aba Preditivo). Metas de peso corporal "
    "e 'dobrar carga' dependem do peso corporal registrado na página inicial."
)
