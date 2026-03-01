from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple

from ..core.models import ClaimedStep, FinalOutputSummary, PlannedStep, ensure_string


def parse_planning_log(agent_log_path: Path) -> Tuple[List[PlannedStep], List[ClaimedStep]]:
    raw = json.loads(agent_log_path.read_text(encoding="utf-8"))
    messages = raw.get("planner_agent", [])
    return _extract_global_plan(messages), _extract_claimed_steps(messages)


def parse_test_output(xml_path: Path) -> FinalOutputSummary:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    testcase = root.find(".//testcase")
    failure = testcase.find("failure") if testcase is not None else None
    system_out_nodes = testcase.findall("system-out") if testcase is not None else []

    status = "failed" if failure is not None else "passed"
    failure_message = ensure_string(failure.attrib.get("message")) if failure is not None else ""
    final_response = ""
    for node in system_out_nodes:
        text = ensure_string(node.text).strip()
        if text:
            final_response = text
            break

    return FinalOutputSummary(status=status, failure_message=failure_message, final_response=final_response)


def detect_videos(base_dir: Path) -> List[Path]:
    found: List[Path] = []
    for ext in ("*.webm", "*.mp4", "*.mov", "*.mkv"):
        found.extend(base_dir.rglob(ext))
    return sorted(set(found))


def _extract_global_plan(messages: list) -> List[PlannedStep]:
    for msg in messages:
        if msg.get("name") != "planner_agent" or msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, dict):
            continue
        plan_text = content.get("plan", "")
        if not plan_text:
            continue
        steps = []
        for line in plan_text.splitlines():
            m = re.match(r"^\s*(\d+)\.\s+(.*)$", line.strip())
            if m:
                steps.append(PlannedStep(step_number=int(m.group(1)), description=m.group(2).strip()))
        if steps:
            return steps
    return []


def _extract_claimed_steps(messages: list) -> List[ClaimedStep]:
    claimed: List[ClaimedStep] = []
    claim_idx = 1
    for idx, msg in enumerate(messages):
        if msg.get("name") != "planner_agent" or msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, dict):
            continue
        summary = ensure_string(content.get("next_step_summary")).strip() or ensure_string(
            content.get("next_step")
        ).strip()
        if not summary:
            continue

        next_user = _find_next_user_feedback(messages, idx + 1)
        claimed_status = _extract_field(next_user, "previous_step_status") if next_user else "UNKNOWN"
        claimed_details = _extract_field(next_user, "current_output") if next_user else ""
        if next_user and not claimed_details:
            claimed_details = next_user.strip()

        claimed.append(
            ClaimedStep(
                claim_index=claim_idx,
                description=summary,
                claimed_status=claimed_status or "UNKNOWN",
                claimed_details=claimed_details.strip(),
                source_summary=summary,
            )
        )
        claim_idx += 1
    return claimed


def _find_next_user_feedback(messages: list, start_index: int) -> str:
    for i in range(start_index, len(messages)):
        m = messages[i]
        if m.get("role") == "user" and m.get("name") == "user":
            content = m.get("content")
            if isinstance(content, str) and "previous_step:" in content:
                return content
            return ""
    return ""


def _extract_field(blob: str, field_name: str) -> str:
    if not blob:
        return ""
    pattern = rf"{re.escape(field_name)}:\s*(.*?)(?:\n[A-Za-z_]+:|\Z)"
    m = re.search(pattern, blob, flags=re.DOTALL)
    if not m:
        return ""
    return m.group(1).strip()

