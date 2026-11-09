"""Bounded READ ONLY diagnostic capture from existing cohort, approvals and ledger."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_cell_content import content_source_identity
from game_predictor_api.domain.grid_training_cohorts import GridCohortError, digest
from game_predictor_api.domain.grid_validation_purpose import require_purpose_protection
from game_predictor_api.domain.symbol_model_snapshots import (
    LAB_RGB_SYMBOL_MODEL_VERSION,
    SymbolModelJobSnapshot,
)

from .grid_cell_content import SqlAlchemyGridCellContentRepository
from .grid_cell_content_models import GridCellContentSessionModel
from .grid_cell_content_pins import apply_blind_a_geometry, content_pin
from .grid_content_diagnostic_measurement import diagnostic_measurement_ready
from .grid_content_preview import protected_source
from .grid_correction_split import contexts
from .grid_model_registry_models import GridModelVersionModel
from .grid_quality_observations import current_targets, own_target
from .grid_training_cohort_evidence import GridCohortEvidenceReader
from .models import SymbolModelIterationModel
from .production_cell_reference import capture_production_reference

CAPTURE_VERSION = "production-crop-capture-v1"
MAX_SOURCES = 50


def _blind_aliases(repo: Any, game: UUID, selected: dict[str, Any]) -> dict[str, list[str]]:
    rows = list(
        repo.session.execute(
            text("""SELECT DISTINCT
        t.value->'source'->>'sourceId' AS source_id, c.phase
        FROM grid_cell_content_sessions c,
        LATERAL jsonb_array_elements(c.document->'targets') t(value)
        WHERE c.game_id=:g LIMIT 2001"""),
            {"g": game},
        ).mappings()
    )
    if len(rows) > 2000 or any(not row["source_id"] for row in rows):
        raise ValueError("CROP_BLIND_PROTECTION_UNAVAILABLE")
    ids = sorted({str(UUID(row["source_id"])) for row in rows})
    aliases = contexts(repo, game, ids, purpose_aware=True) if ids else {}
    if any(
        not value.get("proofSha256") or not isinstance(value.get("aliasComponentIds"), list)
        for value in aliases.values()
    ):
        raise ValueError("CROP_BLIND_PROTECTION_UNAVAILABLE")
    result: dict[str, list[str]] = {key: [] for key in selected}
    for key, own in selected.items():
        own_ids = set(own.get("aliasComponentIds", [])) | set(own.get("componentIds", []))
        for row in rows:
            other = aliases[row["source_id"]]
            other_ids = set(other.get("aliasComponentIds", [])) | set(other.get("componentIds", []))
            if key == row["source_id"] or own_ids & other_ids:
                result[key].append(row["phase"])
    return result


def _closure_pin(value: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "sourceId",
        "proofSha256",
        "allowedRoles",
        "priorRoles",
        "photoRoles",
        "aliasComponentIds",
        "componentIds",
        "validationPurposes",
        "diagnosticExposed",
        "selectionExposed",
    )
    return {**{k: value.get(k) for k in keys}, "contextSha256": digest(value)}


def role_reason(
    source: dict[str, Any], closure: dict[str, Any], split: dict[str, Any]
) -> str | None:
    role = source.get("role")
    if (
        source.get("used") is not True
        or role not in ("TRAIN", "VALIDATION")
        or (role == "VALIDATION" and source.get("validationPurpose") != "A")
    ):
        return "CROP_ROLE_PROTECTED"
    if (
        closure.get("sourceId") != source.get("sourceId")
        or not closure.get("proofSha256")
        or not isinstance(closure.get("aliasComponentIds"), list)
        or role not in closure.get("allowedRoles", [])
        or set(closure.get("priorRoles", [])) - {role}
        or split.get("buffer")
        or split.get("detectorExcluded")
    ):
        return "CROP_ROLE_CLOSURE_UNAVAILABLE"
    if role == "VALIDATION":
        try:
            require_purpose_protection(closure, "A")
        except GridCohortError:
            return "CROP_VALIDATION_PURPOSE_PROTECTED"
    elif closure.get("validationPurposes"):
        return "CROP_VALIDATION_ALIAS_PROTECTED"
    return None


def _measurement(
    session: Session, game: UUID, session_ids: set[str] | None = None
) -> dict[str, Any] | None:
    if session_ids is not None and len(session_ids) != 1:
        return None
    reports = session.scalars(
        select(GridCellContentSessionModel)
        .where(
            GridCellContentSessionModel.game_id == game,
            GridCellContentSessionModel.phase == "frozen",
            GridCellContentSessionModel.report.is_not(None),
            *(
                []
                if session_ids is None
                else [GridCellContentSessionModel.id.in_([UUID(s) for s in session_ids])]
            ),
        )
        .limit(51)
    ).all()
    if len(reports) > 50:
        return None
    qualified, diagnostic = {}, {}
    for measured in reports:
        report = measured.report
        assert report is not None
        item = report.get("games", {}).get(str(game), {})
        if (
            report.get("sha256") == digest({k: v for k, v in report.items() if k != "sha256"})
            and report.get("version") == "cell-content-repeatability-v1"
            and report.get("quantile") == "nearest-rank-p95-v1"
            and report.get("state") == "ready"
            and item.get("state") == "ready"
            and type(item.get("u")) in (int, float)
            and 0 <= item["u"] <= 0.02
            and type(item.get("delta")) in (int, float)
            and 0 <= item["delta"] <= 0.002
        ):
            if report.get("qualificationState") == "ready":
                qualified[report["sha256"]] = report
            else:
                diagnostic[report["sha256"]] = measured
    if qualified:
        return next(iter(qualified.values())) if len(qualified) == 1 else None
    available = {
        sha: measured.report
        for sha, measured in diagnostic.items()
        if diagnostic_measurement_ready(session, game, measured)
    }
    return next(iter(available.values())) if len(available) == 1 else None


def _policy(
    session: Session, payload: dict[str, Any], artifact_root: Path, repository_root: Path
) -> dict[str, Any] | None:
    from game_predictor_worker.images.production_crop_artifacts import read_json
    from game_predictor_worker.images.production_crop_classification import current_runtime_pin

    model = SymbolModelJobSnapshot.from_payload(payload)
    if model.inference_mode != "model":
        return None
    runtime = current_runtime_pin(model)
    runtime_evidence = {
        "runtime": runtime,
        "runtimeAutoAccept": runtime["pipeline"]["manifest"]["policies"]["reviewBoundary"][
            "autoAcceptEnabled"
        ],
    }
    if model.iteration_id is None:
        # Existing canonical M6 artifact; only exact model/report identities
        # are accepted downstream. Runtime scope is explicitly today's diagnostic.
        component = runtime["pipeline"]["manifest"]["components"]["symbol_inference"]
        pins = [p for p in component["artifacts"] if p["role"] == "symbol-confidence-calibration"]
        if component["modelVersion"] != model.model_version or len(pins) != 1:
            return None
        pin = pins[0]
        return {
            **runtime_evidence,
            "artifact": pin,
            "report": read_json(repository_root, pin["relativePath"], pin["sha256"]),
        }
    iteration = session.get(SymbolModelIterationModel, model.iteration_id)
    if (
        iteration is None
        or iteration.candidate_manifest_checksum_sha256 != model.manifest_checksum_sha256
        or iteration.candidate_manifest_relative_path is None
    ):
        return None
    manifest = read_json(
        artifact_root, iteration.candidate_manifest_relative_path, model.manifest_checksum_sha256
    )
    pin = cast(dict[str, Any], manifest.get("artifacts", {})).get("calibration")
    if pin is None:
        return None
    report = read_json(artifact_root, pin["relativePath"], pin["sha256"])
    result = {
        **runtime_evidence,
        "artifact": pin,
        "report": report,
        "candidateManifest": manifest,
        "candidateManifestSha256": model.manifest_checksum_sha256,
        "configurationInputSize": iteration.configuration_payload.get("inputSize"),
    }
    classes_pin = manifest.get("artifacts", {}).get("classes")
    if classes_pin is not None:
        result["classCodes"] = read_json(
            artifact_root, classes_pin["relativePath"], classes_pin["sha256"]
        ).get("classCodes")
    return result


def _classes(session: Session, game: UUID, target: dict[str, Any]) -> list[dict[str, Any]]:
    from game_predictor_worker.images.production_crop_classification import human_class

    board = target["board"]
    if not own_target(target):
        return [
            {"state": "unavailable", "reason": "CLASS_CURRENT_OWNER_UNAVAILABLE"} for _ in range(15)
        ]
    review = target["review"]
    rows = list(
        session.execute(
            text("""SELECT to_jsonb(c) AS cell, s.code
        FROM image_symbol_review_cells c JOIN symbols s ON s.id=c.assigned_symbol_id
        JOIN recognized_boards rb ON rb.id=c.recognized_board_id AND rb.game_id=c.game_id
        JOIN source_images src ON src.id=rb.source_image_id AND src.game_id=c.game_id
        WHERE c.game_id=:g AND c.recognized_board_id=CAST(:b AS uuid)
        AND c.review_item_id=CAST(:r AS uuid)
        AND public.source_replacement_current_v1(
            c.game_id,src.id,src.checksum_sha256,c.sequence_number,c.review_item_id)
        AND s.game_id=:g AND s.status='active' ORDER BY c.cell_index"""),
            {"g": game, "b": board["id"], "r": review["id"]},
        ).mappings()
    )
    events = list(
        session.execute(
            text("""SELECT to_jsonb(e) || jsonb_build_object('human_board_decision', EXISTS (
            SELECT 1 FROM image_review_resolution_events b
            JOIN image_review_items i ON i.id=b.review_item_id AND i.game_id=b.game_id
            WHERE b.game_id=c.game_id AND b.review_item_id=c.review_item_id
            AND b.revision=i.resolution_revision AND b.resolved_by=e.actor
            AND b.action IN ('accepted','corrected') AND i.status IN ('accepted','corrected')
        ))
        FROM image_symbol_review_events e JOIN image_symbol_review_cells c ON c.id=e.cell_review_id
        WHERE c.game_id=:g AND c.recognized_board_id=CAST(:b AS uuid)
        AND c.review_item_id=CAST(:r AS uuid)
        AND e.cell_revision=c.revision
        AND e.action IN ('approve','reassign','board_synchronized')"""),
            {"g": game, "b": board["id"], "r": review["id"]},
        ).scalars()
    )
    rows = [r for r in rows if r["cell"].get("review_item_id") == review["id"]]
    active = {r["cell"]["assigned_symbol_id"]: r["code"] for r in rows}
    by_index = {r["cell"]["cell_index"]: r["cell"] for r in rows}
    return [
        human_class(by_index[j], events, board, active)
        if j in by_index
        else {"state": "unavailable", "reason": "CLASS_REFERENCE_MISSING"}
        for j in range(15)
    ]


def capture(
    session: Session,
    *,
    artifact_root: Path,
    repository_root: Path,
    game: UUID,
    cohort: UUID,
    manifest_sha256: str,
    source_ids: list[UUID],
    grid_version: UUID | None = None,
    lab_iteration: UUID | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Caller holds one READ ONLY transaction. No bytes are read before protection."""
    from game_predictor_worker.images.production_crop_artifacts import sealed

    if not 1 <= len(source_ids) <= MAX_SOURCES or len(set(source_ids)) != len(source_ids):
        raise ValueError("CROP_SOURCE_SELECTION_INVALID")
    if session.scalar(text("SHOW transaction_read_only")) != "on":
        raise ValueError("CROP_READ_ONLY_TRANSACTION_REQUIRED")
    repo = SqlAlchemyGridCellContentRepository(session, artifact_root)
    repo.bind(game)
    snapshot = repo.snapshot(game, cohort, manifest_sha256)
    selected = {str(i) for i in source_ids}
    sources = {s["sourceId"]: s for s in snapshot.sources() if s["sourceId"] in selected}
    if set(sources) != selected:
        raise ValueError("CROP_SOURCE_MEMBERSHIP_CHANGED")
    closure = contexts(repo, game, sorted(selected), purpose_aware=True)
    blind_aliases = _blind_aliases(repo, game, closure)
    split = {s["sourceId"]: s for s in snapshot.manifest["photoSplit"]["sources"]}
    reader = GridCohortEvidenceReader(session, artifact_root)
    measurement = _measurement(session, game)
    photos, seen = [], set()
    for key, frozen in sorted(sources.items()):
        identity = content_source_identity(frozen["sourceIdentity"])
        reason = role_reason(frozen, closure[key], split.get(key, {}))
        if identity.sourceRepresentativeSha256 in seen:
            reason = "CROP_PIXEL_ALIAS_DUPLICATE"
        seen.add(identity.sourceRepresentativeSha256)
        if reason is None and repo.current_source(game, UUID(key)) != identity:
            reason = "CROP_SOURCE_IDENTITY_CHANGED"
        if reason is None and frozen["role"] == "TRAIN" and protected_source(repo, game, identity):
            reason = "CROP_BLIND_SOURCE_PROTECTED"
        if reason is None and frozen["role"] == "TRAIN" and blind_aliases[key]:
            reason = "CROP_BLIND_ALIAS_PROTECTED"
        # A is metrics-only and requires every selected target's completed independent pass.
        a_pins = {}
        photo_measurement = measurement
        if reason is None and frozen["role"] == "VALIDATION":
            for t in frozen["targets"]:
                pin = content_pin(
                    session,
                    game,
                    frozen["sourceIdentity"],
                    t,
                    purpose="A",
                    diagnostic_mode="render-clipping-only",
                )
                if not pin:
                    reason = "CROP_BLIND_A_NOT_FROZEN"
                    break
                a_pins[t["positionIndex"]] = pin
            # The current pins, not unrelated abandoned sessions, select the
            # independent frozen measurement used by internal A scoring.
            ids = {p["contentAnnotation"]["sessionId"] for p in a_pins.values()}
            photo_measurement = _measurement(session, game, ids) if ids else None
            if photo_measurement is None:
                reason = "CROP_BLIND_A_NOT_FROZEN"
        photo = {
            "sourceId": key,
            "role": "A" if frozen["role"] == "VALIDATION" else frozen["role"],
            "frozenSource": None if reason else frozen,
            "protection": {
                "closure": _closure_pin(closure[key]),
                "reason": reason,
                "blindAliasPhases": sorted(set(blind_aliases[key])),
            },
            "state": "unavailable" if reason else "available",
            "reasonCodes": [reason] if reason else [],
            "targets": [],
            "instanceCount": 15 * len(frozen["targets"]),
            "measurement": photo_measurement,
        }
        photos.append(photo)
        if reason:
            continue
        # Existing reader checks human geometry, source revision, slots, owner and renders.
        current = reader.capture(
            game,
            UUID(key),
            frozen.get("ordinal", 0),
            {"role": frozen["role"], "qualification": "eligible", "reasonCodes": []},
            "grid-only",
        )
        targets = {p["positionIndex"]: p for p in current["positions"]}
        live = current_targets(session, game, UUID(key))
        for original in sorted(frozen["targets"], key=lambda t: t["positionIndex"]):
            position = original["positionIndex"]
            item = targets[position]
            if (
                item["label"] is None
                or item["label"]["sequenceNumber"] != original["sequenceNumber"]
            ):
                photo["state"] = "unavailable"
                photo["reasonCodes"].append(item["reason"] or "CROP_SEQUENCE_CHANGED")
                continue
            target = copy.deepcopy(item["label"])
            target.update(
                a_pins[position]
                if a_pins
                else content_pin(session, game, current["source"], target, purpose="TRAIN")
            )
            if a_pins:
                target["classSourceNodes"] = copy.deepcopy(target["nodes"])
                target = apply_blind_a_geometry(target)
            target["productionContentReference"] = capture_production_reference(
                session, game, current["source"], target
            )
            target["classes"] = _classes(session, game, live[position])
            context = target["productionContentReference"]["sourceContext"]
            if context.get("state") == "available":
                try:
                    target["classificationPolicy"] = _policy(
                        session, context["classifier"], artifact_root, repository_root
                    )
                except (OSError, ValueError, KeyError):
                    target["classificationPolicy"] = None
            photo["targets"].append(target)
    a_reports = {
        p["measurement"]["sha256"] for p in photos if p["role"] == "A" and p["state"] == "available"
    }
    if len(a_reports) > 1:
        for photo in photos:
            if photo["role"] == "A":
                photo.update(state="unavailable", frozenSource=None, targets=[])
                photo["reasonCodes"].append("CROP_A_MEASUREMENT_NOT_UNIQUE")
    grid = None
    if grid_version is not None:
        row = session.get(GridModelVersionModel, grid_version)
        if row is None:
            raise ValueError("CROP_GRID_MODEL_UNAVAILABLE")
        from game_predictor_api.domain.grid_model_registry import descriptor_sha256

        manifest = json.loads(row.manifest_json)
        if descriptor_sha256(manifest) != row.manifest_sha256:
            raise ValueError("CROP_GRID_MANIFEST_CHANGED")
        grid = {
            "versionId": str(grid_version),
            "manifest": manifest,
            "manifestSha256": row.manifest_sha256,
        }
    lab = None
    lab_policy = None
    if lab_iteration is not None:
        from .lab_symbol_candidate_validation import require_iteration_candidate

        iteration = session.get(SymbolModelIterationModel, lab_iteration)
        if iteration is None or iteration.game_id != game or iteration.origin != "lab_import":
            raise ValueError("CROP_LAB_ITERATION_INVALID")
        candidate = require_iteration_candidate(session, artifact_root, iteration)
        from game_predictor_api.domain.symbol_model_snapshots import SymbolModelStorageRoot

        lab_manifest = cast(dict[str, Any], candidate.manifest)
        onnx = lab_manifest["artifacts"]["onnx"]
        lab = SymbolModelJobSnapshot(
            iteration_id=iteration.id,
            model_version=LAB_RGB_SYMBOL_MODEL_VERSION,
            manifest_checksum_sha256=candidate.manifest_sha256,
            onnx_checksum_sha256=onnx["sha256"],
            onnx_relative_path=onnx["relativePath"],
            storage_root=SymbolModelStorageRoot.ARTIFACT,
            class_codes=tuple(lab_manifest["classCodes"]),
            input_size=64,
            crop_size=96,
            temperature=1.05,
        ).to_payload()
        try:
            lab_policy = _policy(session, lab, artifact_root, repository_root)
        except (OSError, ValueError, KeyError):
            lab_policy = None
    return snapshot, sealed(
        {
            "schemaVersion": CAPTURE_VERSION,
            "diagnosticOnly": True,
            "qualificationAllowed": False,
            "gameId": str(game),
            "cohortId": str(cohort),
            "manifestSha256": manifest_sha256,
            "photos": photos,
            "measurement": measurement,
            "gridModel": grid,
            "labModel": lab,
            "labClassificationPolicy": lab_policy,
        }
    )
