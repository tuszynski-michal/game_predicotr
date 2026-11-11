"""Trusted opt-in sampling inputs; the existing split and ledger remain authoritative."""

from dataclasses import replace
from typing import Any
from uuid import UUID

from sqlalchemy import select

from game_predictor_api.domain.grid_cell_content import (
    ContentError,
    ContentRevision,
    content_source_identity,
    same_content_frame,
)
from game_predictor_api.domain.grid_content_sampling import (
    CONTENT_SAMPLING_POLICY,
    fresh_regression_preview,
)
from game_predictor_api.domain.grid_correction_split import CorrectionSplitSource
from game_predictor_api.domain.grid_training_cohorts import GridCohortError, digest
from game_predictor_api.domain.source_recording_groups import resolve_ancestor_references

from .grid_cell_content_models import GridCellContentRevisionModel as Revision
from .grid_quality_observations import read_source
from .source_recording_groups import SqlAlchemySourceRecordingRepository
from .source_recording_providers import TrustedRecordingProviders


class ContentSamplingPreparationError(GridCohortError):
    def __init__(self, report: dict[str, Any]) -> None:
        super().__init__(
            "CONTENT_REG_NOT_EVALUABLE", "Fresh full-photo content controls are incomplete."
        )
        self.report = report


def resolve_content_sampling(
    repo: Any, game: UUID, base: UUID, family: UUID, provider_index_sha256: str | None
) -> dict[str, Any]:
    lineage = SqlAlchemySourceRecordingRepository(repo.session).lineage(game, base, family)
    providers = TrustedRecordingProviders(repo.artifact_root, provider_index_sha256).read(lineage)
    resolved = resolve_ancestor_references(lineage, providers)
    return {
        "policy": CONTENT_SAMPLING_POLICY,
        "baseVersionId": str(base),
        "selectionVersion": "stratified-fresh-content-regression-v2",
        "ancestrySha256": digest([resolved.lineage_sha256, resolved.references])
        if resolved.complete
        else None,
        "ancestorGroups": sorted(
            {entry["groupId"] for ref in resolved.references for entry in ref["recordingGroups"]}
        ),
    }


def constrain_content_regression(
    repo: Any,
    game: UUID,
    sources: list[CorrectionSplitSource],
    contexts: dict[str, dict[str, Any]],
    policy: dict[str, Any],
    deadline: Any = None,
    *,
    references: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[CorrectionSplitSource], dict[str, Any]]:
    if policy.get("policy") != CONTENT_SAMPLING_POLICY:
        raise GridCohortError("CONTENT_SAMPLING_POLICY_INVALID", "Unknown content sampling policy.")
    protected = set(policy["ancestorGroups"])
    authority = {key: dict(value) for key, value in contexts.items()}
    complete = set()
    content_counts: dict[str, tuple[int, int]] = {}
    failures: list[dict[str, Any]] = []
    for source in sources:
        if deadline is not None:
            deadline.check(repo.session)
        facts = authority[source.source_id]
        if protected.intersection(facts["componentIds"]):
            facts["priorRoles"] = sorted(set(facts["priorRoles"]) | {"ANCESTOR"})
        # Without a registered recording, exclusions from recording-level ancestors
        # cannot prove this unregistered source independent.
        if protected and not facts["componentIds"]:
            facts["proofSha256"] = None
        rows = list(
            repo.session.scalars(
                select(Revision)
                .where(Revision.game_id == game, Revision.pixel_sha256 == source.pixel_sha256)
                .order_by(Revision.position_index, Revision.revision.desc())
            )
        )
        latest: dict[int, Revision] = {}
        for row in rows:
            latest.setdefault(row.position_index, row)
        positions = (
            set(source.attested_slots)
            or {slot for slot, _ in source.board_bindings}
            or set(range(9))
        )
        known = 0
        settled_positions: set[int] = set()
        try:
            raw_source = read_source(repo.session, game, UUID(source.source_id))
            target_source = content_source_identity(raw_source or {})
        except ContentError as error:
            failures.append({"sourceId": source.source_id, "reasonCode": error.code})
            content_counts[source.source_id] = 15 * len(positions), 0
            continue
        for position in positions:
            row = latest.get(position)
            if row is None:
                continue
            annotation = ContentRevision.model_validate(row.document)
            sequence = dict(source.board_bindings).get(position)
            if sequence is None and source.attested_start is not None:
                sequence = source.attested_start + position
            if (
                annotation.sha256 != row.document_sha256
                or not same_content_frame(annotation.source, target_source)
                or annotation.reference.gameId != game
                or annotation.sequenceNumber != sequence
            ):
                failures.append(
                    {
                        "sourceId": source.source_id,
                        "positionIndex": position,
                        "reasonCode": "CONTENT_REFERENCE_IDENTITY_CONFLICT",
                    }
                )
                continue
            if annotation.reference.humanApproved:
                known += sum(cell.state != "unknown" for cell in annotation.reference.cells)
                if all(cell.state != "unknown" for cell in annotation.reference.cells):
                    settled_positions.add(position)
        content_counts[source.source_id] = 15 * len(positions), known
        if settled_positions == set(range(9)):
            complete.add(source.source_id)
    report = fresh_regression_preview(
        sources,
        authority,
        frozenset(complete),
        ancestry_sha256=policy["ancestrySha256"],
        source_content_counts=content_counts,
        references=references,
        stratified=policy.get("selectionVersion") == "stratified-fresh-content-regression-v2",
    )
    report["contentReferenceFailures"] = failures
    report["contentReferenceFailureCount"] = len(failures)
    report["baseVersionId"] = policy.get("baseVersionId")
    report["sha256"] = digest({k: v for k, v in report.items() if k != "sha256"})
    if report["state"] != "ready":
        raise ContentSamplingPreparationError(report)
    selected, buffers = set(report["sourceIds"]), set(report["bufferSourceIds"])
    constrained = []
    for source in sources:
        if source.source_id in selected:
            constrained.append(replace(source, frozen_role="REGRESSION"))
        elif source.source_id in buffers:
            constrained.append(replace(source, frozen_buffer=True))
        elif source.frozen_role == "REGRESSION":
            # Keep its immutable ledger reservation, but do not evaluate this
            # previously exposed population as part of the new fresh control.
            constrained.append(replace(source, eligible_boards=0, pending_correction=False))
        else:
            constrained.append(replace(source, allowed_roles=source.allowed_roles - {"REGRESSION"}))
    report = {
        **report,
        "policy": CONTENT_SAMPLING_POLICY,
        "excludedLegacyRegressionSourceIds": sorted(
            s.source_id
            for s in sources
            if s.frozen_role == "REGRESSION" and s.source_id not in selected
        ),
    }
    report["sha256"] = digest({k: v for k, v in report.items() if k != "sha256"})
    return constrained, report
