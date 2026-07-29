"""Build or verify the canonical M7 image pipeline manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from game_predictor_worker.images.pipeline_contract import (
    ImagePipelineContractError,
    build_pipeline_envelope,
    current_pipeline_manifest,
    verify_manifest_artifacts,
)

DEFAULT_OUTPUT = Path("ai_docs/quality/m7-image-pipeline-manifest-v1.json")


def _document_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify without writing.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser


def main() -> int:
    args = _parser().parse_args()
    repository_root = args.repository_root.resolve()
    output = args.output
    if not output.is_absolute():
        output = repository_root / output

    try:
        manifest = current_pipeline_manifest()
        verify_manifest_artifacts(manifest, repository_root)
        expected = _document_bytes(build_pipeline_envelope(manifest))
    except ImagePipelineContractError as error:
        print(f"{error.code}: {error}")
        return 1

    if args.check:
        if not output.is_file():
            print(f"IMAGE_PIPELINE_MANIFEST_MISSING: {output}")
            return 1
        if output.read_bytes() != expected:
            print(f"IMAGE_PIPELINE_MANIFEST_DRIFT: {output}")
            return 1
        print(f"Image pipeline manifest is current: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(expected)
    print(f"Wrote image pipeline manifest: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
