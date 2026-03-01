from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

from ..config.settings import AppSettings
from ..pipeline.analyzer import AnalysisPipeline
from ..services.parser_service import detect_videos


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze QA run artifacts and detect plan-vs-video deviations.")
    parser.add_argument("--agent-log", default="agent_logs/agent_inner_logs.json", help="Path to planner/internal log JSON file.")
    parser.add_argument("--test-output", default="agent_logs/test_result.xml", help="Path to Hercules final test output XML.")
    parser.add_argument("--videos", nargs="*", default=[], help="One or more video paths. If omitted, videos are auto-discovered.")
    parser.add_argument("--artifact-root", default="agent_logs", help="Folder used to auto-discover videos when --videos is not provided.")
    parser.add_argument("--output-dir", default="reports", help="Output directory for generated deviation reports.")
    parser.add_argument("--model", default="gpt-4.1-mini", help="OpenAI model for visual reasoning and step evaluation.")
    parser.add_argument("--frame-interval", type=float, default=2.0, help="Seconds between sampled frames per video.")
    parser.add_argument("--max-frames", type=int, default=70, help="Max sampled frames per video.")
    return parser.parse_args()


def main(project_root: Path | None = None) -> int:
    root = project_root.resolve() if project_root else Path.cwd().resolve()
    load_dotenv(root / ".env")
    args = parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: OPENAI_API_KEY missing. Set it in .env or environment.")
        return 1

    settings = _build_settings(args)
    if not settings.agent_log_path.exists():
        print(f"ERROR: agent log not found: {settings.agent_log_path}")
        return 1
    if not settings.test_output_path.exists():
        print(f"ERROR: test output not found: {settings.test_output_path}")
        return 1

    pipeline = AnalysisPipeline(settings=settings, api_key=api_key)
    artifacts = pipeline.run()
    print("Analysis complete.")
    print(f"- JSON report: {artifacts.report_json_path}")
    print(f"- Markdown report: {artifacts.report_md_path}")
    print(f"- Video sampling log: {artifacts.video_log_path}")
    print(f"- LLM analysis log: {artifacts.llm_log_path}")
    return 0


def _build_settings(args: argparse.Namespace) -> AppSettings:
    agent_log_path = Path(args.agent_log).resolve()
    test_output_path = Path(args.test_output).resolve()
    artifact_root = Path(args.artifact_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    video_paths = _resolve_video_paths(args.videos, artifact_root)
    return AppSettings(
        agent_log_path=agent_log_path,
        test_output_path=test_output_path,
        artifact_root=artifact_root,
        output_dir=output_dir,
        video_paths=video_paths,
        model=args.model,
        frame_interval_sec=args.frame_interval,
        max_frames=args.max_frames,
    )


def _resolve_video_paths(videos: List[str], artifact_root: Path) -> List[Path]:
    explicit = [Path(v).resolve() for v in videos if v]
    if explicit:
        return [p for p in explicit if p.exists()]
    return detect_videos(artifact_root.resolve())

