"""End-to-end pipeline: transcribe -> detect -> edit."""

from __future__ import annotations

import shutil
from typing import List, Optional

from .config import FillerConfig
from .detection import detect_fillers
from .editor import clamp_spans, remove_spans
from .media import (
    duration_seconds,
    has_audio_stream,
    has_video_stream,
    probe,
)
from .models import ProcessResult, Word
from .transcription.base import Transcriber


def process(
    input_path: str,
    output_path: str,
    transcriber: Transcriber,
    config: Optional[FillerConfig] = None,
) -> ProcessResult:
    """Remove fillers from ``input_path`` and write the result to ``output_path``.

    Works for both video and audio-only inputs; video is the primary case and audio
    falls out of the same code path.
    """
    config = config or FillerConfig()

    info = probe(input_path)
    has_video = has_video_stream(info)
    has_audio = has_audio_stream(info)
    duration = duration_seconds(info)
    if not has_audio:
        raise ValueError(
            "Input has no audio stream; there is nothing to transcribe or remove."
        )

    words: List[Word] = transcriber.transcribe(input_path)
    spans = detect_fillers(words, config)
    spans = clamp_spans(spans, duration)

    if not spans:
        # Nothing to cut - copy through untouched so callers always get an output file.
        shutil.copyfile(input_path, output_path)
        out_info = probe(output_path)
        return ProcessResult(
            input_path=input_path,
            output_path=output_path,
            removed_spans=[],
            source_duration=duration or 0.0,
            output_duration=duration_seconds(out_info) or (duration or 0.0),
            had_video=has_video,
        )

    remove_spans(
        input_path,
        output_path,
        spans,
        has_video=has_video,
        has_audio=has_audio,
    )

    out_info = probe(output_path)
    return ProcessResult(
        input_path=input_path,
        output_path=output_path,
        removed_spans=spans,
        source_duration=duration or 0.0,
        output_duration=duration_seconds(out_info) or 0.0,
        had_video=has_video,
    )
