"""Freeze and evaluate operator-approved audit pixels without writing domain data."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import torch
from game_predictor_api.application.grid_audit_proposals import FileGridAuditProposalStore
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import (
    create_maintenance_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_worker.symbols.audit_rgb_classifier import AuditRgbClassifier, rgb_batch
from game_predictor_worker.symbols.reference_library import normalize_rows
from numpy.typing import NDArray
from sqlalchemy import text

from scripts import evaluate_symbol_reference_library as reference
from scripts.recognize_grid_audit_symbols import write_json

type FloatArray = NDArray[np.float32]
type IndexArray = NDArray[np.int64]


def is_bulk_approval(action: str, operation_id: object) -> bool:
    """D-465: batch approval of model predictions is not a reference decision."""
    return action == "approve" and operation_id is not None


def safe_improvement(baseline: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """Lower total error cannot hide a regression in an individual symbol."""
    if candidate["cells"] != baseline["cells"] or candidate["errors"] >= baseline["errors"]:
        return False
    if set(candidate["perClass"]) != set(baseline["perClass"]):
        return False
    return all(
        candidate["perClass"][code]["cells"] == value["cells"]
        and candidate["perClass"][code]["errors"] <= value["errors"]
        for code, value in baseline["perClass"].items()
    )


def split_rows(rows: Sequence[dict[str, Any]]) -> tuple[list[str], list[int]]:
    """Source-bound split; exact duplicate pixels never cross split boundaries."""
    splits = []
    for row in rows:
        source = row["render_spec"]["sourceChecksumSha256"]
        bucket = (
            int(hashlib.sha256(("feedback-source-v1:" + source).encode()).hexdigest()[:8], 16) % 10
        )
        splits.append("test" if bucket < 2 else "validation" if bucket < 4 else "train")
    labels_by_pixels: dict[str, set[str]] = {}
    for row in rows:
        labels_by_pixels.setdefault(row["rendered_pixel_checksum_sha256"], set()).add(row["label"])
    owners: dict[str, str] = {}
    retained = []
    for index in sorted(
        range(len(rows)),
        key=lambda i: ({"train": 0, "validation": 1, "test": 2}[splits[i]], rows[i]["id"]),
    ):
        pixels = rows[index]["rendered_pixel_checksum_sha256"]
        if len(labels_by_pixels[pixels]) != 1 or (
            pixels in owners and owners[pixels] != splits[index]
        ):
            continue
        owners[pixels] = splits[index]
        retained.append(index)
    return splits, sorted(retained)


def metrics(expected: IndexArray, predicted: IndexArray, codes: Sequence[str]) -> dict[str, Any]:
    if expected.ndim != 1 or predicted.shape != expected.shape:
        raise ValueError("Metrics require equally sized one-dimensional labels.")
    return {
        "cells": len(expected),
        "errors": int((expected != predicted).sum()),
        "accuracy": float((expected == predicted).mean()) if len(expected) else None,
        "perClass": {
            code: {
                "cells": int((expected == index).sum()),
                "errors": int(((expected == index) & (predicted != expected)).sum()),
            }
            for index, code in enumerate(codes)
        },
    }


def reference_candidates(
    query: FloatArray,
    bank: FloatArray,
    bank_labels: IndexArray,
    bank_sources: Sequence[str],
    base: IndexArray,
) -> dict[str, IndexArray]:
    """Bounded reference alternatives; each vote uses three different source photos."""
    if (
        query.ndim != 2
        or bank.ndim != 2
        or query.shape[1] != bank.shape[1]
        or len(bank) == 0
        or bank_labels.shape != (len(bank),)
        or len(bank_sources) != len(bank)
        or base.shape != (len(query),)
        or not np.isfinite(query).all()
        or not np.isfinite(bank).all()
    ):
        raise ValueError("Reference features, source photos and labels are inconsistent.")
    results = {f"references-3-{threshold}": base.copy() for threshold in (0.90, 0.95, 0.98)}
    results["nearest-0.98"] = base.copy()
    for start in range(0, len(query), 64):
        similarities = query[start : start + 64] @ bank.T
        for offset, scores in enumerate(similarities):
            order = np.argsort(-scores, kind="stable")
            first = int(order[0])
            if scores[first] >= 0.98:
                results["nearest-0.98"][start + offset] = bank_labels[first]
            chosen, sources = [], set()
            for candidate in order:
                source = bank_sources[int(candidate)]
                if source not in sources:
                    chosen.append(int(candidate))
                    sources.add(source)
                if len(chosen) == 3:
                    break
            if len(chosen) == 3 and len(set(bank_labels[chosen])) == 1:
                for threshold in (0.90, 0.95, 0.98):
                    if min(scores[chosen]) >= threshold:
                        results[f"references-3-{threshold}"][start + offset] = bank_labels[first]
    return results


def snapshot(game_id: UUID, output: Path, model_metadata: Path) -> None:
    """Read at most the selected audit's boards in one read-only transaction."""
    if (output / "snapshot.json").exists():
        raise ValueError("Snapshot already exists; reuse it or choose a new output directory.")
    settings = ApiSettings.from_environment()
    audit = FileGridAuditProposalStore(settings.artifact_root).load(game_id)
    directory = settings.artifact_root / "grid-audit-proposals" / str(game_id) / audit.audit_id
    document = json.loads((directory / "proposals.json").read_bytes())
    items = {item["recognizedBoardId"]: item for item in document["items"]}
    factory = create_session_factory(create_maintenance_database_engine(settings))
    with factory() as session:
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        session.execute(text("SET LOCAL statement_timeout = '15s'"))
        GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
        connection = session.connection()
        params = {"game": game_id, "boards": [UUID(board) for board in items]}
        rows = [
            dict(row)
            for row in connection.execute(
                text(f"""
                WITH scoped AS MATERIALIZED (
                    SELECT * FROM image_symbol_review_cells
                    WHERE game_id=:game AND recognized_board_id=ANY(:boards)
                )
                SELECT {reference._CELL_COLUMNS}, s.code AS label,
                       b.source_image_id::text AS source_image_id,
                       coalesce(g.corners, b.board_geometry->'sourceQuad') AS current_corners,
                       c.revision, c.approved_geometry_revision,
                       c.approved_rendered_pixel_checksum_sha256,
                       c.approved_render_spec_checksum_sha256,
                       c.verified_symbol_id_v2::text AS verified_symbol_id_v2
                FROM scoped c
                JOIN recognized_boards b ON b.id=c.recognized_board_id AND b.game_id=c.game_id
                LEFT JOIN image_board_geometry_revisions g
                  ON g.game_id=c.game_id AND g.recognized_board_id=c.recognized_board_id
                 AND g.revision=c.geometry_revision
                JOIN public.symbols s ON s.id=c.assigned_symbol_id
                WHERE c.game_id=:game AND c.recognized_board_id=ANY(:boards)
                  AND c.review_state='approved' AND c.assignment_source='human'
                  AND c.asset_mode='virtual_source' AND c.approved_asset_mode='virtual_source'
                  AND c.source_available AND c.quality_issue IS NULL
                  AND (c.source_visibility IS NULL OR c.source_visibility='full')
                  AND s.status='active' AND c.verified_symbol_id_v2=c.assigned_symbol_id
                  AND c.geometry_revision=b.geometry_revision
                  AND c.approved_geometry_revision=c.geometry_revision
                  AND c.approved_render_spec_checksum_sha256=c.render_spec_checksum_sha256
                  AND c.approved_rendered_pixel_checksum_sha256=c.rendered_pixel_checksum_sha256
                ORDER BY c.id
                """),
                params,
            ).mappings()
        ]
        decisions = {
            str(row["cell_review_id"]): row
            for row in connection.execute(
                text("""
                SELECT DISTINCT ON (e.cell_review_id)
                       e.cell_review_id, e.action, e.operation_id
                FROM image_symbol_review_events e
                WHERE e.game_id=:game AND e.cell_review_id=ANY(:ids)
                  AND e.action IN ('approve', 'reassign')
                ORDER BY e.cell_review_id, e.created_at DESC, e.id DESC
                """),
                {"game": game_id, "ids": [UUID(row["id"]) for row in rows]},
            ).mappings()
        }
        if any(row["id"] not in decisions for row in rows):
            raise ValueError("An approved cell has no auditable human decision.")
        original_count = len(rows)
        rows = [
            row
            for row in rows
            if not is_bulk_approval(
                str(decisions[row["id"]]["action"]), decisions[row["id"]]["operation_id"]
            )
        ]
        excluded_bulk = original_count - len(rows)
        rows = reference._with_render_specs(connection, str(game_id), rows)
        activation = reference._active_model(connection, str(game_id), settings.artifact_root)
        session.rollback()
    metadata = json.loads(model_metadata.read_bytes())
    if activation.checkpoint_sha256 != metadata["checkpointSha256"]:
        raise ValueError("The active model differs from the audit's frozen classifier.")
    for row in rows:
        item = items[str(row["recognized_board_id"])]
        row["item_id"] = item["itemId"]
        row["ordinal"] = item["ordinal"]
        row["geometry_changed_from_proposal"] = (
            row["current_corners"] != item["proposal"]["corners"]
        )
        path = directory / "symbol-suggestions" / f"{item['itemId']}.json"
        if path.exists():
            content = path.read_bytes()
            manifest = json.loads(path.with_name(path.stem + ".manifest.json").read_bytes())
            if hashlib.sha256(content).hexdigest() != manifest["sha256"]:
                raise ValueError("Audit suggestion checksum differs.")
            suggestion = json.loads(content)
            proposal = suggestion["cells"][row["cell_index"]]
            row["shown_code"] = proposal.get("symbolCode")
            row["shown_algorithm"] = suggestion["algorithmVersion"]
            row["shown_generated_at"] = suggestion["generatedAt"]
        else:
            row["shown_code"] = None
            row["shown_algorithm"] = None
    payload = {
        "schema": "grid-audit-approved-feedback-v1",
        "gameId": str(game_id),
        "auditId": audit.audit_id,
        "auditSha256": audit.sha256,
        "artifactRoot": str(settings.artifact_root.resolve()),
        "model": metadata,
        "excludedBulkApprovalCells": excluded_bulk,
        "rows": json.loads(json.dumps(rows, default=str)),
    }
    digest = write_json(output / "snapshot.json", payload)
    write_json(output / "snapshot.manifest.json", {"sha256": digest})
    print(
        json.dumps(
            {
                "frozenCells": len(rows),
                "excludedBulkApprovalCells": excluded_bulk,
                "sources": len({r["source_image_id"] for r in rows}),
                "shownAlgorithms": dict(Counter(r["shown_algorithm"] for r in rows)),
            }
        )
    )


def read_snapshot(output: Path) -> dict[str, Any]:
    content = (output / "snapshot.json").read_bytes()
    expected = json.loads((output / "snapshot.manifest.json").read_bytes())["sha256"]
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError("Feedback snapshot checksum differs.")
    return json.loads(content)  # type: ignore[no-any-return]


def render(output: Path, seconds: int) -> None:
    frozen = read_snapshot(output)
    cells = [reference._cell(row) for row in frozen["rows"]]
    cache, remaining = reference._render(
        cells,
        artifact_root=Path(frozen["artifactRoot"]),
        cache_path=output / "crops.npz",
        deadline=time.monotonic() + seconds - 5,
        context_size=0,
    )
    print(
        json.dumps(
            {
                "cached": len(cache),
                "remaining": remaining,
                "statuses": dict(Counter(entry["status"] for entry in cache.values())),
            }
        )
    )


def features(output: Path) -> None:
    frozen = read_snapshot(output)
    cache = reference._load_cache(output / "crops.npz")
    rows = frozen["rows"]
    crops = []
    for row in rows:
        entry = cache[reference._cache_key(reference._cell(row))]
        if entry["status"] != "ok":
            raise ValueError(f"Unusable approved pixels: {row['id']} / {entry['status']}")
        crops.append(entry["crop"])
    model = frozen["model"]
    classifier = AuditRgbClassifier(
        Path(model["checkpointPath"]), model["checkpointSha256"], model["classCodes"]
    )
    feature_parts, logit_parts = [], []
    with torch.inference_mode():
        for start in range(0, len(crops), 128):
            batch = rgb_batch(np.stack(crops[start : start + 128]))
            spatial = classifier.network.features(batch)
            feature_parts.append(spatial.flatten(1).numpy())
            logit_parts.append(classifier.network.classifier(spatial).numpy())
    np.savez(
        output / "features.tmp.npz",
        features=normalize_rows(np.concatenate(feature_parts)),
        logits=np.concatenate(logit_parts),
    )
    (output / "features.tmp.npz").replace(output / "features.npz")
    write_json(
        output / "features.manifest.json",
        {
            "sha256": hashlib.sha256((output / "features.npz").read_bytes()).hexdigest(),
            "snapshotSha256": hashlib.sha256((output / "snapshot.json").read_bytes()).hexdigest(),
        },
    )
    predictions = np.concatenate(logit_parts).argmax(axis=1)
    errors = []
    for row, predicted in zip(rows, predictions, strict=True):
        code = classifier.class_codes[int(predicted)]
        if code != row["label"]:
            errors.append(
                {
                    "cellId": row["id"],
                    "itemId": row["item_id"],
                    "index": row["cell_index"],
                    "expected": row["label"],
                    "rgb": code,
                    "shown": row["shown_code"],
                    "geometryChanged": row["geometry_changed_from_proposal"],
                }
            )
    write_json(output / "rgb-errors.json", errors)
    print(
        json.dumps(
            {
                "cells": len(rows),
                "rgbErrors": len(errors),
                "pairs": dict(Counter(e["rgb"] + " -> " + e["expected"] for e in errors)),
                "shownDisagreements": sum(r["shown_code"] != r["label"] for r in rows),
                "geometryChanged": sum(r["geometry_changed_from_proposal"] for r in rows),
            }
        )
    )


def evaluate(output: Path) -> None:
    frozen = read_snapshot(output)
    content = (output / "features.npz").read_bytes()
    manifest = json.loads((output / "features.manifest.json").read_bytes())
    if (
        hashlib.sha256(content).hexdigest() != manifest["sha256"]
        or hashlib.sha256((output / "snapshot.json").read_bytes()).hexdigest()
        != manifest["snapshotSha256"]
    ):
        raise ValueError("Feature snapshot checksum differs.")
    rows = frozen["rows"]
    codes = frozen["model"]["classCodes"]
    with np.load(output / "features.npz", allow_pickle=False) as archive:
        spatial = archive["features"]
        base = archive["logits"].argmax(axis=1)
    labels = np.array([codes.index(row["label"]) for row in rows])
    splits, retained = split_rows(rows)
    indices = {
        split: np.array([i for i in retained if splits[i] == split], dtype=np.int64)
        for split in ("train", "validation", "test")
    }
    if any(len(group) == 0 for group in indices.values()):
        raise ValueError("Independent train, validation and test crops are required.")
    if any(set(labels[group]) != set(range(len(codes))) for group in indices.values()):
        raise ValueError("Every active symbol must occur in each independent split.")
    train, validation, test = (indices[key] for key in ("train", "validation", "test"))
    sources = [rows[i]["render_spec"]["sourceChecksumSha256"] for i in train]
    alternatives = reference_candidates(
        spatial[validation], spatial[train], labels[train], sources, base[validation]
    )
    baseline_validation = metrics(labels[validation], base[validation], codes)
    validation_scores = {
        name: metrics(labels[validation], predictions, codes)
        for name, predictions in alternatives.items()
    }
    eligible = [
        name
        for name, score in validation_scores.items()
        if safe_improvement(baseline_validation, score)
    ]
    selected = (
        min(eligible, key=lambda name: (validation_scores[name]["errors"], name))
        if eligible
        else "rgb-v2"
    )
    # The choice is fixed before the test set is evaluated; no test-driven tuning.
    selected_predictions = base[test]
    if selected != "rgb-v2":
        test_candidates = reference_candidates(
            spatial[test], spatial[train], labels[train], sources, base[test]
        )
        selected_predictions = test_candidates[selected]
    baseline_test = metrics(labels[test], base[test], codes)
    selected_test = metrics(labels[test], selected_predictions, codes)
    improved = selected != "rgb-v2" and safe_improvement(baseline_test, selected_test)
    current_rgb_indices = np.array(
        [
            i
            for i, row in enumerate(rows)
            if row["shown_algorithm"] == "symbol-audit-rgb-classifier-v2"
        ],
        dtype=np.int64,
    )
    unchanged_cut_indices = np.array(
        [i for i in current_rgb_indices if not rows[i]["geometry_changed_from_proposal"]],
        dtype=np.int64,
    )
    report = {
        "schema": "grid-audit-feedback-evaluation-v1",
        "snapshotSha256": manifest["snapshotSha256"],
        "checkpointSha256": frozen["model"]["checkpointSha256"],
        "allRgb": metrics(labels, base, codes),
        "currentRgbApproved": metrics(
            labels[current_rgb_indices], base[current_rgb_indices], codes
        ),
        "currentRgbUnchangedCut": metrics(
            labels[unchanged_cut_indices], base[unchanged_cut_indices], codes
        ),
        "splitCells": {key: len(value) for key, value in indices.items()},
        "splitSources": {
            key: len({rows[i]["render_spec"]["sourceChecksumSha256"] for i in value})
            for key, value in indices.items()
        },
        "excludedDuplicateOrConflictingCells": len(rows) - len(retained),
        "baselineValidation": baseline_validation,
        "alternativesValidation": validation_scores,
        "selectionRequiresNoClassRegression": True,
        "selectedUsingValidation": selected,
        "baselineTest": baseline_test,
        "selectedTest": selected_test,
        "independentImprovement": improved,
        "recommendation": "candidate_requires_scope_review" if improved else "retain_rgb_v2",
        "unchangedShownChoicesAreWeakerEvidence": True,
    }
    retained_set = set(retained)
    write_json(
        output / "split.json",
        {
            "assignments": [
                {"cellId": row["id"], "split": split, "retained": i in retained_set}
                for i, (row, split) in enumerate(zip(rows, splits, strict=True))
            ]
        },
    )
    write_json(output / "report.json", report)
    print(json.dumps(report))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("snapshot", "render", "features", "evaluate"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--game-id", type=UUID)
    parser.add_argument("--model-metadata", type=Path)
    parser.add_argument("--seconds", type=int, default=90, choices=range(10, 111))
    arguments = parser.parse_args()
    if arguments.command == "snapshot":
        if arguments.game_id is None or arguments.model_metadata is None:
            parser.error("snapshot requires --game-id and --model-metadata")
        snapshot(arguments.game_id, arguments.output, arguments.model_metadata)
    elif arguments.command == "render":
        render(arguments.output, arguments.seconds)
    elif arguments.command == "features":
        features(arguments.output)
    else:
        evaluate(arguments.output)


if __name__ == "__main__":
    main()
