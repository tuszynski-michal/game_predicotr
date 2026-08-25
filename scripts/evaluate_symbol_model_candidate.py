"""Verify the checksum-bound v19 candidate decision without activating it."""

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
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.symbol_model_snapshot_resolver import (
    SqlAlchemySymbolModelSnapshotResolver,
)
from game_predictor_worker.symbols.v19_candidate import (
    V19_GATE_VERSION,
    V19SymbolCandidateError,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESCRIPTOR = ROOT / "ai_docs/quality/v19-symbol-model-candidate.json"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--check", action="store_true", required=True)
    return parser.parse_args()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise V19SymbolCandidateError("V19_CANDIDATE_CHECK_INVALID", f"{label} invalid.")
    return value


def _verified_json(root: Path, relative_value: object, checksum: str) -> Mapping[str, object]:
    relative = PurePosixPath(str(relative_value))
    if relative.is_absolute() or ".." in relative.parts:
        raise V19SymbolCandidateError(
            "V19_CANDIDATE_CHECK_PATH_UNSAFE", "Candidate decision path is unsafe."
        )
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise V19SymbolCandidateError(
            "V19_CANDIDATE_CHECK_PATH_UNSAFE", "Candidate decision escapes storage."
        )
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != checksum:
        raise V19SymbolCandidateError(
            "V19_CANDIDATE_CHECKSUM_DRIFT", "Candidate decision checksum changed."
        )
    value: Any = json.loads(content)
    return _mapping(value, "decision")


def _verify_file(root: Path, relative_value: object, checksum: str) -> Path:
    relative = PurePosixPath(str(relative_value))
    if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative_value):
        raise V19SymbolCandidateError(
            "V19_CANDIDATE_CHECK_PATH_UNSAFE", "Candidate artifact path is unsafe."
        )
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise V19SymbolCandidateError(
            "V19_CANDIDATE_CHECK_PATH_UNSAFE", "Candidate artifact escapes storage."
        )
    try:
        content = path.read_bytes()
    except OSError as error:
        raise V19SymbolCandidateError(
            "V19_CANDIDATE_ARTIFACT_MISSING", "A pinned candidate artifact is missing."
        ) from error
    if hashlib.sha256(content).hexdigest() != checksum:
        raise V19SymbolCandidateError(
            "V19_CANDIDATE_CHECKSUM_DRIFT", "A candidate artifact checksum changed."
        )
    return path


def main() -> int:
    session = None
    try:
        arguments = _arguments()
        descriptor = _mapping(
            json.loads(arguments.descriptor.read_text(encoding="utf-8")), "descriptor"
        )
        checksum = str(descriptor["expectedDecisionChecksumSha256"])
        settings = get_settings()
        decision = _verified_json(
            settings.artifact_root,
            descriptor["expectedDecisionRelativePath"],
            checksum,
        )
        candidate_manifest_checksum = str(descriptor["expectedCandidateManifestChecksumSha256"])
        candidate_manifest = _verified_json(
            settings.artifact_root,
            descriptor["expectedCandidateManifestRelativePath"],
            candidate_manifest_checksum,
        )
        checkpoint_checksum = str(descriptor["expectedCheckpointChecksumSha256"])
        checkpoint_path = _verify_file(
            settings.artifact_root,
            descriptor["expectedCheckpointRelativePath"],
            checkpoint_checksum,
        )
        candidate_artifacts = _mapping(candidate_manifest.get("artifacts"), "artifacts")
        checkpoint_entry = _mapping(candidate_artifacts.get("checkpoint"), "checkpoint")
        if (
            decision.get("gateVersion") != V19_GATE_VERSION
            or decision.get("cohortChecksumSha256") != descriptor["cohortChecksumSha256"]
            or decision.get("activeModelFingerprintSha256")
            != descriptor["activeModelFingerprintSha256"]
            or decision.get("status") != descriptor["expectedStatus"]
            or decision.get("baseCandidateManifestChecksumSha256") != candidate_manifest_checksum
            or checkpoint_entry.get("sha256") != checkpoint_checksum
            or checkpoint_entry.get("relativePath")
            != checkpoint_path.relative_to(settings.artifact_root).as_posix()
        ):
            raise V19SymbolCandidateError(
                "V19_CANDIDATE_DECISION_DRIFT", "Candidate decision contract changed."
            )
        session = create_session_factory(create_database_engine(settings))()
        active = SqlAlchemySymbolModelSnapshotResolver(
            session, artifact_root=settings.artifact_root
        ).resolve(game_id=UUID(str(descriptor["gameId"])))
        if active.inference_fingerprint != descriptor["activeModelFingerprintSha256"]:
            raise V19SymbolCandidateError(
                "V19_CANDIDATE_ACTIVE_MODEL_DRIFT",
                "The active model changed after candidate training.",
            )
        print(
            json.dumps(
                {
                    "activeModelFingerprintSha256": active.inference_fingerprint,
                    "check": True,
                    "decisionChecksumSha256": checksum,
                    "status": decision["status"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "V19_CANDIDATE_CHECK_FAILED")
        print(json.dumps({"code": code, "message": str(error)}), file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    raise SystemExit(main())
