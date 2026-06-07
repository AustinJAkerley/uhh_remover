"""Command-line interface for uhh_remover.

Examples:
    # Use AssemblyAI (reads ASSEMBLYAI_API_KEY from env), default fillers (uh, um):
    uhh-remover clean input.mp4 output.mp4

    # Wider catch-all and custom fillers:
    uhh-remover clean talk.mov clean.mov --fillers uh,um,er,hmm,like

    # Bring your own transcript (no provider call):
    uhh-remover clean input.mp4 out.mp4 --provider json --transcript words.json

    # Just show what would be cut:
    uhh-remover clean input.mp4 out.mp4 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .config import DEFAULT_FILLERS, FillerConfig
from .detection import detect_fillers
from .editor import clamp_spans
from .media import duration_seconds, has_audio_stream, has_video_stream, probe
from .pipeline import process
from .transcription import available_providers, get_transcriber


def _parse_fillers(value: Optional[str]) -> List[str]:
    if not value:
        return list(DEFAULT_FILLERS)
    return [v.strip() for v in value.split(",") if v.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uhh-remover",
        description="Seamlessly remove filler sounds (uh, um, uhh) from audio/video.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    clean = sub.add_parser("clean", help="Clean a media file.")
    clean.add_argument("input", help="Input video or audio file.")
    clean.add_argument("output", help="Output file path.")
    clean.add_argument(
        "--provider",
        default="assemblyai",
        choices=available_providers(),
        help="Transcription provider (default: assemblyai).",
    )
    clean.add_argument(
        "--api-key",
        default=None,
        help="Provider API key (else read from the provider's env var).",
    )
    clean.add_argument(
        "--transcript",
        default=None,
        help="Path to a transcript JSON (required for --provider json).",
    )
    clean.add_argument(
        "--fillers",
        default=None,
        help=f"Comma-separated filler words (default: {','.join(DEFAULT_FILLERS)}).",
    )
    clean.add_argument(
        "--no-elongations",
        action="store_true",
        help="Do not auto-match elongations (uh -> uhh, uhhh ...).",
    )
    clean.add_argument(
        "--min-duration",
        type=float,
        default=0.0,
        help="Ignore fillers shorter than this (seconds).",
    )
    clean.add_argument(
        "--max-duration",
        type=float,
        default=None,
        help="Ignore fillers longer than this (seconds).",
    )
    clean.add_argument(
        "--pad",
        type=float,
        default=0.02,
        help="Seconds trimmed on each side of a filler (default: 0.02).",
    )
    clean.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the cut list as JSON without writing output.",
    )
    return parser


def _make_config(args) -> FillerConfig:
    return FillerConfig(
        fillers=_parse_fillers(args.fillers),
        match_elongations=not args.no_elongations,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        pad_start=args.pad,
        pad_end=args.pad,
    )


def run_clean(args) -> int:
    config = _make_config(args)
    transcriber = get_transcriber(
        args.provider,
        api_key=args.api_key,
        transcript_path=args.transcript,
    )

    if args.dry_run:
        info = probe(args.input)
        if not has_audio_stream(info):
            print("Input has no audio stream; nothing to do.", file=sys.stderr)
            return 1
        words = transcriber.transcribe(args.input)
        spans = clamp_spans(detect_fillers(words, config), duration_seconds(info))
        print(
            json.dumps(
                {
                    "input": args.input,
                    "had_video": has_video_stream(info),
                    "removed_count": len(spans),
                    "removed_duration": round(sum(s.duration for s in spans), 3),
                    "spans": [
                        {
                            "start": round(s.start, 3),
                            "end": round(s.end, 3),
                            "text": s.text,
                        }
                        for s in spans
                    ],
                },
                indent=2,
            )
        )
        return 0

    result = process(args.input, args.output, transcriber, config)
    print(json.dumps(result.as_dict(), indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "clean":
        return run_clean(args)
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
