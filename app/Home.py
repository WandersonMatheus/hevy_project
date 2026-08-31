import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from _shared import compute_all_insights, get_db_connection, get_latest_bodyweight, render_insight_cards
from hevy_analytics.api.client import HevyAPIError, HevyClient
from hevy_analytics.data_access import load_last_sync_log, load_workouts, log_bodyweight
from hevy_analytics.ingest.sync import run_sync
from hevy_analytics.settings import HEVY_API_KEY, MAX_RETRIES, REQUEST_DELAY_SECONDS

st.set_page_config(page_title="Hevy Analytics", layout="wide")

conn = get_db_connection()

st.title("Hevy Analytics")
st.caption("Análise descritiva, diagnóstica, preditiva e prescritiva do seu treino de musculação.")

col1, col2 = st.columns([3, 1])

with col2:
    if st.button("Sincronizar", use_container_width=True):
        if not HEVY_API_KEY:
            st.error("HEVY_API_KEY não configurada. Copie .env.example para .env e adicione sua key.")
        else:
            with st.spinner("Sincronizando com o Hevy..."):
                try:
                    client = HevyClient(
                        HEVY_API_KEY,
                        request_delay_seconds=REQUEST_DELAY_SECONDS,
                        max_retries=MAX_RETRIES,
                    )
                    result = run_sync(conn, client)
                    st.cache_data.clear()
                    st.success(
                        f"Sincronizado! {result.workouts_upserted} treinos atualizados, "
                        f"{result.workouts_deleted} removidos, {result.templates_upserted} "
                        f"exercícios atualizados ({result.duration_seconds:.1f}s)."
                    )
                except HevyAPIError as exc:
                    st.error(f"Falha na sincronização: {exc}")

    latest_weight = get_latest_bodyweight()
    with st.form("bodyweight_form", clear_on_submit=False):
        st.caption("Peso corporal (não vem do Hevy — registre manualmente)")
        log_date = st.date_input("Data", value=date.today())
        weight_kg = st.number_input(
            "Peso (kg)", min_value=30.0, max_value=250.0, value=latest_weight or 80.0, step=0.1
        )
        if st.form_submit_button("Registrar peso", use_container_width=True):
            log_bodyweight(conn, log_date.isoformat(), weight_kg)
            st.cache_data.clear()
            st.success(f"Peso de {weight_kg}kg registrado para {log_date.isoformat()}.")
    if latest_weight:
        st.caption(f"Último registro: {latest_weight}kg")

with col1:
    workouts_df = load_workouts(conn)
    last_log = load_last_sync_log(conn)

    if workouts_df.empty:
        st.info("Nenhum treino importado ainda. Clique em Sincronizar para importar seu histórico do Hevy.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total de treinos", len(workouts_df))
        m2.metric("Primeiro treino", workouts_df["start_time"].min().date().isoformat())
        m3.metric("Último treino", workouts_df["start_time"].max().date().isoformat())

    if last_log:
        status_label = "ok" if last_log["status"] == "success" else "falhou"
        st.caption(f"Último sync: {last_log['finished_at']} ({status_label})")
    else:
        st.caption("Ainda não houve nenhuma sincronização.")

if not workouts_df.empty:
    st.divider()

    all_insights = compute_all_insights()
    # Prescritivo is already the curated "what needs attention" layer (only
    # below-MEV/above-MRV/fadiga/queda real), so it's the source for alerts
    # here -- no need to re-derive severity from the other three pages.
    alerts = sorted(
        all_insights["prescriptive"],
        key=lambda i: {"critical": 0, "warning": 1, "info": 2, "positive": 3}[i.severity],
    )[:5]
    positives = [
        i
        for insights in (all_insights["descriptive"], all_insights["diagnostic"], all_insights["predictive"])
        for i in insights
        if i.severity == "positive"
    ][:3]

    alert_col, positive_col = st.columns(2)
    with alert_col:
        st.subheader("Pontos de atenção")
        render_insight_cards(alerts, empty_message="Nada de crítico no momento.")
        if len(all_insights["prescriptive"]) > len(alerts):
            st.page_link("pages/4_Prescritivo.py", label="Ver todas as recomendações")
    with positive_col:
        st.subheader("Destaques positivos")
        render_insight_cards(positives, empty_message="Ainda sem destaques positivos claros nesta janela.")

    st.divider()

st.markdown(
    "Use o menu à esquerda para navegar entre as análises: "
    "**Descritivo**, **Diagnóstico**, **Preditivo** e **Prescritivo**."
)
