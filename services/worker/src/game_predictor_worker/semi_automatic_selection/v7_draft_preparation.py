"""Prepare unapproved JPEGs after EOF; never publish owned reviewed outputs."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from .local_source_manifest import LocalSourceManifest
from .v7_draft_catalog import pin_draft_folder
from .v7_draft_coverage import suggest_complete_choices
from .v7_draft_export import publish_draft
from .v7_draft_selection import suggest_draft_choices, suggest_interpolated_choices
from .v7_run_state import V7RunFinalization, _finalization


def drafts_ready(output_directory: Path, *, run_id: str, fingerprint: str) -> bool:
    marker = output_directory / "_propozycje_gotowe.json"
    if not marker.exists():
        return False
    if marker.stat().st_size > 2048:
        raise ValueError("Invalid draft completion marker.")
    payload = json.loads(marker.read_text(encoding="utf-8"))
    if payload.get("runId") != run_id or payload.get("sourceFingerprint") != fingerprint:
        raise ValueError("Output folder belongs to another draft run.")
    return True


def prepare_drafts(
    manifest: LocalSourceManifest,
    scan: dict[str, Any],
    finalization: V7RunFinalization | None,
    *,
    output_directory: Path,
    run_id: str,
    first: int,
    last: int,
    direction: str = "ascending",
    artifact_root: Path | None = None,
    pulse: Callable[[], None] = lambda: None,
) -> int:
    if scan.get("phase") != "finalized":
        raise ValueError("Draft preparation requires a finalized scan.")
    if drafts_ready(output_directory, run_id=run_id, fingerprint=manifest.source_fingerprint):
        return int(json.loads((output_directory / "_propozycje_gotowe.json").read_text())["files"])
    if finalization is None:
        finalization = _finalization(scan.get("finalization"))
    if finalization is None:
        raise ValueError("Draft preparation requires finalization proposals.")
    target = output_directory / "propozycje"
    if target.resolve() != target.absolute() or target.resolve().is_relative_to(
        manifest.source_root
    ):
        raise ValueError("Unsafe draft destination.")
    target.mkdir(parents=True, exist_ok=True)
    if artifact_root is not None:
        pin_draft_folder(
            artifact_root, target, run_id=run_id, fingerprint=manifest.source_fingerprint
        )
    occupied = frozenset(
        (item.sequence_range.start - first) // 9 for item in finalization.selections
    )
    entries: list[tuple[int, int, int, dict[str, object]]] = [
        (
            item.sequence_range.start,
            item.sequence_range.end,
            item.source_index,
            {"state": "proposal", "proofKinds": [kind.value for kind in item.proof_kinds]},
        )
        for item in finalization.selections
    ]
    for choice in suggest_draft_choices(
        cast(list[dict[str, Any]], scan["sourceDiagnostics"]),
        first=first,
        last=last,
        occupied=occupied,
    ):
        entries.append(
            (
                choice.range_start,
                choice.range_end,
                choice.source_index,
                {
                    "state": "inferred",
                    "reason": choice.reason,
                    "matchingLabels": choice.matching_labels,
                    "conflictingLabels": choice.conflicting_labels,
                },
            )
        )
    used = frozenset((start - first) // 9 for start, _, _, _ in entries)
    for estimated_choice in suggest_interpolated_choices(
        cast(list[dict[str, Any]], scan["sourceDiagnostics"]),
        first=first,
        last=last,
        direction=direction,
        occupied=used,
    ):
        entries.append(
            (
                estimated_choice.range_start,
                estimated_choice.range_end,
                estimated_choice.source_index,
                {
                    "state": "estimated",
                    "reason": estimated_choice.reason,
                    "inference": asdict(estimated_choice),
                },
            )
        )
    for coverage_choice in suggest_complete_choices(
        cast(list[dict[str, Any]], scan["sourceDiagnostics"]),
        first=first,
        last=last,
        source_count=len(manifest.sources),
        direction=direction,
        occupied=frozenset((start - first) // 9 for start, _, _, _ in entries),
        used_sources=frozenset(source for _, _, source, _ in entries),
    ):
        entries.append(
            (
                coverage_choice.range_start,
                coverage_choice.range_end,
                coverage_choice.source_index,
                {
                    "state": "estimated",
                    "reason": coverage_choice.reason,
                    "inference": asdict(coverage_choice),
                },
            )
        )
    for index, (start, end, source, metadata) in enumerate(sorted(entries)):
        if index % 16 == 0:
            pulse()
        publish_draft(
            manifest.source_root,
            target,
            manifest.sources[source],
            start=start,
            end=end,
            metadata={"runId": run_id, **metadata},
        )
    # One bounded completion marker. Partial copies remain resumable via sidecars.
    payload = {
        "runId": run_id,
        "sourceFingerprint": manifest.source_fingerprint,
        "files": len(entries),
        "approved": False,
    }
    temp = output_directory / f".draft-ready-{uuid4()}.tmp"
    try:
        with temp.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        marker = output_directory / "_propozycje_gotowe.json"
        try:
            os.link(temp, marker)
        except FileExistsError:
            if json.loads(marker.read_text(encoding="utf-8")) != payload:
                raise ValueError("Concurrent draft completion conflict.") from None
    finally:
        temp.unlink(missing_ok=True)
    return len(entries)
