"""Make byte-exact copies of only the ten pinned calibration preview sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    build_local_source_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".claude" / "v7-pilot-runtime"
PLAN = RUNTIME / "reports" / "r3-real-ocr-preview-plan-rev118.json"
PLAN_FILE_SHA = "16462a15d503d9cb58227c872017ec0be49c761ddfb03c480dbbe2526029122d"
PLAN_SHA = "a00f797e1c1150c0f25863be44ea60c736cecc69acfe8551f2e4564f6e4f0ff9"


def prepare(*, copy: bool) -> dict[str, object]:
    content = PLAN.read_bytes()
    if hashlib.sha256(content).hexdigest() != PLAN_FILE_SHA:
        raise ValueError("The reviewed ten-source plan changed.")
    envelope = json.loads(content)
    plan = envelope["plan"]
    # The historical preview plan uses literal UTF-8 in its canonical checksum.
    canonical = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if (
        hashlib.sha256(canonical).hexdigest() != PLAN_SHA
        or envelope["planChecksumSha256"] != PLAN_SHA
    ):
        raise ValueError("The canonical reviewed plan checksum changed.")
    sources = plan["sources"]
    if len(sources) != 10 or {item["previewIndex"] for item in sources} != set(range(10)):
        raise ValueError("Fixture preparation is bounded to the reviewed ten sources.")
    fixtures = RUNTIME / "fixtures"
    proofs: list[dict[str, object]] = []
    for item in sources:
        index = item["previewIndex"]
        if item["split"] != "calibration" or item["sourceGameRef"] != "777":
            raise ValueError("Only reviewed calibration sources are permitted.")
        source = Path(item["actualPath"])
        before = source.stat()
        data = source.read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        if checksum != item["sourceChecksumSha256"] or len(data) != item["sizeBytes"]:
            raise ValueError("A reviewed source changed before the exact-copy test.")
        name = "B" if index < 6 else f"A{index - 6}"
        target = fixtures / name / source.name
        if copy:
            _require_task_path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.read_bytes() != data:
                    raise ValueError("An existing fixture differs; refuse overwrite.")
            else:
                with target.open("xb") as output:
                    output.write(data)
            if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
                raise ValueError("Fixture copy is not byte-exact.")
        after = source.stat()
        if (
            before.st_mtime_ns != after.st_mtime_ns
            or before.st_size != after.st_size
            or hashlib.sha256(source.read_bytes()).hexdigest() != checksum
        ):
            raise ValueError("The original changed during fixture preparation.")
        proofs.append(
            {
                "previewIndex": index,
                "sourceId": item["sourceId"],
                "sourceChecksumSha256": checksum,
                "originalPath": str(source),
                "copyPath": str(target),
                "fixture": name,
                "originalMtimeNs": before.st_mtime_ns,
                "sizeBytes": len(data),
            }
        )
    bindings: list[dict[str, object]] = []
    if copy:
        for name in ("A0", "A1", "A2", "A3", "B"):
            path = (fixtures / name).resolve(strict=True)
            manifest = build_local_source_manifest(path, selection_id=uuid4(), display_name=name)
            bindings.append(
                {
                    "sourceRoot": str(path),
                    "sourceFingerprint": manifest.source_fingerprint,
                    "sourceGameRef": "777",
                    "geometryFamilyId": plan["provenance"]["geometryFamilyId"],
                }
            )
    report: dict[str, object] = {
        "version": "v7-pilot-exact-fixtures-v1",
        "status": "copied" if copy else "preview",
        "scope": "technical_fixture",
        "countsTowardT12": False,
        "planFileSha256": PLAN_FILE_SHA,
        "planChecksumSha256": PLAN_SHA,
        "sourceProofs": proofs,
        "sourceBindings": bindings,
        "originalsUnchanged": True,
        "operatorOutputsWritten": False,
    }
    if copy:
        (RUNTIME / "fixture-bindings.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        selector = RUNTIME / "fixture-selector.json"
        if not selector.exists():
            with selector.open("x", encoding="utf-8") as output:
                json.dump({"fixture": "B"}, output)
    return report


def _require_task_path(path: Path) -> None:
    if not path.resolve().is_relative_to(RUNTIME.resolve()):
        raise ValueError("Fixture target escaped the task runtime.")
    for ancestor in (path, *path.parents):
        if ancestor.exists():
            stat = ancestor.lstat()
            if ancestor.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
                raise ValueError("Fixture target cannot use links/reparse paths.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copy", action="store_true")
    args = parser.parse_args()
    result = prepare(copy=args.copy)
    print(json.dumps({"status": result["status"], "sourceCount": 10, "scope": "technical_fixture"}))


if __name__ == "__main__":
    main()
