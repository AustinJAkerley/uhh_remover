"""Transcription providers.

A provider turns a media file into a list of :class:`~uhh_remover.models.Word` with
timestamps. We deliberately rely on an external provider for the ML-heavy work instead
of hosting our own model.
"""

from .base import Transcriber
from .assemblyai import AssemblyAITranscriber
from .json_provider import JSONTranscriber
from .registry import get_transcriber, available_providers

__all__ = [
    "Transcriber",
    "AssemblyAITranscriber",
    "JSONTranscriber",
    "get_transcriber",
    "available_providers",
]
