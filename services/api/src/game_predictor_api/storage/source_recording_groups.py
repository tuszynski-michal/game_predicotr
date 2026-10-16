"""Application-role adapter; private registry access only through fixed functions."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from game_predictor_api.domain.source_recording_groups import RecordingError
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter


class SqlAlchemySourceRecordingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bind(self, game_id: UUID, *, write: bool = False) -> None:
        GameStorageRouter().bind(
            self.session,
            game_id,
            intent=GameStorageIntent.WRITE if write else GameStorageIntent.READ,
        )

    def lineage(self, game_id: UUID, base_id: UUID, family_id: UUID) -> dict[str, Any]:
        from game_predictor_api.storage.grid_model_registry import (
            SqlAlchemyGridModelRegistryRepository,
        )

        self.bind(game_id)
        registry = SqlAlchemyGridModelRegistryRepository(self.session)
        registry.lock()
        version = registry.version(base_id)
        if version is None:
            raise RecordingError(
                "RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED", "Base lineage is unavailable.", 422
            )
        if version.family_id != family_id:
            from game_predictor_api.domain.new_game_geometry import verified_json

            fork = registry.family_fork(family_id)
            if (
                fork is None
                or fork.base_version_id != version.id
                or fork.base_manifest_sha256 != version.manifest_sha256
            ):
                raise RecordingError(
                    "RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED",
                    "Training family differs from pinned base.",
                    422,
                )
            frozen = verified_json(fork.lineage_json, fork.lineage_sha256)
            ancestors = frozen.get("ancestors", [])
            if not ancestors or (
                ancestors[0].get("versionId") != str(version.id)
                or ancestors[0].get("manifestSha256") != version.manifest_sha256
            ):
                raise RecordingError(
                    "RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED",
                    "Frozen family lineage differs from pinned base.",
                    422,
                )
            frozen["familyForks"] = {
                **frozen.get("familyForks", {}),
                str(family_id): fork.lineage_sha256,
            }
            return frozen
        return registry.lineage(base_id)

    def _call(self, statement: str, values: dict[str, Any]) -> Any:
        try:
            self.session.execute(text("SET LOCAL lock_timeout='5s'"))
            self.session.execute(text("SET LOCAL statement_timeout='30s'"))
            return self.session.execute(text(statement), values).scalar_one()
        except DBAPIError as error:
            code = str(getattr(error.orig, "sqlstate", ""))
            message = str(error.orig).splitlines()[0]
            known = {
                "RECORDING_NOT_FOUND": 404,
                "RECORDING_COMMAND_CONFLICT": 409,
                "RECORDING_REVISION_CONFLICT": 409,
                "RECORDING_SOURCE_IDENTITY_DRIFT": 409,
                "RECORDING_PAGE_CONFLICT": 409,
                "RECORDING_SOURCE_IDENTITY_UNRESOLVED": 422,
                "RECORDING_CLOSURE_UNRESOLVED": 422,
                "RECORDING_MEMBERSHIP_INCOMPLETE": 422,
                "RECORDING_PAGE_INVALID": 422,
                "RECORDING_DECLARATION_REQUIRED": 422,
                "RECORDING_ROLE_REQUIRED": 422,
                "RECORDING_MANIFEST_INVALID": 422,
                "RECORDING_COMMAND_INVALID": 422,
                "RECORDING_BINDING_INVALID": 422,
            }
            if message in known:
                raise RecordingError(
                    message, "Recording command could not be qualified.", known[message]
                ) from error
            if code in {"55P03", "57014"}:
                raise RecordingError(
                    "RECORDING_REGISTRY_BUSY", "Recording registry is busy.", 503
                ) from error
            raise

    def command(self, game_id: UUID, envelope: dict[str, Any], actor: str) -> dict[str, Any] | None:
        self.bind(game_id, write=not envelope.get("lookup", False))
        return cast(
            dict[str, Any] | None,
            self._call(
                "SELECT public.recording_command(:game,CAST(:body AS jsonb),:actor)",
                {"game": game_id, "body": json.dumps(envelope), "actor": actor},
            ),
        )

    def list_groups(
        self,
        game_id: UUID,
        family_id: UUID | None,
        limit: int,
        after: UUID | None,
        ids: list[UUID] | None = None,
        source_id: UUID | None = None,
    ) -> dict[str, Any]:
        self.bind(game_id)
        source_argument = ",CAST(:source AS uuid)" if source_id is not None else ""
        return cast(
            dict[str, Any],
            self._call(
                "SELECT public.resolve_own_groups("
                f":game,CAST(:ids AS uuid[]),:family,:limit,:after{source_argument})",
                {
                    "game": game_id,
                    "ids": ids or [],
                    "family": family_id,
                    "limit": limit,
                    "after": after,
                    **({"source": source_id} if source_id is not None else {}),
                },
            ),
        )

    def source_pages(
        self, game_id: UUID, selection: dict[str, Any]
    ) -> Iterator[list[dict[str, Any]]]:
        self.bind(game_id)
        self.session.execute(text("SET LOCAL statement_timeout='30s'"))
        result = self.session.execute(
            text("""SELECT id,checksum_sha256 AS byte,normalized_pixel_checksum_sha256 AS pixel,
            oriented_width AS width,oriented_height AS height,
            normalization_adapter_version AS adapter
            FROM game_data_v2.source_images WHERE game_id=:game
            AND ((CAST(:ids AS uuid[]) IS NOT NULL AND id=ANY(CAST(:ids AS uuid[])))
              OR (CAST(:job AS uuid) IS NOT NULL AND import_job_id=CAST(:job AS uuid)))
            ORDER BY id"""),
            {
                "game": game_id,
                "ids": selection.get("sourceIds"),
                "job": selection.get("importJobId"),
            },
            execution_options={"stream_results": True, "yield_per": 200},
        ).mappings()
        for batch in result.partitions(200):
            yield [{**dict(row), "id": str(row["id"])} for row in batch]

    def attest(self, game_id: UUID, ids: list[UUID]) -> list[dict[str, Any]]:
        self.bind(game_id)
        return cast(
            list[dict[str, Any]],
            self._call(
                "SELECT public.attest_own_source_ids(:game,CAST(:ids AS uuid[]))",
                {"game": game_id, "ids": ids},
            ),
        )
