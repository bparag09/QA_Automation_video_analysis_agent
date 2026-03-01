from __future__ import annotations

import base64
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2


@dataclass
class VideoFrame:
    video_path: str
    timestamp_sec: float
    image_path: str


def sample_video_frames(
    video_path: Path, frame_interval_sec: float, max_frames: int
) -> Tuple[List[VideoFrame], Dict[str, Any]]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 1.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_sec = total_frames / fps if fps > 0 else 0
    debug: Dict[str, Any] = {
        "video_path": str(video_path),
        "fps": float(fps),
        "total_frames": int(total_frames),
        "duration_sec": float(duration_sec),
        "frame_interval_sec": float(frame_interval_sec),
        "max_frames": int(max_frames),
        "sampling_mode": "fixed_interval",
        "requested_timestamps_sec": [],
        "sampled": [],
        "read_failures": [],
    }

    if duration_sec <= 0:
        cap.release()
        debug["notes"] = "Video duration is zero or invalid."
        return [], debug

    timestamps = []
    t = 0.0
    while t <= duration_sec and len(timestamps) < max_frames:
        timestamps.append(t)
        t += frame_interval_sec

    if len(timestamps) < min(max_frames, 3):
        step = duration_sec / max(1, min(max_frames, 6))
        timestamps = [min(duration_sec, i * step) for i in range(min(max_frames, 6))]
        debug["sampling_mode"] = "fallback_spread"

    debug["requested_timestamps_sec"] = [round(ts, 3) for ts in timestamps]
    temp_dir = Path(tempfile.mkdtemp(prefix="video_frames_"))
    debug["temp_dir"] = str(temp_dir)

    frames: List[VideoFrame] = []
    for idx, ts in enumerate(timestamps):
        frame_no = min(total_frames - 1, max(0, int(math.floor(ts * fps))))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ok, frame = cap.read()
        if not ok:
            debug["read_failures"].append({"index": idx, "timestamp_sec": round(ts, 3), "frame_no": frame_no})
            continue
        output_path = temp_dir / f"frame_{idx:03d}_{int(ts)}s.jpg"
        cv2.imwrite(str(output_path), frame)
        frames.append(VideoFrame(video_path=str(video_path), timestamp_sec=ts, image_path=str(output_path)))
        debug["sampled"].append(
            {"index": idx, "timestamp_sec": round(ts, 3), "frame_no": int(frame_no), "image_path": str(output_path)}
        )

    cap.release()
    debug["sample_count"] = len(frames)
    return frames, debug


def encode_image_to_data_url(image_path: Path) -> str:
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"

