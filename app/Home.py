import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

st.set_page_config(page_title="Hevy Analytics", layout="wide")

LOGO_PATH = Path(__file__).resolve().parent / "assets" / "logo.png"
_logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode() if LOGO_PATH.exists() else ""

NAVY = "#0B1120"
NAVY_LIGHT = "#141B2E"
BLUE = "#23ADED"
GREEN = "#A3E635"

st.markdown(
    f"""
    <style>
        div[data-testid="stAppViewContainer"] > .main {{ padding-top: 0; }}
        div[data-testid="stMainBlockContainer"] {{ padding-top: 0; }}
    </style>
    <div style="background:linear-gradient(135deg, {NAVY} 0%, {NAVY_LIGHT} 100%);
                border-radius:16px; padding:3rem 2.5rem; margin-bottom:2rem; text-align:center;">
        <img src="data:image/png;base64,{_logo_b64}" style="width:88px; height:88px; border-radius:18px; margin-bottom:1.2rem;">
        <div style="font-size:2.2rem; font-weight:700; color:white; margin-bottom:0.5rem;">Hevy Analytics</div>
        <div style="font-size:1.05rem; color:#B8C4DA; max-width:640px; margin:0 auto;">
            Seus treinos do Hevy, cruzados com ciência do esporte, em quatro camadas de análise
            <span style="color:{BLUE};">descritiva</span>, <span style="color:{BLUE};">diagnóstica</span>,
            <span style="color:{BLUE};">preditiva</span> e <span style="color:{BLUE};">prescritiva</span> —
            mais rastreamento de <span style="color:{GREEN};">metas</span> com estimativa de prazo.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("Sessões")

SESSIONS = [
    ("Painel", "pages/0_Painel.py", "Sincronize seus dados, registre peso corporal, e veja o resumo do que precisa da sua atenção.", BLUE),
    ("Descritivo", "pages/1_Descritivo.py", "O que aconteceu: tonnage, volume por grupo muscular, frequência, variedade de exercícios.", BLUE),
    ("Diagnóstico", "pages/2_Diagnostico.py", "Por que: volume vs. MEV/MAV/MRV, platô, fadiga, e se você reage melhor a mais volume.", BLUE),
    ("Preditivo", "pages/3_Preditivo.py", "Pra onde a força está indo: 1RM estimado, tendência e projeção por exercício.", BLUE),
    ("Prescritivo", "pages/4_Prescritivo.py", "O que fazer a respeito: recomendações baseadas em regras, não em achismo.", BLUE),
    ("Metas", "pages/5_Metas.py", "Defina metas de peso, força relativa ou dor, e veja o quanto falta e como chegar lá.", GREEN),
]

cols = st.columns(3)
for i, (title, path, desc, accent) in enumerate(SESSIONS):
    with cols[i % 3]:
        st.markdown(
            f"""
            <div style="border:1px solid #E2E8F0; border-left:4px solid {accent}; border-radius:8px;
                        padding:1rem 1.2rem; margin-bottom:0.8rem; min-height:132px;">
                <div style="font-weight:700; font-size:1.05rem; margin-bottom:0.35rem;">{title}</div>
                <div style="font-size:0.88rem; color:#475569; line-height:1.4;">{desc}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.page_link(path, label=f"Abrir {title}")

st.divider()
st.caption(
    "Metodologia baseada em regras explícitas e editáveis (config/landmarks.yaml, config/context.yaml) — "
    "sem machine learning, sem caixa-preta. Código aberto em "
    "[github.com/WandersonMatheus/hevy_project](https://github.com/WandersonMatheus/hevy_project)."
)
