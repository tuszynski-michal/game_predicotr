"""Bounded read-only feedback snapshot and checksum validation of referenced JPEGs."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.v7_selection_delivery import V7OutputOperation
from game_predictor_api.domain.v7_selection_feedback import (
    V7FeedbackOwner,
    build_feedback_manifest,
    relative_source_path,
)
from game_predictor_api.storage.models import (
    SemiAutomaticImageSelectionRangeModel as Range,
)
from game_predictor_api.storage.models import (
    SemiAutomaticImageSelectionRunModel as Run,
)
from game_predictor_api.storage.models import (
    V7OutputOperationModel as Operation,
)


def verify_feedback_source(root: str, source: dict[str, object]) -> str | None:
    try:
        source_root = Path(root).resolve(strict=True)
        path = source_root.joinpath(*relative_source_path(source).parts).resolve(strict=True)
        path.relative_to(source_root)
        if not path.is_file() or path.stat().st_size != source.get("sizeBytes"):
            return "source_changed"
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        return None if checksum == source.get("checksumSha256") else "source_changed"
    except ValueError:
        return "source_path_invalid"
    except OSError:
        return "source_unavailable"


def read_feedback_manifest(
    session: Session, run_ids: Sequence[UUID], *, maximum_operations: int = 10_000
) -> dict[str, object]:
    """Require caller-owned consistent read-only transaction; never load run checkpoints."""
    if not run_ids or len(run_ids) > 50 or not 1 <= maximum_operations <= 100_000:
        raise ValueError("Select 1–50 runs and an operation limit of 1–100000.")
    if (
        session.scalar(text("SHOW transaction_read_only")) != "on"
        or session.scalar(text("SHOW transaction_isolation")) != "repeatable read"
    ):
        raise ValueError("Feedback export requires REPEATABLE READ READ ONLY.")
    found = set(
        session.scalars(
            select(Run.id).where(Run.id.in_(run_ids), Run.workflow_mode == "v7_selection")
        )
    )
    if found != set(run_ids):
        raise ValueError("Every requested run must be an existing V7 selection run.")
    rows = session.execute(
        select(
            Operation,
            Range.v7_output_owner_operation_id,
            Range.source_index,
            Range.output_checksum_sha256,
            Range.v7_output_generation,
        )
        .join(Range, Range.id == Operation.range_id)
        .where(Operation.run_id.in_(run_ids), Range.run_id == Operation.run_id)
        .order_by(
            Operation.run_id, Range.expected_index, Operation.decision_generation, Operation.id
        )
        .limit(maximum_operations + 1)
    ).all()
    if len(rows) > maximum_operations:
        raise ValueError(
            "Operation limit exceeded; select fewer runs or increase the explicit limit."
        )
    operations: list[V7OutputOperation] = []
    owners: dict[tuple[UUID, UUID], V7FeedbackOwner] = {}
    for row, owner_id, source_index, checksum, generation in rows:
        operation = V7OutputOperation(
            row.id,
            row.run_id,
            row.range_id,
            row.request_payload,
            row.context_payload,
            row.decision_generation,
            row.reserved_revision,
            row.state,
            row.receipt,
            row.error_code,
            row.created_at,
            row.updated_at,
        )
        if operation.request_fingerprint != row.request_fingerprint:
            raise ValueError("Immutable operation request fingerprint changed.")
        operations.append(operation)
        owners[(row.run_id, row.range_id)] = V7FeedbackOwner(
            owner_id, source_index, checksum, generation
        )
    manifest = build_feedback_manifest(operations, owners, validate_source=verify_feedback_source)
    manifest["runIds"] = sorted(str(run_id) for run_id in set(run_ids))
    return manifest
