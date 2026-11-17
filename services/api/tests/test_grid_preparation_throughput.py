"""Compatibility and bounded work for materialization of existing cohorts."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.application import grid_training_cohort_commands as commands
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.storage.grid_cohort_materialization_progress import (
    PROGRESS_KEY,
    saved_counts,
)
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository as Repository,
)


def summary():
    return {
        "roles": [
            {"role": role, "eligibleBoards": 60, "eligiblePhotos": 20, "eligibleFullPhotos": 10}
            for role in ("TRAIN", "VALIDATION", "REGRESSION")
        ],
        "reasonCounts": {"EXCLUDED": 1},
        "previewSha256": "unchanged",
    }


def source(role="TRAIN", *, used=True, boards=3, full=False):
    return {"role": role, "used": used, "boards": boards, "full": full}


def counts_repository(pages):
    calls = []
    repo = object.__new__(Repository)

    def read(*args):
        calls.append(args)
        return iter(
            SimpleNamespace(page_index=index * 5, document={"sources": page})
            for index, page in enumerate(pages)
        )

    repo.pages = read
    return repo, calls


def cohort():
    return SimpleNamespace(
        game_id=uuid4(), id=uuid4(), revision=4, document={"sourceCount": 13}, summary=summary()
    )


def test_legacy_counts_bootstrap_once_then_survive_new_repository():
    pages = [[source(), source("VALIDATION", full=True), source(None, used=False)]]
    repo, scans = counts_repository(pages)
    row = cohort()
    old_summary = deepcopy(row.summary)
    prior = repo.summary_view(row)
    assert len(scans) == 1
    repo.record_materialized_counts(row, 5, [source(boards=2)], 10)
    row.revision += 1
    assert len(scans) == 2
    assert {key: row.summary[key] for key in old_summary} == old_summary
    new_repo, new_scans = counts_repository(pages)
    current = new_repo.summary_view(row)
    assert not new_scans
    assert current["roles"][0]["materializedBoards"] == 5
    assert current["roles"][0]["materializedPhotos"] == 2
    assert current["roles"][1] == prior["roles"][1]
    assert PROGRESS_KEY not in current
    new_repo.record_materialized_counts(row, 10, [source("REGRESSION")], 13)
    row.revision += 1
    assert not new_scans
    assert saved_counts(row.summary, row.revision, 13, cursor=13)["REGRESSION"]["photos"] == 1


@pytest.mark.parametrize("change", ["revision", "cursor", "negative", "role", "boolean", "limit"])
def test_invalid_or_stale_derived_counts_are_rebuilt_from_pages(change):
    pages = [[source(boards=2)]]
    repo, scans = counts_repository(pages)
    row = cohort()
    repo.record_materialized_counts(row, 5, [source(boards=1)], 10)
    row.revision += 1
    progress = row.summary[PROGRESS_KEY]
    if change == "revision":
        progress["revision"] -= 1
    elif change == "cursor":
        progress["throughCursor"] = 99
    elif change == "negative":
        progress["counts"]["TRAIN"]["boards"] = -1
    elif change == "role":
        del progress["counts"]["REGRESSION"]
    elif change == "boolean":
        progress["counts"]["TRAIN"]["boards"] = True
    else:
        progress["counts"]["TRAIN"]["photos"] = 21
    assert repo.summary_view(row)["roles"][0]["materializedBoards"] == 2
    assert len(scans) == 2


def test_cursor_mismatch_cannot_increment_stale_counts():
    repo, _ = counts_repository([[source(boards=2)]])
    row = cohort()
    repo.record_materialized_counts(row, 5, [source(boards=1)], 10)
    row.revision += 1
    repo.record_materialized_counts(row, 5, [source(boards=4)], 10)
    row.revision += 1
    assert repo.summary_view(row)["roles"][0]["materializedBoards"] == 6


def test_bootstrap_excludes_the_just_inserted_page_before_adding_its_counts():
    repo, scans = counts_repository([[source(boards=2)], [source(boards=4)]])
    row = cohort()
    repo.record_materialized_counts(row, 5, [source(boards=4)], 10)
    row.revision += 1
    assert repo.summary_view(row)["roles"][0]["materializedBoards"] == 6
    assert len(scans) == 1


def execute_fixture(monkeypatch, *, total=103, elapsed=0):
    row = SimpleNamespace(id=uuid4(), revision=9, status="materializing", cursor=5)
    calls, events, receipts = [], [], []

    def cas(row, expected):
        if row.revision != expected:
            raise GridCohortError("GRID_COHORT_REVISION_CONFLICT", "stale")

    def materialize(service, game, row, body, deadline):
        cas(row, body["expectedRevision"])
        assert body["cursor"] == row.cursor
        calls.append(row.cursor)
        row.cursor = min(row.cursor + 5, total)
        row.revision += 1
        if row.cursor == total:
            row.status = "ready_to_freeze"

    def receipt(game, row, kind, body, outcome):
        receipts.append(dict(body))
        return {"revision": row.revision, "cursor": row.cursor}

    repo = SimpleNamespace(
        bind=lambda *a, **k: None,
        key_lock=lambda *a: None,
        replay=lambda *a: None,
        cohort=lambda *a: row,
        cas=cas,
        next_materialization=lambda row: row.cursor,
        session=object(),
        event=lambda *a: events.append(a),
        receipt=receipt,
    )
    monkeypatch.setattr(commands, "_materialize", materialize)
    monkeypatch.setattr(commands, "acquire_cohort_asset_guard", lambda *a, **k: None)
    monkeypatch.setattr(commands, "CohortDeadline", lambda: SimpleNamespace(check=lambda *a: None))
    clock = iter([0, *([elapsed] * 21)])
    monkeypatch.setattr(commands, "monotonic", lambda: next(clock))
    body = {"expectedRevision": 9, "cursor": 5, "idempotencyKey": str(uuid4())}
    return SimpleNamespace(repository=repo), row, body, calls, events, receipts


def test_ordinary_command_keeps_one_physical_page(monkeypatch):
    service, row, body, calls, events, receipts = execute_fixture(monkeypatch)
    commands.execute(service, uuid4(), row.id, "materialize-page", body, "owner")
    assert calls == [5] and row.cursor == 10 and row.revision == 10
    assert len(events) == len(receipts) == 1 and body["cursor"] == 5


def test_internal_group_preserves_pages_and_bounds_receipts(monkeypatch):
    service, row, body, calls, events, receipts = execute_fixture(monkeypatch)
    result = commands.execute(
        service, uuid4(), row.id, "materialize-page", body, "owner", materialization_pages=20
    )
    assert calls == list(range(5, 103, 5))
    assert result == {"cursor": 103, "revision": 29}
    assert row.status == "ready_to_freeze" and len(events) == len(receipts) == 1


def test_group_yields_after_time_slice_and_keeps_original_input(monkeypatch):
    service, row, body, calls, _, _ = execute_fixture(monkeypatch, elapsed=2)
    original = dict(body)
    commands.execute(
        service, uuid4(), row.id, "materialize-page", body, "owner", materialization_pages=20
    )
    assert calls == [5] and body == original


@pytest.mark.parametrize("limit", [0, 21, True, 1.5])
def test_invalid_internal_group_is_rejected_before_storage(monkeypatch, limit):
    service, row, body, calls, _, _ = execute_fixture(monkeypatch)
    with pytest.raises(ValueError):
        commands.execute(
            service, uuid4(), row.id, "materialize-page", body, "owner", materialization_pages=limit
        )
    assert not calls


def test_unchanged_receipt_replays_before_any_materialization(monkeypatch):
    service, row, body, calls, _, _ = execute_fixture(monkeypatch)
    service.repository.replay = lambda *a: {"old": "response"}
    assert commands.execute(
        service, uuid4(), row.id, "materialize-page", body, "owner", materialization_pages=20
    ) == {"old": "response"}
    assert not calls


def test_group_and_ordinary_pages_publish_identical_labels_images_and_root(monkeypatch, tmp_path):
    import hashlib
    from io import BytesIO

    from game_predictor_api.domain.canonical_source import decode_canonical_source_bytes
    from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
    from PIL import Image

    members = []
    originals = []
    for index in range(20):
        stream = BytesIO()
        Image.new("RGB", (80, 60), (index * 10, 34, 56)).save(stream, format="JPEG")
        raw = stream.getvalue()
        sha = hashlib.sha256(raw).hexdigest()
        frame = decode_canonical_source_bytes(raw, expected_source_checksum_sha256=sha)
        identity = {
            "relative_path": f"originals/{index}.jpg",
            "checksum_sha256": sha,
            "normalized_pixel_checksum_sha256": frame.source.normalized_pixel_checksum_sha256,
            "normalization_adapter_version": frame.source.normalization_adapter_version,
            "oriented_width": 80,
            "oriented_height": 60,
            "exif_orientation": None,
        }
        role = "TRAIN" if index < 10 else "VALIDATION" if index < 15 else "REGRESSION"
        members.append(
            SimpleNamespace(
                source_id=uuid4(),
                ordinal=index,
                role=role,
                frozen={
                    "used": True,
                    "source": identity,
                    "reasons": [],
                    "recording": {},
                    "positions": [
                        {"label": {"position": p, "nodes": [{"x": 2.5, "y": 3.75}]}}
                        for p in range(3)
                    ],
                    "screenEligible": False,
                },
            )
        )
        originals.append(raw)
    monkeypatch.setattr(commands, "deleted_original_checksums", lambda *a: set())
    monkeypatch.setattr(commands, "acquire_cohort_asset_guard", lambda *a, **k: None)
    monkeypatch.setattr(commands, "CohortDeadline", lambda: SimpleNamespace(check=lambda *a: None))
    monkeypatch.setattr(commands, "monotonic", lambda: 0)
    from game_predictor_api.storage import grid_training_cohort_currentness

    monkeypatch.setattr(grid_training_cohort_currentness, "check_member", lambda *a: None)
    game, identifier, family, base = uuid4(), uuid4(), uuid4(), uuid4()

    def prepare(directory):
        for index, raw in enumerate(originals):
            target = directory / f"data/originals/{index}.jpg"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        row = SimpleNamespace(
            id=identifier,
            game_id=game,
            status="preview_ready",
            revision=1,
            manifest_path=None,
            manifest_sha256=None,
            created_at=None,
            document={
                "sourceCount": 20,
                "policyVersion": "application-grid-cohort-v1",
                "familyId": str(family),
                "baseVersionId": str(base),
                "mode": "grid-only",
                "base": {},
                "preprocessing": {},
            },
            summary={
                "previewSha256": "a" * 64,
                "roles": [
                    {
                        "role": r,
                        "eligibleBoards": n * 3,
                        "eligiblePhotos": n,
                        "eligibleFullPhotos": 0,
                        "missingBoards": 0,
                        "missingPhotos": 0,
                        "missingFullPhotos": 0,
                        "recordingRequired": False,
                    }
                    for r, n in [("TRAIN", 10), ("VALIDATION", 5), ("REGRESSION", 5)]
                ],
                "reasonCounts": {},
            },
        )
        pages = []
        repo = object.__new__(Repository)
        repo.session = SimpleNamespace(add=pages.append, flush=lambda: None)
        repo.bind = lambda *a, **k: None
        repo.cohort = lambda *a, **k: row
        repo.key_lock = lambda *a: None
        repo.replay = lambda *a: None
        repo.event = lambda *a: None
        repo.cas = (
            lambda row, expected: None if row.revision == expected else pytest.fail("revision")
        )
        repo.lock_materialization = lambda row, expected: row
        repo.members = lambda game, identifier, cursor, limit: members[cursor : cursor + limit]
        repo.iter_members = lambda *a: iter(members)
        repo.pages = lambda game, identifier, kind: iter(p for p in pages if p.kind == kind)
        repo.next_materialization = lambda row: len(pages) * 5 if len(pages) < 4 else None
        repo.receipt = lambda *a: {"cohort": repo.view(row)}
        return SimpleNamespace(repository=repo, artifacts=GridCohortArtifactStore(directory)), row

    ordinary, old_row = prepare(tmp_path / "ordinary")
    grouped, new_row = prepare(tmp_path / "grouped")
    for cursor in range(0, 20, 5):
        commands.execute(
            ordinary,
            game,
            identifier,
            "materialize-page",
            {
                "cursor": cursor,
                "expectedRevision": old_row.revision,
                "idempotencyKey": str(uuid4()),
            },
            "owner",
        )
    commands.execute(
        grouped,
        game,
        identifier,
        "materialize-page",
        {"cursor": 0, "expectedRevision": 1, "idempotencyKey": str(uuid4())},
        "owner",
        materialization_pages=20,
    )
    assert old_row.manifest_sha256 == new_row.manifest_sha256
    assert old_row.revision == new_row.revision == 5
    assert old_row.status == new_row.status == "ready_to_freeze"
    for page in ordinary.repository.pages(game, identifier, "materialization"):
        assert (
            ordinary.artifacts.safe(page.path).read_bytes()
            == grouped.artifacts.safe(page.path).read_bytes()
        )


@pytest.mark.parametrize(
    "status,kind",
    [
        ("preparing", "prepare-page"),
        ("preview_ready", "materialize-page"),
        ("materializing", "materialize-page"),
        ("ready_to_freeze", "freeze"),
    ],
)
def test_parent_groups_only_materialization(status, kind):
    from contextlib import nullcontext

    from game_predictor_api.application.grid_correction_learning import (
        GridCorrectionLearningService,
    )

    row = SimpleNamespace(document={})
    session = SimpleNamespace(get=lambda *a: row, begin=lambda: nullcontext())
    calls = []
    cohort_service = SimpleNamespace(
        repository=SimpleNamespace(bind=lambda *a: None),
        get=lambda *a: {
            "status": status,
            "revision": 7,
            "nextCaptureCursor": 200,
            "nextMaterializationCursor": 5,
            "previewSha256": "a" * 64,
            "manifestSha256": "b" * 64,
        },
        command=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    service = object.__new__(GridCorrectionLearningService)
    service.session_factory = lambda: nullcontext(session)
    service._cohorts = lambda *a: cohort_service
    job = SimpleNamespace(
        id=uuid4(),
        game_id=uuid4(),
        checkpoint_payload=None,
        input_payload={"actor": "owner", "pins": {}, "preview": {}},
    )
    _, finished = service.advance(job)
    assert not finished and len(calls) == 1
    args, kwargs = calls[0]
    assert args[2] == kind
    assert kwargs == ({"materialization_pages": 20} if kind == "materialize-page" else {})


def test_materialization_lock_projects_revision_and_allows_fk_key_share():
    from sqlalchemy.dialects import postgresql

    statements = []
    repo = object.__new__(Repository)
    repo.session = SimpleNamespace(scalar=lambda statement: statements.append(statement) or 7)
    row = SimpleNamespace(game_id=uuid4(), id=uuid4(), revision=7)
    assert repo.lock_materialization(row, 7) is row
    sql = str(statements[0].compile(dialect=postgresql.dialect()))
    assert "FOR NO KEY UPDATE" in sql and "document" not in sql
    with pytest.raises(GridCohortError, match="Reload"):
        repo.lock_materialization(row, 6)
