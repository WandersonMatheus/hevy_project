import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from hevy_analytics.config.landmarks import load_landmarks
from hevy_analytics.data_access import load_exercise_templates, load_sets, load_workouts
from hevy_analytics.db.connection import get_connection, init_db
from hevy_analytics.settings import DB_PATH, LANDMARKS_PATH


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
