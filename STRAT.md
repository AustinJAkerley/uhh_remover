# STRAT.md — "uhh_remover" Strategy

Goal: A user uploads a **video** or **audio-only** file to our web platform / API, we detect
filler sounds ("uh", "uhh", "um", "er", "ah", elongated "uhhhh", etc.) and remove them
**seamlessly**, then return a cleaned file.

This document describes the approach I plan to try **first** (the MVP), plus a ranked list of
**fallback / "level-up" strategies** we can layer in if the output quality isn't good enough.

---

## 0. Locked-in decisions & current MVP status

Decisions for this build:
- **Filler scope:** configurable; **default = `uh`, `um`** plus their elongations (`uhh`,
  `ummm`, …). Callers can widen to a catch-all (`er`, `hmm`, `like`, `you know`).
- **Mode:** **auto one-shot** — no preview/approval step in the default flow.
- **Footage:** **arbitrary** — must work on any input, not just talking-head.
- **ML:** use a **provider**, not our own model. MVP uses **AssemblyAI** (`disfluencies`
  on) for word-level filler timestamps. Any other ASR can be plugged in via the `json`
  provider. Cost is acceptable / billable to customers.
- **Retention:** **forever** — uploaded media and results are not auto-deleted.
- **Target:** **video-first** working MVP; audio-only is a byproduct of the same pipeline.

**What's built now (MVP):** `transcribe (AssemblyAI) → detect (configurable) → edit
(ffmpeg)`. The editor uses ffmpeg `select`/`aselect` to drop filler time-ranges from video
**and** audio together and re-stamp timestamps, so output stays in sync on any footage
(the **Tier 0** hard cut below). Ships as a Python package, a `uhh-remover` CLI, and a
FastAPI service. The video "seamlessness" upgrades (Tiers 1–4) remain the roadmap if the
hard cut isn't good enough.

---

## 1. The core problem, broken down

Removing an "uhh" is really three sub-problems:

1. **Detection** — find the exact start/end timestamps of every filler.
2. **Editing** — remove those spans without introducing audible clicks or visible jumps.
3. **Delivery** — do it all in an async, scalable web/API pipeline.

The detection problem is shared between audio and video. The *editing* problem is where audio
and video diverge sharply: audio editing is mostly solved; **video is the hard part** because
cutting time out of a clip creates a visible "jump cut."

---

## 2. Detection strategy (shared by audio + video)

This is the foundation — get this right and everything downstream gets easier.

### Primary approach: ASR + forced alignment + filler classification

1. **Demux audio** from the upload with `ffmpeg` → mono 16 kHz WAV for analysis (we keep the
   original high-quality audio/video untouched for the final render).
2. **Transcribe with word-level timestamps.** Use **WhisperX** (faster-whisper backend +
   wav2vec2 forced alignment). WhisperX gives accurate per-word `start`/`end` times, which is
   exactly what we need to make tight cuts.
3. **The catch:** vanilla Whisper *deletes* most fillers from its transcript (it's trained to
   produce clean text), so we can't rely on the transcript alone. We combine signals:
   - **Lexical fillers** that Whisper *does* emit ("um", "uh", "you know", "like", "so").
   - **A dedicated disfluency detector** for the rest. Options: a fine-tuned token classifier
     for disfluencies, or an acoustic model that flags non-lexical vocalizations.
   - **Acoustic heuristics for elongated "uhhhh"** — a filler is typically a sustained,
     low-energy, near-monotone vowel with flat pitch and long duration sitting between two
     silences. We can flag word-aligned segments matching that profile (long duration,
     stable F0, vowel-like formants) as candidates.
4. **Build a cut list**: a list of `(start, end)` spans flagged as filler, with a small
   confidence score each.
5. **Pad & snap to silence/zero-crossings.** Expand each span slightly to the nearest
   surrounding silence and snap cut points to audio zero-crossings to avoid clicks.

### Knobs we expose to the user
- **Aggressiveness** (conservative → aggressive): only cut high-confidence "uhh", vs. also cut
  "um / like / you know".
- **Min filler duration** (e.g., ignore <120 ms blips).
- **Preview mode**: return the cut list / a marked-up transcript so the user can approve before
  we render. Hugely reduces "it cut a word I wanted" complaints.

---

## 3. Audio-only editing strategy

This is the easier case and we can ship it first.

### Primary approach: remove + crossfade (NOT just silence)
For each filler span:
1. **Delete the span entirely** (shorten the timeline) rather than muting it — a muted gap
   leaves an unnatural pause where the "uhh" used to be.
2. **Equal-power crossfade** (~10–30 ms) across the join so there's no click/pop.
3. **Snap cuts to zero-crossings** and respect the noise floor.

### On "replace with background mic noise" (your idea)
You're right that a hard digital-silence cut sounds unnatural — real recordings have a constant
**room tone** (the mic's background hiss/ambience), and a sudden gap of *true* silence is
jarring. Two ways to use this:

- **(Preferred) Remove the filler, then bridge the join with a tiny slice of room tone** so the
  transition floor matches the rest of the track. This keeps speech tight *and* natural.
- **(Your literal idea) Replace the filler in-place with room tone** (same length). This keeps
  the original timing/pacing but does **not** shorten the clip — useful if we must preserve
  exact duration (e.g., to stay in sync with a fixed video track we don't want to re-cut).

**Room-tone extraction:** automatically sample the quietest inter-speech gaps to build a short
noise profile, then loop/granulate it (with randomization to avoid an obvious repeating loop) to
generate bridge audio that matches *this specific recording*.

### Nice-to-haves later
- Light **de-click / de-breath** pass for breaths left adjacent to removed fillers.
- Optional **loudness normalization** (EBU R128) on the final render.

---

## 4. Video editing strategy (the tricky part)

When we cut time out of the audio, the video frames over that span must go too — which produces a
**jump cut**: the speaker's head/hands teleport. Our job is to hide that. Strategies, from
cheapest/fastest to most advanced:

### Tier 0 — Plain jump cut (baseline, ship-it MVP)
Cut audio + video together, re-mux. Fast, perfectly in sync, zero AI. Looks fine when the speaker
is fairly still; looks janky when they move a lot. This is our correctness baseline.

### Tier 1 — Short dissolve / crossfade over the cut
Apply a 2–5 frame cross-dissolve at each join. Cheap (ffmpeg/OpenCV), and it noticeably softens
the jump. Often "good enough" for talking-head content.

### Tier 2 — "Invisible cut" tricks (the YouTuber playbook)
- **Punch-in zoom:** at each cut, briefly scale the frame ~5–10%. The change in framing masks the
  positional jump — this is the single highest bang-for-buck trick for talking-head video.
- **Auto B-roll / cutaway:** overlay a held still or supplied b-roll across the cut.
- **Background stabilization:** if the camera is static, stabilize so only the subject moves; the
  jump becomes much less noticeable, especially with a Tier 1 dissolve on top.

### Tier 3 — AI frame interpolation (morph across the cut)
Use a frame-interpolation model (**RIFE**, **FILM**) to synthesize a few transition frames
between the last pre-cut frame and the first post-cut frame, producing a smooth morph instead of
a hard jump. Works well for small motions, can warp on large pose changes.

### Tier 4 — Generative talking-head reconstruction (the "seamless" dream)
Use a face/lip generative model to **synthesize a bridge** of the speaker's face that continues
naturally across the cut (lip-sync driven by the *cleaned* audio, e.g. Wav2Lip-style, or a video
diffusion / portrait-animation model). This is the closest to truly "seamless," but it's the most
expensive, GPU-heavy, slowest, and most prone to uncanny artifacts. Reserve for premium tier.

### Recommended video path
Ship **Tier 0** for correctness, immediately add **Tier 1 + Tier 2 punch-in** as the default
(best quality-per-compute), and treat **Tier 3/4** as opt-in "enhance" modes we evaluate against
real footage.

---

## 5. Reassembly & quality

- Render edits against the **original full-quality** media (not the 16 kHz analysis copy).
- Keep audio/video **frame-accurate in sync** — derive video cuts from the same cut list as
  audio, snapped to frame boundaries.
- Preserve original container/codec/bitrate where possible; re-encode only what we touch.
- **QC pass:** report number of fillers removed, total time saved, and (optionally) a
  before/after waveform + the marked transcript.

---

## 6. Platform / API architecture

Processing is slow and may need a GPU, so everything is **asynchronous**.

```
Client ──upload──▶ API (FastAPI)
                     │  create job, store file in object storage (S3/GCS)
                     ▼
                  Job queue (Redis + Celery/RQ)
                     │
                     ▼
                  Worker (GPU-capable): ffmpeg + WhisperX + editor
                     │  writes result to object storage
                     ▼
Client ◀──poll/webhook── status ──▶ download signed URL
```

- **API endpoints (sketch):**
  - `POST /jobs` — upload media + options (aggressiveness, video tier, preview-only). Returns `job_id`.
  - `GET /jobs/{id}` — status: `queued | processing | needs_review | done | failed`.
  - `GET /jobs/{id}/cutlist` — the proposed cuts / marked transcript (for preview/approval).
  - `POST /jobs/{id}/render` — approve cut list and render final.
  - `GET /jobs/{id}/result` — signed download URL.
- **Concerns to design for:** large uploads (chunked/resumable), file-size & duration limits,
  job timeouts, GPU autoscaling, cost controls, retention/auto-deletion of user media (privacy),
  and abuse/format validation.

### Suggested build order (milestones)
1. **M1 — Audio-only CLI:** ffmpeg + WhisperX detection + remove/crossfade + room-tone bridge.
2. **M2 — Wrap in API** with async job queue + storage + preview cut list.
3. **M3 — Video Tier 0/1/2** (jump cut → dissolve → punch-in).
4. **M4 — Quality dial-up:** Tier 3 interpolation, then evaluate Tier 4 generative.
5. **M5 — Web front-end** (upload, preview/approve, download).

---

## 7. Open questions for you
- **Filler scope:** just "uh/um/uhh", or also "like / you know / so / I mean"?
- **Preview/approval step**, or fully automatic one-shot?
- **Target content:** mostly talking-head/podcast, or arbitrary footage? (Heavily affects how
  hard the video case is.)
- **Quality vs. speed/cost** target, and is a **GPU** budget available for Tier 3/4?
- **Privacy:** how long may we retain uploaded media?

---

## 8. TL;DR recommendation
Build the **audio pipeline first** (WhisperX detection → remove + crossfade + room-tone bridge) —
it's high-value and shippable quickly. For **video**, start with a clean jump cut, then default to
**short dissolve + punch-in zoom** (cheap and surprisingly seamless), and only invest in
AI interpolation / generative face synthesis if the simpler tricks aren't good enough on real
footage.
