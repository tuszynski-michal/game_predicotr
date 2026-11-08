"""Exact assessment membership derived from an independently pinned frozen cohort.

This is a projection of the existing snapshot reader, not a second GT/role ledger.
Never construct it from a calibration sidecar or its self-declared target hashes.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from .full_board_calibration import AssessedTarget, CalibrationPlan, ReferenceTarget, make_plan
from .grid_training_cohorts import digest


@dataclass(frozen=True)
class FrozenAssessmentReferences:
    game_id: UUID
    cohort_id: UUID
    manifest_sha256: str
    references: Mapping[str, str]
    targets: Mapping[str, tuple[tuple[str, str, int, str], ...]]
    source_counts: Mapping[str, int]
    role_proof_sha256: str
    content_references: Mapping[tuple[str, int], tuple[str, int, bool]] = field(
        default_factory=dict
    )

    @classmethod
    def from_sources(
        cls,
        manifest: Mapping[str, Any],
        manifest_sha256: str,
        sources: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> "FrozenAssessmentReferences":
        references, targets, counts = {}, {}, {}
        for role in ("A", "B", "REGRESSION"):
            ordered = sorted(sources[role], key=lambda source: source["sourceId"])
            if len({source["sourceId"] for source in ordered}) != len(ordered):
                raise ValueError("CALIBRATION_FROZEN_SOURCE_DUPLICATE")
            references[role] = digest(
                [
                    {
                        "sourceId": source["sourceId"],
                        "identity": source["sourceIdentity"],
                        "targets": source["targets"],
                        "purpose": source.get("validationPurpose"),
                        "purposeProofSha256": source["purposeProofSha256"],
                    }
                    for source in ordered
                ]
            )
            identities = tuple(
                sorted(
                    (
                        source["sourceId"],
                        source["sourceIdentity"]["normalized_pixel_checksum_sha256"],
                        target["positionIndex"],
                        digest(target),
                    )
                    for source in ordered
                    for target in source["targets"]
                )
            )
            if len({(source, slot) for source, _, slot, _ in identities}) != len(identities):
                raise ValueError("CALIBRATION_FROZEN_TARGET_DUPLICATE")
            targets[role], counts[role] = identities, len(ordered)
        return cls(
            UUID(manifest["gameId"]),
            UUID(manifest["cohortId"]),
            manifest_sha256,
            references,
            targets,
            counts,
            digest(
                {
                    "cohortManifestSha256": manifest_sha256,
                    "splitSha256": manifest["photoSplit"]["sha256"],
                    "assessments": references,
                }
            ),
            {
                (
                    source["sourceIdentity"]["normalized_pixel_checksum_sha256"],
                    target["positionIndex"],
                ): (
                    target["contentReferenceSha256"],
                    target["contentReferenceRevision"],
                    target["contentReferenceInputCropped"],
                )
                for source in sources["A"]
                for target in source["targets"]
                if isinstance(target.get("contentReferenceSha256"), str)
                and type(target.get("contentReferenceRevision")) is int
                and target["contentReferenceRevision"] >= 1
                and type(target.get("contentReferenceInputCropped")) is bool
            },
        )

    def require_targets(self, role: str, observed: Sequence[AssessedTarget]) -> None:
        actual = sorted(
            (
                str(item.sourceId),
                item.sourceRepresentativeSha256,
                item.positionIndex,
                item.groundTruthSha256,
            )
            for item in observed
        )
        if (
            any(item.gameId != self.game_id for item in observed)
            or len({(source, slot) for source, _, slot, _ in actual}) != len(actual)
            or tuple(actual) != self.targets[role]
        ):
            raise ValueError("CALIBRATION_FROZEN_TARGET_SET_CHANGED:" + role)

    def require_plan(self, prepared: Mapping[str, Any]) -> CalibrationPlan:
        plan = CalibrationPlan.model_validate(prepared["plan"])
        if plan.version.endswith("-v2"):
            references = [
                ReferenceTarget.model_validate(value) for value in prepared["selectionReferences"]
            ]
            for item in references:
                edge = item.inputEdgeReference
                if (
                    edge is not None
                    and edge.referenceKind == "verified_content"
                    and (
                        self.content_references.get(
                            (item.sourceRepresentativeSha256, item.positionIndex)
                        )
                        != (edge.contentReferenceSha256, edge.contentRevision, edge.inputCropped)
                    )
                ):
                    raise ValueError("INPUT_EDGE_FROZEN_CONTENT_REFERENCE_REQUIRED")
            expected = {(sha, slot) for _, sha, slot, _ in self.targets["A"]}
            if {
                (item.sourceRepresentativeSha256, item.positionIndex) for item in references
            } != expected:
                raise ValueError("INPUT_EDGE_FROZEN_REFERENCE_CHANGED")
            rebuilt = make_plan(
                references,
                game_id=plan.gameId,
                candidate_sha=plan.candidateManifestSha256,
                baseline_sha=plan.baselineManifestSha256,
                routing_sha=plan.routingSha256,
                role_proof_sha=plan.roleProofSha256,
                b_assessment_sha=plan.bAssessmentSha256,
                regression_assessment_sha=plan.regressionAssessmentSha256,
                feature_version="full-board-completeness-features-v2",
            )
            if rebuilt != plan:
                raise ValueError("INPUT_EDGE_PLAN_CHANGED")
        if (
            plan.gameId != self.game_id
            or plan.roleProofSha256 != self.role_proof_sha256
            or plan.bAssessmentSha256 != self.references["B"]
            or plan.regressionAssessmentSha256 != self.references["REGRESSION"]
            or prepared.get("referenceAssessmentSha256") != self.references["A"]
            or prepared.get("cohortManifestSha256") != self.manifest_sha256
            or prepared.get("cohortId") != str(self.cohort_id)
            or prepared.get("bTargets") != len(self.targets["B"])
            or prepared.get("bSources") != self.source_counts["B"]
            or prepared.get("regressionTargets") != len(self.targets["REGRESSION"])
            or prepared.get("regressionSources") != self.source_counts["REGRESSION"]
            or prepared.get("plannedConfigurations") != len(plan.menu)
            or prepared.get("plannedComparisons") != len(plan.menu) * len(self.targets["B"])
        ):
            raise ValueError("CALIBRATION_FROZEN_PLAN_CHANGED")
        return plan
