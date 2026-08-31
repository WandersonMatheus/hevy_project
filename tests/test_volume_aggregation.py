import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hevy_analytics.analytics.descriptive import weekly_muscle_group_volume
from hevy_analytics.analytics.diagnostic import classify_volume
from hevy_analytics.config.landmarks import load_landmarks
from hevy_analytics.settings import LANDMARKS_PATH


@pytest.fixture
def landmarks():
    return load_landmarks(LANDMARKS_PATH)


@pytest.fixture
def templates_df():
    return pd.DataFrame(
        [
            {
                "id": "TPL1",
                "primary_muscle_group": "chest",
                "secondary_muscle_groups": ["triceps", "shoulders"],
            }
        ]
    )


def _make_sets_df(n_hard_sets: int, start_time: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "workout_id": "W1",
                "start_time": pd.Timestamp(start_time),
                "exercise_template_id": "TPL1",
                "set_type": "normal",
                "weight_kg": 80,
                "reps": 8,
                "rpe": 8,
            }
            for _ in range(n_hard_sets)
        ]
    )


def test_weekly_volume_credits_primary_and_secondary(landmarks, templates_df):
    sets_df = _make_sets_df(4, "2026-01-05")  # a Monday
    result = weekly_muscle_group_volume(sets_df, templates_df, landmarks)

    chest_row = result[result["muscle_group"] == "chest"].iloc[0]
    triceps_row = result[result["muscle_group"] == "triceps"].iloc[0]

    assert chest_row["hard_sets"] == 4
    assert triceps_row["hard_sets"] == 4 * landmarks.secondary_muscle_credit


def test_classify_volume_below_mev(landmarks, templates_df):
    sets_df = _make_sets_df(1, "2026-01-05")
    volume_df = weekly_muscle_group_volume(sets_df, templates_df, landmarks)
    classified = classify_volume(volume_df, landmarks)

    chest_row = classified[classified["muscle_group"] == "chest"].iloc[0]
    assert chest_row["classification"] == "below_mev"


def test_classify_volume_above_mrv(landmarks, templates_df):
    sets_df = _make_sets_df(30, "2026-01-05")
    volume_df = weekly_muscle_group_volume(sets_df, templates_df, landmarks)
    classified = classify_volume(volume_df, landmarks)

    chest_row = classified[classified["muscle_group"] == "chest"].iloc[0]
    assert chest_row["classification"] == "above_mrv"
