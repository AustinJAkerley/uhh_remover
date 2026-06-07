"""Transcriber interface."""

from __future__ import annotations

import abc
from typing import List

from ..models import Word


class Transcriber(abc.ABC):
    """Produces word-level timestamps for a media file.

    Implementations must include filler words (uh/um/...) in their output; many ASR
    systems strip them by default, so providers that expose a "disfluencies" option
    must enable it.
    """

    name: str = "base"

    @abc.abstractmethod
    def transcribe(self, media_path: str) -> List[Word]:
        """Return words with start/end times in seconds, in chronological order."""
        raise NotImplementedError
