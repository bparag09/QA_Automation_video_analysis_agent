from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

from src.video_analysis_agent.cli.main import main


if __name__ == "__main__":
    raise SystemExit(main(project_root=ROOT))

