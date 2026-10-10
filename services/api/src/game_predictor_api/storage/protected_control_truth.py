"""Read-only frozen human truth and current approval checks for pilot promotion."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import numpy as np
from game_predictor_worker.images.normalization import rgb_pixel_checksum_sha256
from game_predictor_worker.symbols import protected_sources as protections
from PIL import Image
from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.application.virtual_cell_previews import render_virtual_symbol_cell_png
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.lab_symbol_candidate import MUMIE_CLASS_CODES, MUMIE_CLASS_LABELS
from game_predictor_api.domain.protected_control_truth import (
    TRUTH_VERSION,
    ControlTruth,
    CurrentControlDecision,
    compare_control_truth,
    truth_quad,
)
from game_predictor_api.storage.symbol_cell_training_source_repository import (
    _virtual_asset,
    _with_manifest_render_specs,
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _json(content: bytes) -> Mapping[str, Any]:
    value = json.loads(content)
    if "payload" in value:
        if _digest(value["payload"]) != value.get("sha256"):
            raise ValueError("A human proof envelope has drifted.")
        value = value["payload"]
    if not isinstance(value, dict):
        raise ValueError("A human proof must be a JSON object.")
    return cast(Mapping[str, Any], value)


def load_control_truth(
    artifact_root: Path, game_id: UUID
) -> tuple[tuple[ControlTruth, ...], dict[str, object]]:
    """Verify the code-pinned descriptor, originals and every frozen human proof."""
    try:
        protected = protections.load_protected_sources(artifact_root, str(game_id))
        if protected is None:
            raise ValueError("Control truth is scoped to the Mumie pilot.")
        data_root = artifact_root.resolve() / "data"
        envelope = _json(
            protections.managed_path(data_root, protections.DESCRIPTOR_PATH).read_bytes()
        )
        if _digest(envelope) != protections.DESCRIPTOR_SHA256:
            raise ValueError("Frozen descriptor changed between reads.")
        if envelope.get("controlTruthVersion") != TRUTH_VERSION:
            raise ValueError("The frozen human truth descriptor is missing.")
        proofs: dict[str, tuple[str, bytes]] = {}
        for proof in envelope["controlTruthProofs"]:
            content = protections.managed_path(data_root, proof["relativePath"]).read_bytes()
            checksum = hashlib.sha256(content).hexdigest()
            if checksum != proof["fileChecksumSha256"] or checksum != proof["proofId"]:
                raise ValueError("A frozen human proof file has drifted.")
            if checksum in proofs:
                raise ValueError("Duplicate human proof reference.")
            proofs[checksum] = (proof["kind"], content)
        rows = envelope["controlTruthRows"]
        mappings = envelope["controlTruthSymbolMappings"]
        if (
            tuple(m["dbSymbolCode"] for m in mappings) != MUMIE_CLASS_CODES
            or tuple(m["labDisplayName"] for m in mappings) != MUMIE_CLASS_LABELS
        ):
            raise ValueError(
                "Frozen lab-to-DB symbol mapping differs from the qualified R2 catalog."
            )
        codes = {}
        for mapping in mappings:
            kind, content = proofs[mapping["proofId"]]
            dictionary = _json(content)["dictionary"]
            entries = [e for e in dictionary["entries"] if e["id"] == mapping["labSymbolId"]]
            if (
                kind != "preparation"
                or len(entries) != 1
                or (entries[0]["code"], entries[0]["display_name"])
                != (mapping["labCode"], mapping["labDisplayName"])
                or mapping["labSymbolId"] in codes
            ):
                raise ValueError(
                    "The explicit symbol mapping has no unique frozen lab dictionary proof."
                )
            codes[mapping["labSymbolId"]] = mapping["dbSymbolCode"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("Frozen human controls cannot be empty.")
        truths = []
        for row in rows:
            truth = ControlTruth.from_payload(row)
            if codes.get(truth.symbol_id) != truth.symbol_code:
                raise ValueError("The human label has no qualified lab-to-DB symbol mapping.")
            if (
                truth.source_byte_sha256 not in protected.byte_checksums
                or truth.source_pixel_sha256 not in protected.pixel_checksums
            ):
                raise ValueError("Human truth is outside the frozen protected sources.")
            kind, proof_content = proofs[truth.proof_id]
            proof = _json(proof_content)
            if kind == "preparation":
                decisions = [
                    s["decision"]
                    for s in proof["samples"]
                    if s["decision"]["decision_id"] == truth.decision_id
                ]
                if len(decisions) != 1:
                    raise ValueError("A control has no unique immutable human decision.")
                decision = decisions[0]
                binding = decision["binding"]
                actual = (
                    binding["source_sha256"],
                    binding["board_index"],
                    binding["cell_index"],
                    truth_quad(binding["quad"]),
                )
            elif kind == "feedback_manifest":
                decisions = [d for d in proof["decisions"] if d["decision_id"] == truth.decision_id]
                if len(decisions) != 1:
                    raise ValueError("A control has no unique batch human decision.")
                decision = decisions[0]
                cases = [c for c in proof["cases"] if c["case_id"] == decision["case_id"]]
                if len(cases) != 1:
                    raise ValueError("A human decision has no immutable crop binding.")
                binding = cases[0]
                actual = (
                    binding["source"]["sha256"],
                    binding["board"] - 1,
                    binding["field"] - 1,
                    truth_quad(binding["quad"]),
                )
            else:
                raise ValueError("Unknown human proof origin.")
            if actual != (
                truth.source_byte_sha256,
                truth.position_index,
                truth.cell_index,
                truth.source_quad,
            ) or (
                decision["symbol_id"],
                decision["origin"],
                decision["actor"],
                decision["action"],
                decision["revision"],
            ) != (
                truth.symbol_id,
                truth.origin,
                row["actor"],
                row["action"],
                row["decisionRevision"],
            ):
                raise ValueError("Frozen control labels or provenance differ from the human proof.")
            crop_kind, crop_content = proofs[row["cropProofId"]]
            if crop_kind != "crop_png" or row["cropProofId"] != binding["byte_sha256"]:
                raise ValueError("A control has no immutable crop pixels.")
            with Image.open(BytesIO(crop_content)) as image:
                rgb = np.asarray(image.convert("RGB"))
            if (
                rgb.shape != (96, 96, 3)
                or hashlib.sha256(rgb.tobytes()).hexdigest() != binding["pixel_sha256"]
                or rgb_pixel_checksum_sha256(rgb) != truth.crop_pixel_sha256
            ):
                raise ValueError("Frozen crop pixels differ from the exact human approval.")
            truths.append(truth)
        if len({t.control_id for t in truths}) != len(truths):
            raise ValueError("Duplicate control truth identity.")
        return tuple(truths), protected.reference()
    except (protections.ProtectedSourceError, OSError, ValueError, KeyError, TypeError) as error:
        raise JobConflictError(
            "PROTECTED_CONTROL_TRUTH_PROOF_INVALID",
            "Brak lub zmiana zamrożonego dowodu ludzkiej oceny "
            "blokuje promocję nowego modelu Mumii.",
            details={"status": "PROOF_INVALID", "reason": str(error)},
        ) from error


_CURRENT_QUERY = """
SELECT c.*, rb.position_index, rb.geometry_revision AS current_geometry_revision,
       rb.source_geometry_revision_id AS current_source_geometry_revision_id,
       src.relative_path AS source_relative_path, src.checksum_sha256 AS source_checksum_sha256,
       COALESCE(src.oriented_width, src.width) AS source_width,
       COALESCE(src.oriented_height, src.height) AS source_height,
       COALESCE(src.normalized_pixel_checksum_sha256,
                sgr.normalized_pixel_checksum_sha256) AS normalized_pixel_checksum_sha256,
       sgr.geometry_checksum_sha256, sym.code AS assigned_symbol_code
FROM image_symbol_review_cells c
JOIN recognized_boards rb ON rb.id = c.recognized_board_id
JOIN source_images src ON src.id = rb.source_image_id
JOIN image_source_geometry_revisions sgr ON sgr.id = c.source_geometry_revision_id
LEFT JOIN symbols sym ON sym.id = c.assigned_symbol_id AND sym.game_id = c.game_id
JOIN image_board_search_fast_documents d ON d.game_id = c.game_id
 AND d.sequence_number = c.sequence_number AND d.review_item_id = c.review_item_id
WHERE c.game_id = :game_id AND
 (src.checksum_sha256 = ANY(CAST(:byte_checksums AS text[])) OR
  COALESCE(src.normalized_pixel_checksum_sha256,
           sgr.normalized_pixel_checksum_sha256) = ANY(CAST(:pixel_checksums AS text[])))
ORDER BY c.sequence_number, c.cell_index, c.id
"""


def current_control_decisions(
    session: Session,
    artifact_root: Path,
    game_id: UUID,
    truths: tuple[ControlTruth, ...],
    *,
    lock: bool,
) -> tuple[CurrentControlDecision, ...]:
    """Lock even pending controls at promotion, so a concurrent approval cannot race it."""
    query = _CURRENT_QUERY + (" FOR SHARE OF c, rb, src, sgr, d" if lock else "")
    rows = tuple(
        session.execute(
            text(query),
            {
                "game_id": game_id,
                "byte_checksums": sorted({t.source_byte_sha256 for t in truths}),
                "pixel_checksums": sorted({t.source_pixel_sha256 for t in truths}),
            },
        ).mappings()
    )
    approved = tuple(
        row
        for row in rows
        if row["review_state"] == "approved"
        and row["assignment_source"] in {"human", "board_decision"}
        and row["assigned_symbol_id"] is not None
        and row["source_available"]
        and row["asset_mode"] == "virtual_source"
        and all(
            row[current] == row[expected]
            for current, expected in (
                ("crop_sample_id", "approved_crop_sample_id"),
                ("crop_checksum_sha256", "approved_crop_checksum_sha256"),
                ("geometry_revision", "approved_geometry_revision"),
                ("geometry_revision", "current_geometry_revision"),
                ("asset_mode", "approved_asset_mode"),
                ("source_geometry_revision_id", "approved_source_geometry_revision_id"),
                ("source_geometry_revision_id", "current_source_geometry_revision_id"),
                ("render_spec_checksum_sha256", "approved_render_spec_checksum_sha256"),
                ("rendered_pixel_checksum_sha256", "approved_rendered_pixel_checksum_sha256"),
            )
        )
    )
    if not approved:
        return ()
    try:
        specs = _with_manifest_render_specs(session, game_id=game_id, rows=approved)
        decisions = []
        source_pixels: dict[str, str] = {}
        for row in specs:
            byte = str(row["source_checksum_sha256"])
            if byte not in source_pixels:
                source_pixels[byte] = protections.source_pixel_identity(
                    artifact_root / "data", str(row["source_relative_path"]), byte
                )
            if source_pixels[byte] != row["normalized_pixel_checksum_sha256"]:
                raise ValueError("Current source decoded pixels differ from its persisted binding.")
            quad = truth_quad(row["render_spec"]["paddedSourceQuad"])
            matches = [
                t
                for t in truths
                if (
                    t.source_pixel_sha256,
                    t.source_width,
                    t.source_height,
                    t.position_index,
                    t.cell_index,
                    t.source_quad,
                    t.crop_pixel_sha256,
                )
                == (
                    source_pixels[byte],
                    row["source_width"],
                    row["source_height"],
                    row["position_index"],
                    row["cell_index"],
                    quad,
                    row["rendered_pixel_checksum_sha256"],
                )
            ]
            if not matches:
                continue
            if not isinstance(row["assigned_symbol_code"], str):
                raise ValueError("Current human label has no symbol in the current game catalog.")
            render_virtual_symbol_cell_png(artifact_root=artifact_root, asset=_virtual_asset(row))
            decisions.append(
                CurrentControlDecision(
                    cell_id=str(row["id"]),
                    source_pixel_sha256=source_pixels[byte],
                    source_width=int(row["source_width"]),
                    source_height=int(row["source_height"]),
                    position_index=int(row["position_index"]),
                    cell_index=int(row["cell_index"]),
                    source_quad=quad,
                    crop_pixel_sha256=str(row["rendered_pixel_checksum_sha256"]),
                    symbol_id=str(row["assigned_symbol_id"]),
                    symbol_code=row["assigned_symbol_code"],
                    revision=int(row["revision"]),
                    source_geometry_revision_id=str(row["source_geometry_revision_id"]),
                )
            )
        return tuple(decisions)
    except ValueError as error:
        raise JobConflictError(
            "PROTECTED_CONTROL_CURRENT_PROVENANCE_INVALID",
            "Bieżący crop kontrolny ma niezgodną proweniencję. "
            "Odśwież ocenę przed promocją modelu.",
            details={"status": "PROVENANCE_INVALID", "reason": str(error)},
        ) from error


def require_control_truth_promotion(
    session: Session,
    artifact_root: Path,
    game_id: UUID,
    configuration: Mapping[str, object],
    *,
    lock: bool,
) -> dict[str, object]:
    truths, reference = load_control_truth(artifact_root, game_id)
    if configuration.get("protectedSourceExclusions") != reference:
        raise JobConflictError(
            "PROTECTED_CONTROL_CANDIDATE_UNQUALIFIED",
            "Kandydat nie pochodzi z kohorty przypiętej do aktualnej ochrony kontrolnych źródeł.",
        )
    report = compare_control_truth(
        truths, current_control_decisions(session, artifact_root, game_id, truths, lock=lock)
    )
    if report["status"] == "OPEN":
        raise JobConflictError(
            "PROTECTED_CONTROL_TRUTH_CONFLICT_OPEN",
            "OPEN: bieżąca ludzka etykieta tego samego wycinka różni się "
            "od zamrożonej prawdy kontrolnej. Promocja nowego modelu Mumii jest zablokowana.",
            details=report,
        )
    return report
