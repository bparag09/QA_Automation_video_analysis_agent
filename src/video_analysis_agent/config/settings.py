from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppSettings:
    agent_log_path: Path
    test_output_path: Path
    artifact_root: Path
    output_dir: Path
    video_paths: list[Path]
    model: str
    frame_interval_sec: float
    max_frames: int

