"""Freeze and verify the inventory of a local-only v7 evaluation corpus."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "worker" / "src"))

from game_predictor_worker.semi_automatic_selection.v7_configuration import (  # noqa: E402
    load_v7_corpus_manifest,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path)
    parser.add_argument("--inventory-output", type=Path)
    return parser.parse_args()


def _canonical_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        + b"\n"
    )


def main() -> int:
    args = _arguments()
    manifest = load_v7_corpus_manifest(args.manifest)
    if args.corpus_root is not None:
        manifest = replace(manifest, corpus_root=args.corpus_root)
    payload = {
        "cases": [item.as_dict() for item in manifest.freeze_inventory()],
        "manifestFingerprint": manifest.fingerprint(),
        "schemaVersion": 1,
    }
    content = _canonical_bytes(payload)
    if args.inventory_output is not None:
        target = args.inventory_output.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != content:
            raise RuntimeError(
                "Frozen corpus inventory differs; create a new review artifact instead."
            )
        if not target.exists():
            target.write_bytes(content)
    print(content.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
