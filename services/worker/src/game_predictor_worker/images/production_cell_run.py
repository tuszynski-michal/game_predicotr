"""Rebuild production-content summaries from durable per-instance observations."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.production_cell_evaluation import ContentGameEvidence

from .grid_cohort_dataset import GridAssessmentDataset, GridBoardDataset
from .production_cell_evaluation import ProductionContentObserver, reference_context


def content_enabled(snapshot: Any) -> bool:
    return bool(
        snapshot.manifest.get("photoSplit", {}).get("contentSampling", {}).get("policy")
        == "full-symbol-content-sampling-v1"
    )


class ProductionContentRun:
    def __init__(
        self, snapshot: Any, *, roles: tuple[str, ...] = ("VALIDATION", "REGRESSION")
    ) -> None:
        self.snapshot = snapshot
        self.game = snapshot.manifest["gameId"]
        self.reasons: set[str] = set()
        self.u: float | None = None
        self.delta: float | None = None
        self.measurement_sha: str | None = None
        self.classifiers: set[str] = set()
        self.configurations: set[str] = set()
        reports = {}
        if not roles or any(role not in ("VALIDATION", "REGRESSION") for role in roles):
            raise ValueError("CONTENT_REFERENCE_ROLE_INVALID")
        for role in roles:
            dataset = (
                GridBoardDataset(snapshot, role)
                if role == "VALIDATION"
                else GridAssessmentDataset(snapshot, role)
            )
            for source, _ in dataset.indexed():
                for target in source["targets"]:
                    context = reference_context(target)
                    if context is None:
                        self.reasons.add("CONTENT_RENDER_REFERENCE_MISSING")
                        continue
                    self.classifiers.add(digest(context["classifier"]))
                    self.configurations.add(digest(context["renderConfiguration"]))
                    measurement = target["productionContentReference"]["measurement"]
                    # REG never estimates u/delta, including when it has its own session.
                    if role == "VALIDATION" and measurement is not None:
                        report = measurement["report"]
                        if report.get("sha256") != digest(
                            {k: v for k, v in report.items() if k != "sha256"}
                        ):
                            raise ValueError("CONTENT_MEASUREMENT_CHECKSUM")
                        reports[report["sha256"]] = report
        if len(reports) != 1:
            self.reasons.add("CONTENT_MEASUREMENT_UNIQUE_REFERENCE_REQUIRED")
        else:
            sha, report = next(iter(reports.items()))
            item = report.get("games", {}).get(self.game, {})
            if (
                report.get("version") != "cell-content-repeatability-v1"
                or report.get("quantile") != "nearest-rank-p95-v1"
                or report.get("state") != "ready"
                or report.get("qualificationState") != "ready"
                or item.get("state") != "ready"
                or item.get("u") is None
                or item.get("delta") is None
                or not 0 <= item["u"] <= 0.02
                or not 0 <= item["delta"] <= 0.002
            ):
                self.reasons.add("CONTENT_MEASUREMENT_NOT_EVALUABLE")
            else:
                self.u, self.delta, self.measurement_sha = item["u"], item["delta"], sha

    def observer(self, role: str) -> ProductionContentObserver:
        return ProductionContentObserver(self.snapshot, role, u=self.u)

    def verify_photo_details(
        self, role: str, rows: list[dict[str, Any]], *, input_contexts: dict[str, Any] | None = None
    ) -> None:
        """Replay renderer/matching/content with frozen pixels, without another NN inference."""
        from types import SimpleNamespace

        import numpy as np

        from ..training_core.grid_correction_metrics import CorrectionControlPhoto, evaluate_photo
        from ..training_core.grid_evaluation import predictions
        from .grid_cohort_dataset import has_full_geometry
        from .production_cell_input import require_input_context, verify_input

        dataset = (
            GridBoardDataset(self.snapshot, role)
            if role == "VALIDATION"
            else GridAssessmentDataset(self.snapshot, role)
        )
        sources = {source["sourceId"]: (source, labels) for source, labels in dataset.indexed()}
        if len(rows) != len(sources) or {row["sourceId"] for row in rows} != set(sources):
            raise ValueError("CONTENT_DETAIL_ROSTER_CHANGED")
        for row in rows:
            source, labels = sources[row["sourceId"]]
            frame = self.snapshot.frame(source, role)
            recorded = row["contentEvaluation"]
            boards = {b["positionIndex"]: b for b in recorded["boards"]}

            def input_reader(
                frame: Any,
                source: Any,
                target: Any,
                detection: Any,
                engine: Any,
                game: Any,
                boards: Any = boards,
            ) -> Any:
                proof = boards[target["positionIndex"]][engine]["inputEvidence"]
                if proof is not None:
                    require_input_context(
                        proof, None if input_contexts is None else input_contexts[engine]
                    )
                if proof is not None and proof["screenQuad"] != detection.screen_quad.tolist():
                    raise ValueError("INPUT_CONTENT_DETECTION_CHANGED")
                return verify_input(frame, source, target, proof, game)

            observer = ProductionContentObserver(
                self.snapshot, role, u=self.u, input_reader=input_reader
            )

            def load_frame(frame: Any = frame) -> Any:
                return frame.rgb

            photo = CorrectionControlPhoto(
                source["sourceId"],
                row["groupId"],
                source["original"]["sha256"],
                tuple(nodes for nodes, _ in labels),
                load_frame,
                full_geometry=has_full_geometry(source),
            )
            observed = {}
            for name in ("base", "candidate"):
                found = [
                    SimpleNamespace(
                        nodes=None
                        if d["nodes"] is None
                        else np.asarray(d["nodes"], dtype=np.float64),
                        screen_quad=np.asarray(d["screenQuad"], dtype=np.float64),
                    )
                    for d in recorded["models"][name]["detections"]
                ]
                result = evaluate_photo(
                    photo.source_id,
                    photo.group_id,
                    list(photo.labels),
                    predictions(found),
                    full_geometry=photo.full_geometry,
                )
                if result.as_dict() != row[name]:
                    raise ValueError("CONTENT_DETAIL_METRICS_CHANGED")
                observed[name] = found, result, name
            if observer(photo, frame.rgb, observed) != recorded:
                raise ValueError("CONTENT_DETAIL_RENDER_CHANGED")

    def finish(
        self,
        root: Path,
        job_id: Any,
        *,
        verified_details: Mapping[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        roles = {}
        for role in ("VALIDATION", "REGRESSION"):
            if verified_details is None:
                path = root / "grid-model-evaluations" / str(job_id) / f"{self.game}-{role}.json"
                if path.stat().st_size > 96 * 1024 * 1024:
                    raise ValueError("CONTENT_DETAIL_SIZE_LIMIT")
                document = json.loads(path.read_bytes())
            else:
                # Consume exactly the documents whose bytes and identity the caller checked.
                document = verified_details[role]
            if (
                document["gameId"] != self.game
                or document["jobId"] != str(job_id)
                or document["role"] != role
            ):
                raise ValueError("CONTENT_DETAIL_IDENTITY")
            details = [row["contentEvaluation"] for row in document["photos"]]
            roles[role] = summarize_content(details)
        split = self.snapshot.manifest.get("photoSplit", {})
        selected = split.get("contentSampling", {})
        selected_ids = set(selected.get("sourceIds", []))
        pins = {pin["sourceId"]: pin for pin in split.get("sources", [])}
        expected_reg = {
            source_id
            for source_id in selected_ids
            if source_id in pins
            and pins[source_id].get("representative") is True
            and pins[source_id].get("eligibleBoards", 0) > 0
        }
        actual_reg = {
            source["sourceId"]
            for source, _ in GridAssessmentDataset(self.snapshot, "REGRESSION").indexed()
        }
        fresh = (
            content_enabled(self.snapshot)
            and selected.get("state") == "ready"
            and selected_ids <= pins.keys()
            and bool(expected_reg)
            and actual_reg == expected_reg
        )
        return ContentGameEvidence.model_validate(
            {
                "gameId": self.game,
                "state": "not_evaluable" if self.reasons else "ready",
                "reasonCodes": sorted(self.reasons),
                "u": self.u,
                "delta": self.delta,
                "measurementSha256": self.measurement_sha,
                "classifierSnapshotSha256s": sorted(self.classifiers),
                "renderConfigurationSha256s": sorted(self.configurations),
                "freshRegression": fresh,
                "roles": roles,
            }
        ).model_dump(mode="json")


def summarize_content(photos: list[dict[str, Any]]) -> dict[str, Any]:
    boards = [b for photo in photos for b in photo["boards"]]
    cells = [cell for board in boards for cell in board["cells"]]
    states = Counter(cell["contentState"] for cell in cells)
    visible = [cell for cell in cells if cell["contentState"] == "visible"]
    models = {}
    for name in ("base", "candidate"):
        counts = Counter(cell[name]["finalContentState"] for cell in visible)
        models[name] = {
            **{key: counts[key] for key in ("preserved", "borderline", "clipped", "missing")},
            **{
                key: sum(bool(cell[name][flag]) for cell in visible)
                for key, flag in (
                    ("wrongCells", "wrongCell"),
                    ("ties", "tie"),
                    ("foreignSymbols", "foreignFullSymbol"),
                )
            },
            "usableBoards": sum(board[name]["usable"] for board in boards),
            "ambiguousBoards": sum(board[name]["matchAmbiguous"] for board in boards),
        }
    rank = {"preserved": 0, "borderline": 1, "clipped": 2, "missing": 2}
    reasons = {code for photo in photos for code in photo["reasonCodes"]}
    if not photos:
        reasons.add("CONTENT_PHOTOS_REQUIRED")
    return {
        "state": "not_evaluable" if reasons else "ready",
        "reasonCodes": sorted(reasons),
        "photos": len(photos),
        "fullPhotos": sum(
            bool(photo["fullGeometry"])
            and all(
                cell["contentState"] != "unknown"
                for board in photo["boards"]
                for cell in board["cells"]
            )
            for photo in photos
        ),
        "slots": len(cells),
        "visible": states["visible"],
        "unknown": states["unknown"],
        "occluded": states["occluded"],
        "outOfFrame": states["out_of_frame"],
        "referenceSha256": digest([photo["referenceSha256"] for photo in photos]),
        **models,
        "degradedInstances": sum(
            rank[c["candidate"]["finalContentState"]] > rank[c["base"]["finalContentState"]]
            for c in visible
        ),
        **{
            key: sum(bool(c["candidate"][flag]) and not c["base"][flag] for c in visible)
            for key, flag in (
                ("newWrongCells", "wrongCell"),
                ("newTies", "tie"),
                ("newForeignSymbols", "foreignFullSymbol"),
            )
        },
        "newMatchAmbiguities": sum(
            b["candidate"]["matchAmbiguous"] and not b["base"]["matchAmbiguous"] for b in boards
        ),
    }


def unavailable_content(game: dict[str, Any]) -> dict[str, Any]:
    roles = {}
    for role, metrics in game["roles"].items():
        empty = summarize_content([])
        empty.update(
            photos=metrics["photos"],
            fullPhotos=0,
            slots=metrics["base"]["boards_expected"] * 15,
            unknown=metrics["base"]["boards_expected"] * 15,
            reasonCodes=["CONTENT_FROZEN_REFERENCE_REQUIRED"],
        )
        roles[role] = empty
    return {
        "gameId": game["gameId"],
        "state": "not_evaluable",
        "reasonCodes": ["CONTENT_FROZEN_REFERENCE_REQUIRED"],
        "u": None,
        "delta": None,
        "measurementSha256": None,
        "classifierSnapshotSha256s": [],
        "renderConfigurationSha256s": [],
        "freshRegression": False,
        "roles": roles,
    }
