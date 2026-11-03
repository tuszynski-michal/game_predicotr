"""Purge orchestration reuses the cleanup transaction and quarantine lifecycle."""

from typing import Any
from uuid import UUID

from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.symbol_readability import digest
from game_predictor_api.storage.source_replacement_purge import SourcePurge


class SourcePurgeService:
    def __init__(self, cleanup: Any) -> None:
        self.cleanup = cleanup
        self.store = cleanup._artifact_store
        self.repo = cleanup.replacement_plans

    @property
    def purge(self) -> SourcePurge:
        return SourcePurge(self.repo, self.cleanup._repository)

    def _preview(self, game: UUID, request: Any) -> tuple[Any, ...]:
        row, fresh, candidates, retained = self.purge.prepare(game, request)
        previews, mixed_previews = self.store.source_preview_paths(game, fresh["_purge_cell_ids"])
        candidates = tuple(sorted(set(candidates) | set(previews)))
        retained["shared_preview_atlases"] = mixed_previews
        resolved = self.store.resolve(candidates)
        if resolved.ambiguous:
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_PURGE_PATH_AMBIGUOUS", "Nie można jednoznacznie wskazać plików."
            )
        shared = self.purge.shared(resolved.present, game, [UUID(s) for s in fresh["source_ids"]])
        files = self.store.file_proof(tuple(p for p in resolved.present if p not in shared))
        identity = {
            "game": str(game),
            "batch": str(request.batch_id),
            "entry": str(request.entry_id),
            "revision": row["revision"],
            "files": files,
            "shared": sorted(shared),
            "retained": retained,
            "scope": row["document"]["frozen_scope_digest"],
        }
        response = {
            "game_id": game,
            "batch_id": request.batch_id,
            "entry_id": request.entry_id,
            "revision": row["revision"],
            "preview_token": digest(identity),
            "source_ids": fresh["source_ids"],
            "sequence_numbers": fresh["sequence_numbers"],
            "file_count": len(files),
            "missing_file_count": len(resolved.missing),
            "shared_file_count": len(shared),
            "bytes_to_delete": sum(f["size"] for f in files),
            "retained_metadata": retained,
            "record_counts": {
                "boards": len(fresh["boards"]),
                "geometry_revisions": len(fresh["geometry_revisions"]),
            },
        }
        return row, fresh, files, response

    def preview(self, game: UUID, request: Any) -> dict[str, Any]:
        return self._preview(game, request)[3]

    def execute(self, game: UUID, request: Any) -> dict[str, Any]:
        receipt = self.purge.receipt(game, request)
        if receipt is not None:
            state = self.store.recover_purge(receipt["purge"])
            return self._public_result(receipt, state)
        row, fresh, files, preview = self._preview(game, request)
        if not request.confirmed or request.preview_token != preview["preview_token"]:
            raise SourceReplacementError(
                "SOURCE_REPLACEMENT_PURGE_PREVIEW_STALE", "Potwierdź aktualny podgląd usuwania."
            )
        key = digest({"game": str(game), "command": request.model_dump(mode="json")})
        purge = {
            "operationType": "source_replacement_purge",
            "quarantineKey": key,
            "sourceIds": fresh["source_ids"],
            "fileProof": files,
            "fileCount": len(files),
            "bytesToDelete": preview["bytes_to_delete"],
            "sharedFileCount": preview["shared_file_count"],
            "missingFileCount": preview["missing_file_count"],
            "retainedMetadata": preview["retained_metadata"],
            "command": request.model_dump(mode="json", by_alias=True),
        }
        self.store.quarantine(key, tuple(f["path"] for f in files))
        try:
            result = self.purge.execute(game, request, row, fresh, purge)
        except BaseException:
            self.store.restore(key)
            raise
        self.cleanup._pending_quarantines.add(key)
        return self._public_result(result, "pending")

    @staticmethod
    def _public_result(result: dict[str, Any], status: str) -> dict[str, Any]:
        purge = {
            k: v for k, v in result["purge"].items() if k not in {"fileProof", "quarantineKey"}
        }
        purge.update(
            fileStatus=status, deletedBytes=purge["bytesToDelete"] if status == "finalized" else 0
        )
        return {**result, "purge": purge}

    def manifest(self, game: UUID, batch: UUID) -> dict[str, Any]:
        document = self.repo.get(game, batch)
        for entry in document["entries"]:
            purge = entry.get("purge")
            if purge:
                entry["purge"] = self._public_result(
                    {"purge": purge}, self.store.purge_status(purge)
                )["purge"]
        return document
