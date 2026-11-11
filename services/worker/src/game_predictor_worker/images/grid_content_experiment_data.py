"""File-only experiment input proof, real base error bank and A-only evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import numpy as np
import torch
from game_predictor_api.domain.grid_content_experiment_inputs import require_inputs
from game_predictor_api.domain.grid_training_cohorts import digest

from ..geometry_core.inference import DecodeSettings, NeuralGridEngine
from ..training_core.evaluation_precision import evaluation_precision
from ..training_core.grid_content_experiment import selection_record
from ..training_core.grid_correction_metrics import (
    CorrectionControlPhoto,
    evaluate_photo,
    measure_role,
)
from ..training_core.grid_evaluation import predictions
from ..training_core.neural_grid_network import BoardExport, ScreenExport
from .grid_cohort_dataset import ContentTrainingDataset, GridBoardDataset, has_full_geometry
from .grid_model_evaluation_handler import GridModelEvaluationJobHandler
from .production_cell_run import ProductionContentRun, summarize_content


class ContentAssessmentEngine:
    """The single closed R2/R3 route, shared by A selection and exported inference."""

    def __init__(self, engine: Any, routing: Mapping[str, Any]) -> None:
        from ..geometry_core.rescue import GridRescueVariantV2
        from .grid_rescue_strategy import require_completeness_routing

        self.engine, self.variant, self.path = engine, GridRescueVariantV2(), "combined"
        self.routing = require_completeness_routing(routing)
        self.last_baseline: list[Any] = []
        self.last_result: Any = None

    def analyse(self, rgb: Any) -> list[Any]:
        from .grid_rescue_strategy import execute_path

        self.last_baseline = self.engine.analyse(rgb)
        self.last_result = execute_path(
            self.last_baseline,
            width=rgb.shape[1],
            height=rgb.shape[0],
            variant=self.variant,
            path=self.path,
            expected_positions=set(range(9)),
            routing=self.routing,
            detect=lambda geometry: self.engine.detect(rgb, geometry=geometry),
            recrop=lambda position, detection, geometry: self.engine.recrop(
                rgb, detection, geometry=geometry
            ),
        )
        return list(self.last_result.detections)


def verify_inputs(
    plan: Mapping[str, Any], inputs: Mapping[str, Any], snapshots: Sequence[Any]
) -> None:
    """Check full server proofs against frozen files, never infer unseen from missing history."""
    require_inputs(inputs, plan)
    indexed = {s.manifest["gameId"]: s for s in snapshots}
    if set(indexed) != {p["gameId"] for p in plan["cohorts"]}:
        raise ValueError("CONTENT_EXPERIMENT_COHORT_SCOPE")
    for pin in plan["cohorts"]:
        snapshot = indexed[pin["gameId"]]
        if snapshot.manifest_sha256 != pin["manifestSha256"]:
            raise ValueError("CONTENT_EXPERIMENT_COHORT_CHANGED")
        split = snapshot.manifest["photoSplit"]
        if split.get("contentSampling", {}).get("policy") != "full-symbol-content-sampling-v1":
            raise ValueError("CONTENT_EXPERIMENT_REFERENCE_REQUIRED")
        members = {p["sourceId"]: p for p in split["sources"]}
        used = {s["sourceId"]: s for s in snapshot.sources() if s.get("used")}
        for key, role, purpose in (
            ("trainEligibility", "TRAIN", None),
            ("selectionRoster", "VALIDATION", "A"),
            ("calibrationRoster", "VALIDATION", "B"),
            ("regressionRoster", "REGRESSION", None),
        ):
            game = next(g for g in inputs[key]["games"] if g["gameId"] == pin["gameId"])
            if key == "trainEligibility" and set(game["trainingSourceIds"]) != {
                source["sourceId"] for source in used.values() if source["role"] == "TRAIN"
            }:
                raise ValueError("CONTENT_EXPERIMENT_TRAIN_ROSTER_CHANGED")
            if key != "trainEligibility" and game["splitSha256"] != split["sha256"]:
                raise ValueError("CONTENT_EXPERIMENT_SPLIT_CHANGED")
            expected = {
                p["sourceId"]
                for p in members.values()
                if p["role"] == role
                and p.get("validationPurpose") == purpose
                and p.get("representative")
                and p.get("eligibleBoards", 0) > 0
                and not p.get("detectorExcluded")
                and not p.get("contentExcluded")
            }
            selected = {s["sourceId"] for s in game["sources"]}
            if (key != "trainEligibility" and selected != expected) or not selected <= expected:
                raise ValueError("CONTENT_EXPERIMENT_ROLE_ROSTER_CHANGED")
            for source in game["sources"]:
                actual = members[source["sourceId"]]
                frozen = used.get(source["sourceId"])
                if (
                    frozen is None
                    or frozen["role"] != role
                    or any(
                        source[k] != actual[k]
                        for k in (
                            "sourceSha256",
                            "pixelSha256",
                            "qualifiedLabelsSha256",
                            "eligibleBoards",
                        )
                    )
                ):
                    raise ValueError("CONTENT_EXPERIMENT_SOURCE_CHANGED")
                identity = frozen["sourceIdentity"]
                if (
                    identity["checksum_sha256"] != source["sourceSha256"]
                    or identity["normalized_pixel_checksum_sha256"] != source["pixelSha256"]
                ):
                    raise ValueError("CONTENT_EXPERIMENT_SOURCE_CHANGED")
                if key == "trainEligibility" and (
                    actual.get("registryProofSha256") != source["splitRegistryProofSha256"]
                    or not set(actual.get("componentIds", []))
                    <= set(source["closure"]["componentIds"])
                ):
                    raise ValueError("CONTENT_BANK_SOURCE_PROOF_CHANGED")


def require_render_preflight(snapshots: Sequence[Any], crop_policy: str | None = None) -> None:
    """Metadata-only guard before any network, bank measurement or optimizer work."""
    from game_predictor_api.domain.grid_render_reference import require_reference_v2

    from .production_cell_evaluation import reference_context

    for snapshot in snapshots:
        expected = (
            snapshot.manifest["photoSplit"].get("contentSampling", {}).get("evaluationContract")
        )
        if crop_policy is not None and (
            crop_policy != "full-cell-v2"
            or expected is None
            or expected.get("classifier", {}).get("cropPolicyVersion") != crop_policy
            or expected.get("renderConfiguration", {}).get("paddingFraction") != 0
        ):
            raise ValueError("CONTENT_FULL_CELL_RENDER_REQUIRED")
        configurations: set[str] = set()
        for source in snapshot.sources() if expected is not None else ():
            if not source.get("used"):
                continue
            for target in source["targets"]:
                pin = target.get("productionContentReference")
                is_a = (
                    source.get("role") == "VALIDATION"
                    and source.get("validationPurpose", "A") == "A"
                )
                if pin is None:
                    if is_a or source.get("role") == "TRAIN":
                        raise ValueError("CONTENT_RENDER_REFERENCE_MISSING")
                    continue
                require_reference_v2(pin, snapshot.manifest["gameId"])
                if pin["evaluationContract"] != expected:
                    raise ValueError("CONTENT_RENDER_CONTRACT_MIXED")
                if is_a and pin.get("measurement") is None:
                    raise ValueError("CONTENT_A_MEASUREMENT_REQUIRED")
                context = reference_context(target)
                if context is None:
                    if is_a:
                        raise ValueError("CONTENT_RENDER_REFERENCE_MISSING")
                    continue
                configurations.add(digest(context["renderConfiguration"]))
        if expected is not None and len(configurations) != 1:
            raise ValueError("CONTENT_RENDER_CONTRACT_MIXED")
        reference = ProductionContentRun(snapshot, roles=("VALIDATION",))
        if reference.reasons:
            raise ValueError("CONTENT_SELECTION_REFERENCE_NOT_EVALUABLE")


def torch_engine(network: Any, recipe: Any, device: str) -> NeuralGridEngine:
    """The production decoder with actual trained tensors, no GT-generated detections."""
    screen_graph, board_graph = (
        ScreenExport(network.screen).eval(),
        BoardExport(network.board).eval(),
    )

    @torch.inference_mode()
    def screen(pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        with evaluation_precision():
            outputs = screen_graph(torch.from_numpy(pixels).to(device))
        return tuple(v.float().cpu().numpy() for v in outputs)

    @torch.inference_mode()
    def board(pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        with evaluation_precision():
            outputs = board_graph(torch.from_numpy(pixels).to(device))
        return tuple(v.float().cpu().numpy() for v in outputs)

    return NeuralGridEngine(screen, board, DecodeSettings.of(recipe))


def measure_bank(
    plan: Mapping[str, Any],
    inputs: Mapping[str, Any],
    snapshots: Sequence[Any],
    engine: Any,
    before_photo: Any,
) -> dict[str, Any]:
    """Measure only positively proven TRAIN. An error-free bank remains an honest bank."""
    verify_inputs(plan, inputs, snapshots)
    games = []
    for snapshot in sorted(snapshots, key=lambda s: s.manifest["gameId"]):
        game = snapshot.manifest["gameId"]
        proof = next(g for g in inputs["trainEligibility"]["games"] if g["gameId"] == game)
        allowed = {s["sourceId"]: s for s in proof["sources"]}
        rows = []
        for source, labels in ContentTrainingDataset(snapshot, "TRAIN").indexed():
            if source["sourceId"] not in allowed:
                continue
            before_photo()
            frame = snapshot.frame(source, "TRAIN")
            found = engine.analyse(frame.rgb)
            evaluation = evaluate_photo(
                source["sourceId"],
                source["sourceId"],
                [n for n, _ in labels],
                predictions(found),
                full_geometry=has_full_geometry(source),
            )
            rows.append(
                {
                    "source": allowed[source["sourceId"]],
                    "metrics": evaluation.as_dict(),
                    "detections": [
                        {
                            "screenQuad": d.screen_quad.tolist(),
                            "nodes": None if d.nodes is None else d.nodes.tolist(),
                        }
                        for d in found
                    ],
                }
            )
        if {r["source"]["sourceId"] for r in rows} != set(allowed):
            raise ValueError("CONTENT_BANK_SOURCE_UNAVAILABLE")
        rows.sort(key=lambda row: row["source"]["sourceId"])
        reasons = (
            ["CONTENT_BANK_NO_ELIGIBLE_SOURCES"]
            if not rows
            else ["CONTENT_BANK_NO_GEOMETRY_ERRORS"]
            if all(
                row["metrics"].get("full_geometry") is True
                and row["metrics"].get("complete_correct_strict") is True
                for row in rows
            )
            else []
        )
        games.append(
            {
                "gameId": game,
                "eligibilitySha256": proof["sha256"],
                "sources": rows,
                "reasonCodes": reasons,
            }
        )
    body = {
        "schemaVersion": "content-base-error-bank-v1",
        "planSha256": plan["sha256"],
        "baseWeightsSha256": plan["baseWeightsSha256"],
        "trainEligibilitySha256": inputs["trainEligibility"]["sha256"],
        "games": games,
    }
    return {**body, "sha256": digest(body)}


def auxiliary(photos: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    rank = {"preserved": 0, "borderline": 1, "clipped": 2, "missing": 2}
    counts = {
        "baselineUsablePhotos": 0,
        "candidateUsablePhotos": 0,
        "newClipped": 0,
        "newBorderline": 0,
        "newDamagedInstances": 0,
    }
    for photo in photos:
        for name, key in (("base", "baselineUsablePhotos"), ("candidate", "candidateUsablePhotos")):
            counts[key] += bool(
                photo["fullGeometry"]
                and photo["boards"]
                and all(b[name]["usable"] for b in photo["boards"])
            )
        for board in photo["boards"]:
            ambiguity = board["candidate"]["matchAmbiguous"] and not board["base"]["matchAmbiguous"]
            for cell in board["cells"]:
                if cell["contentState"] != "visible":
                    continue
                before, after = cell["base"], cell["candidate"]
                for state, key in (("clipped", "newClipped"), ("borderline", "newBorderline")):
                    counts[key] += (
                        after["finalContentState"] == state and before["finalContentState"] != state
                    )
                counts["newDamagedInstances"] += bool(
                    ambiguity
                    or rank[after["finalContentState"]] > rank[before["finalContentState"]]
                    or any(
                        after[k] and not before[k]
                        for k in ("wrongCell", "tie", "foreignFullSymbol")
                    )
                )
    return counts


class ContentSelectionEvaluator:
    """A only, including its frozen u/delta; B/REG pixels and GT are never requested."""

    def __init__(
        self,
        snapshots: Sequence[Any],
        base: Any,
        recipe: Any,
        device: str,
        arm: str,
        step: Any,
        before_photo: Any,
        routing: Any = None,
    ) -> None:
        self.snapshots, self.base, self.recipe, self.device = snapshots, base, recipe, device
        self.arm, self.step, self.before_photo = arm, step, before_photo
        self.routing = routing
        self.references = {
            s.manifest["gameId"]: ProductionContentRun(s, roles=("VALIDATION",)) for s in snapshots
        }

    def __call__(self, network: Any) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.measure(torch_engine(network, self.recipe, self.device))["selection"],
        )

    def measure(self, candidate: Any) -> dict[str, Any]:
        """The same frozen A and production crops for checkpoint and exported engines."""
        from .grid_content_consistency import photo_outcome

        if self.arm in ("R2", "R3"):
            if self.routing is None:
                raise ValueError("CONTENT_EXPERIMENT_ROUTING_REQUIRED")
            candidate = ContentAssessmentEngine(candidate, self.routing)
        rows: list[dict[str, Any]] = []
        photos_proof: list[dict[str, Any]] = []
        for snapshot in sorted(self.snapshots, key=lambda s: s.manifest["gameId"]):
            reference = self.references[snapshot.manifest["gameId"]]
            if reference.reasons:
                raise ValueError("CONTENT_SELECTION_REFERENCE_NOT_EVALUABLE")
            groups = {
                s["sourceId"]: s["sourceId"]
                for s, _ in GridBoardDataset(snapshot, "VALIDATION").indexed()
            }
            photos = GridModelEvaluationJobHandler._photos(
                snapshot, "VALIDATION", groups, correction=True
            )
            quality, details = measure_role(
                cast(Sequence[CorrectionControlPhoto], photos),
                self.base,
                candidate,
                before_photo=lambda _: self.before_photo(),
                content_observation=reference.observer("VALIDATION"),
            )
            observed = [d["contentEvaluation"] for d in details]
            photos_proof.extend(
                {
                    "gameId": snapshot.manifest["gameId"],
                    "manifestSha256": snapshot.manifest_sha256,
                    "sourceId": detail["sourceId"],
                    "referenceSha256": detail["contentEvaluation"]["referenceSha256"],
                    "outcomeSha256": digest(photo_outcome(detail)),
                }
                for detail in details
            )
            rows.append(
                {
                    "gameId": snapshot.manifest["gameId"],
                    "quality": quality,
                    "content": summarize_content(observed),
                    "u": reference.u,
                    "delta": reference.delta,
                    "measurementSha256": reference.measurement_sha,
                    "auxiliary": auxiliary(observed),
                }
            )
        return {"selection": selection_record(rows, self.arm, self.step()), "photos": photos_proof}
