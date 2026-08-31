from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Insight:
    id: str
    type: Literal["descriptive", "diagnostic", "predictive", "prescriptive"]
    title: str
    body: str
    metrics: dict = field(default_factory=dict)
    muscle_group: str | None = None
    exercise: str | None = None
    severity: Literal["positive", "info", "warning", "critical"] = "info"
    created_at: str | None = None

    def to_markdown(self) -> str:
        lines = [f"## {self.title}", "", self.body]
        if self.metrics:
            lines.append("")
            for key, value in self.metrics.items():
                lines.append(f"- **{key}**: {value}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "metrics": self.metrics,
            "muscle_group": self.muscle_group,
            "exercise": self.exercise,
            "severity": self.severity,
            "created_at": self.created_at,
        }
