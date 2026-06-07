"""uhh_remover - seamlessly remove filler sounds (uh, um, uhh) from audio/video.

Video-first: the same pipeline cleans audio-only files as a byproduct.

High level flow:
    transcribe (provider) -> detect fillers (configurable) -> edit (ffmpeg) -> output
"""

from .config import FillerConfig, DEFAULT_FILLERS
from .models import Word, FillerSpan, ProcessResult
from .pipeline import process

__all__ = [
    "FillerConfig",
    "DEFAULT_FILLERS",
    "Word",
    "FillerSpan",
    "ProcessResult",
    "process",
    "__version__",
]

__version__ = "0.1.0"
