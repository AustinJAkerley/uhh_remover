"""ffmpeg-based editor that removes filler spans while keeping A/V in sync.

Strategy (STRAT.md "Tier 0" baseline, hardened for arbitrary footage):
    Use ffmpeg's ``select`` / ``aselect`` filters to *drop* the frames/samples that
    fall inside a filler span, then re-stamp presentation timestamps so the kept
    media is contiguous. The exact same time ranges are removed from both the video
    and audio streams, so they stay perfectly aligned regardless of content.

This is a hard cut. Softer joins (dissolves, punch-in, AI interpolation) are layered
on later per STRAT.md; they are deliberately out of scope for the MVP because the
hard-cut path is the one that works reliably on *any* input.
"""

from __future__ import annotations

import subprocess
from typing import List, Optional

from .media import ffmpeg_path
from .models import FillerSpan

# Tail of ffmpeg stderr to surface when it fails (full logs can be very long).
MAX_STDERR_CHARS = 4000


def clamp_spans(
    spans: List[FillerSpan], duration: Optional[float]
) -> List[FillerSpan]:
    """Clamp spans to [0, duration], drop empty/invalid ones, and sort."""
    cleaned: List[FillerSpan] = []
    for s in spans:
        start = max(0.0, s.start)
        end = s.end if duration is None else min(s.end, duration)
        if end - start > 1e-3:
            cleaned.append(FillerSpan(start, end, s.text))
    return sorted(cleaned, key=lambda s: s.start)


def build_select_expr(spans: List[FillerSpan]) -> str:
    """ffmpeg select expression that is true for frames we KEEP."""
    terms = "+".join(
        f"between(t,{s.start:.4f},{s.end:.4f})" for s in spans
    )
    return f"not({terms})"


def build_ffmpeg_command(
    input_path: str,
    output_path: str,
    spans: List[FillerSpan],
    *,
    has_video: bool,
    has_audio: bool,
) -> List[str]:
    """Construct the ffmpeg argv to remove ``spans`` from ``input_path``."""
    expr = build_select_expr(spans)
    args: List[str] = [ffmpeg_path(), "-y", "-i", input_path]

    if has_video:
        args += ["-vf", f"select='{expr}',setpts=N/FRAME_RATE/TB"]
    if has_audio:
        args += ["-af", f"aselect='{expr}',asetpts=N/SR/TB"]

    if has_video:
        # Re-encode is mandatory once frames are dropped; pick broadly-compatible codecs.
        args += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
        if has_audio:
            args += ["-c:a", "aac"]
    # Audio-only outputs let the container pick its default encoder (wav->pcm, mp3->lame).

    args += [output_path]
    return args


def remove_spans(
    input_path: str,
    output_path: str,
    spans: List[FillerSpan],
    *,
    has_video: bool,
    has_audio: bool,
) -> None:
    """Run ffmpeg to produce ``output_path`` with ``spans`` removed."""
    cmd = build_ffmpeg_command(
        input_path,
        output_path,
        spans,
        has_video=has_video,
        has_audio=has_audio,
    )
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed to edit media:\n"
            + " ".join(cmd)
            + "\n\n"
            + proc.stderr[-MAX_STDERR_CHARS:]
        )
