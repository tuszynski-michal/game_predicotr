"""Paged cohort capture and immutable file publication with database CAS receipts."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid5

from PIL import __version__ as pillow_version
from sqlalchemy import Uuid, column, func, select, table

from game_predictor_api.domain.canonical_source import CANONICAL_SOURCE_LOADER_VERSION
from game_predictor_api.domain.grid_training_cohorts import (
    MATERIALIZATION_PAGE_SIZE,
    POLICY,
    SNAPSHOT_FORMAT,
    WEIGHT_POLICY,
    GridCohortError,
    canonical,
    require_minima,
)
from game_predictor_api.domain.new_game_geometry import verified_json
from game_predictor_api.storage.grid_cohort_asset_retention import acquire_cohort_asset_guard
from game_predictor_api.storage.grid_model_registry_models import GridModelVersionModel
from game_predictor_api.storage.grid_training_cohort_evidence import GridCohortEvidenceReader
from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortModel as Cohort
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortPageModel as Page,
)
from game_predictor_api.storage.grid_training_cohort_repository import CohortDeadline
from game_predictor_api.storage.source_recording_groups import SqlAlchemySourceRecordingRepository

if TYPE_CHECKING:
    from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService


def prepare(
    service: GridTrainingCohortService, game: UUID, body: dict[str, Any], actor: str
) -> dict[str, Any]:
    repo = service.repository
    deadline = CohortDeadline()
    repo.bind(game, write=True)
    repo.key_lock(game, "prepare", body["idempotencyKey"])
    if replay := repo.replay(game, "prepare", body, None):
        return replay
    lineage = SqlAlchemySourceRecordingRepository(repo.session).lineage(
        game, UUID(body["baseVersionId"]), UUID(body["familyId"])
    )
    base = repo.session.get(GridModelVersionModel, UUID(body["baseVersionId"]))
    if base is None:
        raise GridCohortError("GRID_MODEL_BASE_UNAVAILABLE", "The immutable base is unavailable.")
    manifest = verified_json(base.manifest_json, base.manifest_sha256)
    selection = body["selector"]
    sources_table = table(
        "source_images", column("id", Uuid), column("game_id", Uuid), column("import_job_id", Uuid)
    )
    selector = select(sources_table.c.id).where(sources_table.c.game_id == game)
    imports = [UUID(value) for value in selection.get("importJobIds") or []]
    if selection.get("sourceIds"):
        selector = selector.where(
            sources_table.c.id.in_([UUID(value) for value in selection["sourceIds"]])
        )
    elif imports:
        selector = selector.where(sources_table.c.import_job_id.in_(imports))
    else:
        selector = selector.where(sources_table.c.import_job_id == UUID(selection["importJobId"]))
    count = repo.session.scalar(select(func.count()).select_from(selector.subquery()))
    # Every listed import must hold own sources of the game: an exact selection, not a filter.
    covered = (
        repo.session.scalar(
            select(func.count(func.distinct(sources_table.c.import_job_id))).where(
                sources_table.c.game_id == game, sources_table.c.import_job_id.in_(imports)
            )
        )
        if imports
        else 0
    )
    if (
        not count
        or (selection.get("sourceIds") and count != len(selection["sourceIds"]))
        or (imports and covered != len(imports))
    ):
        raise GridCohortError(
            "GRID_COHORT_SELECTION_UNAVAILABLE",
            "The exact own source selection is unavailable.",
            404,
        )
    identifier = uuid5(game, "grid-cohort:" + body["idempotencyKey"])
    document = {
        "schemaVersion": POLICY,
        "policyVersion": POLICY,
        "weightPolicy": WEIGHT_POLICY,
        "mode": body["mode"],
        "familyId": body["familyId"],
        "baseVersionId": body["baseVersionId"],
        "base": {
            "versionId": str(base.id),
            "familyId": str(base.family_id),
            "manifestSha256": base.manifest_sha256,
            "manifest": manifest,
        },
        "lineage": lineage,
        "selector": {
            key: selection[key]
            for key in ("sourceIds", "importJobId", "importJobIds")
            if selection.get(key) is not None
        },
        "recordings": body["recordings"],
        "sourceCount": count,
        "preprocessing": {
            key: manifest[key]
            for key in ("preprocessingVersion", "decodingPolicyVersion", "inferenceManifest")
        },
    }
    row = Cohort(
        game_id=game,
        id=identifier,
        revision=1,
        status="preparing",
        document=document,
        summary={"roles": [], "reasonCounts": {}},
        created_by=actor,
    )
    repo.session.add(row)
    repo.session.flush()
    # INSERT SELECT fixes exact own membership and deterministic ordinals without
    # loading a recording-sized identifier array into the application.
    selected = selector.subquery()
    from sqlalchemy import cast, insert, literal
    from sqlalchemy.dialects.postgresql import ARRAY, JSONB
    from sqlalchemy.dialects.postgresql import UUID as PGUUID

    from game_predictor_api.storage.grid_training_cohort_models import (
        GridTrainingCohortMemberModel as Member,
    )

    repo.session.execute(
        insert(Member).from_select(
            [
                "game_id",
                "cohort_id",
                "source_id",
                "live_source_image_id",
                "ordinal",
                "role",
                "frozen",
                "board_ids",
                "review_ids",
                "cell_ids",
            ],
            select(
                literal(game),
                literal(identifier),
                selected.c.id,
                selected.c.id,
                func.row_number().over(order_by=selected.c.id) - 1,
                literal(None),
                cast(literal("{}"), JSONB),
                cast(literal("{}"), ARRAY(PGUUID())),
                cast(literal("{}"), ARRAY(PGUUID())),
                cast(literal("{}"), ARRAY(PGUUID())),
            ),
        )
    )
    persisted_count = repo.session.scalar(
        select(func.count())
        .select_from(Member)
        .where(Member.game_id == game, Member.cohort_id == identifier)
    )
    if persisted_count != count:
        raise GridCohortError(
            "GRID_COHORT_SELECTION_CHANGED",
            "The selected import membership changed during preparation.",
        )
    deadline.check(repo.session)
    repo.event(game, identifier, "prepared", {"sourceCount": count})
    return repo.receipt(game, row, "prepare", body, "prepared")


def _preview_sha(repo: Any, row: Cohort) -> str:
    checksum = hashlib.sha256(canonical(row.document))
    for page in repo.pages(row.game_id, row.id, "capture"):
        checksum.update(page.sha256.encode("ascii"))
    checksum.update(
        canonical({key: value for key, value in row.summary.items() if key != "previewSha256"})
    )
    return checksum.hexdigest()


def _capture(
    service: GridTrainingCohortService,
    game: UUID,
    row: Cohort,
    body: dict[str, Any],
    deadline: CohortDeadline,
) -> None:
    repo = service.repository
    capture_start = datetime.now(UTC).isoformat()
    cursor = body["cursor"]
    if row.status != "preparing" or cursor != repo.next_capture(row):
        raise GridCohortError(
            "GRID_COHORT_CURSOR_CONFLICT", "Capture must continue at its saved cursor."
        )
    members = repo.members(game, row.id, cursor)
    previous = None
    # Stored ordinals follow source UUID order. The capability resolves only
    # already-persisted members; no second discovery resolver is introduced.
    if cursor:
        from game_predictor_api.storage.grid_training_cohort_models import (
            GridTrainingCohortMemberModel as Member,
        )

        previous = repo.session.scalar(
            select(Member.source_id).where(
                Member.game_id == game, Member.cohort_id == row.id, Member.ordinal == cursor - 1
            )
        )
    mapping = {
        item["sourceId"]: item for item in repo.recording_page(game, row.id, previous)["items"]
    }
    reader = GridCohortEvidenceReader(repo.session, service.artifacts.root)
    captures = []
    for member in members:
        deadline.check(repo.session)
        proof = mapping.get(str(member.source_id))
        if proof is None:
            raise GridCohortError(
                "RECORDING_PAGE_MISMATCH", "The stored member page did not resolve exactly."
            )
        captures.append(
            reader.capture(game, member.source_id, member.ordinal, proof, row.document["mode"])
        )
    capture_window = {"startedAt": capture_start, "completedAt": datetime.now(UTC).isoformat()}
    published = service.artifacts.publish_json(
        game,
        row.id,
        {
            "schemaVersion": "application-grid-capture-page-v1",
            "captureWindow": capture_window,
            "members": captures,
        },
    )
    repo.bind(game, write=True)
    locked = repo.cohort(game, row.id, lock=True)
    repo.cas(locked, body["expectedRevision"])
    for member, frozen in zip(members, captures, strict=True):
        member.frozen, member.role = frozen, frozen["role"]
        labels = [position["label"] for position in frozen["positions"] if position["label"]]
        member.board_ids = [UUID(label["boardId"]) for label in labels]
        member.review_ids = [UUID(label["reviewItemId"]) for label in labels]
        member.cell_ids = [UUID(value) for value in frozen["dependencyCellIds"]]
    repo.session.add(
        Page(
            game_id=game,
            cohort_id=row.id,
            kind="capture",
            page_index=cursor,
            path=published["path"],
            sha256=published["sha256"],
            document={**published, "captureWindow": capture_window, "assets": [published]},
        )
    )
    repo.session.flush()
    with repo.session.no_autoflush:
        repo.refresh_summary(locked)
        if repo.next_capture(locked) is None:
            locked.summary = {**locked.summary, "previewSha256": _preview_sha(repo, locked)}
            locked.status = "preview_ready"
        locked.revision += 1


def _materialize(
    service: GridTrainingCohortService,
    game: UUID,
    row: Cohort,
    body: dict[str, Any],
    deadline: CohortDeadline,
) -> None:
    repo, cursor = service.repository, body["cursor"]
    if row.status not in ("preview_ready", "materializing") or cursor != repo.next_materialization(
        row
    ):
        raise GridCohortError(
            "GRID_COHORT_CURSOR_CONFLICT", "Materialization must continue at its saved cursor."
        )
    sources = []
    from game_predictor_api.storage.grid_training_cohort_currentness import check_member

    for member in repo.members(game, row.id, cursor, MATERIALIZATION_PAGE_SIZE):
        deadline.check(repo.session)
        frozen = member.frozen
        original = None
        if frozen["used"]:
            check_member(repo, member)
            original = service.artifacts.copy_source(game, row.id, frozen["source"])
        sources.append(
            {
                "sourceId": str(member.source_id),
                "ordinal": member.ordinal,
                "role": member.role,
                "used": frozen["used"],
                "reasons": frozen["reasons"],
                "sourceIdentity": frozen["source"],
                "original": original,
                "targets": [
                    position["label"] for position in frozen["positions"] if position["label"]
                ]
                if frozen["used"]
                else [],
                "screenEligible": frozen["screenEligible"],
            }
        )
    published = service.artifacts.publish_json(
        game,
        row.id,
        {
            "schemaVersion": "application-grid-snapshot-page-v1",
            "firstOrdinal": sources[0]["ordinal"],
            "lastOrdinal": sources[-1]["ordinal"],
            "sources": sources,
        },
    )
    published.update(
        boardCount=sum(len(value["targets"]) for value in sources),
        screenCount=sum(value["used"] and value["screenEligible"] for value in sources),
    )
    last = sources[-1]["ordinal"] + 1 == row.document["sourceCount"]
    root = None
    if last:

        def descriptors(kind: str) -> Iterator[dict[str, Any]]:
            for page in repo.pages(game, row.id, kind):
                keys = ("path", "sha256", "bytes", "boardCount", "screenCount")
                yield {key: page.document[key] for key in keys if key in page.document}
            if kind == "materialization":
                yield published

        page_index = service.artifacts.publish_index(game, row.id, descriptors("materialization"))
        capture_index = service.artifacts.publish_index(game, row.id, descriptors("capture"))
        require_minima(row.summary)
        root = service.artifacts.publish_json(
            game,
            row.id,
            {
                "schemaVersion": SNAPSHOT_FORMAT,
                "policyVersion": POLICY,
                "weightPolicy": WEIGHT_POLICY,
                "gameId": str(game),
                "cohortId": str(row.id),
                "familyId": row.document["familyId"],
                "mode": row.document["mode"],
                "base": row.document["base"],
                "decoder": {
                    "adapterVersion": CANONICAL_SOURCE_LOADER_VERSION,
                    "pixelAlgorithm": "rgb-uint8-v1",
                    "pillowVersion": pillow_version,
                },
                "preprocessing": row.document["preprocessing"],
                "pageIndex": page_index,
                "captureIndex": capture_index,
                "pageCount": (row.document["sourceCount"] + 4) // 5,
                "previewSha256": row.summary["previewSha256"],
                "counts": {
                    item["role"]: {
                        "boards": item["eligibleBoards"],
                        "photos": item["eligiblePhotos"],
                        "fullPhotos": item["eligibleFullPhotos"],
                    }
                    for item in row.summary["roles"]
                },
            },
        )
    repo.bind(game, write=True)
    locked = repo.cohort(game, row.id, lock=True)
    repo.cas(locked, body["expectedRevision"])
    repo.session.add(
        Page(
            game_id=game,
            cohort_id=row.id,
            kind="materialization",
            page_index=cursor,
            path=published["path"],
            sha256=published["sha256"],
            document={
                **published,
                "sources": [
                    {
                        "role": value["role"],
                        "used": value["used"],
                        "boards": len(value["targets"]),
                        "full": value["screenEligible"],
                    }
                    for value in sources
                ],
                "assets": [
                    published,
                    *(value["original"] for value in sources if value["original"] is not None),
                    *([root, page_index, capture_index] if root else []),
                ],
            },
        )
    )
    repo.session.flush()
    locked.status = "ready_to_freeze" if root else "materializing"
    if root:
        locked.manifest_path, locked.manifest_sha256 = root["path"], root["sha256"]
    locked.revision += 1


def execute(
    service: GridTrainingCohortService,
    game: UUID,
    identifier: UUID,
    kind: str,
    body: dict[str, Any],
    actor: str,
) -> dict[str, Any]:
    if kind == "freeze":
        from game_predictor_api.application.grid_training_cohort_freeze import freeze

        return freeze(service, game, identifier, body, actor)
    deadline, repo = CohortDeadline(), service.repository
    repo.bind(game)
    repo.key_lock(game, kind, body["idempotencyKey"])
    if replay := repo.replay(game, kind, body, identifier):
        return replay
    row = repo.cohort(game, identifier)
    repo.cas(row, body["expectedRevision"])
    if kind in ("prepare-page", "materialize-page"):
        acquire_cohort_asset_guard(repo.session, game, identifier, deadline=deadline)
    if kind == "prepare-page":
        _capture(service, game, row, body, deadline)
    elif kind == "materialize-page":
        _materialize(service, game, row, body, deadline)
    elif kind == "cancel":
        repo.bind(game, write=True)
        row = repo.cohort(game, identifier, lock=True)
        repo.cas(row, body["expectedRevision"])
        if row.status in ("frozen", "canceled"):
            raise GridCohortError("GRID_COHORT_STATE_CONFLICT", "This cohort cannot be canceled.")
        row.status, row.revision = "canceled", row.revision + 1
    else:
        raise GridCohortError(
            "GRID_COHORT_COMMAND_INVALID", "Unknown explicit cohort command.", 422
        )
    deadline.check(repo.session)
    repo.event(game, identifier, kind, {"revision": row.revision})
    return repo.receipt(game, row, kind, body, "completed")
