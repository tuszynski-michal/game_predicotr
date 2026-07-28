"""Create or verify a deterministic source-image discovery manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.discovery import (  # noqa: E402
    ImageDiscoveryError,
    discover_images,
    known_checksums_from_manifest,
    select_unseen_images,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--known-manifest", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that --output already contains the deterministic result.",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="Return exit code 1 when an image-like source has a discovery issue.",
    )
    return parser.parse_args()


def _validate_output_path(source_root: Path, output: Path) -> Path:
    root = source_root.resolve(strict=True)
    resolved_output = output.resolve()
    if resolved_output.is_relative_to(root):
        raise ImageDiscoveryError(
            "IMAGE_DISCOVERY_OUTPUT_IN_SOURCE",
            "Discovery output must be stored outside the read-only source root.",
        )
    return resolved_output


def _write_atomic(output: Path, content: bytes) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(output)


def main() -> int:
    args = _parse_args()
    try:
        manifest = discover_images(args.source_root)
        content = manifest.to_json_bytes()
        known_checksums = (
            known_checksums_from_manifest(args.known_manifest)
            if args.known_manifest is not None
            else frozenset()
        )
        unseen = select_unseen_images(manifest, known_checksums)
        if args.check and args.output is None:
            raise ImageDiscoveryError(
                "IMAGE_DISCOVERY_CHECK_OUTPUT_REQUIRED",
                "--check requires --output.",
            )
        if args.output is None:
            sys.stdout.buffer.write(content)
        else:
            output = _validate_output_path(args.source_root, args.output)
            if args.check:
                try:
                    existing = output.read_bytes()
                except OSError as error:
                    raise ImageDiscoveryError(
                        "IMAGE_DISCOVERY_MANIFEST_MISSING",
                        "Expected discovery manifest cannot be read.",
                    ) from error
                if existing != content:
                    raise ImageDiscoveryError(
                        "IMAGE_DISCOVERY_MANIFEST_DRIFT",
                        "Discovery manifest differs from the current source folder.",
                    )
            else:
                _write_atomic(output, content)
            print(
                json.dumps(
                    {
                        "discoveryManifestSha256": hashlib.sha256(content).hexdigest(),
                        "duplicateFileCount": manifest.duplicate_file_count,
                        "issueCount": len(manifest.issues),
                        "knownImageCount": len(manifest.images) - len(unseen),
                        "sourceFileCount": manifest.source_file_count,
                        "status": "clean" if not manifest.issues else "issues",
                        "uniqueImageCount": len(manifest.images),
                        "unseenImageCount": len(unseen),
                    },
                    sort_keys=True,
                )
            )
        if args.require_clean and manifest.issues:
            return 1
        return 0
    except ImageDiscoveryError as error:
        print(
            json.dumps(
                {"code": error.code, "message": str(error), "status": "failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
