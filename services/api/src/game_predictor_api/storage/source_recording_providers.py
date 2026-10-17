"""Explicit bounded installation of checksum-pinned recording ancestor providers."""

import hashlib
import json
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from game_predictor_api.domain.source_recording_groups import (
    RecordingError,
    protected_recording_mapping,
    recording_sha256,
)

SHA256 = re.compile(r"[0-9a-f]{64}")


def _ancestor_is_closed(value: dict[str, Any]) -> bool:
    if set(value) != {
        "versionId",
        "manifestSha256",
        "snapshotId",
        "cohortId",
        "publicationEvidenceSha256",
        "historicalReportSha256",
        "evaluation",
    }:
        return False
    try:
        UUID(value["versionId"])
        if value["cohortId"] is not None:
            UUID(value["cohortId"])
        if not isinstance(value["snapshotId"], str) or not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,255}", value["snapshotId"]
        ):
            return False
        if not SHA256.fullmatch(value["manifestSha256"]):
            return False
        if any(
            value[k] is not None and not SHA256.fullmatch(value[k])
            for k in ("publicationEvidenceSha256", "historicalReportSha256")
        ):
            return False
        evaluation = value["evaluation"]
        if evaluation is not None:
            if not isinstance(evaluation, dict) or set(evaluation) != {
                "evaluationId",
                "evaluationSha256",
                "cohortSha256",
            }:
                return False
            UUID(evaluation["evaluationId"])
            if any(
                not SHA256.fullmatch(evaluation[k]) for k in ("evaluationSha256", "cohortSha256")
            ):
                return False
        return True
    except (ValueError, TypeError, KeyError):
        return False


def _provider_root(artifact_root: Path) -> Path:
    base = artifact_root.resolve()
    root = base / "data" / "recording-providers"
    if not root.resolve().is_relative_to(base) or any(
        p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
        for p in (root.parent, root)
    ):
        raise RecordingError("RECORDING_PROVIDER_UNRESOLVED", "Unsafe provider storage.", 422)
    return root


@contextmanager
def _index_lease(root: Path) -> Iterator[None]:
    """OS-owned nonblocking lock releases after crash; the lock file is durable."""
    lease = root / "install.lock"
    if lease.is_symlink():
        raise RecordingError("RECORDING_PROVIDER_UNRESOLVED", "Unsafe provider lease.", 422)
    with lease.open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RecordingError(
                "RECORDING_PROVIDER_INDEX_CONFLICT", "Provider installer is busy."
            ) from error
        try:
            yield
        finally:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_provider(path: Path, checksum: str) -> dict[str, Any]:
    if (
        not SHA256.fullmatch(checksum)
        or not path.is_file()
        or path.is_symlink()
        or path.stat().st_size > 1_048_576
    ):
        raise RecordingError(
            "RECORDING_PROVIDER_UNRESOLVED", "Installed provider is unavailable.", 422
        )
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != checksum:
        raise RecordingError(
            "RECORDING_PROVIDER_UNRESOLVED", "Installed provider checksum differs.", 422
        )
    try:
        payload = json.loads(content)
        if set(payload) != {
            "schemaVersion",
            "ancestor",
            "complete",
            "recordingIdentityAvailable",
            "recordingGroups",
        }:
            raise ValueError("Unknown provider fields")
        if payload["schemaVersion"] != "recording-ancestor-provider-v1" or not isinstance(
            payload["ancestor"], dict
        ):
            raise ValueError("Unknown provider schema")
        if not _ancestor_is_closed(payload["ancestor"]):
            raise ValueError("Provider ancestor provenance differs")
        if not isinstance(payload["complete"], bool) or not isinstance(
            payload["recordingIdentityAvailable"], bool
        ):
            raise ValueError("Provider completeness must be explicit")
        if not protected_recording_mapping(payload["recordingGroups"]):
            raise ValueError("Invalid provider groups")
        return cast(dict[str, Any], payload)
    except (ValueError, TypeError, KeyError) as error:
        raise RecordingError(
            "RECORDING_PROVIDER_UNRESOLVED", "Installed provider is invalid.", 422
        ) from error


class TrustedRecordingProviders:
    """Server config pins the index SHA. No per-cohort installation or HTTP upload."""

    def __init__(self, artifact_root: Path, index_sha256: str | None = None) -> None:
        self.root = _provider_root(artifact_root)
        self.index_sha256 = index_sha256

    def read(self, lineage: dict[str, Any]) -> dict[str, dict[str, Any]]:
        if self.index_sha256 is None:
            return {}
        index_path = self.root / "index.json"
        if (
            not index_path.is_file()
            or index_path.is_symlink()
            or index_path.stat().st_size > 1_048_576
        ):
            raise RecordingError(
                "RECORDING_PROVIDER_UNRESOLVED", "Provider index is unavailable.", 422
            )
        content = index_path.read_bytes()
        if hashlib.sha256(content).hexdigest() != self.index_sha256:
            raise RecordingError(
                "RECORDING_PROVIDER_UNRESOLVED", "Provider index checksum differs.", 422
            )
        try:
            index = json.loads(content)
            if (
                set(index) != {"schemaVersion", "providers"}
                or index["schemaVersion"] != "recording-provider-index-v1"
                or not isinstance(index["providers"], dict)
            ):
                raise ValueError("Provider index schema")
            for identifier, checksum in index["providers"].items():
                UUID(identifier)
                if not isinstance(checksum, str) or not SHA256.fullmatch(checksum):
                    raise ValueError("Provider index checksum")
            result = {}
            for ancestor in lineage["ancestors"]:
                identifier = ancestor["versionId"]
                checksum = index["providers"].get(identifier)
                if checksum is not None:
                    result[identifier] = read_provider(self.root / f"{checksum}.json", checksum)
            return result
        except (ValueError, TypeError, KeyError) as error:
            raise RecordingError(
                "RECORDING_PROVIDER_UNRESOLVED", "Provider index is invalid.", 422
            ) from error


def install_recording_provider(
    artifact_root: Path, source: Path, checksum: str, expected_index_sha256: str | None
) -> str:
    """One-time explicit operator deployment action, never called by API/GET."""
    from game_predictor_api.application.source_recording_groups import RecordingManifestStore

    provider = read_provider(source, checksum)
    root = _provider_root(artifact_root)
    index_path = root / "index.json"
    index: dict[str, Any] = {"schemaVersion": "recording-provider-index-v1", "providers": {}}
    if index_path.exists():
        if index_path.is_symlink() or index_path.stat().st_size > 1_048_576:
            raise RecordingError("RECORDING_PROVIDER_UNRESOLVED", "Unsafe provider index.", 422)
        current_sha = hashlib.sha256(index_path.read_bytes()).hexdigest()
        TrustedRecordingProviders(artifact_root, current_sha).read({"ancestors": []})
        index = json.loads(index_path.read_bytes())
        if index["providers"].get(provider["ancestor"]["versionId"]) == recording_sha256(provider):
            # Lost index-publication response: read-only acknowledgement of the
            # exact already installed provider, without overwriting later entries.
            read_provider(root / f"{recording_sha256(provider)}.json", recording_sha256(provider))
            return current_sha
        if expected_index_sha256 is None or current_sha != expected_index_sha256:
            raise RecordingError("RECORDING_PROVIDER_INDEX_CONFLICT", "Provider index changed.")
        # Validate the full old index before publishing a replacement.
        TrustedRecordingProviders(artifact_root, expected_index_sha256).read({"ancestors": []})
    elif expected_index_sha256 is not None:
        raise RecordingError("RECORDING_PROVIDER_INDEX_CONFLICT", "Expected index is missing.")
    normalized_sha = RecordingManifestStore.publish(
        root / f"{recording_sha256(provider)}.json", provider
    )
    index["providers"][provider["ancestor"]["versionId"]] = normalized_sha
    # Index replacement is explicit and CAS-bound. The OS lease survives neither
    # a crash nor process exit, so the same deployment can resume after restart.
    root.mkdir(parents=True, exist_ok=True)
    with _index_lease(root):
        if (
            index_path.exists()
            and hashlib.sha256(index_path.read_bytes()).hexdigest() != expected_index_sha256
        ):
            raise RecordingError("RECORDING_PROVIDER_INDEX_CONFLICT", "Provider index changed.")
        content = json.dumps(index, sort_keys=True, separators=(",", ":")).encode()
        temporary = root / f"{hashlib.sha256(content).hexdigest()}.pending"
        RecordingManifestStore.publish(temporary, index)
        temporary.replace(index_path)
        return hashlib.sha256(content).hexdigest()
