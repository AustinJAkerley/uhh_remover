"""Provider registry / factory."""

from __future__ import annotations

from typing import List, Optional

from .assemblyai import AssemblyAITranscriber
from .base import Transcriber
from .json_provider import JSONTranscriber


def available_providers() -> List[str]:
    return ["assemblyai", "json"]


def get_transcriber(
    provider: str,
    *,
    api_key: Optional[str] = None,
    transcript_path: Optional[str] = None,
) -> Transcriber:
    """Construct a transcriber by name.

    Args:
        provider: One of :func:`available_providers`.
        api_key: API key for network providers (or read from env).
        transcript_path: Path to a transcript JSON (required for the ``json`` provider).
    """
    provider = (provider or "").strip().lower()
    if provider == "assemblyai":
        return AssemblyAITranscriber(api_key=api_key)
    if provider == "json":
        if not transcript_path:
            raise ValueError("The 'json' provider requires transcript_path.")
        return JSONTranscriber(transcript_path)
    raise ValueError(
        f"Unknown provider '{provider}'. Available: {', '.join(available_providers())}"
    )
