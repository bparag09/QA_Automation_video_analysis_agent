from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class PlannedStep:
    step_number: int
    description: str


@dataclass
class ClaimedStep:
    claim_index: int
    description: str
    claimed_status: str
    claimed_details: str
    source_summary: str


@dataclass
class FinalOutputSummary:
    status: str
    failure_message: str
    final_response: str


@dataclass
class StepEvaluation:
    step: str
    description: str
    result: str
    notes: str


@dataclass
class DeviationReport:
    overall: str
    has_deviations: bool
    steps: List[StepEvaluation]
    assumptions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall": self.overall,
            "has_deviations": self.has_deviations,
            "steps": [asdict(step) for step in self.steps],
            "assumptions": self.assumptions,
        }


def ensure_string(value: Optional[Any]) -> str:
    if value is None:
        return ""
    return str(value)

