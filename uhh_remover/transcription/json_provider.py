"""JSON ("bring your own transcript") provider.

Reads word timings from a JSON file instead of calling a network provider. Useful for:
  * Re-running edits without paying for transcription again.
  * Integrating a different ASR system: just emit the JSON shape below.
  * Deterministic testing.

Accepted JSON shapes::

    {"words": [{"text": "uh", "start": 1.2, "end": 1.5}, ...]}

or a bare list::

    [{"text": "uh", "start": 1.2, "end": 1.5}, ...]

``start``/``end`` are seconds by default. If the values look like milliseconds (or the
top-level object sets ``"units": "ms"``) they are converted.
"""

from __future__ import annotations

import json
from typing import List

from ..models import Word
from .base import Transcriber


class JSONTranscriber(Transcriber):
    name = "json"

    def __init__(self, transcript_path: str):
        self.transcript_path = transcript_path

    def transcribe(self, media_path: str) -> List[Word]:  # media_path unused
        with open(self.transcript_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            raw_words = data.get("words", [])
            units = (data.get("units") or "s").lower()
        else:
            raw_words = data
            units = "s"

        if units not in ("s", "ms"):
            raise ValueError(
                f"Invalid 'units' {units!r} in transcript; expected 's' or 'ms'."
            )
        divisor = 1000.0 if units == "ms" else 1.0
        words: List[Word] = []
        for w in raw_words:
            if w.get("start") is None or w.get("end") is None:
                continue
            words.append(
                Word(
                    text=w.get("text", ""),
                    start=float(w["start"]) / divisor,
                    end=float(w["end"]) / divisor,
                )
            )
        return words
