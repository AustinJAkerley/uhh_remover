"""Filler detection: turn a transcript (list of Words) into cut spans.

Pure logic, no I/O, no ffmpeg - so it is fully unit-testable.
"""

from __future__ import annotations

import re
from typing import List

from .config import FillerConfig
from .models import FillerSpan, Word


def _normalize(text: str) -> str:
    """Lower-case and strip surrounding punctuation/whitespace from a token."""
    return re.sub(r"^\W+|\W+$", "", (text or "").strip().lower())


def _elongate_pattern(word: str) -> str:
    """Build a regex that matches a word and its elongations.

    "uh" -> "u+h+"  (matches uh, uhh, uhhh, uuhh, ...)
    "um" -> "u+m+"
    Repeated identical letters collapse into a single ``+`` group.
    """
    out = []
    for ch in word:
        esc = re.escape(ch)
        if out and out[-1] == esc + "+":
            continue  # collapse consecutive duplicates: "uhh" -> u+h+
        out.append(esc + "+")
    return "".join(out)


def build_matcher(config: FillerConfig):
    """Compile a single case-insensitive regex that fullmatches any filler token."""
    patterns: List[str] = []
    for word in config.normalized_fillers():
        if config.match_elongations:
            patterns.append(_elongate_pattern(word))
        else:
            patterns.append(re.escape(word))
    patterns.extend(p for p in config.extra_patterns if p)

    if not patterns:
        # Match nothing.
        return re.compile(r"(?!x)x")
    combined = "|".join(f"(?:{p})" for p in patterns)
    return re.compile(f"^(?:{combined})$", re.IGNORECASE)


def is_filler(text: str, config: FillerConfig) -> bool:
    """True if ``text`` (a single token) is a filler under ``config``."""
    token = _normalize(text)
    if not token:
        return False
    return build_matcher(config).match(token) is not None


def detect_fillers(words: List[Word], config: FillerConfig) -> List[FillerSpan]:
    """Return merged, padded cut spans for every filler word in ``words``.

    Steps:
      1. Match each word against the (possibly elongated) filler set.
      2. Apply min/max duration guards.
      3. Pad each span and clamp at 0.
      4. Merge spans that overlap or are within ``merge_gap`` of each other.
    """
    matcher = build_matcher(config)
    raw: List[FillerSpan] = []
    for w in words:
        token = _normalize(w.text)
        if not token or not matcher.match(token):
            continue
        dur = w.duration
        if dur < config.min_duration:
            continue
        if config.max_duration is not None and dur > config.max_duration:
            continue
        start = max(0.0, w.start - config.pad_start)
        end = w.end + config.pad_end
        raw.append(FillerSpan(start=start, end=end, text=token))

    return _merge_spans(raw, config.merge_gap)


def _merge_spans(spans: List[FillerSpan], merge_gap: float) -> List[FillerSpan]:
    if not spans:
        return []
    spans = sorted(spans, key=lambda s: s.start)
    merged: List[FillerSpan] = [
        FillerSpan(spans[0].start, spans[0].end, spans[0].text)
    ]
    for s in spans[1:]:
        last = merged[-1]
        if s.start <= last.end + merge_gap:
            last.end = max(last.end, s.end)
            last.text = (last.text + " " + s.text).strip()
        else:
            merged.append(FillerSpan(s.start, s.end, s.text))
    return merged
