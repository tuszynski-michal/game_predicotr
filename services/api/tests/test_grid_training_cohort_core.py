"""Small CPU regressions for exact labels, bounded copies and durable publication."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.grid_training_cohort_commands import _materialize
from game_predictor_api.domain.canonical_source import decode_canonical_source_bytes
from game_predictor_api.domain.grid_training_cohorts import (
    GridCohortError,
    exact_lattice,
    require_minima,
    role_summary,
)
from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
from game_predictor_api.storage.grid_training_cohort_currentness import check_member
from PIL import Image


def test_streamed_statement_budget_uses_normal_cursor_on_the_same_connection(monkeypatch):
    import game_predictor_api.storage.grid_training_cohort_repository as module

    now = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    deadline = module.CohortDeadline()
    statements = []

    class ServerCursor:
        def execute(self, sql):
            raise AssertionError("DECLARE CURSOR FOR SET is invalid")

    class NormalCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            statements.append("closed")

        def execute(self, sql):
            statements.append(sql)

    connection = SimpleNamespace(
        connection=SimpleNamespace(dbapi_connection=SimpleNamespace(cursor=NormalCursor))
    )
    query_cursor = ServerCursor()
    deadline.apply_statement_timeout(connection, query_cursor)
    now[0] = 158.0
    deadline.apply_statement_timeout(connection, query_cursor)
    assert statements == [
        "SET LOCAL statement_timeout=30000",
        "closed",
        "SET LOCAL statement_timeout=2000",
        "closed",
    ]
    now[0] = 160.0
    with pytest.raises(GridCohortError, match="60 second budget"):
        deadline.apply_statement_timeout(connection, query_cursor)
    # Cleanup of an aborted capability savepoint must not execute SET first,
    # and must remain possible after expiry without granting another query.
    deadline.apply_statement_timeout(connection, query_cursor, "ROLLBACK TO SAVEPOINT owned")
    assert len(statements) == 4


@pytest.mark.parametrize("statement", ["ROLLBACK", "ROLLBACK TO SAVEPOINT sa_savepoint_1"])
def test_aborted_capability_rollback_preserves_reason_after_deadline(statement):
    from game_predictor_api.storage.grid_training_cohort_repository import CohortDeadline

    deadline = CohortDeadline()
    deadline.end = 0

    def aborted_cursor():
        raise AssertionError("An aborted transaction cannot execute a control SET")

    connection = SimpleNamespace(
        connection=SimpleNamespace(dbapi_connection=SimpleNamespace(cursor=aborted_cursor))
    )
    reason = GridCohortError("RECORDING_ALIAS_CHANGED", "The actual alias proof changed.")
    with pytest.raises(GridCohortError) as preserved:
        try:
            raise reason
        except GridCohortError:
            deadline.apply_statement_timeout(connection, object(), statement)
            raise
    assert preserved.value is reason
    with pytest.raises(GridCohortError) as expired:
        deadline.apply_statement_timeout(connection, object(), "SELECT 1")
    assert expired.value.code == "GRID_COHORT_TIMEOUT"


@pytest.mark.parametrize("action", ["geometry_saved", "approved"])
def test_guarded_manual_origin_survives_later_approval_without_historical_model(tmp_path, action):
    from game_predictor_api.storage.grid_training_cohort_evidence import GridCohortEvidenceReader

    game, source, board, review, revision = [str(uuid4()) for _ in range(5)]
    target = {
        "board": {
            "id": board,
            "geometry_revision": 2,
            "source_geometry_revision_id": revision,
            "geometry_checksum_sha256": "a" * 64,
            "approved_geometry_revision": 2,
            "geometry_approved_by": "operator",
            "geometry_approved_at": "2026-10-16T00:00:00Z",
        },
        "review": {"id": review},
    }
    event = {
        "id": str(uuid4()),
        "action": action,
        "board_checksum_sha256": "a" * 64,
        "actor": "operator",
        "created_at": "2026-10-16T00:00:00Z",
    }
    reader = GridCohortEvidenceReader(None, tmp_path)

    def row(sql, **values):
        if "FROM image_board_geometry_review_events e" in sql:
            return event
        if "SELECT to_jsonb(r)" in sql:
            return {"id": str(uuid4())}
        return None

    reader._row = row
    result = reader.approval(UUID(game), UUID(source), target)
    assert result["origin"] == "human_corrected" and result["weight"] == 4
    assert result["basis"] == "guarded_manual_save"


@pytest.mark.parametrize("change", ["withdrawn", "reverted", "owner"])
def test_currentness_never_uses_repoint_exception_for_real_withdrawal(monkeypatch, change):
    import copy

    import game_predictor_api.storage.grid_training_cohort_currentness as module
    from game_predictor_api.domain.grid_training_cohorts import target_fence
    from game_predictor_api.storage.grid_reinference import source_fence

    game, source = uuid4(), uuid4()
    target = {
        "board": {
            "id": str(uuid4()),
            "geometry_revision": 0,
            "source_image_id": str(source),
            "source_geometry_revision_id": str(uuid4()),
            "approved_geometry_revision": 0,
            "geometry_approved_by": "operator",
            "geometry_approved_at": "2026-10-16T00:00:00Z",
        },
        "review": {"id": str(uuid4()), "status": "pending"},
        "owner": None,
        "foreignOwner": None,
    }
    old = copy.deepcopy(target)
    if change == "withdrawn":
        target["board"]["approved_geometry_revision"] = None
    if change == "owner":
        target["foreignOwner"] = {"id": str(uuid4())}
    monkeypatch.setattr(module, "read_source", lambda *args: {"id": str(source)})
    monkeypatch.setattr(module, "current_targets", lambda *args: {0: target})
    monkeypatch.setattr(
        module,
        "unchanged_approved_target",
        lambda *args: pytest.fail("Withdrawal reached repoint exception"),
    )
    selected = SimpleNamespace(
        game_id=game,
        source_id=source,
        live_source_image_id=source,
        role="TRAIN",
        frozen={
            "used": True,
            "sourceFence": source_fence({"id": str(source)}),
            "positions": [
                {
                    "positionIndex": 0,
                    "label": {"targetFence": target_fence(old), "approvalFence": {}},
                }
            ],
        },
    )
    session = SimpleNamespace(
        execute=lambda *args: SimpleNamespace(
            scalar_one_or_none=lambda: "reverted" if change == "reverted" else "active"
        )
    )
    with pytest.raises(GridCohortError) as error:
        check_member(SimpleNamespace(session=session), selected)
    assert error.value.code == "GRID_COHORT_LABEL_STALE"
    state = module.inspect_member(SimpleNamespace(session=session), selected)
    assert state.live_source_linked is True
    assert state.human_label_withdrawn is (None if change == "owner" else True)


@pytest.mark.parametrize(
    "states,expected_human,expected_live",
    [
        ([], None, None),
        ([(False, None, None)], None, None),
        ([(True, True, False)], False, True),
        ([(True, False, None)], None, False),
        ([(True, True, None)], None, True),
        ([(True, True, True)], True, True),
        ([(True, None, None), (True, False, True)], True, False),
    ],
)
def test_eligibility_facts_use_one_bounded_metadata_scan_and_never_read_files(
    monkeypatch, states, expected_human, expected_live
):
    import game_predictor_api.storage.grid_training_cohort_currentness as module

    monkeypatch.setattr(module.event, "listen", lambda *args: None)
    monkeypatch.setattr(module.event, "remove", lambda *args: None)
    monkeypatch.setattr(
        module, "inspect_member", lambda repo, value: module.MemberCurrentness(*value)
    )
    scans = []

    def members(*args):
        scans.append(True)
        yield from states

    summary = role_summary(
        "grid-only",
        [member("TRAIN") for _ in range(10)]
        + [member(role) for role in ("VALIDATION", "REGRESSION") for _ in range(5)],
    )
    repo = SimpleNamespace(
        session=SimpleNamespace(connection=lambda: object()),
        iter_members=members,
        recording_command=lambda *args: {},
    )
    row = SimpleNamespace(
        game_id=uuid4(),
        id=uuid4(),
        status="frozen",
        revision=7,
        manifest_sha256="a" * 64,
        summary=summary,
    )

    class NoFiles:
        def __getattribute__(self, name):
            pytest.fail("GET attempted artifact I/O")

    result = module.eligibility(repo, row, NoFiles())
    assert result["humanLabelWithdrawn"] is expected_human
    assert result["liveSourceLinked"] is expected_live
    assert result["snapshotBytesAvailable"] is None
    assert scans == [True]


@pytest.fixture(autouse=True)
def clean_exact_long_fixture(tmp_path):
    # The shared owned-TEMP helper uses an unprefixed rmtree. Remove only this
    # test's own child directory using Windows' native long-path spelling.
    yield
    import os
    import shutil
    from pathlib import Path

    if os.name == "nt":
        target = tmp_path.resolve()
        assert target.name.startswith("test_") and target != target.parent
        shutil.rmtree(Path("\\\\?\\" + str(target)))


def lattice():
    nodes = [
        {"x": float(10 + column * 12), "y": float(10 + row * 16)}
        for row in range(4)
        for column in range(6)
    ]
    nodes[8] = {"x": 35.25, "y": 27.75}
    return nodes


@pytest.mark.parametrize(
    "change,expected",
    [
        ("materialized_cells", True),
        ("symbol", True),
        ("render_configuration", False),
        ("nodes", False),
        ("grid_issue", False),
        ("source_revision_without_proof", False),
    ],
)
def test_later_cell_materialization_keeps_only_exact_geometry_and_render_parity(change, expected):
    import copy

    from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
    from game_predictor_api.domain.image_geometry_v2 import DirectCellRenderConfiguration
    from game_predictor_api.storage.grid_quality_observations import geometry_approval_fence
    from game_predictor_api.storage.grid_training_cohort_evidence import unchanged_approved_target

    game, source = uuid4(), uuid4()
    nodes, cells = exact_lattice({"latticeNodes": lattice()}, 100, 100)
    configuration = DirectCellRenderConfiguration(
        "renderer-v1", "preprocess-v1", "bilinear-v1", 16, 16, 0.1
    ).to_dict()
    old = {
        "board": {
            "id": str(uuid4()),
            "geometry_revision": 0,
            "source_geometry_revision_id": str(uuid4()),
            "geometry_checksum_sha256": "a" * 64,
            "board_geometry": {"latticeNodes": nodes},
        },
        "review": {"id": str(uuid4()), "status": "pending"},
        "owner": None,
        "foreignOwner": None,
        "pending": None,
        "cells": [],
        "renders": [],
    }
    current = copy.deepcopy(old)
    current["cells"] = [
        {"id": str(uuid4()), "cell_index": index, "quality_issue": None, "review_state": "approved"}
        for index in range(15)
    ]
    if change == "symbol":
        current["cells"][0]["predicted_symbol_id"] = str(uuid4())
    if change == "grid_issue":
        current["cells"][0].update(quality_issue="grid_issue", review_state="pending")
    live_configuration = copy.deepcopy(configuration)
    if change == "render_configuration":
        live_configuration["outputWidth"] = 17
    if change == "nodes":
        current["board"]["board_geometry"]["latticeNodes"][8]["x"] += 0.5
    if change == "source_revision_without_proof":
        current["board"]["source_geometry_revision_id"] = str(uuid4())
        current["board"]["geometry_checksum_sha256"] = "b" * 64
    entries = []
    for index, quad in enumerate(cells):
        spec = {"sourceQuad": quad, "configuration": live_configuration}
        entries.append(
            {
                "cellIndex": index,
                "renderSpec": spec,
                "renderSpecChecksumSha256": sha256_canonical_json(spec),
            }
        )
    current["renders"] = [{"cells": {"cells": entries}}]
    session = SimpleNamespace(
        connection=lambda: SimpleNamespace(
            execute=lambda *args: SimpleNamespace(scalar_one_or_none=lambda: None)
        )
    )
    assert (
        unchanged_approved_target(
            session,
            game,
            source,
            geometry_approval_fence(old),
            current,
            render_proof={"configuration": configuration, "cellQuads": cells},
            source_row={"oriented_width": 100, "oriented_height": 100},
        )
        is expected
    )


def test_exact_deformed_lattice_roundtrip_retains_inner_node_in_adjacent_cells():
    nodes = lattice()
    exported, cells = exact_lattice({"latticeNodes": nodes}, 100, 100)
    assert exported == nodes
    assert cells[1][2] == nodes[8]
    assert cells[2][3] == nodes[8]
    assert cells[6][1] == nodes[8]
    assert cells[7][0] == nodes[8]


@pytest.mark.parametrize("value", [[], lattice()[:4], [{"x": 0, "y": 0}] * 24])
def test_exact_label_never_interpolates_missing_or_invalid_nodes(value):
    with pytest.raises(GridCohortError):
        exact_lattice({"latticeNodes": value}, 100, 100)


def member(role, boards=9, *, used=True, full=True):
    return {
        "role": role,
        "used": used,
        "boardEligibleCount": boards,
        "screenEligible": full,
        "recording": {"qualification": "eligible", "groupId": role},
        "reasons": [],
    }


def test_role_minima_require_photos_and_controls_not_only_board_total():
    values = [member("TRAIN") for _ in range(10)] + [
        member(role) for role in ("VALIDATION", "REGRESSION") for _ in range(5)
    ]
    result = role_summary("grid-only", values)
    require_minima(result)
    assert sum(item["eligibleBoards"] for item in result["roles"]) == 180
    # Five nine-board control photos count as 45 labels; a single photo with
    # an inflated board total cannot satisfy the five-photo requirement.
    invalid = role_summary("grid-only", values[:10] + [member("VALIDATION", 45), *values[15:]])
    assert invalid["roles"][1]["missingPhotos"] == 4
    with pytest.raises(GridCohortError, match="independent recording"):
        require_minima(invalid)


def test_excluded_and_unknown_members_never_count_even_with_apparent_labels():
    result = role_summary("screen+grid", [member("TRAIN", used=False), member(None)])
    assert all(item["eligibleBoards"] == 0 for item in result["roles"])
    assert result["roles"][0]["missingFullPhotos"] == 10


def test_immutable_publish_survives_new_store_and_lost_response(tmp_path):
    game, cohort = uuid4(), uuid4()
    first = GridCohortArtifactStore(tmp_path).publish_json(game, cohort, {"nodes": lattice()})
    restarted = GridCohortArtifactStore(tmp_path)
    assert restarted.publish_json(game, cohort, {"nodes": lattice()}) == first
    assert restarted.read_json(first["path"], first["sha256"])["nodes"] == lattice()
    assert not list(tmp_path.rglob("*.staged"))
    restarted.safe(first["path"]).write_bytes(b"changed")
    with pytest.raises(GridCohortError, match="changed"):
        restarted.read_json(first["path"], first["sha256"])


@pytest.mark.parametrize("path", ["../outside", "C:/outside", "data\\outside", "/outside"])
def test_artifact_namespace_rejects_escaping_paths(tmp_path, path):
    with pytest.raises(GridCohortError):
        GridCohortArtifactStore(tmp_path).safe(path)


def test_copy_is_original_bytes_with_absent_exif_and_independent_restart(tmp_path):
    stream = BytesIO()
    Image.new("RGB", (80, 60), (12, 34, 56)).save(stream, format="JPEG")
    raw = stream.getvalue()
    import hashlib

    sha = hashlib.sha256(raw).hexdigest()
    frame = decode_canonical_source_bytes(raw, expected_source_checksum_sha256=sha)
    source = {
        "relative_path": "originals/tiny.jpg",
        "checksum_sha256": sha,
        "normalized_pixel_checksum_sha256": frame.source.normalized_pixel_checksum_sha256,
        "normalization_adapter_version": frame.source.normalization_adapter_version,
        "oriented_width": 80,
        "oriented_height": 60,
        "exif_orientation": None,
    }
    path = tmp_path / "data/originals/tiny.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    game, cohort = uuid4(), uuid4()
    result = GridCohortArtifactStore(tmp_path).copy_source(game, cohort, source)
    assert GridCohortArtifactStore(tmp_path).verify(result["path"], sha).read_bytes() == raw


def test_five_selected_copies_never_retain_previous_decoded_frame(tmp_path):
    import weakref

    from game_predictor_api.domain.canonical_source import CANONICAL_SOURCE_LOADER_VERSION

    class Frame:
        def __init__(self):
            self.source = SimpleNamespace(
                normalized_pixel_checksum_sha256="a" * 64,
                normalization_adapter_version=CANONICAL_SOURCE_LOADER_VERSION,
                width=10,
                height=10,
                exif_orientation=None,
            )

    previous = None
    store = GridCohortArtifactStore(tmp_path)

    def decode(source):
        nonlocal previous
        assert previous is None or previous() is None
        frame = Frame()
        previous = weakref.ref(frame)
        return frame, b"tiny"

    store.decode_source = decode
    store._publish = lambda *args: {"path": "immutable", "sha256": "b" * 64, "bytes": 4}
    source = {
        "normalized_pixel_checksum_sha256": "a" * 64,
        "normalization_adapter_version": CANONICAL_SOURCE_LOADER_VERSION,
        "oriented_width": 10,
        "oriented_height": 10,
        "exif_orientation": None,
    }
    results = [store.copy_source(uuid4(), uuid4(), source) for _ in range(5)]
    assert len(results) == 5 and previous() is None


def test_removed_source_is_distinct_from_withdrawn_label_and_missing_file():
    selected = SimpleNamespace(frozen={"used": True}, role="TRAIN", live_source_image_id=None)
    with pytest.raises(GridCohortError) as error:
        check_member(None, selected)
    assert error.value.code == "SOURCE_REMOVED_NEW_USE_BLOCKED" and error.value.status == 409


def test_removed_excluded_source_never_blocks_actual_used_members():
    from game_predictor_api.storage.grid_training_cohort_currentness import inspect_member

    selected = SimpleNamespace(frozen={"used": False}, live_source_image_id=None)
    result = inspect_member(None, selected)
    assert not result.used and result.error is None
    assert result.human_label_withdrawn is None and result.live_source_linked is None


@pytest.mark.parametrize("reverse", [False, True])
def test_removed_used_source_blocks_even_with_other_unresolved_proof(monkeypatch, reverse):
    import game_predictor_api.storage.grid_training_cohort_currentness as module

    removed = SimpleNamespace(frozen={"used": True}, live_source_image_id=None)
    unknown = object()
    real_inspect = module.inspect_member
    monkeypatch.setattr(module.event, "listen", lambda *args: None)
    monkeypatch.setattr(module.event, "remove", lambda *args: None)
    monkeypatch.setattr(
        module,
        "inspect_member",
        lambda repo, selected: real_inspect(repo, selected)
        if selected is removed
        else module.MemberCurrentness(
            True,
            True,
            None,
            GridCohortError("APPROVAL_PROVENANCE_UNRESOLVED", "The proof is unavailable."),
        ),
    )
    rows = [removed, unknown] if not reverse else [unknown, removed]
    scans = []

    def members(*args):
        scans.append(True)
        yield from rows

    repo = SimpleNamespace(
        session=SimpleNamespace(connection=lambda: object()),
        iter_members=members,
        recording_command=lambda *args: {},
    )
    row = SimpleNamespace(
        game_id=uuid4(),
        id=uuid4(),
        status="frozen",
        revision=7,
        manifest_sha256="a" * 64,
        summary=role_summary(
            "grid-only",
            [member("TRAIN") for _ in range(10)]
            + [member(role) for role in ("VALIDATION", "REGRESSION") for _ in range(5)],
        ),
    )

    class NoFiles:
        def __getattribute__(self, name):
            pytest.fail("Metadata qualification read snapshot bytes")

    result = module.eligibility(repo, row, NoFiles())
    assert result["qualification"] == "blocked"
    assert result["reasons"] == [
        "APPROVAL_PROVENANCE_UNRESOLVED",
        "SOURCE_REMOVED_NEW_USE_BLOCKED",
    ]
    assert result["liveSourceLinked"] is False
    assert result["humanLabelWithdrawn"] is None
    assert result["snapshotBytesAvailable"] is None and scans == [True]


@pytest.mark.parametrize("code", ["SOURCE_REMOVED_NEW_USE_BLOCKED", "GRID_COHORT_MINIMUM_NOT_MET"])
def test_private_typed_reason_keeps_409_and_recovers_savepoint(tmp_path, code):
    from contextlib import contextmanager

    from game_predictor_api.storage.grid_training_cohort_repository import (
        SqlAlchemyGridTrainingCohortRepository,
    )
    from sqlalchemy.exc import DBAPIError

    calls = []
    aborted = [False]

    @contextmanager
    def begin_nested():
        calls.append("savepoint")
        try:
            yield
        except DBAPIError:
            aborted[0] = False
            calls.append("rollback")
            raise

    def execute(statement, params=None):
        if "recording_cohort_command_v3" in str(statement):
            aborted[0] = True
            raise DBAPIError(str(statement), params, Exception(code))
        assert not aborted[0]
        return 1

    session = SimpleNamespace(begin_nested=begin_nested, execute=execute)
    repo = SqlAlchemyGridTrainingCohortRepository(session, tmp_path)
    with pytest.raises(GridCohortError) as error:
        repo.recording_command(uuid4(), {"kind": "validate_cohort_use"}, "fixture-human")
    assert error.value.code == code and error.value.status == 409
    assert calls == ["savepoint", "rollback"] and session.execute("SELECT 1") == 1


@pytest.mark.parametrize(
    "case",
    ["current", "already_complete", "historical", "foreign", "rejected", "superseded", "no_review"],
)
def test_identity_completion_requires_exact_current_own_target_under_existing_fences(
    monkeypatch, case
):
    import hashlib

    from game_predictor_api.application import grid_source_identities as module
    from game_predictor_api.domain.source_canonical_metadata import SourceCanonicalMetadata

    game, source_id, revision_id = uuid4(), uuid4(), uuid4()
    content = BytesIO()
    Image.new("RGB", (24, 20), "navy").save(content, format="JPEG")
    checksum = hashlib.sha256(content.getvalue()).hexdigest()
    frame = decode_canonical_source_bytes(
        content.getvalue(), expected_source_checksum_sha256=checksum
    )
    assert frame.source.exif_orientation is None
    canonical = SourceCanonicalMetadata(
        frame.raw_width,
        frame.raw_height,
        frame.source.width,
        frame.source.height,
        None,
        frame.source.coordinate_space,
        frame.source.normalization_adapter_version,
        frame.source.normalized_pixel_checksum_sha256,
    ).to_dict()
    source = {**dict.fromkeys(canonical), "checksum_sha256": checksum}
    if case == "already_complete":
        source.update(canonical)
    revision = {
        **canonical,
        "status": "current",
        "geometry_checksum_sha256": "a" * 64,
        "source_checksum_sha256": checksum,
    }
    target = {
        "board": {
            "id": str(uuid4()),
            "source_image_id": str(source_id),
            "status": "recognized",
            "source_geometry_revision_id": str(revision_id),
        },
        "review": {"id": str(uuid4()), "status": "pending"},
        "owner": None,
        "foreignOwner": None,
    }
    if case == "historical":
        target["board"]["source_geometry_revision_id"] = str(uuid4())
    elif case == "foreign":
        target["foreignOwner"] = {"id": str(uuid4())}
    elif case == "rejected":
        target["board"]["status"] = "rejected"
    elif case == "superseded":
        target["review"]["status"] = "superseded"
    elif case == "no_review":
        target["review"] = None
    events, updates, receipts = [], [], []

    def execute(statement, parameters=None):
        sql = str(statement)
        if "FOR UPDATE" in sql:
            assert events == ["decode", "ownership"]
            events.append("source_lock")
        if "to_jsonb(r)" in sql:
            assert events[-1] == "source_lock"
            return SimpleNamespace(scalar_one_or_none=lambda: revision)
        if sql.startswith("UPDATE source_images"):
            assert events[-1] == "current_targets"
            updates.append(parameters)
        return SimpleNamespace()

    session = SimpleNamespace(
        execute=execute,
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="fixture")),
        add=receipts.append,
        flush=lambda: None,
    )
    repo = SimpleNamespace(
        session=session,
        bind=lambda *a, **k: None,
        key_lock=lambda *a: None,
        identity_replay=lambda *a: None,
    )

    def decode(value):
        assert events == [] and value is source
        events.append("decode")
        return frame, content.getvalue()

    def targets(locked_session, scoped_game, scoped_source):
        assert (locked_session, scoped_game, scoped_source) == (session, game, source_id)
        assert events == ["decode", "ownership", "source_lock"]
        events.append("current_targets")
        return {0: target}

    monkeypatch.setattr(module, "read_source", lambda *a: source)
    monkeypatch.setattr(
        module, "acquire_sequence_ownership_lock", lambda *a, **k: events.append("ownership")
    )
    monkeypatch.setattr(module, "current_targets", targets)
    body = {
        "idempotencyKey": str(uuid4()),
        "sources": [
            {
                "sourceId": str(source_id),
                "expectedSourceSha256": checksum,
                "expectedSourceGeometryRevisionId": str(revision_id),
                "expectedGeometrySha256": "a" * 64,
            }
        ],
    }
    if case in ("current", "already_complete"):
        result = module.complete(repo, SimpleNamespace(decode_source=decode), game, body, "human")
        expected = "completed" if case == "current" else "already_complete"
        assert result["receipt"]["results"] == [{"sourceId": str(source_id), "outcome": expected}]
        assert len(receipts) == 1 and len(updates) == (case == "current")
        if updates:
            assert updates[0]["exif_orientation"] is None
    else:
        with pytest.raises(GridCohortError) as error:
            module.complete(repo, SimpleNamespace(decode_source=decode), game, body, "human")
        assert error.value.code == "SOURCE_GEOMETRY_IDENTITY_UNRESOLVED"
        assert not updates and not receipts


def test_materialize_excluded_member_never_reads_pixels_or_generates_negatives(tmp_path):
    game, identifier = uuid4(), uuid4()
    source = SimpleNamespace(
        source_id=uuid4(),
        ordinal=0,
        role=None,
        frozen={
            "used": False,
            "reasons": ["RECORDING_SELECTION_REQUIRED"],
            "source": {},
            "positions": [{"label": {"ignored": True}}],
            "screenEligible": False,
        },
    )
    row = SimpleNamespace(
        id=identifier, status="preview_ready", document={"sourceCount": 2}, revision=2
    )
    session = SimpleNamespace(add=lambda value: None, flush=lambda: None)
    repo = SimpleNamespace(
        session=session,
        next_materialization=lambda row: 0,
        members=lambda *args: [source],
        bind=lambda *args, **kwargs: None,
        cohort=lambda *args, **kwargs: row,
        cas=lambda *args: None,
    )
    store = GridCohortArtifactStore(tmp_path)
    store.copy_source = lambda *args: pytest.fail("Excluded source decoded")
    service = SimpleNamespace(repository=repo, artifacts=store)
    _materialize(
        service,
        game,
        row,
        {"cursor": 0, "expectedRevision": 2},
        SimpleNamespace(check=lambda *args: None),
    )
    pages = list(tmp_path.rglob("*.json"))
    import json

    value = json.loads(
        store.safe(pages[0].relative_to(tmp_path).as_posix()).read_text(encoding="utf-8")
    )["sources"][0]
    assert value["original"] is None and value["targets"] == [] and not value["used"]
    assert row.revision == 3 and row.status == "materializing"
