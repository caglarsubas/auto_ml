"""Explicit offline candidate scorer; run in the recorded Python/native environment."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from deployment import native_candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("input", type=Path)
    parser.add_argument("--export-sha256", required=True, help="Digest retained independently from the server export response")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--chunk-size", type=int, default=500)
    args = parser.parse_args()
    try:
        with args.export.open("rb") as stream:
            raw_export = stream.read(native_candidate.MAX_EXPORT_BYTES + 1)
        with args.input.open("rb") as stream:
            raw_input = stream.read(native_candidate.MAX_INPUT_BYTES + 1)
        result = native_candidate.score(raw_export, args.export_sha256, raw_input, chunk_size=args.chunk_size)
        # Never overwrite an earlier receipt or input/export through this CLI.
        with args.output.open("xb") as stream:
            stream.write(native_candidate.canonical(result))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Candidate scoring blocked: {exc}\n")


if __name__ == "__main__":
    main()
