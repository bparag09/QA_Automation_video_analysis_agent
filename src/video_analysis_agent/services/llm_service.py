from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI

from ..core.models import ClaimedStep, DeviationReport, FinalOutputSummary, PlannedStep, StepEvaluation
from .video_service import VideoFrame, encode_image_to_data_url


class LlmEvaluator:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.debug_artifacts: Dict[str, Any] = {"model": model, "summarize_video_frames": {}, "evaluate": {}}

    def summarize_video_frames(self, frames: List[VideoFrame]) -> Dict[str, Any]:
        if not frames:
            result = {"events": [], "notes": "No video frames available."}
            self.debug_artifacts["summarize_video_frames"] = {
                "frame_count": 0,
                "notes": "No frames supplied to vision summarizer.",
                "raw_response_text": "",
                "parsed_summary": result,
            }
            return result

        frame_refs: List[Dict[str, Any]] = []
        content = [
            {
                "type": "input_text",
                "text": (
                    "You are a QA run observer. Analyze each frame sequence and extract visible actions with evidence.\n"
                    "Return STRICT JSON with this shape:\n"
                    '{"events":[{"timestamp":"mm:ss","action":"...","evidence":"visible text/ui detail"}],"notes":"..."}'
                ),
            }
        ]

        for frame in frames:
            mm = int(frame.timestamp_sec // 60)
            ss = int(frame.timestamp_sec % 60)
            stamp = f"{mm:02d}:{ss:02d}"
            frame_refs.append({"timestamp": stamp, "video_file": Path(frame.video_path).name, "image_path": frame.image_path})
            content.append({"type": "input_text", "text": f"Frame timestamp: {stamp} from {Path(frame.video_path).name}"})
            content.append({"type": "input_image", "image_url": encode_image_to_data_url(Path(frame.image_path)), "detail": "low"})

        response = self.client.responses.create(
            model=self.model,
            input=[{"role": "user", "content": content}],
            temperature=0,
        )
        parsed = _coerce_json(response.output_text, default={"events": [], "notes": response.output_text})
        self.debug_artifacts["summarize_video_frames"] = {
            "frame_count": len(frames),
            "frame_refs": frame_refs,
            "raw_response_text": response.output_text,
            "parsed_summary": parsed,
        }
        return parsed

    def evaluate(
        self,
        planned_steps: List[PlannedStep],
        claimed_steps: List[ClaimedStep],
        video_summary: Dict[str, Any],
        final_summary: FinalOutputSummary,
    ) -> DeviationReport:
        if not _has_video_evidence(video_summary):
            report = _evaluate_without_video(planned_steps, claimed_steps, final_summary)
            self.debug_artifacts["evaluate"] = {
                "mode": "fallback_without_video",
                "planned_step_count": len(planned_steps),
                "claimed_step_count": len(claimed_steps),
                "final_summary": {
                    "status": final_summary.status,
                    "failure_message": final_summary.failure_message,
                    "final_response": final_summary.final_response,
                },
                "report": report.to_dict(),
            }
            return report

        prompt_payload = _build_evaluation_payload(planned_steps, claimed_steps, video_summary, final_summary)
        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Return STRICT JSON only.\n" + json.dumps(prompt_payload, ensure_ascii=True, indent=2)}],
                }
            ],
            temperature=0,
        )
        parsed = _coerce_json(response.output_text, default={})
        report = _normalize_report(parsed, claimed_steps)
        self.debug_artifacts["evaluate"] = {
            "mode": "vision_plus_reasoning",
            "planned_step_count": len(planned_steps),
            "claimed_step_count": len(claimed_steps),
            "prompt_payload": prompt_payload,
            "raw_response_text": response.output_text,
            "parsed_response": parsed,
            "report": report.to_dict(),
        }
        return report

    def get_debug_artifacts(self) -> Dict[str, Any]:
        return self.debug_artifacts


def _build_evaluation_payload(
    planned_steps: List[PlannedStep],
    claimed_steps: List[ClaimedStep],
    video_summary: Dict[str, Any],
    final_summary: FinalOutputSummary,
) -> Dict[str, Any]:
    return {
        "task": "Determine if each claimed step is visibly executed in the video evidence.",
        "rules": [
            "Use video evidence first.",
            "If step is claimed but not visibly supported, mark result as 'DEVIATION'.",
            "If step is visible, mark 'OBSERVED'.",
            "If no relevant visual evidence is available, mark 'NOT_VERIFIABLE'.",
            "Use final output to cross-check consistency, especially failures/assertions.",
        ],
        "planned_steps": [{"step_number": s.step_number, "description": s.description} for s in planned_steps],
        "claimed_steps": [
            {
                "claim_index": s.claim_index,
                "description": s.description,
                "claimed_status": s.claimed_status,
                "claimed_details": s.claimed_details,
            }
            for s in claimed_steps
        ],
        "video_summary": video_summary,
        "final_output": {
            "status": final_summary.status,
            "failure_message": final_summary.failure_message,
            "final_response": final_summary.final_response,
        },
        "output_format": {
            "overall": "short sentence",
            "has_deviations": "boolean",
            "assumptions": ["string"],
            "steps": [
                {
                    "step": "Step id or number",
                    "description": "claimed action",
                    "result": "OBSERVED|DEVIATION|NOT_VERIFIABLE",
                    "notes": "brief evidence-based explanation with timestamp if possible",
                }
            ],
        },
    }


def _coerce_json(raw_text: str, default: Dict[str, Any]) -> Dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            return default
    obj_match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(1))
        except json.JSONDecodeError:
            return default
    return default


def _normalize_report(data: Dict[str, Any], fallback_claims: List[ClaimedStep]) -> DeviationReport:
    raw_steps = data.get("steps") if isinstance(data, dict) else None
    normalized_steps: List[StepEvaluation] = []
    if isinstance(raw_steps, list):
        for idx, row in enumerate(raw_steps, start=1):
            if isinstance(row, dict):
                normalized_steps.append(
                    StepEvaluation(
                        step=str(row.get("step", f"Claim {idx}")),
                        description=str(row.get("description", "")),
                        result=str(row.get("result", "NOT_VERIFIABLE")).upper(),
                        notes=str(row.get("notes", "")),
                    )
                )
    if not normalized_steps:
        for c in fallback_claims:
            normalized_steps.append(
                StepEvaluation(
                    step=f"Claim {c.claim_index}",
                    description=c.description,
                    result="NOT_VERIFIABLE",
                    notes="LLM response could not be parsed into structured step results.",
                )
            )
    has_deviations = any(s.result == "DEVIATION" for s in normalized_steps)
    overall = str(data.get("overall", "")).strip() if isinstance(data, dict) else ""
    if not overall:
        overall = "No deviations detected." if not has_deviations else "Deviation(s) detected."
    assumptions = data.get("assumptions", []) if isinstance(data, dict) else []
    if not isinstance(assumptions, list):
        assumptions = [str(assumptions)]
    return DeviationReport(
        overall=overall,
        has_deviations=has_deviations,
        steps=normalized_steps,
        assumptions=[str(a) for a in assumptions],
    )


def _has_video_evidence(video_summary: Dict[str, Any]) -> bool:
    events = video_summary.get("events", [])
    return isinstance(events, list) and len(events) > 0


def _evaluate_without_video(
    planned_steps: List[PlannedStep],
    claimed_steps: List[ClaimedStep],
    final_summary: FinalOutputSummary,
) -> DeviationReport:
    failure_blob = f"{final_summary.failure_message} {final_summary.final_response}".lower()
    fallback_descriptions = [s.description for s in planned_steps] if planned_steps else [s.description for s in claimed_steps]
    steps: List[StepEvaluation] = []
    for idx, desc in enumerate(fallback_descriptions, start=1):
        lowered = desc.lower()
        if _is_explicitly_contradicted(lowered, failure_blob):
            steps.append(
                StepEvaluation(
                    step=str(idx),
                    description=desc,
                    result="DEVIATION",
                    notes="Contradicted by final test output/assertion, and no usable video evidence was available.",
                )
            )
        else:
            steps.append(
                StepEvaluation(
                    step=str(idx),
                    description=desc,
                    result="NOT_VERIFIABLE",
                    notes="No video evidence available, so this action cannot be visually validated.",
                )
            )
    has_deviations = any(s.result == "DEVIATION" for s in steps)
    overall = (
        "Deviation(s) inferred from final output. Missing video evidence limits visual validation."
        if has_deviations
        else "No deviations inferred from final output, but visual validation was not possible."
    )
    return DeviationReport(
        overall=overall,
        has_deviations=has_deviations,
        steps=steps,
        assumptions=["No video frames were available; results rely on planner claims and final test output only."],
    )


def _is_explicitly_contradicted(step_desc: str, failure_blob: str) -> bool:
    keyword_pairs = [
        ("turtle neck", "not available"),
        ("turtle neck", "only the 'crew neck'"),
        ("one product", "only the 'crew neck'"),
        ("one product", "not available"),
    ]
    for k1, k2 in keyword_pairs:
        if k1 in step_desc and k2 in failure_blob:
            return True
    if any(token in step_desc for token in ("assert", "filter", "turtle neck", "one product")):
        return any(token in failure_blob for token in ("not available", "failed", "could not proceed", "only"))
    return False

