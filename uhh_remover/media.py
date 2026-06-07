"""Thin wrappers around ffprobe/ffmpeg for media introspection."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Optional


class FFmpegNotFound(RuntimeError):
    pass


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise FFmpegNotFound(
            f"'{tool}' not found on PATH. Install ffmpeg (which provides ffmpeg and "
            f"ffprobe) to process media."
        )
    return path


def ffprobe_path() -> str:
    return _require("ffprobe")


def ffmpeg_path() -> str:
    return _require("ffmpeg")


def probe(path: str) -> dict:
    """Return ffprobe's JSON for ``path``."""
    out = subprocess.run(
        [
            ffprobe_path(),
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout or "{}")


def has_video_stream(info: dict) -> bool:
    for s in info.get("streams", []):
        # Ignore cover-art / attached pictures, which present as video streams.
        if s.get("codec_type") == "video" and s.get("disposition", {}).get(
            "attached_pic", 0
        ) != 1:
            return True
    return False


def has_audio_stream(info: dict) -> bool:
    return any(s.get("codec_type") == "audio" for s in info.get("streams", []))


def duration_seconds(info: dict) -> Optional[float]:
    fmt = info.get("format", {})
    if "duration" in fmt:
        try:
            return float(fmt["duration"])
        except (TypeError, ValueError):
            pass
    for s in info.get("streams", []):
        if "duration" in s:
            try:
                return float(s["duration"])
            except (TypeError, ValueError):
                continue
    return None
