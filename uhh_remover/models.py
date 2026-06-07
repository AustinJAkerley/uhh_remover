"""Core data types shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Word:
    """A single transcribed word with its timing (seconds)."""

    text: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class FillerSpan:
    """A time range (seconds) flagged for removal."""

    start: float
    end: float
    text: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class ProcessResult:
    """Summary returned after processing a file."""

    input_path: str
    output_path: str
    removed_spans: List[FillerSpan] = field(default_factory=list)
    source_duration: float = 0.0
    output_duration: float = 0.0
    had_video: bool = False

    @property
    def removed_count(self) -> int:
        return len(self.removed_spans)

    @property
    def removed_duration(self) -> float:
        return sum(s.duration for s in self.removed_spans)

    def as_dict(self) -> dict:
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "had_video": self.had_video,
            "removed_count": self.removed_count,
            "removed_duration": round(self.removed_duration, 3),
            "source_duration": round(self.source_duration, 3),
            "output_duration": round(self.output_duration, 3),
            "removed_spans": [
                {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text}
                for s in self.removed_spans
            ],
        }
