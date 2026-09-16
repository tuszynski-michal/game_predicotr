"""Bounded, read-only diagnostics for the additive virtual-geometry rollout."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from game_predictor_api.storage.additive_virtual_geometry_contracts import (
    optional_verification_outcome_value,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    VerifiedTrainingCohortCellModel,
)

_DEFAULT_LIMIT = 200
_MAX_LIMIT = 500


@dataclass(frozen=True, slots=True)
class AdditiveContractDiagnosticSample:
    category: str
    record_id: UUID
    backfill_ready: bool
    reason: str


@dataclass(frozen=True, slots=True)
class AdditiveContractDiagnostics:
    samples: tuple[AdditiveContractDiagnosticSample, ...]
    truncated: bool

    @property
    def ready_count(self) -> int:
        return sum(sample.backfill_ready for sample in self.samples)

    @property
    def ambiguous_count(self) -> int:
        return sum(not sample.backfill_ready for sample in self.samples)


class SqlAlchemyAdditiveVirtualGeometryDiagnostics:
    """Inspect only bounded candidate rows and never mutate historical data."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def inspect(self, *, limit: int = _DEFAULT_LIMIT) -> AdditiveContractDiagnostics:
        if limit < 1 or limit > _MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")
        samples: list[AdditiveContractDiagnosticSample] = []
        truncated = False

        def remaining() -> int:
            return max(0, limit + 1 - len(samples))

        source_rows = tuple(
            self._session.scalars(
                select(ImageSourceGeometryRevisionModel)
                .where(
                    or_(
                        ImageSourceGeometryRevisionModel.topology_fingerprint_sha256.is_(None),
                        ImageSourceGeometryRevisionModel.sequence_attestation_checksum_sha256.is_(
                            None
                        ),
                    )
                )
                .order_by(ImageSourceGeometryRevisionModel.id)
                .limit(remaining())
            )
        )
        samples.extend(
            AdditiveContractDiagnosticSample(
                category="source_geometry",
                record_id=row.id,
                backfill_ready=True,
                reason="derivable_from_pinned_topology_and_attestation",
            )
            for row in source_rows
        )

        if remaining() > 0:
            observation_rows = tuple(
                self._session.scalars(
                    select(CellObservationModel)
                    .where(
                        CellObservationModel.asset_mode == "virtual_source",
                        or_(
                            CellObservationModel.logical_cell_key_v2.is_(None),
                            CellObservationModel.render_identity_v2_sha256.is_(None),
                        ),
                    )
                    .order_by(CellObservationModel.id)
                    .limit(remaining())
                )
            )
            samples.extend(
                AdditiveContractDiagnosticSample(
                    category="cell_observation",
                    record_id=row.id,
                    backfill_ready=isinstance(row.render_spec, dict),
                    reason=(
                        "derivable_from_checksummed_render_spec"
                        if isinstance(row.render_spec, dict)
                        else "render_spec_missing_or_invalid"
                    ),
                )
                for row in observation_rows
            )

        if remaining() > 0:
            review_rows = tuple(
                self._session.scalars(
                    select(ImageSymbolReviewCellModel)
                    .where(
                        or_(
                            ImageSymbolReviewCellModel.verification_outcome.is_(None),
                            ImageSymbolReviewCellModel.logical_cell_key_v2.is_(None),
                        )
                    )
                    .order_by(ImageSymbolReviewCellModel.id)
                    .limit(remaining())
                )
            )
            for row in review_rows:
                outcome = optional_verification_outcome_value(
                    review_state=row.review_state,
                    quality_issue=row.quality_issue,
                    assigned_symbol_id=row.assigned_symbol_id,
                    prediction_present=row.prediction_symbol_code not in {None, "?"},
                    assignment_source=row.assignment_source,
                )
                identity_ready = row.asset_mode != "virtual_source" or isinstance(
                    row.render_spec, dict
                )
                samples.append(
                    AdditiveContractDiagnosticSample(
                        category="symbol_review_cell",
                        record_id=row.id,
                        backfill_ready=outcome is not None and identity_ready,
                        reason=(
                            "legacy_state_is_unambiguous"
                            if outcome is not None and identity_ready
                            else "legacy_state_or_render_identity_is_ambiguous"
                        ),
                    )
                )

        if remaining() > 0:
            cohort_rows = tuple(
                self._session.scalars(
                    select(VerifiedTrainingCohortCellModel)
                    .where(
                        VerifiedTrainingCohortCellModel.asset_mode == "virtual_source",
                        or_(
                            VerifiedTrainingCohortCellModel.logical_cell_key_v2.is_(None),
                            VerifiedTrainingCohortCellModel.render_identity_v2_sha256.is_(None),
                        ),
                    )
                    .order_by(VerifiedTrainingCohortCellModel.id)
                    .limit(remaining())
                )
            )
            samples.extend(
                AdditiveContractDiagnosticSample(
                    category="verified_training_cell",
                    record_id=row.id,
                    backfill_ready=isinstance(row.render_spec, dict),
                    reason=(
                        "derivable_from_frozen_render_spec"
                        if isinstance(row.render_spec, dict)
                        else "frozen_render_spec_missing_or_invalid"
                    ),
                )
                for row in cohort_rows
            )

        if len(samples) > limit:
            truncated = True
            samples = samples[:limit]
        return AdditiveContractDiagnostics(samples=tuple(samples), truncated=truncated)


__all__ = [
    "AdditiveContractDiagnosticSample",
    "AdditiveContractDiagnostics",
    "SqlAlchemyAdditiveVirtualGeometryDiagnostics",
]
