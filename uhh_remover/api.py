"""Minimal web platform / API for uhh_remover.

Auto one-shot: upload a file, we process it in the background and you download the
result. Jobs and files are persisted to disk and kept indefinitely ("forever" retention)
- nothing is auto-deleted.

Run with:
    pip install -r requirements.txt
    uvicorn uhh_remover.api:app --reload

This is intentionally simple (in-process background tasks + a JSON job index). For
production scale, swap the background task for a real queue (Celery/RQ) and the local
disk for object storage - see STRAT.md.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from typing import List, Optional

from .config import FillerConfig
from .pipeline import process
from .transcription import get_transcriber

try:
    from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.responses import FileResponse, JSONResponse
except ImportError as exc:  # pragma: no cover - import guard
    raise RuntimeError(
        "FastAPI is required for the API. Install it with: pip install -r requirements.txt"
    ) from exc


DATA_DIR = os.environ.get("UHH_DATA_DIR", os.path.abspath("./uhh_data"))
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
_INDEX_LOCK = threading.Lock()

# Output containers we allow. The chosen format is validated against this fixed allowlist
# before it is ever used to build a path, so user input can never influence the
# filesystem path (no path injection / traversal). Uploaded inputs are stored under a
# fixed name; ffmpeg detects the input format from the content, not the extension.
ALLOWED_FORMATS = {
    "mp4", "mov", "mkv", "webm", "avi",  # video
    "wav", "mp3", "m4a", "aac", "flac", "ogg",  # audio
}
_DISPLAY_NAME = re.compile(r"[^A-Za-z0-9._ -]")


def _display_name(name: Optional[str]) -> str:
    """A human-friendly, harmless label for the upload (metadata only, never a path)."""
    base = os.path.basename(name or "")
    base = _DISPLAY_NAME.sub("_", base).strip().lstrip(".")
    return base or "input"



app = FastAPI(title="uhh_remover", version="0.1.0")

# Job IDs are uuid4().hex (32 lowercase hex chars). Validating against this fixed pattern
# before using a job id in any filesystem path prevents path traversal via the URL.
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _validate_job_id(job_id: str) -> str:
    if not _JOB_ID_RE.match(job_id or ""):
        raise HTTPException(status_code=404, detail="Job not found")
    return job_id


def _safe_job_path(job_id: str, *parts: str) -> Optional[str]:
    """Resolve a path inside a job directory, or None if it escapes JOBS_DIR.

    Normalizes the full path and verifies it stays within JOBS_DIR, defeating any
    path-traversal attempt from a crafted ``job_id`` (e.g. ``../../etc/passwd``).
    """
    base = os.path.realpath(JOBS_DIR)
    resolved = os.path.realpath(os.path.join(base, job_id, *parts))
    if os.path.commonpath([base, resolved]) != base:
        return None
    return resolved


def _job_dir(job_id: str) -> str:
    return os.path.join(JOBS_DIR, _validate_job_id(job_id))


def _meta_path(job_id: str) -> str:
    return os.path.join(_job_dir(job_id), "job.json")


def _read_meta(job_id: str) -> Optional[dict]:
    if not _JOB_ID_RE.fullmatch(job_id or ""):
        return None
    path = _safe_job_path(job_id, "job.json")
    if path is None or not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_meta(job_id: str, meta: dict) -> None:
    os.makedirs(_job_dir(job_id), exist_ok=True)
    with _INDEX_LOCK:
        with open(_meta_path(job_id), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)


def _run_job(
    job_id: str,
    input_path: str,
    output_path: str,
    config: FillerConfig,
    provider: str,
    api_key: Optional[str],
) -> None:
    meta = _read_meta(job_id) or {}
    try:
        meta["status"] = "processing"
        _write_meta(job_id, meta)

        transcriber = get_transcriber(provider, api_key=api_key)
        result = process(input_path, output_path, transcriber, config)

        meta["status"] = "done"
        meta["result"] = result.as_dict()
        _write_meta(job_id, meta)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the client
        meta["status"] = "failed"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        _write_meta(job_id, meta)


@app.post("/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    fillers: Optional[str] = Form(None),
    provider: str = Form("assemblyai"),
    output_format: str = Form("mp4"),
):
    output_format = (output_format or "mp4").strip().lower().lstrip(".")
    if output_format not in ALLOWED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported output_format. Allowed: {sorted(ALLOWED_FORMATS)}",
        )

    job_id = uuid.uuid4().hex
    jdir = _job_dir(job_id)
    os.makedirs(jdir, exist_ok=True)

    # Fixed, non-user-derived filenames inside a per-job UUID directory. ffmpeg detects
    # the input container from its content, so the input needs no real extension.
    display_name = _display_name(file.filename)
    input_path = os.path.join(jdir, "input.bin")
    with open(input_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)

    output_path = os.path.join(jdir, f"output.{output_format}")

    filler_list: Optional[List[str]] = (
        [f.strip() for f in fillers.split(",") if f.strip()] if fillers else None
    )
    config = FillerConfig(fillers=filler_list) if filler_list else FillerConfig()

    meta = {
        "id": job_id,
        "status": "queued",
        "filename": display_name,
        "output_format": output_format,
        "input_path": input_path,
        "output_path": output_path,
        "provider": provider,
    }
    _write_meta(job_id, meta)

    background_tasks.add_task(
        _run_job,
        job_id,
        input_path,
        output_path,
        config,
        provider,
        os.environ.get("ASSEMBLYAI_API_KEY"),
    )
    return JSONResponse({"id": job_id, "status": "queued"}, status_code=202)


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    meta = _read_meta(job_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Job not found")
    public = {k: v for k, v in meta.items() if k not in ("input_path", "output_path")}
    return public


@app.get("/jobs/{job_id}/result")
def get_result(job_id: str):
    meta = _read_meta(job_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if meta.get("status") != "done":
        raise HTTPException(status_code=409, detail=f"Job is {meta.get('status')}")
    output_path = meta.get("output_path")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Result file missing")
    return FileResponse(output_path, filename=f"cleaned_{meta.get('filename')}")
