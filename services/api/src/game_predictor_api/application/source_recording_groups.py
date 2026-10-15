"""Frozen membership pages and provisional recording resolutions, without training."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID, uuid4, uuid5

from game_predictor_api.domain.source_recording_groups import (
    RecordingError,
    canonical_recording_json,
    recording_sha256,
    resolve_ancestor_references,
)
from game_predictor_api.schemas.source_recording_groups import SourceRecordingCommandRequest


class RecordingRepository(Protocol):
    def command(
        self, game_id: UUID, envelope: dict[str, Any], actor: str
    ) -> dict[str, Any] | None: ...
    def list_groups(
        self,
        game_id: UUID,
        family_id: UUID | None,
        limit: int,
        after: UUID | None,
        ids: list[UUID] | None = None,
    ) -> dict[str, Any]: ...
    def source_pages(
        self, game_id: UUID, selection: dict[str, Any]
    ) -> Iterator[list[dict[str, Any]]]: ...
    def attest(self, game_id: UUID, ids: list[UUID]) -> list[dict[str, Any]]: ...
    def lineage(self, game_id: UUID, base_id: UUID, family_id: UUID) -> dict[str, Any]: ...


class RecordingProviders(Protocol):
    def read(self, lineage: dict[str, Any]) -> dict[str, dict[str, Any]]: ...


class UnresolvedRecordingProviders:
    def read(self, lineage: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {}


class RecordingManifestStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve() / "data" / "recording-memberships"

    def path(self, game: UUID, identifier: UUID) -> Path:
        result = self.root / str(game) / str(identifier)
        if not result.resolve().is_relative_to(self.root) or any(
            p.is_symlink() for p in (self.root, result.parent, result)
        ):
            raise RecordingError("RECORDING_MANIFEST_INVALID", "Unsafe membership storage.")
        return result

    @staticmethod
    def publish(path: Path, payload: object) -> str:
        content = canonical_recording_json(payload).encode()
        checksum = hashlib.sha256(content).hexdigest()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.is_symlink() or path.read_bytes() != content:
                raise RecordingError("RECORDING_MANIFEST_DRIFT", "Membership evidence changed.")
            return checksum
        temporary = path.parent / f".{uuid4().hex[:16]}.tmp"
        try:
            with temporary.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            try:
                # Atomic create without replacing another command's published evidence.
                if os.name == "nt":
                    # Windows rename fails if destination already exists.
                    os.rename(temporary, path)
                else:
                    os.link(temporary, path)
            except FileExistsError as error:
                if path.is_symlink() or path.read_bytes() != content:
                    raise RecordingError(
                        "RECORDING_MANIFEST_DRIFT", "Membership evidence changed."
                    ) from error
        finally:
            temporary.unlink(missing_ok=True)
        return checksum

    @staticmethod
    def read(path: Path, expected: str | None = None) -> dict[str, Any]:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_048_576:
            raise RecordingError(
                "RECORDING_MANIFEST_INVALID", "Membership evidence is unavailable."
            )
        content = path.read_bytes()
        if expected and hashlib.sha256(content).hexdigest() != expected:
            raise RecordingError("RECORDING_MANIFEST_DRIFT", "Membership evidence changed.")
        return cast(dict[str, Any], json.loads(content))


class SourceRecordingGroupsService:
    def __init__(
        self,
        repository: RecordingRepository,
        artifact_root: Path,
        providers: RecordingProviders | None = None,
    ) -> None:
        self.repository = repository
        self.manifests = RecordingManifestStore(artifact_root)
        self.providers = providers or UnresolvedRecordingProviders()

    def list_groups(
        self,
        game: UUID,
        family: UUID | None,
        limit: int,
        after: UUID | None,
        group_id: UUID | None = None,
    ) -> dict[str, Any]:
        return self.repository.list_groups(
            game, family, limit, after, [group_id] if group_id else None
        )

    def execute(
        self, game: UUID, command: SourceRecordingCommandRequest, actor: str
    ) -> dict[str, Any]:
        body = command.model_dump(mode="json", by_alias=True, exclude_none=True)
        envelope: dict[str, Any] = {"request": body, "lookup": True}
        previous = self.repository.command(game, envelope, actor)
        if previous is not None:
            return previous
        envelope.pop("lookup")
        if command.kind == "prepare":
            identifier = uuid5(game, str(command.idempotency_key))
            directory = self.manifests.path(game, identifier)
            manifest_path = directory / "manifest.json"
            if manifest_path.exists():
                manifest = self.manifests.read(manifest_path)
                if manifest["requestSha256"] != recording_sha256(body):
                    raise RecordingError(
                        "RECORDING_COMMAND_CONFLICT", "Preparation key has different input."
                    )
            else:
                pages = []
                count = 0
                for index, rows in enumerate(self.repository.source_pages(game, body["selection"])):
                    checksum = self.manifests.publish(
                        directory / f"{index:08d}.json", {"sources": rows}
                    )
                    pages.append(checksum)
                    count += len(rows)
                if count == 0 or (
                    body["selection"].get("sourceIds")
                    and count != len(body["selection"]["sourceIds"])
                ):
                    raise RecordingError(
                        "RECORDING_NOT_FOUND", "Selected sources are unavailable.", 404
                    )
                manifest = {
                    "schemaVersion": "recording-membership-v1",
                    "id": str(identifier),
                    "gameId": str(game),
                    "count": count,
                    "pages": pages,
                    "requestSha256": recording_sha256(body),
                }
                self.manifests.publish(manifest_path, manifest)
            envelope["manifest"] = {
                "id": str(identifier),
                "sha256": recording_sha256(manifest),
                "count": manifest["count"],
                "pages": len(manifest["pages"]),
            }
        elif command.kind == "attach":
            assert (
                command.group_id is not None
                and command.manifest_id is not None
                and command.page_index is not None
            )
            view = self.repository.list_groups(game, None, 1, None, [command.group_id])["items"][0]
            directory = self.manifests.path(game, command.manifest_id)
            manifest = self.manifests.read(directory / "manifest.json", view["manifestSha256"])
            if command.page_index >= len(manifest["pages"]):
                raise RecordingError("RECORDING_PAGE_INVALID", "Unknown membership page.", 422)
            page = self.manifests.read(
                directory / f"{command.page_index:08d}.json", manifest["pages"][command.page_index]
            )
            rows = self.repository.attest(game, [UUID(row["id"]) for row in page["sources"]])
            expected = {row["id"]: row for row in page["sources"]}
            for row in rows:
                pinned = expected[row["sourceId"]]
                if any(
                    pinned[key] != row[target]
                    for key, target in (
                        ("byte", "byteSha256"),
                        ("pixel", "pixelSha256"),
                        ("width", "width"),
                        ("height", "height"),
                        ("adapter", "adapter"),
                    )
                ):
                    raise RecordingError(
                        "RECORDING_SOURCE_IDENTITY_DRIFT",
                        "Source identity changed after membership capture.",
                    )
            envelope["sourceIds"] = [row["sourceId"] for row in rows]
            envelope["identities"] = rows
        elif command.kind == "freeze":
            assert command.base_version_id is not None and command.family_id is not None
            lineage = self.repository.lineage(game, command.base_version_id, command.family_id)
            resolved = resolve_ancestor_references(lineage, self.providers.read(lineage))
            envelope["ancestry"] = {
                "complete": resolved.complete,
                "lineageSha256": resolved.lineage_sha256,
                "references": list(resolved.references),
            }
        result = self.repository.command(game, envelope, actor)
        assert result is not None
        return result
