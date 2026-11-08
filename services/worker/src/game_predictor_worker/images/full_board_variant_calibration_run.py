"""Separate, durable A -> B -> REG calibration for actual final input variants."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.domain.full_board_calibration import AssessedTarget, ReferenceTarget
from game_predictor_api.domain.full_board_variant_calibration import (
    assess_variant_regression,
    build_variant_profile,
    build_variant_qualification,
    make_variant_plan,
    require_variant_plan,
    seal_variant_b,
)

from ..training_core.grid_correction_metrics import CorrectionControlPhoto, measure_role
from .full_board_calibration_observations import CalibrationObserver
from .full_board_calibration_run import MAX_EVIDENCE_BYTES, FullBoardCalibrationRun
from .full_board_variant_context import (
    engine_variant_contexts,
    observe_variant_witness,
    verify_variant_witness,
)
from .grid_cohort_dataset import frame_rgb_and_box, has_full_geometry
from .grid_rescue_strategy import slots
from .production_cell_run import ProductionContentRun


class VariantCalibrationObserver(CalibrationObserver):
    def __init__(self, *, contexts: list[dict[str, Any]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.contexts = contexts

    def __call__(self, photo: Any, rgb: Any, observed: Mapping[str, Any]) -> list[dict[str, Any]]:
        targets = super().__call__(photo, rgb, observed)
        self.input_proofs = []  # v3 has one paired witness, not a parallel A proof list.
        source = self.sources[photo.source_id]
        found, measured, engine = observed["candidate"]
        usable = [d for d in found if d.nodes is not None]
        matches = {m.label: m for m in measured.matching.matches}
        binding = slots(found)
        boards = {
            b["positionIndex"]: b for b in (self.production_observation or {}).get("boards", [])
        }
        rows = []
        for index, target in enumerate(targets):
            position = target["positionIndex"]
            match = matches.get(index)
            detection = None if match is None else usable[match.prediction]
            board = boards.get(position)
            bound = (
                binding is not None
                and position in binding
                and found[binding[position]] is detection
                and board is not None
                and not board["candidate"]["matchAmbiguous"]
            )
            witness = observe_variant_witness(
                source=source,
                position=position,
                detection=detection,
                engine=engine,
                contexts=self.contexts,
                input_proof=board["candidate"]["inputEvidence"]
                if bound and board is not None
                else None,
            )
            key = None if witness is None else witness["variantKey"]
            edge = target.get("inputEdgeReference")
            if edge is not None and key is not None:
                target = {**target, "inputEdgeReference": {**edge, "variantSha256": key}}
            rows.append(
                {
                    "variantKey": key,
                    "target": target,
                    "witness": witness,
                    "reasonCode": "VARIANT_BINDING_UNRESOLVED" if witness is None else None,
                }
            )
        return rows


class VariantCalibrationRun(FullBoardCalibrationRun):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.contexts = engine_variant_contexts(self.engines[1], self.candidate_sha)
        from game_predictor_api.storage.full_board_calibration_evidence import (
            snapshot_assessment_references,
        )

        from .production_cell_input import engine_input_context

        self.frozen = snapshot_assessment_references(
            self.snapshot,
            input_context=engine_input_context(self.engines[1]),
            variant_contexts=self.contexts,
        )

    def _path(self, phase: str) -> Path:
        return super()._path("variant-" + phase)

    def observer(self, role: str) -> VariantCalibrationObserver:
        key = "A" if role == "VALIDATION" else role
        return VariantCalibrationObserver(
            contexts=self.contexts,
            game_id=self.game,
            sources={s["sourceId"]: s for s, _ in self.rows[key]},
            game_aspect=self.aspect,
            routing=self.routing,
            role="VALIDATION-A" if key == "A" else role,
            routing_sha=self.routing_sha,
            frame_loader=lambda source: self.snapshot.frame(
                source,
                "VALIDATION" if key in ("A", "B") else "REGRESSION",
                validation_purpose=key if key in ("A", "B") else "A",
            ),
        )

    def _verify_rows(self, role: str, rows: list[dict[str, Any]]) -> None:
        self.frozen.require_targets(
            role, [AssessedTarget.model_validate(row["target"]) for row in rows]
        )
        sources = {s["sourceId"]: s for s, _ in self.rows[role]}
        contexts = {c["sha256"]: c for c in self.contexts}
        for row in rows:
            if row["variantKey"] is None:
                if row["witness"] is not None or not row["reasonCode"]:
                    raise ValueError("VARIANT_UNRESOLVED_INVALID")
                continue
            source = sources[row["target"]["sourceId"]]
            target = next(
                t for t in source["targets"] if t["positionIndex"] == row["target"]["positionIndex"]
            )
            verify_variant_witness(
                self.snapshot,
                source,
                target,
                row["witness"],
                contexts[row["variantKey"]],
                role="VALIDATION" if role in ("A", "B") else "REGRESSION",
                validation_purpose=role if role in ("A", "B") else None,
            )

    def _variant_observations(self, role: str) -> list[dict[str, Any]]:
        path = self.root / "grid-model-evaluations" / str(self.job_id) / f"{self.game}-{role}.json"
        with path.open("rb") as handle:
            payload = handle.read(MAX_EVIDENCE_BYTES + 1)
        if len(payload) > MAX_EVIDENCE_BYTES:
            raise ValueError("CALIBRATION_EVIDENCE_SIZE_LIMIT")
        document = json.loads(payload)
        if document["gameId"] != self.game or document["jobId"] != str(self.job_id):
            raise ValueError("CALIBRATION_DETAIL_IDENTITY")
        rows = [target for row in document["photos"] for target in row["calibrationTargets"]]
        self._verify_rows("A" if role == "VALIDATION" else role, rows)
        return rows

    def prepare_b(self, before_photo: Callable[[int], None]) -> None:
        a = self._variant_observations("VALIDATION")
        references = []
        for row in a:
            target = AssessedTarget.model_validate(row["target"])
            reference = ReferenceTarget(
                gameId=target.gameId,
                sourceRepresentativeSha256=target.sourceRepresentativeSha256,
                positionIndex=target.positionIndex,
                role="VALIDATION-A",
                humanGood=target.candidateGood,
                features=target.candidateFeatures,
                inputEdgeReference=target.inputEdgeReference,
            ).model_dump(mode="json")
            references.append({**row, "sourceId": str(target.sourceId), "target": reference})
        plan = make_variant_plan(
            game_id=UUID(self.game),
            candidate_sha=self.candidate_sha,
            baseline_sha=self.baseline_sha,
            cohort_id=self.frozen.cohort_id,
            cohort_manifest_sha=self.frozen.manifest_sha256,
            role_proof_sha=self.role_proof,
            reference_assessment_sha=self.references["A"],
            b_assessment_sha=self.references["B"],
            regression_assessment_sha=self.references["REGRESSION"],
            allowed_variants=self.contexts,
            selection_references=references,
            game_log_aspect_reference=self.aspect,
            b_targets=len(self.frozen.targets["B"]),
            b_sources=self.frozen.source_counts["B"],
            regression_targets=len(self.frozen.targets["REGRESSION"]),
            regression_sources=self.frozen.source_counts["REGRESSION"],
        )
        verifier = self.frozen.variant_observation_verifier
        if verifier is None:
            raise ValueError("VARIANT_INDEPENDENT_VERIFIER_REQUIRED")
        verifier("A", plan, plan["selectionReferences"])
        self._seal("plan", plan)  # all menus immutable before any B pixel/network access
        if self._path("b").exists():
            sealed = self._read(self._path("b"))
            self._verify_rows("B", sealed["observations"])
            if seal_variant_b(plan, sealed["observations"]) != sealed:
                raise ValueError("VARIANT_B_SEAL_CHANGED")
            return
        photos = []
        for source, targets in self.rows["B"]:

            def load_rgb(source: dict[str, Any] = source) -> Any:
                return self.snapshot.frame(source, "VALIDATION", validation_purpose="B").rgb

            def load_support(source: dict[str, Any] = source) -> Any:
                return frame_rgb_and_box(
                    self.snapshot.frame(source, "VALIDATION", validation_purpose="B")
                )

            photos.append(
                CorrectionControlPhoto(
                    str(source["sourceId"]),
                    str(source["sourceId"]),
                    source["original"]["sha256"],
                    tuple(nodes for nodes, _ in targets),
                    load_rgb,
                    full_geometry=has_full_geometry(source),
                    load_with_support=load_support,
                )
            )
        _, measured = measure_role(
            photos,
            *self.engines,
            before_photo=before_photo,
            observation=self.observer("B"),
            content_observation=ProductionContentRun(self.snapshot).observer("B"),
        )
        rows = [target for row in measured for target in row["calibrationTargets"]]
        self._verify_rows("B", rows)
        self._seal("b", seal_variant_b(plan, rows))

    def finish(self) -> dict[str, Any]:
        plan = require_variant_plan(self._read(self._path("plan"))).model_dump(mode="json")
        if (
            plan["allowedVariants"] != self.contexts
            or plan["cohortManifestSha256"] != self.frozen.manifest_sha256
            or plan["roleProofSha256"] != self.role_proof
            or plan["candidateManifestSha256"] != self.candidate_sha
            or plan["baselineManifestSha256"] != self.baseline_sha
            or self.frozen.variant_observation_verifier is None
        ):
            raise ValueError("VARIANT_PLAN_CONTEXT_CHANGED")
        self.frozen.variant_observation_verifier("A", plan, plan["selectionReferences"])
        sealed = self._read(self._path("b"))
        self._verify_rows("B", sealed["observations"])
        if seal_variant_b(plan, sealed["observations"]) != sealed:
            raise ValueError("VARIANT_B_SEAL_CHANGED")
        regression = self._variant_observations("REGRESSION")
        result = assess_variant_regression(plan, sealed, regression)
        profile = build_variant_profile(plan, sealed, result)
        self._seal(
            "final",
            {
                "version": "full-board-variant-calibration-evidence-v1",
                "plan": plan,
                "b": sealed,
                "regressionTargets": regression,
                "result": result,
                "profile": profile,
            },
        )
        path = self._path("final")
        evidence = {
            "path": path.relative_to(self.root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        return build_variant_qualification(plan, sealed, result, evidence)
