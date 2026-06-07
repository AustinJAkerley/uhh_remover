"""End-to-end test: generate a synthetic clip, remove a span, verify it shrank.

Skipped automatically if ffmpeg/ffprobe are not installed.
"""

import json
import os
import shutil

import pytest

from uhh_remover.config import FillerConfig
from uhh_remover.media import duration_seconds, has_video_stream, probe
from uhh_remover.pipeline import process
from uhh_remover.transcription.json_provider import JSONTranscriber

ffmpeg = shutil.which("ffmpeg")
ffprobe = shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(
    not (ffmpeg and ffprobe), reason="ffmpeg/ffprobe not installed"
)


def _make_clip(path: str, seconds: int = 6):
    import subprocess

    subprocess.run(
        [
            ffmpeg, "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x240:rate=25",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-shortest", "-pix_fmt", "yuv420p", path,
        ],
        check=True, capture_output=True,
    )


def test_video_pipeline_removes_span(tmp_path):
    src = str(tmp_path / "src.mp4")
    out = str(tmp_path / "out.mp4")
    _make_clip(src, seconds=6)

    # Pretend a 2s "uhhh" sits between t=2 and t=4.
    transcript = tmp_path / "t.json"
    transcript.write_text(
        json.dumps(
            {
                "words": [
                    {"text": "hello", "start": 0.0, "end": 1.0},
                    {"text": "uhhh", "start": 2.0, "end": 4.0},
                    {"text": "world", "start": 5.0, "end": 6.0},
                ]
            }
        )
    )

    result = process(
        src, out, JSONTranscriber(str(transcript)),
        FillerConfig(pad_start=0.0, pad_end=0.0),
    )

    assert os.path.exists(out)
    assert result.had_video is True
    assert result.removed_count == 1
    # ~2s removed; output should be clearly shorter than the source.
    assert result.source_duration - result.output_duration > 1.5

    info = probe(out)
    assert has_video_stream(info)
    assert duration_seconds(info) < result.source_duration - 1.0


def test_no_fillers_copies_through(tmp_path):
    src = str(tmp_path / "src.mp4")
    out = str(tmp_path / "out.mp4")
    _make_clip(src, seconds=3)

    transcript = tmp_path / "t.json"
    transcript.write_text(json.dumps({"words": [
        {"text": "hello", "start": 0.0, "end": 1.0},
        {"text": "world", "start": 1.5, "end": 2.5},
    ]}))

    result = process(src, out, JSONTranscriber(str(transcript)), FillerConfig())
    assert result.removed_count == 0
    assert os.path.exists(out)
