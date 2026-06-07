"""AssemblyAI transcription provider.

AssemblyAI is a good fit because it can return *disfluencies* (uh, um, uhh, er, hmm)
inline with word-level timestamps - exactly what we need to cut fillers. We just turn
on ``disfluencies`` and read the per-word timings.

Docs: https://www.assemblyai.com/docs/
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

from ..models import Word
from .base import Transcriber

API_BASE = "https://api.assemblyai.com/v2"
_POLL_INTERVAL = 3.0
_UPLOAD_CHUNK = 5 * 1024 * 1024


class AssemblyAITranscriber(Transcriber):
    """Transcribe via AssemblyAI, keeping filler words."""

    name = "assemblyai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        timeout: float = 1800.0,
        poll_interval: float = _POLL_INTERVAL,
    ):
        self.api_key = api_key or os.environ.get("ASSEMBLYAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "AssemblyAI API key missing. Pass api_key= or set ASSEMBLYAI_API_KEY."
            )
        self.timeout = timeout
        self.poll_interval = poll_interval

    # -- internal helpers ---------------------------------------------------

    def _session(self):
        try:
            import requests  # imported lazily so the package works without it
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "The 'requests' package is required for the AssemblyAI provider. "
                "Install it with: pip install requests"
            ) from exc
        s = requests.Session()
        s.headers.update({"authorization": self.api_key})
        return s

    def _upload(self, session, media_path: str) -> str:
        def gen():
            with open(media_path, "rb") as f:
                while True:
                    data = f.read(_UPLOAD_CHUNK)
                    if not data:
                        break
                    yield data

        resp = session.post(f"{API_BASE}/upload", data=gen())
        resp.raise_for_status()
        return resp.json()["upload_url"]

    # -- public API ---------------------------------------------------------

    def transcribe(self, media_path: str) -> List[Word]:
        session = self._session()
        upload_url = self._upload(session, media_path)

        create = session.post(
            f"{API_BASE}/transcript",
            json={
                "audio_url": upload_url,
                "disfluencies": True,  # keep uh/um/uhh in the transcript
                "punctuate": True,
                "format_text": False,
            },
        )
        create.raise_for_status()
        transcript_id = create.json()["id"]

        deadline = time.monotonic() + self.timeout
        poll_url = f"{API_BASE}/transcript/{transcript_id}"
        while True:
            status_resp = session.get(poll_url)
            status_resp.raise_for_status()
            payload = status_resp.json()
            status = payload.get("status")
            if status == "completed":
                return self._parse_words(payload)
            if status == "error":
                raise RuntimeError(
                    f"AssemblyAI transcription failed: {payload.get('error')}"
                )
            if time.monotonic() > deadline:
                raise TimeoutError("AssemblyAI transcription timed out.")
            time.sleep(self.poll_interval)

    @staticmethod
    def _parse_words(payload: dict) -> List[Word]:
        words: List[Word] = []
        for w in payload.get("words") or []:
            text = w.get("text", "")
            start = w.get("start")
            end = w.get("end")
            if start is None or end is None:
                continue
            # AssemblyAI timestamps are milliseconds.
            words.append(Word(text=text, start=start / 1000.0, end=end / 1000.0))
        return words
