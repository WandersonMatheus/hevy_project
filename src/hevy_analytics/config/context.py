from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ExternalActivity:
    name: str
    affected_muscle_groups: list[str]
    note: str


def load_context(path: Path) -> list[ExternalActivity]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [ExternalActivity(**a) for a in raw.get("external_activities", [])]


def note_for_muscle_group(activities: list[ExternalActivity], muscle_group: str | None) -> str | None:
    if not muscle_group:
        return None
    for activity in activities:
        if muscle_group in activity.affected_muscle_groups:
            return activity.note
    return None
