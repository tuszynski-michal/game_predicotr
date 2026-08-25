"""Train one inactive spatial symbol-model candidate from the frozen v19 cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from game_predictor_api.config import get_settings
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
)
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.symbol_model_snapshot_resolver import (
    SqlAlchemySymbolModelSnapshotResolver,
)
from game_predictor_api.storage.training_dataset_catalog_repository import (
    SqlAlchemyTrainingDatasetCatalogRepository,
)
from game_predictor_worker.images.symbol_classifier import TrainingConfig
from game_predictor_worker.images.symbol_onnx import LocalSymbolOnnxAdapter
from game_predictor_worker.symbols.candidate_gate import SymbolModelBaseline
from game_predictor_worker.symbols.v19_candidate import (
    V19SymbolCandidateError,
    load_v19_candidate_dataset,
    train_v19_symbol_candidate,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESCRIPTOR = ROOT / "ai_docs/quality/v19-symbol-model-candidate.json"
DEFAULT_COHORT_ROOT = ROOT / "artifacts/quality/v19-symbol-residuals"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--cohort-root", type=Path, default=DEFAULT_COHORT_ROOT)
    return parser.parse_args()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise V19SymbolCandidateError("V19_CANDIDATE_DESCRIPTOR_INVALID", f"{label} invalid.")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise V19SymbolCandidateError(
            "V19_CANDIDATE_DESCRIPTOR_INVALID", f"{label} must be an integer."
        )
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise V19SymbolCandidateError(
            "V19_CANDIDATE_DESCRIPTOR_INVALID", f"{label} must be numeric."
        )
    return float(value)


def _descriptor(path: Path) -> Mapping[str, object]:
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise V19SymbolCandidateError(
            "V19_CANDIDATE_DESCRIPTOR_INVALID", "Cannot read the candidate descriptor."
        ) from error
    result = _mapping(value, "descriptor")
    if result.get("version") != "v19-symbol-model-candidate-descriptor-v1":
        raise V19SymbolCandidateError(
            "V19_CANDIDATE_DESCRIPTOR_INVALID", "Candidate descriptor version is unsupported."
        )
    return result


def _baseline_path(snapshot: SymbolModelJobSnapshot, artifact_root: Path) -> Path:
    storage_root = snapshot.storage_root
    relative_path = snapshot.onnx_relative_path
    relative = PurePosixPath(relative_path)
    root = ROOT if storage_root is SymbolModelStorageRoot.REPOSITORY else artifact_root
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise V19SymbolCandidateError(
            "V19_CANDIDATE_BASELINE_PATH_INVALID", "Active model path escapes managed storage."
        )
    return path


def main() -> int:
    session = None
    try:
        arguments = _arguments()
        descriptor = _descriptor(arguments.descriptor)
        game_id = UUID(str(descriptor["gameId"]))
        cohort_checksum = str(descriptor["cohortChecksumSha256"])
        evaluation_checksum = str(descriptor["evaluationChecksumSha256"])
        evaluation_path = arguments.cohort_root / "reports" / f"{evaluation_checksum}.json"
        evaluation_content = evaluation_path.read_bytes()
        if hashlib.sha256(evaluation_content).hexdigest() != evaluation_checksum:
            raise V19SymbolCandidateError(
                "V19_CANDIDATE_EVALUATION_DRIFT",
                "The pinned residual evaluation checksum changed.",
            )
        evaluation = json.loads(evaluation_content)
        if (
            not isinstance(evaluation, Mapping)
            or evaluation.get("decision", {}).get("value") != "retrain"
        ):
            raise V19SymbolCandidateError(
                "V19_CANDIDATE_RETRAIN_NOT_AUTHORIZED",
                "The pinned residual evaluation does not authorize retraining.",
            )
        settings = get_settings()
        session = create_session_factory(create_database_engine(settings))()
        snapshot = SqlAlchemySymbolModelSnapshotResolver(
            session, artifact_root=settings.artifact_root
        ).resolve(game_id=game_id)
        expected_fingerprint = str(descriptor["activeModelFingerprintSha256"])
        if snapshot.inference_fingerprint != expected_fingerprint:
            raise V19SymbolCandidateError(
                "V19_CANDIDATE_ACTIVE_MODEL_DRIFT",
                "The active symbol model differs from the pinned baseline.",
            )
        catalog = SqlAlchemyTrainingDatasetCatalogRepository(session).get(game_id=game_id)
        if catalog is None:
            raise V19SymbolCandidateError(
                "V19_CANDIDATE_CATALOG_MISSING", "The active symbol catalog is unavailable."
            )
        dataset = load_v19_candidate_dataset(
            cohort_path=arguments.cohort_root / "cohorts" / f"{cohort_checksum}.json",
            expected_cohort_checksum_sha256=cohort_checksum,
            crop_root=arguments.cohort_root,
            class_ids_by_code={symbol.code: symbol.id for symbol in catalog.symbols},
        )
        config_raw = _mapping(descriptor.get("trainingConfiguration"), "trainingConfiguration")
        config = TrainingConfig(
            seed=_integer(config_raw.get("seed"), "trainingConfiguration.seed"),
            epochs=_integer(config_raw.get("epochs"), "trainingConfiguration.epochs"),
            batch_size=_integer(config_raw.get("batchSize"), "trainingConfiguration.batchSize"),
            learning_rate=_number(
                config_raw.get("learningRate"), "trainingConfiguration.learningRate"
            ),
            weight_decay=_number(
                config_raw.get("weightDecay"), "trainingConfiguration.weightDecay"
            ),
            input_size=_integer(config_raw.get("inputSize"), "trainingConfiguration.inputSize"),
        )
        baseline_adapter = LocalSymbolOnnxAdapter(
            _baseline_path(snapshot, settings.artifact_root),
            expected_sha256=snapshot.onnx_checksum_sha256,
            class_codes=snapshot.class_codes,
            input_size=snapshot.input_size,
        )
        candidate_root = (
            settings.artifact_root
            / "data/models"
            / catalog.game_code
            / "v19-candidates"
            / cohort_checksum
            / str(config.seed)
        )
        run = train_v19_symbol_candidate(
            artifact_root=settings.artifact_root,
            candidate_root=candidate_root,
            dataset=dataset,
            baseline=SymbolModelBaseline(
                iteration_id=str(snapshot.iteration_id),
                adapter=baseline_adapter,
                temperature=max(0.50, snapshot.temperature),
            ),
            baseline_fingerprint_sha256=snapshot.inference_fingerprint,
            config=config,
            progress=lambda stage: print(json.dumps({"stage": stage}), flush=True),
        )
        current = SqlAlchemySymbolModelSnapshotResolver(
            session, artifact_root=settings.artifact_root
        ).resolve(game_id=game_id)
        if current.inference_fingerprint != expected_fingerprint:
            raise V19SymbolCandidateError(
                "V19_CANDIDATE_ACTIVE_MODEL_MUTATED",
                "Candidate training changed the active model pointer.",
            )
        print(
            json.dumps(
                {
                    "activeModelFingerprintSha256": current.inference_fingerprint,
                    "candidateManifestChecksumSha256": (
                        run.base_candidate.manifest_checksum_sha256
                    ),
                    "checkpointChecksumSha256": run.checkpoint_checksum_sha256,
                    "decisionChecksumSha256": run.decision_checksum_sha256,
                    "decisionRelativePath": run.decision_relative_path,
                    "status": run.decision["status"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (KeyError, OSError, TypeError, ValueError) as error:
        code = getattr(error, "code", "V19_CANDIDATE_TRAINING_FAILED")
        print(json.dumps({"code": code, "message": str(error)}), file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    raise SystemExit(main())
