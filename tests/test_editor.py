"""Unit tests for editor command building (pure, no ffmpeg execution)."""

from uhh_remover.editor import build_select_expr, clamp_spans, build_ffmpeg_command
from uhh_remover.models import FillerSpan


def test_build_select_expr():
    spans = [FillerSpan(1.0, 1.5), FillerSpan(3.0, 3.2)]
    expr = build_select_expr(spans)
    assert expr == "not(between(t,1.0000,1.5000)+between(t,3.0000,3.2000))"


def test_clamp_spans_drops_empty_and_clamps():
    spans = [
        FillerSpan(-1.0, 0.5),   # clamps start to 0
        FillerSpan(2.0, 100.0),  # clamps end to duration
        FillerSpan(4.0, 4.0005), # too small -> dropped
    ]
    out = clamp_spans(spans, duration=10.0)
    assert len(out) == 2
    assert out[0].start == 0.0
    assert out[1].end == 10.0


def test_command_includes_video_and_audio_filters():
    cmd = build_ffmpeg_command(
        "in.mp4", "out.mp4", [FillerSpan(1.0, 1.5)],
        has_video=True, has_audio=True,
    )
    joined = " ".join(cmd)
    assert "-vf" in cmd and "-af" in cmd
    assert "select=" in joined and "aselect=" in joined
    assert "libx264" in cmd


def test_command_audio_only_has_no_video_filter():
    cmd = build_ffmpeg_command(
        "in.wav", "out.wav", [FillerSpan(1.0, 1.5)],
        has_video=False, has_audio=True,
    )
    assert "-vf" not in cmd
    assert "-af" in cmd
    assert "libx264" not in cmd
