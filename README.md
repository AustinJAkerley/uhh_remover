# uhh_remover

Seamlessly remove filler sounds — **uh**, **um**, **uhh** (and friends) — from **video**
and **audio** files. Upload a file (CLI or API), get back a cleaned one.

Video-first: the same pipeline cleans audio-only files as a byproduct.

> See [`STRAT.md`](./STRAT.md) for the full strategy, the video "seamlessness" tiers, and
> the roadmap.

## How it works

```
transcribe (AI provider) ─▶ detect fillers (configurable) ─▶ edit (ffmpeg) ─▶ output
```

1. **Transcribe** with a provider that keeps filler words and gives word-level
   timestamps. We use **[AssemblyAI](https://www.assemblyai.com/)** with its
   `disfluencies` option (returns `uh`/`um`/`uhh`/… inline). We rely on a provider for
   the ML rather than hosting our own model; you can swap in any ASR via the `json`
   provider.
2. **Detect** which words are fillers. Configurable; defaults to `uh`/`um` plus their
   elongations (`uhh`, `ummm`, …).
3. **Edit** with `ffmpeg`: the filler time-ranges are dropped from the video *and* audio
   together and timestamps re-stamped, so the result stays perfectly in sync on
   arbitrary footage. (This is the reliable hard-cut baseline; softer/AI joins are the
   next tiers in `STRAT.md`.)

## Requirements

- Python 3.9+
- **ffmpeg** on your `PATH` (provides `ffmpeg` and `ffprobe`)
- An AssemblyAI API key in `ASSEMBLYAI_API_KEY` (only for the `assemblyai` provider)

```bash
pip install -r requirements.txt   # or: pip install -e .[api,test]
```

## CLI

```bash
export ASSEMBLYAI_API_KEY=...

# Clean a video (default fillers: uh, um + elongations):
uhh-remover clean input.mp4 output.mp4

# Audio works the same way:
uhh-remover clean podcast.wav clean.wav

# Wider catch-all:
uhh-remover clean talk.mov clean.mov --fillers uh,um,er,hmm,like

# Preview the cut list without rendering:
uhh-remover clean input.mp4 out.mp4 --dry-run

# Bring your own transcript (no provider call / no API cost):
uhh-remover clean input.mp4 out.mp4 --provider json --transcript words.json
```

Useful flags: `--no-elongations`, `--min-duration`, `--max-duration`, `--pad`.

### Bring-your-own-transcript JSON

```json
{ "words": [ {"text": "uh", "start": 1.2, "end": 1.5}, {"text": "hello", "start": 1.6, "end": 2.0} ] }
```

`start`/`end` are seconds (use `"units": "ms"` for milliseconds).

## API (web platform)

Auto one-shot: upload, we process in the background, you download. Jobs/files are kept
indefinitely (nothing is auto-deleted).

```bash
pip install -r requirements.txt
uvicorn uhh_remover.api:app --reload
```

| Method | Path                 | Description                                   |
| ------ | -------------------- | --------------------------------------------- |
| POST   | `/jobs`              | Upload `file` (+ optional `fillers`). Returns `id`. |
| GET    | `/jobs/{id}`         | Job status (`queued`/`processing`/`done`/`failed`) + result summary. |
| GET    | `/jobs/{id}/result`  | Download the cleaned file (when `done`).      |

```bash
curl -F file=@input.mp4 http://localhost:8000/jobs           # -> {"id": "..."}
curl http://localhost:8000/jobs/<id>                          # poll status
curl -OJ http://localhost:8000/jobs/<id>/result               # download
```

The MVP API uses in-process background tasks + local disk. For scale, swap in a real
queue and object storage (see `STRAT.md`).

## Testing

```bash
python -m pytest
```

Detection/editor tests are pure-Python; the end-to-end test generates a synthetic clip
with ffmpeg and is skipped automatically if ffmpeg isn't installed.

## Layout

```
uhh_remover/
  config.py            filler configuration (defaults: uh, um + elongations)
  detection.py         transcript -> cut spans (pure, tested)
  editor.py            ffmpeg removal keeping A/V in sync
  media.py             ffprobe helpers
  pipeline.py          transcribe -> detect -> edit
  cli.py               `uhh-remover` command
  api.py               FastAPI platform
  transcription/       provider abstraction (assemblyai, json)
```
