"""Read-only CPU comparison on a previously evaluated, checksum-bound control set.

Historical selection uses VALIDATION only; REGRESSION confirms the frozen choice.
No database writes, training, publication or activation are performed.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

REPOSITORY = Path(__file__).resolve().parents[1]
for relative in ("services/api/src", "services/worker/src"):
    sys.path.insert(0, str(REPOSITORY / relative))

from game_predictor_api.application.grid_model_evaluation import bundle_sha256  # noqa: E402
from game_predictor_api.domain.grid_model_registry import descriptor_sha256  # noqa: E402
from game_predictor_worker.images.grid_cohort_dataset import GridCohortSnapshot  # noqa: E402
from game_predictor_worker.images.grid_model_evaluation_handler import (  # noqa: E402
    GridModelEvaluationJobHandler,
)
from game_predictor_worker.images.grid_rescue_assessment import load_assessment_engine  # noqa: E402
from game_predictor_worker.training_core.grid_correction_metrics import (  # noqa: E402
    CorrectionControlPhoto,
    measure_role,
)
from game_predictor_worker.training_core.grid_evaluation import input_sha256  # noqa: E402


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def write_new(path: Path, value: Any) -> None:
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")


def ranking(metrics: dict[str, Any]) -> tuple[float, float, float]:
    """Full-photo correctness, board correctness, then photo-macro geometry error."""
    return (
        float(metrics["photo_complete_correct_rate"]),
        float(metrics["board_correct_rate"]),
        -float(metrics["normalized_error"]),
    )


def choose_historical(results: dict[str, dict[str, Any]], identities: list[str]) -> str:
    if not identities or len(set(identities)) != len(identities):
        raise ValueError("HISTORICAL_SCOPE_INVALID")
    # Lexical identity breaks exact ties reproducibly; no REGRESSION result is an input.
    return sorted(identities, key=lambda key: (ranking(results[key]["metrics"]), key))[-1]


class LastFrameEngine:
    """Avoid duplicate self-comparison inference; retain only one result per model."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.key: tuple[Any, ...] | None = None
        self.result: list[Any] = []

    def analyse(self, rgb: Any) -> list[Any]:
        key = (rgb.shape, str(rgb.dtype), hashlib.sha256(rgb.tobytes()).digest())
        if key != self.key:
            self.result = list(self.engine.analyse(rgb))
            self.key = key
        return self.result


def read_detail(root: Path, pin: dict[str, Any]) -> dict[str, Any]:
    path = root / pin["path"]
    if not path.resolve().is_relative_to(root.resolve()) or any(
        value.is_symlink() or value.is_junction() for value in (path, *path.parents)
    ):
        raise ValueError("DETAIL_PATH_UNSAFE")
    if path.stat().st_size > 96 * 1024 * 1024:
        raise ValueError("DETAIL_TOO_LARGE")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("DETAIL_CHECKSUM_MISMATCH")
    return dict(json.loads(raw))


def frozen_funnel(manifest: dict[str, Any]) -> dict[str, Any]:
    pins = manifest["photoSplit"]["sources"]
    all_train = [p for p in pins if p.get("role") == "TRAIN"]
    assigned = [p for p in all_train if p["representative"]]
    labelled = [p for p in assigned if 0 < p.get("qualifiedBoards", p["eligibleBoards"]) < 9]
    full = [p for p in assigned if p.get("qualifiedBoards", p["eligibleBoards"]) == 9]
    empty = [p for p in assigned if p.get("qualifiedBoards", p["eligibleBoards"]) == 0]
    return {
        "populationPhotos": len(pins),
        "assignedTrainPhotos": len(all_train),
        "representativeTrainPhotos": len(assigned),
        "partialTrainPhotos": len(labelled),
        "partialQualifiedBoards": sum(
            p.get("qualifiedBoards", p["eligibleBoards"]) for p in labelled
        ),
        "usedCounts": manifest["counts"],
        "fullTrainRepresentatives": len(full),
        "emptyTrainRepresentatives": len(empty),
        "emptyTrainPendingCorrectionPhotos": sum(bool(p.get("pendingCorrection")) for p in empty),
        "trainOmissionCounts": {
            "nonRepresentativeAliases": len(all_train) - len(assigned),
            "partialPhotosExcludedFromScreen": len(labelled),
            "noQualifiedBoards": len(empty),
        },
        "trainAssignmentsReconciled": len(full)
        + len(labelled)
        + len(empty)
        + len(all_train)
        - len(assigned)
        == len(all_train),
        "screenTrainCountReconciled": len(full) == manifest["counts"]["TRAIN"]["photos"],
        "populationBufferFlags": sum(bool(p.get("buffer")) for p in pins),
        "reasonProvenance": (
            "Derived from frozen split flags; detailed per-label rejection reasons "
            "are not stored in this manifest."
        ),
    }


def write_funnel_evidence(root: Path, cohort: dict[str, Any], output: Path) -> None:
    path = root / cohort["manifestPath"]
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("MANIFEST_PATH_UNSAFE")
    with path.open("rb") as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != cohort["manifestSha256"]:
        raise ValueError("MANIFEST_CHECKSUM_MISMATCH")
    source = Path(__file__).read_bytes()
    source_path = output.with_suffix(".source.txt")
    with source_path.open("xb") as stream:
        stream.write(source)
    write_new(
        output,
        {
            "schemaVersion": "grid-funnel-evidence-v3",
            "cohort": cohort,
            "sourceFile": source_path.name,
            "sourceSha256": hashlib.sha256(source).hexdigest(),
            "recordedAt": datetime.now(UTC).isoformat(),
            "counts": frozen_funnel(json.loads(raw)),
        },
    )


def run(args: argparse.Namespace) -> None:
    root, output = args.artifact_root.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt_raw = args.acceptance.read_bytes()
    receipt = json.loads(receipt_raw)
    evaluation = receipt["evaluation"]
    report = evaluation["report"]
    if evaluation["status"] != "completed" or report["versionId"] != args.candidate:
        raise ValueError("EVALUATION_BINDING_MISMATCH")
    if len(report["games"]) != 1 or len(report["cohorts"]) != 1:
        raise ValueError("SINGLE_GAME_COMPARISON_REQUIRED")
    with urlopen(
        args.api.rstrip("/") + "/api/v1/admin/grid-model-versions", timeout=10
    ) as response:
        catalogue = json.load(response)
    versions = {str(item["manifest"]["versionId"]): item for item in catalogue}
    identities = [*args.historical, args.candidate]
    if len(set(identities)) != len(identities):
        raise ValueError("MODEL_SCOPE_DUPLICATED")
    if report["baseVersionId"] not in args.historical:
        raise ValueError("ORIGINAL_BASELINE_REQUIRED")
    selected = {}
    for identity in identities:
        item = versions[identity]
        manifest = item["manifest"]
        if (
            not item["available"]
            or manifest["familyId"] != report["familyId"]
            or manifest["modelVersion"] != "neural-grid-v1"
            or descriptor_sha256(manifest) != item["manifestSha256"]
        ):
            raise ValueError("MODEL_NOT_COMPARABLE")
        selected[identity] = item
    if selected[args.candidate]["manifestSha256"] != report["manifestSha256"]:
        raise ValueError("CANDIDATE_MANIFEST_DRIFT")
    pin = report["cohorts"][0]
    spec = json.loads(args.spec.read_bytes())["payload"]
    if (
        spec["cohort"]["cohortId"] != pin["cohortId"]
        or spec["cohort"]["manifestSha256"] != pin["manifestSha256"]
        or spec["cohort"]["gameId"] != pin["gameId"]
    ):
        raise ValueError("COHORT_BINDING_MISMATCH")
    scope = {
        "schemaVersion": "grid-historical-comparison-v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "acceptanceSha256": hashlib.sha256(receipt_raw).hexdigest(),
        "candidate": args.candidate,
        "historical": args.historical,
        "reference": report["baseVersionId"],
        "cohort": spec["cohort"],
        "models": selected,
        "threads": args.threads,
        "selectionRole": "VALIDATION",
        "selectionRule": "photo-correct-board-correct-normalized-error-identity-v1",
        "regressionUse": "confirmation-only-after-historical-selection",
    }
    write_new(output / "input.json", scope)
    print("Frozen input identities; reading the existing immutable snapshot", flush=True)
    snapshot = GridCohortSnapshot(root, spec["cohort"]["manifestPath"], pin["manifestSha256"])
    write_new(output / "data-funnel.json", frozen_funnel(snapshot.manifest))
    photos: dict[str, list[CorrectionControlPhoto]] = {}
    game = report["games"][0]
    for role in ("VALIDATION", "REGRESSION"):
        old = read_detail(root, game["roles"][role]["detail"])
        groups = {row["sourceId"]: row["groupId"] for row in old["photos"]}
        values = GridModelEvaluationJobHandler._photos(snapshot, role, groups, correction=True)
        control_photos = [value for value in values if isinstance(value, CorrectionControlPhoto)]
        if len(control_photos) != len(values):
            raise ValueError("CORRECTION_PHOTO_TYPE_REQUIRED")
        if input_sha256(values) != game["roles"][role]["inputSha256"] or {
            value.source_id for value in values
        } != set(groups):
            raise ValueError("CONTROL_PHOTO_DRIFT")
        photos[role] = control_photos
        print(f"Verified {role}: {len(values)} identical photos", flush=True)
    results: dict[str, dict[str, Any]] = {}

    def measure(identity: str, role: str) -> dict[str, Any]:
        item = selected[identity]["manifest"]
        directory = root / item["managedDirectory"]
        if not directory.resolve().is_relative_to(root):
            raise ValueError("MODEL_PATH_UNSAFE")
        engine = LastFrameEngine(
            load_assessment_engine(directory, bundle_sha256(item), args.threads)
        )
        summary, rows = measure_role(
            photos[role],
            engine,
            engine,
            before_photo=lambda index: print(
                f"{role} {identity[:8]} photo {index + 1}/{len(photos[role])}", flush=True
            ),
            cell_cut=True,
        )
        value = {
            "versionId": identity,
            "role": role,
            "inputSha256": summary["inputSha256"],
            "metrics": summary["candidate"],
            "boardsWithinCells": summary["cellCut"]["candidate"],
            "details": rows,
        }
        write_new(output / f"{identity}-{role}.json", value)
        del engine
        gc.collect()
        return value

    for identity in identities:
        results[identity] = measure(identity, "VALIDATION")
    best = choose_historical(results, args.historical)
    write_new(
        output / "historical-selection.json", {"versionId": best, "rule": scope["selectionRule"]}
    )
    print(f"Historical choice frozen from VALIDATION: {best}", flush=True)
    regression = {
        identity: measure(identity, "REGRESSION")
        for identity in dict.fromkeys((best, args.candidate, report["baseVersionId"]))
    }
    report_result = {
        "inputSha256": hashlib.sha256(canonical(scope)).hexdigest(),
        "bestHistorical": best,
        "validation": results,
        "regression": regression,
        "limitations": report["limitations"],
        "activationPerformed": False,
    }
    write_new(output / "comparison.json", report_result)
    print("Comparison complete; no training or activation performed", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--historical", nargs="+", required=True)
    parser.add_argument("--threads", type=int, choices=(1, 2), default=1)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
