"""Copy only checksum-pinned evaluation assets into a portable comparison report."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .comparison_production_cells import INDEX_VERSION, _inside, _write_output
from .grid_cohort_dataset import GridCohortSnapshot


def _copy(source: Path, destination: Path, pin: dict[str, Any], limit: int) -> None:
    # Read and check before creating any destination; never overwrite a foreign file.
    with _inside(source, pin["path"]).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit or hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("CONTENT_COMPARISON_BUNDLE_CHECKSUM_OR_SIZE")
    if "bytes" in pin and len(raw) != pin["bytes"]:
        raise ValueError("CONTENT_COMPARISON_BUNDLE_BYTE_COUNT")
    output = _inside(destination, pin["path"])
    if output.exists():
        if (
            output.stat().st_size != len(raw)
            or hashlib.sha256(output.read_bytes()).hexdigest() != pin["sha256"]
        ):
            raise ValueError("CONTENT_COMPARISON_BUNDLE_DESTINATION_CONFLICT")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects an existing artifact if another writer races.
    with output.open("xb") as stream:
        stream.write(raw)


def build_production_package(
    report_root: Path,
    artifact_root: Path,
    evaluation: dict[str, Any],
    source_ids: set[str],
) -> dict[str, str]:
    """Use report pins and canonical cohort paths, without a DB or model invocation.

    Metadata for the snapshot is copied intact; original images are restricted to
    explicitly selected report photos. Missing assets remain per-source unavailable.
    """
    report_root, artifact_root = report_root.resolve(), artifact_root.absolute()
    report = evaluation["report"]
    if report.get("schemaVersion") != "grid-model-evaluation-read-v6":
        return {s: "CONTENT_COMPARISON_T3_REPORT_REQUIRED" for s in source_ids}
    entries: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    seen: set[str] = set()
    for cohort in report["cohorts"]:
        game, cohort_id = cohort["gameId"], cohort["cohortId"]
        manifest = {
            "path": (
                f"data/grid-training-cohorts/{game}/{cohort_id}/pages/"
                f"{cohort['manifestSha256']}.json"
            ),
            "sha256": cohort["manifestSha256"],
        }
        try:
            snapshot = GridCohortSnapshot(artifact_root, manifest["path"], manifest["sha256"])
            selected = [s for s in snapshot.sources() if s["sourceId"] in source_ids]
            game_report = next(g for g in report["games"] if g["gameId"] == game)
            if not selected:
                continue
            _copy(artifact_root, report_root, manifest, 16 * 1024 * 1024)
            index_pin = snapshot.manifest["pageIndex"]
            _copy(artifact_root, report_root, index_pin, 16 * 1024 * 1024)
            # The index is JSONL, and all page bytes are independently pinned.
            for line in _inside(artifact_root, index_pin["path"]).read_bytes().splitlines():
                _copy(artifact_root, report_root, json.loads(line), 16 * 1024 * 1024)
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
            for source_id in source_ids - entries.keys():
                errors.setdefault(source_id, str(error))
            continue
        for source in selected:
            source_id = source["sourceId"]
            try:
                if source_id in seen:
                    raise ValueError("CONTENT_COMPARISON_SOURCE_NOT_UNIQUE")
                seen.add(source_id)
                role = source["role"]
                if (
                    source["used"] is not True
                    or role not in ("VALIDATION", "REGRESSION")
                    or (role == "VALIDATION" and source.get("validationPurpose") != "A")
                ):
                    raise ValueError("CONTENT_COMPARISON_SOURCE_ROLE_UNAVAILABLE")
                detail = game_report["roles"][role]["detail"]
                _copy(artifact_root, report_root, detail, 96 * 1024 * 1024)
                # Use the snapshot's actual canonical frame/pin, never an image
                # at the same pathname from a current source or preview directory.
                snapshot.frame(source, role)
                _copy(artifact_root, report_root, source["original"], 64 * 1024 * 1024)
                entries[source_id] = {
                    "sourceId": source_id,
                    "gameId": game,
                    "role": role,
                    "manifest": manifest,
                    "detail": detail,
                }
                errors.pop(source_id, None)
            except (OSError, ValueError, KeyError, TypeError) as error:
                entries.pop(source_id, None)
                errors[source_id] = str(error)
    for source_id in source_ids - entries.keys():
        errors.setdefault(source_id, "CONTENT_COMPARISON_SOURCE_NOT_IN_PINNED_COHORTS")
    index = {"schemaVersion": INDEX_VERSION, "entries": list(entries.values())}
    raw = json.dumps(index, ensure_ascii=False, allow_nan=False).encode()
    if len(raw) > 1024 * 1024 or len(entries) > 4096:
        raise ValueError("CONTENT_COMPARISON_INDEX_SIZE_LIMIT")
    _write_output(report_root, "production-cells/index.json", raw)
    return errors
