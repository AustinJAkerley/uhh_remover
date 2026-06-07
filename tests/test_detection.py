"""Unit tests for filler detection (pure logic, no ffmpeg/provider)."""

from uhh_remover.config import FillerConfig
from uhh_remover.detection import detect_fillers, is_filler
from uhh_remover.models import Word


def test_default_matches_uh_um_and_elongations():
    cfg = FillerConfig()
    assert is_filler("uh", cfg)
    assert is_filler("um", cfg)
    assert is_filler("uhh", cfg)
    assert is_filler("uhhhh", cfg)
    assert is_filler("Ummm", cfg)
    assert is_filler("uh,", cfg)  # surrounding punctuation stripped
    assert not is_filler("under", cfg)
    assert not is_filler("hello", cfg)


def test_no_elongations_flag():
    cfg = FillerConfig(match_elongations=False)
    assert is_filler("uh", cfg)
    assert not is_filler("uhh", cfg)


def test_configurable_fillers():
    cfg = FillerConfig(fillers=["er", "hmm"])
    assert is_filler("er", cfg)
    assert is_filler("hmm", cfg)
    assert not is_filler("uh", cfg)  # uh not in this custom set


def test_extra_patterns():
    cfg = FillerConfig(fillers=[], extra_patterns=[r"you know"])
    assert is_filler("you know", cfg)


def test_detect_builds_padded_spans():
    cfg = FillerConfig(pad_start=0.05, pad_end=0.05, merge_gap=0.0)
    words = [
        Word("Hello", 0.0, 0.5),
        Word("uh", 1.0, 1.4),
        Word("world", 2.0, 2.5),
    ]
    spans = detect_fillers(words, cfg)
    assert len(spans) == 1
    assert abs(spans[0].start - 0.95) < 1e-6
    assert abs(spans[0].end - 1.45) < 1e-6


def test_min_duration_guard():
    cfg = FillerConfig(min_duration=0.2)
    words = [Word("uh", 1.0, 1.1)]  # only 0.1s long
    assert detect_fillers(words, cfg) == []


def test_max_duration_guard():
    cfg = FillerConfig(max_duration=1.0)
    words = [Word("uhhhhh", 1.0, 3.0)]  # 2s, exceeds max
    assert detect_fillers(words, cfg) == []


def test_merge_adjacent_fillers():
    cfg = FillerConfig(pad_start=0.0, pad_end=0.0, merge_gap=0.2)
    words = [
        Word("uh", 1.0, 1.3),
        Word("um", 1.4, 1.7),  # gap of 0.1 <= merge_gap
    ]
    spans = detect_fillers(words, cfg)
    assert len(spans) == 1
    assert abs(spans[0].start - 1.0) < 1e-6
    assert abs(spans[0].end - 1.7) < 1e-6


def test_spans_sorted_and_separate_when_far():
    cfg = FillerConfig(pad_start=0.0, pad_end=0.0, merge_gap=0.1)
    words = [
        Word("um", 5.0, 5.3),
        Word("uh", 1.0, 1.3),
    ]
    spans = detect_fillers(words, cfg)
    assert len(spans) == 2
    assert spans[0].start < spans[1].start
