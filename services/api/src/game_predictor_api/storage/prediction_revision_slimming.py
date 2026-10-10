"""Slimming and retention of symbol prediction revisions (D-467 S8, TASK-0794).

Two maintenance operations used by ``scripts/slim_prediction_revisions.py``:

- **slim**: every revision not processed yet (``legacy_predictions_sha256 IS
  NULL``) gets ``legacy_predictions_sha256`` = its v1 digest and loses
  ``predictions[].virtualCell.renderSpec``.  The v2 digest is checked before
  and after the write (read back in the same transaction); any difference
  raises ``PredictionRevisionSlimError`` and the caller rolls the batch back.
  A revision that is already slim only gets the digest (v1 == v2), which marks
  it processed.  ``crop_manifest_checksum_sha256`` and
  ``model_checksum_sha256`` are never touched.
- **retention**: revisions of superseded review items that have no review
  cells, are referenced by no cell and whose item never received a
  reference-library revision (no ``apply-revert`` anchor) are deleted.

Both work in batches inside the caller's transaction, keyed by ``id`` so a
run can resume after the last committed batch.  Statements are scoped by
``game_id`` (one partition, explicit filter -- the database role bypasses
row-level security).
"""

from __future__ import annotations

import json
import random
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast
from uuid import UUID

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.prediction_revisions import (
    canonical_json,
    has_virtual_render_spec,
    predictions_digest,
    predictions_digest_v1,
    slim_predictions,
)

REVISIONS: Final = "game_data_v2.image_symbol_prediction_revisions"
CELLS: Final = "game_data_v2.image_symbol_review_cells"
ITEMS: Final = "game_data_v2.image_review_items"
LIBRARY_MODEL_VERSION: Final = "symbol-reference-library-v1"

Executor = Session | Connection


class PredictionRevisionSlimError(RuntimeError):
    """A slimmed revision would not keep its v2 digest; the batch must roll back."""

    def __init__(self, code: str, message: str, *, revision_id: UUID | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.revision_id = revision_id


@dataclass(frozen=True, slots=True)
class SlimBatch:
    scanned: int
    slimmed: int
    already_slim: int
    stored_bytes_before: int
    stored_bytes_after: int
    last_id: UUID | None


@dataclass(frozen=True, slots=True)
class RetentionBatch:
    deleted: int
    stored_bytes: int


def legacy_digest_column_present(executor: Executor) -> bool:
    """Whether migration 0137 added ``legacy_predictions_sha256``."""

    return bool(
        executor.execute(
            text(
                """SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'game_data_v2'
                      AND table_name = 'image_symbol_prediction_revisions'
                      AND column_name = 'legacy_predictions_sha256')"""
            )
        ).scalar_one()
    )


def preview_slim(
    executor: Executor, *, game_id: UUID, sample_size: int = 500, seed: int = 794
) -> dict[str, Any]:
    """Read-only plan: counts, stored bytes and a sample-based size estimate.

    Counting the revisions that still carry ``renderSpec`` exactly would
    decompress every payload, so the share is estimated on a sample of
    ``sample_size`` consecutive revisions from a random ``id``.  The stored
    size after slimming is estimated with the zlib-compressed size ratio of
    the slim and full canonical JSON (a proxy for TOAST compression; the
    uncompressed ratio is reported too).
    """

    column = legacy_digest_column_present(executor)
    pending_filter = "AND legacy_predictions_sha256 IS NULL" if column else ""
    totals = (
        executor.execute(
            text(
                f"""SELECT count(*) AS revisions,
                       coalesce(sum(pg_column_size(predictions)), 0) AS stored_bytes,
                       count(*) FILTER (WHERE TRUE {pending_filter}) AS pending
                FROM {REVISIONS} WHERE game_id = :game_id"""
            ),
            {"game_id": game_id},
        )
        .mappings()
        .one()
    )
    start = UUID(int=random.Random(seed).getrandbits(128))
    rows = list(
        executor.execute(
            text(
                f"""SELECT id, predictions, pg_column_size(predictions) AS stored_bytes
                FROM {REVISIONS}
                WHERE game_id = :game_id AND id >= :start {pending_filter}
                ORDER BY id LIMIT :limit"""
            ),
            {"game_id": game_id, "start": start, "limit": sample_size},
        ).mappings()
    )
    with_spec = 0
    stored = 0
    full_json = 0
    slim_json = 0
    full_zlib = 0
    slim_zlib = 0
    mismatches = 0
    for row in rows:
        predictions = cast(Sequence[Mapping[str, Any]], row["predictions"])
        stored += int(row["stored_bytes"])
        slim = slim_predictions(predictions)
        full_bytes = canonical_json(list(predictions))
        slim_bytes = canonical_json(slim)
        full_json += len(full_bytes)
        slim_json += len(slim_bytes)
        full_zlib += len(zlib.compress(full_bytes))
        slim_zlib += len(zlib.compress(slim_bytes))
        if has_virtual_render_spec(predictions):
            with_spec += 1
        if predictions_digest(slim) != predictions_digest(predictions):
            mismatches += 1
    ratio = slim_zlib / full_zlib if full_zlib else 1.0
    pending = int(totals["pending"])
    estimated_after = round(int(totals["stored_bytes"]) * ratio)
    return {
        "legacyDigestColumnPresent": column,
        "revisions": int(totals["revisions"]),
        "pendingRevisions": pending,
        "storedPredictionBytes": int(totals["stored_bytes"]),
        "sample": {
            "revisions": len(rows),
            "withRenderSpec": with_spec,
            "storedBytes": stored,
            "canonicalJsonBytesFull": full_json,
            "canonicalJsonBytesSlim": slim_json,
            "zlibBytesFull": full_zlib,
            "zlibBytesSlim": slim_zlib,
            "slimToFullRatioUncompressed": round(slim_json / full_json, 4) if full_json else 1.0,
            "slimToFullRatio": round(ratio, 4),
            "digestV2Mismatches": mismatches,
        },
        "estimate": {
            "revisionsWithRenderSpec": round(pending * with_spec / len(rows)) if rows else 0,
            "storedPredictionBytesAfter": estimated_after,
            "storedPredictionBytesSaved": int(totals["stored_bytes"]) - estimated_after,
        },
    }


def slim_batch(
    executor: Executor,
    *,
    game_id: UUID,
    after_id: UUID | None,
    batch_size: int,
) -> SlimBatch:
    """Slim the next ``batch_size`` unprocessed revisions after ``after_id``."""

    if not 1 <= batch_size <= 2_000:
        raise ValueError("batch_size must be between 1 and 2000")
    after_filter = "" if after_id is None else "AND id > :after_id"
    rows = list(
        executor.execute(
            text(
                f"""SELECT id, predictions, pg_column_size(predictions) AS stored_bytes
                FROM {REVISIONS}
                WHERE game_id = :game_id AND legacy_predictions_sha256 IS NULL {after_filter}
                ORDER BY id LIMIT :limit
                FOR UPDATE"""
            ),
            {"game_id": game_id, "after_id": after_id, "limit": batch_size},
        ).mappings()
    )
    if not rows:
        return SlimBatch(0, 0, 0, 0, 0, None)
    expected: dict[UUID, str] = {}
    slimmed = 0
    before = 0
    for row in rows:
        revision_id = cast(UUID, row["id"])
        predictions = cast(Sequence[Mapping[str, Any]], row["predictions"])
        before += int(row["stored_bytes"])
        legacy = predictions_digest_v1(predictions)
        digest = predictions_digest(predictions)
        slim = slim_predictions(predictions)
        if predictions_digest(slim) != digest or predictions_digest_v1(slim) != digest:
            raise PredictionRevisionSlimError(
                "PREDICTION_REVISION_SLIM_DIGEST_DRIFT",
                "The slim projection does not keep the v2 digest.",
                revision_id=revision_id,
            )
        expected[revision_id] = digest
        if has_virtual_render_spec(predictions):
            slimmed += 1
            executor.execute(
                text(
                    f"""UPDATE {REVISIONS}
                    SET predictions = CAST(:predictions AS jsonb),
                        legacy_predictions_sha256 = :legacy
                    WHERE game_id = :game_id AND id = :id"""
                ),
                {
                    "predictions": json.dumps(slim, ensure_ascii=False),
                    "legacy": legacy,
                    "game_id": game_id,
                    "id": revision_id,
                },
            )
        else:
            executor.execute(
                text(
                    f"""UPDATE {REVISIONS} SET legacy_predictions_sha256 = :legacy
                    WHERE game_id = :game_id AND id = :id"""
                ),
                {"legacy": legacy, "game_id": game_id, "id": revision_id},
            )
    after = 0
    checked = 0
    for row in executor.execute(
        text(
            f"""SELECT id, predictions, pg_column_size(predictions) AS stored_bytes
            FROM {REVISIONS} WHERE game_id = :game_id AND id = ANY(:ids)"""
        ),
        {"game_id": game_id, "ids": list(expected)},
    ).mappings():
        revision_id = cast(UUID, row["id"])
        predictions = cast(Sequence[Mapping[str, Any]], row["predictions"])
        after += int(row["stored_bytes"])
        checked += 1
        if has_virtual_render_spec(predictions) or (
            predictions_digest(predictions) != expected[revision_id]
        ):
            raise PredictionRevisionSlimError(
                "PREDICTION_REVISION_SLIM_VERIFY_FAILED",
                "A slimmed revision read back with a different v2 digest.",
                revision_id=revision_id,
            )
    if checked != len(expected):
        raise PredictionRevisionSlimError(
            "PREDICTION_REVISION_SLIM_VERIFY_FAILED",
            "A slimmed revision could not be read back.",
        )
    return SlimBatch(
        scanned=len(rows),
        slimmed=slimmed,
        already_slim=len(rows) - slimmed,
        stored_bytes_before=before,
        stored_bytes_after=after,
        last_id=cast(UUID, rows[-1]["id"]),
    )


_RETENTION_CANDIDATES: Final = f"""
WITH items AS MATERIALIZED (
  SELECT i.id FROM {ITEMS} i
  WHERE i.game_id = :game_id AND i.status = 'superseded'
    AND NOT EXISTS (
      SELECT 1 FROM {CELLS} c WHERE c.game_id = i.game_id AND c.review_item_id = i.id)
    AND NOT EXISTS (
      SELECT 1 FROM {REVISIONS} l
      WHERE l.game_id = i.game_id AND l.review_item_id = i.id
        AND l.model_version = :library_model_version)
)
SELECT p.id, p.review_item_id, pg_column_size(p.predictions) AS stored_bytes
FROM {REVISIONS} p JOIN items ON items.id = p.review_item_id
WHERE p.game_id = :game_id
  AND NOT EXISTS (
    SELECT 1 FROM {CELLS} c WHERE c.game_id = p.game_id AND c.prediction_revision_id = p.id)
"""


def preview_retention(executor: Executor, *, game_id: UUID) -> dict[str, Any]:
    row = (
        executor.execute(
            text(
                f"""SELECT count(*) AS revisions, count(DISTINCT review_item_id) AS items,
                       coalesce(sum(stored_bytes), 0) AS stored_bytes
                FROM ({_RETENTION_CANDIDATES}) candidates"""
            ),
            {"game_id": game_id, "library_model_version": LIBRARY_MODEL_VERSION},
        )
        .mappings()
        .one()
    )
    return {
        "revisions": int(row["revisions"]),
        "reviewItems": int(row["items"]),
        "storedPredictionBytes": int(row["stored_bytes"]),
    }


def delete_retention_batch(executor: Executor, *, game_id: UUID, batch_size: int) -> RetentionBatch:
    """Delete up to ``batch_size`` retention candidates; locks the rows first."""

    if not 1 <= batch_size <= 5_000:
        raise ValueError("batch_size must be between 1 and 5000")
    rows = list(
        executor.execute(
            text(f"{_RETENTION_CANDIDATES} ORDER BY p.id LIMIT :limit FOR UPDATE OF p"),
            {
                "game_id": game_id,
                "library_model_version": LIBRARY_MODEL_VERSION,
                "limit": batch_size,
            },
        ).mappings()
    )
    if not rows:
        return RetentionBatch(0, 0)
    deleted = executor.execute(
        text(f"DELETE FROM {REVISIONS} WHERE game_id = :game_id AND id = ANY(:ids)"),
        {"game_id": game_id, "ids": [row["id"] for row in rows]},
    )
    count = int(getattr(deleted, "rowcount", 0) or 0)
    if count != len(rows):
        raise PredictionRevisionSlimError(
            "PREDICTION_REVISION_RETENTION_DRIFT",
            "A retention candidate disappeared before it was deleted.",
        )
    return RetentionBatch(deleted=count, stored_bytes=sum(int(row["stored_bytes"]) for row in rows))


__all__ = [
    "LIBRARY_MODEL_VERSION",
    "PredictionRevisionSlimError",
    "RetentionBatch",
    "SlimBatch",
    "delete_retention_batch",
    "legacy_digest_column_present",
    "preview_retention",
    "preview_slim",
    "slim_batch",
]
