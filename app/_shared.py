import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from hevy_analytics.config.context import load_context
from hevy_analytics.config.landmarks import load_landmarks
from hevy_analytics.data_access import (
    latest_bodyweight,
    load_bodyweight_logs,
    load_exercise_templates,
    load_goals,
    load_pain_logs,
    load_sets,
    load_workouts,
)
from hevy_analytics.db.connection import get_connection, init_db
from hevy_analytics.settings import CONTEXT_PATH, DB_PATH, LANDMARKS_PATH

# Brand palette, sampled from the project logo (app/assets/logo.png).
NAVY = "#0B1120"
NAVY_LIGHT = "#141B2E"
NAVY_LIGHTER = "#1B2438"
BLUE = "#23ADED"
GREEN = "#A3E635"
TEXT = "#E5E9F0"
TEXT_MUTED = "#9AA6BC"
BORDER = "#26304A"

# Extended categorical palette for charts with many series (e.g. per-muscle-
# group bars): starts with the two brand colors, then fills out with hues
# chosen for contrast against each other and against the navy background.
CATEGORICAL_PALETTE = [
    BLUE, GREEN, "#F59E0B", "#F472B6", "#818CF8", "#2DD4BF",
    "#FB7185", "#FACC15", "#38BDF8", "#4ADE80", "#C084FC", "#FDBA74",
]

# Shared with severity styling below, so a chart's category colors read the
# same way as the insight cards (e.g. "above_mrv" is always the same red).
SEMANTIC_COLORS = {"critical": "#F87171", "warning": "#FBBF24", "info": BLUE, "positive": GREEN}


def style_fig(fig):
    """Applies the brand palette/dark theme to a Plotly figure. Plotly Express
    assigns trace colors at creation time, so for multi-series charts also
    pass color_discrete_sequence=CATEGORICAL_PALETTE (or color_discrete_map)
    directly to px.bar/px.line -- this just handles layout/background/font,
    which apply regardless of how traces were colored."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=NAVY_LIGHT,
        plot_bgcolor=NAVY_LIGHT,
        font_color=TEXT,
        legend_title_text="",
        margin=dict(t=30, l=10, r=10, b=10),
    )
    fig.update_xaxes(gridcolor=BORDER, zerolinecolor=BORDER)
    fig.update_yaxes(gridcolor=BORDER, zerolinecolor=BORDER)
    return fig


@st.cache_resource
def get_db_connection():
    conn = get_connection(DB_PATH)
    init_db(conn)
    return conn


@st.cache_data
def get_landmarks():
    return load_landmarks(LANDMARKS_PATH)


@st.cache_data
def get_workouts_df():
    return load_workouts(get_db_connection())


@st.cache_data
def get_sets_df():
    return load_sets(get_db_connection())


@st.cache_data
def get_templates_df():
    return load_exercise_templates(get_db_connection())


@st.cache_data
def get_context():
    return load_context(CONTEXT_PATH)


@st.cache_data
def get_bodyweight_df():
    return load_bodyweight_logs(get_db_connection())


@st.cache_data
def get_latest_bodyweight():
    return latest_bodyweight(get_db_connection())


@st.cache_data
def get_goals_df():
    return load_goals(get_db_connection())


@st.cache_data
def get_pain_logs_df():
    return load_pain_logs(get_db_connection())


@st.cache_data
def compute_all_insights():
    """Runs the full descriptive -> diagnostic -> predictive -> prescriptive
    pipeline once and returns every generated Insight, tagged by type. Used
    by the Home page to build a cross-cutting summary without each analysis
    page having to know about the others."""
    from hevy_analytics.analytics.descriptive import (
        generate_descriptive_insights,
        weekly_muscle_group_volume,
    )
    from hevy_analytics.analytics.diagnostic import (
        classify_volume,
        detect_fatigue_signals,
        detect_plateau,
        generate_diagnostic_insights,
    )
    from hevy_analytics.analytics.predictive import best_e1rm_per_session, generate_overview_insight
    from hevy_analytics.analytics.prescriptive import generate_recommendations
    from hevy_analytics.analytics.responsiveness import generate_responsiveness_insights, volume_responsiveness

    workouts_df = get_workouts_df()
    sets_df = get_sets_df()
    templates_df = get_templates_df()
    landmarks = get_landmarks()
    activities = get_context()

    if workouts_df.empty:
        return {"descriptive": [], "diagnostic": [], "predictive": [], "prescriptive": []}

    volume_df = weekly_muscle_group_volume(sets_df, templates_df, landmarks)
    classified = classify_volume(volume_df, landmarks)
    e1rm_df = best_e1rm_per_session(sets_df, landmarks)
    plateau_df = detect_plateau(e1rm_df, landmarks)
    fatigue_df = detect_fatigue_signals(sets_df, landmarks)
    responsiveness_df = volume_responsiveness(sets_df, templates_df, landmarks)

    descriptive = generate_descriptive_insights(workouts_df, sets_df, volume_df, landmarks)
    diagnostic = generate_diagnostic_insights(
        classified, plateau_df, fatigue_df, templates_df, landmarks, activities
    )
    diagnostic += generate_responsiveness_insights(responsiveness_df, landmarks)
    overview = generate_overview_insight(e1rm_df, templates_df)
    predictive = [overview] if overview else []
    prescriptive = generate_recommendations(classified, plateau_df, fatigue_df, templates_df, landmarks)

    return {
        "descriptive": descriptive,
        "diagnostic": diagnostic,
        "predictive": predictive,
        "prescriptive": prescriptive,
    }


_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "positive": 3}
_SEVERITY_STYLE = {
    "critical": {"label": "Crítico", "color": SEMANTIC_COLORS["critical"], "bg": "#2A1418"},
    "warning": {"label": "Atenção", "color": SEMANTIC_COLORS["warning"], "bg": "#2A2210"},
    "info": {"label": "Info", "color": SEMANTIC_COLORS["info"], "bg": "#122436"},
    "positive": {"label": "Positivo", "color": SEMANTIC_COLORS["positive"], "bg": "#1F2A0E"},
}


def render_insight_cards(insights, empty_message: str = "Nada a reportar no momento.") -> None:
    """Shared card renderer for lists of hevy_analytics.insights.models.Insight,
    used by every analysis page so descriptive/diagnostic/predictive/prescriptive
    all present their narrative insights the same way. Plain colored left-border
    cards with a small severity label -- no icons/emoji."""
    if not insights:
        st.markdown(
            f'<div style="padding:0.7rem 1rem; border-radius:6px; background:{_SEVERITY_STYLE["info"]["bg"]}; '
            f'color:{_SEVERITY_STYLE["info"]["color"]}; font-size:0.9rem;">{html.escape(empty_message)}</div>',
            unsafe_allow_html=True,
        )
        return

    for insight in sorted(insights, key=lambda i: _SEVERITY_ORDER[i.severity]):
        style = _SEVERITY_STYLE[insight.severity]
        st.markdown(
            f"""
            <div style="border-left:3px solid {style['color']}; background:{style['bg']};
                        border-radius:4px; padding:0.7rem 1rem; margin-bottom:0.6rem;">
                <div style="font-size:0.7rem; font-weight:600; letter-spacing:0.04em;
                            text-transform:uppercase; color:{style['color']}; margin-bottom:0.2rem;">
                    {style['label']}
                </div>
                <div style="font-weight:600; color:{TEXT}; margin-bottom:0.2rem;">{html.escape(insight.title)}</div>
                <div style="font-size:0.92rem; color:{TEXT_MUTED}; line-height:1.5; white-space:pre-line;">{html.escape(insight.body)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if insight.metrics:
            with st.expander("Detalhes / copiar como Markdown"):
                st.text_area(
                    "Markdown",
                    insight.to_markdown(),
                    key=f"md-{insight.id}",
                    label_visibility="collapsed",
                )
