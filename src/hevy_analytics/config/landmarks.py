from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class VolumeLandmark:
    mev: float
    mav: float
    mrv: float


@dataclass(frozen=True)
class DeloadRule:
    window_sessions: int
    rpe_increase_threshold: float
    weight_tolerance_pct: float


@dataclass(frozen=True)
class PlateauRule:
    window_sessions: int
    min_e1rm_improvement_pct: float


@dataclass(frozen=True)
class Landmarks:
    hard_set_types: list[str]
    secondary_muscle_credit: float
    muscle_groups: dict[str, VolumeLandmark]
    default_landmark: VolumeLandmark
    one_rm_formula: str
    max_reps_for_estimate: int
    deload_rule: DeloadRule
    plateau_rule: PlateauRule

    def landmark_for(self, muscle_group: str) -> VolumeLandmark:
        return self.muscle_groups.get(muscle_group, self.default_landmark)


def load_landmarks(path: Path) -> Landmarks:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    muscle_groups = {
        name: VolumeLandmark(**values)
        for name, values in raw["muscle_groups"].items()
        if name != "default"
    }
    default_landmark = VolumeLandmark(**raw["muscle_groups"]["default"])

    return Landmarks(
        hard_set_types=raw["hard_set_types"],
        secondary_muscle_credit=raw["secondary_muscle_credit"],
        muscle_groups=muscle_groups,
        default_landmark=default_landmark,
        one_rm_formula=raw["one_rep_max"]["primary_formula"],
        max_reps_for_estimate=raw["one_rep_max"]["max_reps_for_estimate"],
        deload_rule=DeloadRule(**raw["rpe_rules"]["deload"]),
        plateau_rule=PlateauRule(**raw["rpe_rules"]["plateau"]),
    )


def find_unmapped_muscle_groups(landmarks: Landmarks, muscle_groups_in_db: set[str]) -> set[str]:
    """Diagnostic helper: which muscle-group strings seen in the DB have no
    explicit yaml entry and therefore silently fall back to `default`."""
    return {mg for mg in muscle_groups_in_db if mg and mg not in landmarks.muscle_groups}
