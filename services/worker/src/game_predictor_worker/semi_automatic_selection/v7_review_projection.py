"""Pure canonical projection of the finalized V7 checkpoint for existing review."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from game_predictor_api.domain.v7_selection_delivery import payload_fingerprint

from .v7_occurrences import V7Occurrence
from .v7_run_state import V7PinnedSourceManifest, V7RunFinalization, V7RunStateError


@dataclass(frozen=True, slots=True)
class V7ReviewProjection:
    range_start: int
    range_end: int
    source_index: int | None
    group_first_source_index: int | None
    group_last_source_index: int | None
    payload: dict[str, object]
    fingerprint: str


def source_diagnostics(
    scan_state: dict[str, object],
    *,
    source_indexes: Iterable[int] | None = None,
    pinned_manifest: V7PinnedSourceManifest | None = None,
) -> dict[int, dict[str, object]]:
    """Project the same canon, optionally for a worker-owned validated delta."""

    manifest = pinned_manifest or V7PinnedSourceManifest.from_dict(scan_state["sourceManifest"])
    if pinned_manifest is not None:
        raw_manifest = scan_state["sourceManifest"]
        if not isinstance(raw_manifest, dict) or any(
            raw_manifest.get(key) != value
            for key, value in (
                ("selectionId", str(manifest.selection_id)),
                ("sourceRoot", str(manifest.source_root)),
                ("manifestChecksumSha256", manifest.manifest_checksum_sha256),
                ("sourceFingerprint", manifest.source_fingerprint),
            )
        ):
            raise V7RunStateError("V7_SOURCE_MANIFEST_DRIFT", "The delta manifest changed.")
    indexes = None if source_indexes is None else frozenset(_index(i) for i in source_indexes)
    if indexes is not None and any(i >= len(manifest.sources) for i in indexes):
        raise V7RunStateError("V7_RUN_STATE_CHECKPOINT_INVALID", "Invalid delta source index.")
    qualities = {
        _index(row["sourceIndex"]): row
        for row in _rows(scan_state["frameQualities"])
        if indexes is None or row["sourceIndex"] in indexes
    }
    errors = {
        _index(row["sourceIndex"]): row["reasonCode"]
        for row in _rows(scan_state["sourceErrors"])
        if indexes is None or row["sourceIndex"] in indexes
    }
    result: dict[int, dict[str, object]] = {}
    for raw in _rows(scan_state.get("sourceDiagnostics", [])):
        index = _index(raw["sourceIndex"])
        if indexes is not None and index not in indexes:
            continue
        source = manifest.sources[index]
        labels = {_index(label["positionIndex"]): label for label in _rows(raw["labels"])}
        observed = cast(list[int], raw["observedPositionIndices"])
        quality = qualities.get(index)
        boards = (
            {}
            if quality is None
            else {_index(board["positionIndex"]): board for board in _rows(quality["boards"])}
        )
        slots = []
        for position in range(9):
            label = labels.get(position)
            slots.append(
                {
                    "positionIndex": position,
                    "state": (
                        "recognized"
                        if label is not None
                        else "observed_without_number"
                        if position in observed
                        else "not_observed"
                    ),
                    "sequenceNumber": None if label is None else label["sequenceNumber"],
                    "recognitionConfidence": None
                    if label is None
                    else label["recognitionConfidence"],
                    "positionConfidence": None if label is None else label["positionConfidence"],
                    **{
                        key: boards.get(position, {}).get(key, "unknown")
                        for key in (
                            "visibility",
                            "readability",
                            "blur",
                            "occlusion",
                            "symbolContentLoss",
                            "decoration",
                        )
                    },
                }
            )
        result[index] = {
            "version": "v7-source-diagnostics-v1",
            "sourceIndex": index,
            "sourceId": source.source_id,
            "sourceChecksumSha256": source.checksum_sha256,
            "sourceErrorCode": errors.get(index),
            "slots": slots,
            "proof": raw["proof"],
        }
    if indexes is not None and result.keys() != indexes:
        raise V7RunStateError("V7_RUN_STATE_CHECKPOINT_INVALID", "Missing delta diagnostics.")
    return result


def build_review_projections(
    scan_state: dict[str, object],
    finalization: V7RunFinalization,
) -> tuple[V7ReviewProjection, ...]:
    if (
        scan_state.get("phase") != "finalized"
        or scan_state.get("finalization") != finalization.as_dict()
    ):
        raise V7RunStateError("V7_SCAN_FINALIZATION_REQUIRED", "Review requires validated EOF.")
    tracker = cast(dict[str, object], scan_state["tracker"])
    occurrences = tuple(
        V7Occurrence.from_dict(raw) for raw in _rows(tracker["finalizedOccurrences"])
    )
    occurrences_by_range: dict[tuple[int, int], list[V7Occurrence]] = {}
    for occurrence in occurrences:
        key = (occurrence.sequence_range.start, occurrence.sequence_range.end)
        occurrences_by_range.setdefault(key, []).append(occurrence)
    selections = {
        (value.sequence_range.start, value.sequence_range.end): value
        for value in finalization.selections
    }
    diagnostics = source_diagnostics(scan_state)
    ranges = cast(list[list[int]], scan_state["expectedRanges"])
    result = []
    for start, end in sorted(ranges):
        selection = selections.get((start, end))
        matching = occurrences_by_range.get((start, end), [])
        selected_occurrence = next(
            (
                occurrence
                for occurrence in matching
                if selection is not None and occurrence.occurrence_id == selection.occurrence_id
            ),
            None,
        )
        payload: dict[str, object] = {
            "version": "v7-review-projection-v1",
            "rangeStart": start,
            "rangeEnd": end,
            "candidate": None
            if selection is None
            else {
                "sourceIndex": selection.source_index,
                "sourceId": selection.source_id,
                "diagnostics": diagnostics.get(selection.source_index),
                "proofKinds": [kind.value for kind in selection.proof_kinds],
                "warnings": [warning.value for warning in selection.quality.warnings],
            },
            "provenSources": [
                {
                    **proof.as_dict(),
                    "occurrenceId": occurrence.occurrence_id,
                    "rangeStart": start,
                    "rangeEnd": end,
                }
                for occurrence in matching
                for proof in occurrence.proven_sources
            ],
            "occurrenceId": None
            if selected_occurrence is None
            else selected_occurrence.occurrence_id,
            "manualConfirmationRequired": True,
            "sourceManifestFingerprint": cast(dict[str, object], scan_state["sourceManifest"])[
                "sourceFingerprint"
            ],
        }
        result.append(
            V7ReviewProjection(
                start,
                end,
                None if selection is None else selection.source_index,
                None if selected_occurrence is None else selected_occurrence.first_source_index,
                None if selected_occurrence is None else selected_occurrence.last_source_index,
                payload,
                payload_fingerprint(payload),
            )
        )
    return tuple(result)


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise V7RunStateError("V7_RUN_STATE_CHECKPOINT_INVALID", "Invalid V7 metadata rows.")
    return cast(list[dict[str, object]], value)


def _index(value: object) -> int:
    if type(value) is not int or value < 0:
        raise V7RunStateError("V7_RUN_STATE_CHECKPOINT_INVALID", "Invalid V7 source index.")
    return value
