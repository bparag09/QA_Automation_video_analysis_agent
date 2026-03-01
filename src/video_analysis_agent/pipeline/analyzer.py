from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config.settings import AppSettings
from ..services.llm_service import LlmEvaluator
from ..services.parser_service import parse_planning_log, parse_test_output
from ..services.report_service import write_debug_logs, write_report_files
from ..services.video_service import sample_video_frames


@dataclass
class RunArtifacts:
    report_json_path: Path
    report_md_path: Path
    video_log_path: Path
    llm_log_path: Path


class AnalysisPipeline:
    def __init__(self, settings: AppSettings, api_key: str) -> None:
        self.settings = settings
        self.evaluator = LlmEvaluator(api_key=api_key, model=settings.model)

    def run(self) -> RunArtifacts:
        planned_steps, claimed_steps = parse_planning_log(self.settings.agent_log_path)
        final_summary = parse_test_output(self.settings.test_output_path)

        all_frames = []
        sampling_logs = []
        for video_path in self.settings.video_paths:
            frames, debug = sample_video_frames(
                video_path=video_path,
                frame_interval_sec=self.settings.frame_interval_sec,
                max_frames=self.settings.max_frames,
            )
            all_frames.extend(frames)
            sampling_logs.append(debug)

        video_summary = self.evaluator.summarize_video_frames(all_frames)
        report = self.evaluator.evaluate(
            planned_steps=planned_steps,
            claimed_steps=claimed_steps,
            video_summary=video_summary,
            final_summary=final_summary,
        )

        report_json_path, report_md_path = write_report_files(report, self.settings.output_dir)
        video_log_payload = {
            "total_videos": len(self.settings.video_paths),
            "total_sampled_frames": len(all_frames),
            "videos": sampling_logs,
        }
        video_log_path, llm_log_path = write_debug_logs(
            self.settings.output_dir,
            video_payload=video_log_payload,
            llm_payload=self.evaluator.get_debug_artifacts(),
        )
        return RunArtifacts(
            report_json_path=report_json_path,
            report_md_path=report_md_path,
            video_log_path=video_log_path,
            llm_log_path=llm_log_path,
        )

