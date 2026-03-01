from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from ..core.models import DeviationReport


def write_report_files(report: DeviationReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "deviation_report.json"
    md_path = output_dir / "deviation_report.md"
    generated_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = report.to_dict()
    payload["generated_at_utc"] = generated_at_utc

    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    md_path.write_text(_to_markdown(report, generated_at_utc), encoding="utf-8")
    return json_path, md_path


def write_debug_logs(output_dir: Path, video_payload: dict, llm_payload: dict) -> tuple[Path, Path]:
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    video_log_path = logs_dir / "video_sampling_log.json"
    llm_log_path = logs_dir / "llm_analysis_log.json"
    video_log_path.write_text(json.dumps(video_payload, indent=2, ensure_ascii=True), encoding="utf-8")
    llm_log_path.write_text(json.dumps(llm_payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return video_log_path, llm_log_path


def _to_markdown(report: DeviationReport, generated_at_utc: str) -> str:
    lines = [
        "# Deviation Report",
        "",
        f"**Generated At (UTC):** {generated_at_utc}",
        "",
        f"**Overall:** {report.overall}",
        "",
        "| Step | Description | Result | Notes |",
        "|---|---|---|---|",
    ]
    for row in report.steps:
        desc = _sanitize_cell(row.description)
        result = _sanitize_cell(row.result)
        notes = _sanitize_cell(row.notes)
        lines.append(f"| {row.step} | {desc} | {result} | {notes} |")
    if report.assumptions:
        lines.append("")
        lines.append("## Assumptions")
        for assumption in report.assumptions:
            lines.append(f"- {assumption}")
    if not report.has_deviations:
        lines.append("")
        lines.append("➡️ No deviations detected.")
    return "\n".join(lines) + "\n"


def _sanitize_cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()

