"""Atomic metadata projection inside the existing selection job transaction."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import cast
from uuid import UUID

from game_predictor_api.domain.v7_selection_delivery import payload_fingerprint
from game_predictor_api.storage.models import (
    SemiAutomaticImageSelectionRangeModel,
    SemiAutomaticImageSelectionRunModel,
    V7SourceObservationModel,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_worker.jobs.runtime import JobHandlerError

from .v7_observation_codec import deserialize_scan_observation, serialize_scan_observation
from .v7_review_projection import build_review_projections, source_diagnostics
from .v7_run_state import V7PinnedSourceManifest, V7RunFinalization, V7ScanObservation


def persist_v7_observations(
    session: Session,
    run_id: UUID,
    checkpoint: dict[str, object],
    changed_at: datetime,
    *,
    source_indexes: Iterable[int] | None = None,
    pinned_manifest: V7PinnedSourceManifest | None = None,
    diagnostic_scan_state: dict[str, object] | None = None,
    observations: tuple[V7ScanObservation, ...] | None = None,
) -> None:
    scan_state = (
        diagnostic_scan_state if diagnostic_scan_state is not None else checkpoint.get("scanState")
    )
    if not isinstance(scan_state, dict):
        raise JobHandlerError("V7_RUN_STATE_CHECKPOINT_INVALID", "Missing V7 scan state.")
    diagnostics = source_diagnostics(
        scan_state, source_indexes=source_indexes, pinned_manifest=pinned_manifest
    )
    if observations is not None:
        by_index = {observation.source_index: observation for observation in observations}
        if len(by_index) != len(observations) or by_index.keys() != diagnostics.keys():
            raise JobHandlerError(
                "V7_SOURCE_OBSERVATION_CHANGED", "Independent observations changed."
            )
        diagnostics = {
            index: {**payload, "resumeObservation": serialize_scan_observation(by_index[index])}
            for index, payload in diagnostics.items()
        }
    rows = _observations(session, run_id, tuple(diagnostics))
    for index, payload in diagnostics.items():
        fingerprint = payload_fingerprint(payload)
        row = rows.get(index)
        if row is not None:
            _require_observation_matches(row, payload, fingerprint)
            continue
        session.add(
            V7SourceObservationModel(
                run_id=run_id,
                source_index=index,
                source_checksum_sha256=cast(str, payload["sourceChecksumSha256"]),
                payload_fingerprint=fingerprint,
                payload=payload,
                created_at=changed_at,
            )
        )


def verify_v7_observation_prefix(
    session: Session, run_id: UUID, checkpoint: dict[str, object]
) -> None:
    """Audit durable history once on claim and EOF, including missing/extra rows."""

    if not checkpoint:
        diagnostics: dict[int, dict[str, object]] = {}
    else:
        scan_state = checkpoint.get("scanState")
        if not isinstance(scan_state, dict):
            raise JobHandlerError("V7_RUN_STATE_CHECKPOINT_INVALID", "Missing V7 scan state.")
        diagnostics = source_diagnostics(scan_state)
    rows = _observations(session, run_id, None)
    if rows.keys() != diagnostics.keys():
        raise JobHandlerError(
            "V7_SOURCE_OBSERVATION_CHANGED", "The durable observation prefix changed."
        )
    for index, payload in diagnostics.items():
        _require_observation_matches(rows[index], payload, payload_fingerprint(payload))


def _observations(
    session: Session, run_id: UUID, indexes: tuple[int, ...] | None
) -> dict[int, V7SourceObservationModel]:
    if indexes == ():
        return {}
    statement = select(V7SourceObservationModel).where(V7SourceObservationModel.run_id == run_id)
    if indexes is not None:
        statement = statement.where(V7SourceObservationModel.source_index.in_(indexes))
    return {row.source_index: row for row in session.scalars(statement)}


def _require_observation_matches(
    row: V7SourceObservationModel, payload: dict[str, object], fingerprint: str
) -> None:
    stored = row.payload
    if "resumeObservation" in stored and "resumeObservation" not in payload:
        # Claim/EOF audit compares the historical public diagnostics canon.
        # The independent recovery record remains part of the immutable digest.
        raw = stored["resumeObservation"]
        try:
            if serialize_scan_observation(deserialize_scan_observation(raw)) != raw:
                raise ValueError("Noncanonical independent observation.")
        except (TypeError, ValueError) as error:
            raise JobHandlerError(
                "V7_SOURCE_OBSERVATION_CHANGED", "A recovery observation changed."
            ) from error
        if row.payload_fingerprint != payload_fingerprint(stored):
            raise JobHandlerError("V7_SOURCE_OBSERVATION_CHANGED", "An observation digest changed.")
        stored = {key: value for key, value in stored.items() if key != "resumeObservation"}
        fingerprint = row.payload_fingerprint
    if (
        row.source_checksum_sha256 != payload["sourceChecksumSha256"]
        or row.payload_fingerprint != fingerprint
        or stored != payload
    ):
        raise JobHandlerError(
            "V7_SOURCE_OBSERVATION_CHANGED", "A committed observation is immutable."
        )


def project_v7_finalization(
    session: Session,
    run: SemiAutomaticImageSelectionRunModel,
    checkpoint: dict[str, object],
    finalization: V7RunFinalization,
    changed_at: datetime,
) -> dict[str, object]:
    scan_state = cast(dict[str, object], checkpoint["scanState"])
    projections = build_review_projections(scan_state, finalization)
    fingerprint = payload_fingerprint([item.payload for item in projections])
    old_fingerprint = run.checkpoint.get("v7ProjectionFingerprint")
    if old_fingerprint is not None and old_fingerprint != fingerprint:
        raise JobHandlerError("V7_REVIEW_PROJECTION_CHANGED", "Final review is immutable.")
    rows = tuple(
        session.scalars(
            select(SemiAutomaticImageSelectionRangeModel)
            .where(SemiAutomaticImageSelectionRangeModel.run_id == run.id)
            .order_by(SemiAutomaticImageSelectionRangeModel.range_start)
            .with_for_update()
        )
    )
    by_range = {(row.range_start, row.range_end): row for row in rows}
    if len(by_range) != len(projections):
        raise JobHandlerError("V7_REVIEW_PROJECTION_CHANGED", "Expected ranges changed.")
    sources = cast(dict[str, object], scan_state["sourceManifest"])["sources"]
    source_rows = cast(list[dict[str, object]], sources)
    for projection in projections:
        row = by_range.get((projection.range_start, projection.range_end))
        if row is None:
            raise JobHandlerError("V7_REVIEW_PROJECTION_CHANGED", "Expected range is missing.")
        if row.v7_projection_fingerprint is not None:
            if row.v7_projection_fingerprint != projection.fingerprint:
                raise JobHandlerError("V7_REVIEW_PROJECTION_CHANGED", "Review row changed.")
            continue  # Includes a reviewed/replaced row; never restore the proposal over its owner.
        if row.status != "missing" or row.output_checksum_sha256 is not None:
            raise JobHandlerError("V7_REVIEW_PROJECTION_CHANGED", "Unexpected legacy selection.")
        row.v7_review = projection.payload
        row.v7_projection_fingerprint = projection.fingerprint
        row.group_first_source_index = projection.group_first_source_index
        row.group_last_source_index = projection.group_last_source_index
        if projection.source_index is not None:
            source = source_rows[projection.source_index]
            row.status = "proposed"
            row.source_index = projection.source_index
            row.source_relative_path = cast(str, source["relativePath"])
            row.source_size_bytes = cast(int, source["sizeBytes"])
            row.source_checksum_sha256 = cast(str, source["checksumSha256"])
            row.selection_method = "v7_review_proposal"
        row.revision += 1
        row.updated_at = changed_at
    counters = dict(run.counters)
    counters["proposed"] = sum(row.status == "proposed" for row in rows)
    counters["missing"] = sum(row.status == "missing" for row in rows)
    counters["autoSelected"] = 0
    run.counters = counters
    return {**checkpoint, "v7ProjectionFingerprint": fingerprint}
