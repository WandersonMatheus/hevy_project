import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from _shared import get_db_connection
from hevy_analytics.api.client import HevyAPIError, HevyClient
from hevy_analytics.data_access import load_last_sync_log, load_workouts
from hevy_analytics.ingest.sync import run_sync
from hevy_analytics.settings import HEVY_API_KEY, MAX_RETRIES, REQUEST_DELAY_SECONDS

st.set_page_config(page_title="Hevy Analytics", page_icon="🏋️", layout="wide")

conn = get_db_connection()

st.title("🏋️ Hevy Analytics")
st.caption("Análise descritiva, diagnóstica, preditiva e prescritiva do seu treino de musculação.")

col1, col2 = st.columns([3, 1])

with col2:
    if st.button("🔄 Sincronizar", use_container_width=True):
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
        status_icon = "✅" if last_log["status"] == "success" else "❌"
        st.caption(f"{status_icon} Último sync: {last_log['finished_at']} ({last_log['status']})")
    else:
        st.caption("Ainda não houve nenhuma sincronização.")

st.divider()
st.markdown(
    "Use o menu à esquerda para navegar entre as análises: "
    "**Descritivo**, **Diagnóstico**, **Preditivo** e **Prescritivo**."
)
