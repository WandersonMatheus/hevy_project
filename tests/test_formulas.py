import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hevy_analytics.analytics.formulas import (
    brzycki_1rm,
    epley_1rm,
    estimate_1rm,
    is_hard_set,
    tonnage,
)


def test_epley_1rm_matches_known_value():
    assert epley_1rm(100, 5) == pytest.approx(116.67, abs=0.01)


def test_epley_1rm_at_one_rep_equals_weight():
    assert epley_1rm(100, 1) == pytest.approx(103.33, abs=0.01)


def test_brzycki_1rm_matches_known_value():
    assert brzycki_1rm(100, 5) == pytest.approx(112.5, abs=0.01)


def test_brzycki_1rm_raises_above_37_reps():
    with pytest.raises(ValueError):
        brzycki_1rm(100, 37)


def test_estimate_1rm_dispatches_correctly():
    assert estimate_1rm(100, 5, "epley") == epley_1rm(100, 5)
    assert estimate_1rm(100, 5, "brzycki") == brzycki_1rm(100, 5)


def test_estimate_1rm_unknown_formula_raises():
    with pytest.raises(ValueError):
        estimate_1rm(100, 5, "made_up_formula")


def test_tonnage():
    assert tonnage(80, 8) == 640


def test_is_hard_set():
    hard_types = ["normal", "failure", "dropset"]
    assert is_hard_set("normal", hard_types) is True
    assert is_hard_set("warmup", hard_types) is False
