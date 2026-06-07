"""Configuration for filler detection.

Defaults are intentionally conservative: only ``uh`` / ``um`` (and their elongated
variants like ``uhh``, ``ummm``) are removed. Everything is overridable so callers can
opt into a wider catch-all (``like``, ``you know``, ``er``, ``hmm`` ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# Base filler words removed by default. Elongations (uhh, umm, uhhh ...) are handled
# automatically when ``match_elongations`` is True.
DEFAULT_FILLERS: List[str] = ["uh", "um"]


@dataclass
class FillerConfig:
    """Controls which words count as fillers and how aggressively they are cut.

    Attributes:
        fillers: Base filler words to remove (case-insensitive).
        match_elongations: If True, ``uh`` also matches ``uhh``/``uhhh``/``uuhh`` etc.
        extra_patterns: Raw regex patterns (fullmatch, case-insensitive) for advanced
            users who want to match things the base list can't express.
        min_duration: Ignore flagged words shorter than this (seconds). Guards against
            clipping a real word that happens to look like a filler.
        max_duration: If set, ignore flagged words longer than this (seconds).
        pad_start: Seconds of extra audio trimmed before each filler.
        pad_end: Seconds of extra audio trimmed after each filler.
        merge_gap: Merge two filler spans separated by a gap <= this (seconds) into one
            cut, avoiding a tiny sliver of audio between back-to-back fillers.
    """

    fillers: List[str] = field(default_factory=lambda: list(DEFAULT_FILLERS))
    match_elongations: bool = True
    extra_patterns: List[str] = field(default_factory=list)
    min_duration: float = 0.0
    max_duration: Optional[float] = None
    pad_start: float = 0.02
    pad_end: float = 0.02
    merge_gap: float = 0.15

    def normalized_fillers(self) -> List[str]:
        """Lower-cased, de-duplicated (order-preserving), non-empty filler list."""
        seen = set()
        result = []
        for f in self.fillers:
            f = (f or "").strip().lower()
            if f and f not in seen:
                seen.add(f)
                result.append(f)
        return result
