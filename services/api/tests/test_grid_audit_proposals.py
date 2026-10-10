"""TASK-0840: the read-only grid-audit proposal list, its import and its HTTP surface."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_audit_proposals import create_grid_audit_proposals_router
from game_predictor_api.application.grid_audit_proposals import (
    GRID_AUDIT_MANIFEST_FILE,
    GRID_AUDIT_PROPOSALS_DIRECTORY,
    GRID_AUDIT_PROPOSALS_FILE,
    FileGridAuditProposalStore,
    GridAuditBoardReader,
    GridAuditProposalService,
)
from game_predictor_api.application.grid_audit_symbol_suggestions import (
    FileGridAuditSymbolSuggestionStore,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.grid_audit_proposals import (
    GridAuditBoardState,
    GridAuditImportStatus,
    GridAuditProposalError,
    GridAuditProposalItem,
    GridAuditQueueStatus,
    derive_grid_audit_queue_status,
    parse_grid_audit_proposal_document,
    proposal_grid_from_nodes,
)
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewError,
    ImageGridReviewListItem,
    ImageGridReviewSlotKind,
    ImageGridReviewState,
)
from game_predictor_api.main import create_app

from scripts import import_grid_audit_proposals as importer

GAME_ID = UUID("bfc4f949-5c14-4850-b02a-db99610bcfa5")


def _nodes(left: float = 100.0, top: float = 50.0, width: float = 50.0) -> list[list[float]]:
    """6 x 4 row-major lattice nodes of a slightly sheared board."""

    return [
        [left + column * width + row * 0.4, top + row * 40.0 + column * 0.6]
        for row in range(4)
        for column in range(6)
    ]


def _worklist_board(index: int, *, decided: int = 0, revision: int = 1) -> importer.WorklistBoard:
    return importer.WorklistBoard(
        item_id=f"p{index:05d}",
        verdict_source="operator" if index % 2 else "rule",
        audit_class="column_shift",
        level="S",
        human_decided_cells=decided,
        recognized_board_id=UUID(int=index + 1),
        source_image_id=UUID(int=1000 + index),
        import_job_id=UUID(int=2000),
        sequence_number=170_000 + index,
        position_index=index % 9,
        audit_geometry_revision=revision,
        network_index=index % 9,
    )


def _items(
    boards: Sequence[importer.WorklistBoard],
    current: Mapping[UUID, importer.CurrentBoard] | None = None,
) -> list[GridAuditProposalItem]:
    nodes = {(board.source_image_id, board.network_index or 0): _nodes() for board in boards}
    states = (
        {board.recognized_board_id: importer.CurrentBoard(1, True) for board in boards}
        if current is None
        else current
    )
    return importer.build_items(boards, nodes, states)


def _write(
    root: Path,
    items: Sequence[GridAuditProposalItem],
    *,
    audit_id: str = "silent-grid-777-20261004",
    created_at: str = "2026-10-04T09:00:00+00:00",
) -> Path:
    content = importer.document_bytes(
        audit_id=audit_id,
        game_id=GAME_ID,
        created_at=created_at,
        items=items,
        sources={},
        verification={"transactionReadOnly": True},
    )
    target = root / GRID_AUDIT_PROPOSALS_DIRECTORY / str(GAME_ID) / audit_id
    importer.write_artifact(
        target,
        content,
        audit_id=audit_id,
        game_id=GAME_ID,
        created_at=created_at,
        items=len(items),
    )
    return target


def _review_item(item: GridAuditProposalItem, revision: int) -> ImageGridReviewListItem:
    return ImageGridReviewListItem(
        slot_id=uuid4(),
        slot_kind=ImageGridReviewSlotKind.CURRENT_REVIEW,
        review_item_id=UUID(int=10_000 + item.ordinal),
        game_id=GAME_ID,
        import_job_id=item.import_job_id,
        recognized_board_id=item.recognized_board_id,
        pending_geometry_id=None,
        source_image_id=item.source_image_id,
        position_index=item.position_index,
        sequence_number=item.sequence_number,
        source_checksum_sha256="a" * 64,
        source_width=1200,
        source_height=900,
        geometry_revision=revision,
        approved_geometry_revision=None,
        resolution_revision=0,
        topology=BoardTopology(rows=3, columns=5),
        geometry={"quad": [{"x": 1, "y": 1}, {"x": 9, "y": 1}, {"x": 9, "y": 9}, {"x": 1, "y": 9}]},
        asset_mode="virtual_source",
        geometry_engine_name="manual_v1",
        geometry_engine_version="v1",
        board_confidence=1.0,
        reason_codes=(),
        state=ImageGridReviewState.NEEDS_VALIDATION,
    )


class MemoryBoardReader(GridAuditBoardReader):
    def __init__(self, revisions: dict[UUID, int], review_revision: int | None = None) -> None:
        self.revisions = revisions
        self.review_revision = review_revision
        self.reads = 0

    def board_states(
        self, *, game_id: UUID, board_ids: Sequence[UUID]
    ) -> Mapping[UUID, GridAuditBoardState]:
        assert game_id == GAME_ID
        self.reads += 1
        return {
            board_id: GridAuditBoardState(board_id, self.revisions[board_id], True)
            for board_id in board_ids
            if board_id in self.revisions
        }

    def review_item(
        self, *, game_id: UUID, item: GridAuditProposalItem
    ) -> ImageGridReviewListItem | None:
        revision = self.revisions.get(item.recognized_board_id)
        if revision is None:
            return None
        return _review_item(
            item, revision if self.review_revision is None else self.review_revision
        )


# --- domain -----------------------------------------------------------------------------------


def _item(status: GridAuditImportStatus, *, revision: int = 3) -> GridAuditProposalItem:
    return GridAuditProposalItem(
        ordinal=0,
        item_id="p00001",
        verdict_source="operator",
        audit_class="row_shift",
        level="S",
        human_decided_cells=0,
        recognized_board_id=UUID(int=1),
        source_image_id=UUID(int=2),
        import_job_id=UUID(int=3),
        sequence_number=1,
        position_index=0,
        audit_geometry_revision=revision,
        import_geometry_revision=revision,
        import_status=status,
        proposal=proposal_grid_from_nodes(_nodes())
        if status is GridAuditImportStatus.PROPOSAL
        else None,
    )


@pytest.mark.parametrize(
    ("status", "board", "expected"),
    [
        (GridAuditImportStatus.PROPOSAL, (3, True), GridAuditQueueStatus.OPEN),
        (GridAuditImportStatus.PROPOSAL, (4, True), GridAuditQueueStatus.CORRECTED),
        (GridAuditImportStatus.PROPOSAL, (2, True), GridAuditQueueStatus.STALE),
        (GridAuditImportStatus.PROPOSAL, (3, False), GridAuditQueueStatus.REMOVED),
        (GridAuditImportStatus.PROPOSAL, None, GridAuditQueueStatus.REMOVED),
        (GridAuditImportStatus.STALE, (4, True), GridAuditQueueStatus.STALE),
        (GridAuditImportStatus.STALE, (3, True), GridAuditQueueStatus.STALE),
        (GridAuditImportStatus.BOARD_MISSING, (3, True), GridAuditQueueStatus.REMOVED),
        (GridAuditImportStatus.NO_NETWORK_GRID, (3, True), GridAuditQueueStatus.NO_PROPOSAL),
        (GridAuditImportStatus.NO_NETWORK_GRID, (4, True), GridAuditQueueStatus.CORRECTED),
    ],
)
def test_queue_status_is_open_only_for_the_audited_revision(
    status: GridAuditImportStatus,
    board: tuple[int, bool] | None,
    expected: GridAuditQueueStatus,
) -> None:
    item = _item(status)
    state = None if board is None else GridAuditBoardState(UUID(int=1), board[0], board[1])
    assert derive_grid_audit_queue_status(item, state) is expected


def test_proposal_corners_are_the_outer_lattice_nodes_in_editor_winding() -> None:
    nodes = _nodes(left=100.4, top=49.6)
    grid = proposal_grid_from_nodes(nodes)
    assert [(point.x, point.y) for point in grid.corners] == [
        (round(nodes[0][0]), round(nodes[0][1])),
        (round(nodes[5][0]), round(nodes[5][1])),
        (round(nodes[23][0]), round(nodes[23][1])),
        (round(nodes[18][0]), round(nodes[18][1])),
    ]
    assert len(grid.nodes) == 24
    with pytest.raises(GridAuditProposalError):
        proposal_grid_from_nodes(nodes[:23])


def test_document_rejects_tampered_corners_and_proposals_on_stale_items() -> None:
    items = _items([_worklist_board(0)])
    document = json.loads(
        importer.document_bytes(
            audit_id="a",
            game_id=GAME_ID,
            created_at="2026-10-04T00:00:00+00:00",
            items=items,
            sources={},
            verification={},
        )
    )
    assert parse_grid_audit_proposal_document(document, sha256="0" * 64).items == tuple(items)
    tampered = json.loads(json.dumps(document))
    tampered["items"][0]["proposal"]["corners"][0]["x"] += 5
    with pytest.raises(GridAuditProposalError, match="malformed"):
        parse_grid_audit_proposal_document(tampered, sha256="0" * 64)
    stale = json.loads(json.dumps(document))
    stale["items"][0]["importStatus"] = "stale"
    with pytest.raises(GridAuditProposalError):
        parse_grid_audit_proposal_document(stale, sha256="0" * 64)


# --- import -----------------------------------------------------------------------------------


def test_import_marks_changed_and_missing_boards_and_keeps_symbol_boards_first(
    tmp_path: Path,
) -> None:
    audit = tmp_path / "audit"
    (audit / "review").mkdir(parents=True)
    rows = []
    suspects = []
    boards_lines = []
    network: dict[str, list[dict[str, object]]] = {}
    for index, decided in enumerate([0, 3, 0, 1]):
        board_id, image_id = UUID(int=index + 1), UUID(int=1000 + index)
        rows.append(
            {
                "itemId": f"p{index:05d}",
                "verdictSource": "operator",
                "class": "row_shift",
                "humanDecidedCells": str(decided),
                "level": "S",
                "positionIndex": "1",
                "sequenceNumber": str(500 + index),
                "recognizedBoardId": str(board_id),
                "sourceImageId": str(image_id),
                "importJobId": str(UUID(int=9)),
                "gridIssueCellReviewId": "",
                "reviewerCorrectionQueue": "",
                "gridIssueCellIndex": "",
            }
        )
        suspects.append(
            {
                "itemId": f"p{index:05d}",
                "imageId": str(image_id),
                "networkIndex": 1,
                "correction": {
                    "recognizedBoardId": str(board_id),
                    "positionIndex": 1,
                    "sequenceNumber": 500 + index,
                    "currentGeometryRevision": 1,
                },
            }
        )
        boards_lines.append(
            json.dumps({"board": {"recognizedBoardId": str(board_id), "geometryRevision": 1}})
        )
        network[str(image_id)] = [{"nodes": _nodes(0, 0)}, {"nodes": _nodes()}]
    with (audit / "review" / "correction-worklist.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (audit / "suspects.json").write_text(
        json.dumps({"paired": suspects, "savedOnly": []}), encoding="utf-8"
    )
    (audit / "boards.jsonl").write_text("\n".join(boards_lines) + "\n", encoding="utf-8")
    (audit / "network-0-of-1.jsonl").write_text(
        "".join(
            json.dumps({"boards": value, "error": None, "imageId": key}) + "\n"
            for key, value in network.items()
        ),
        encoding="utf-8",
    )
    joined = importer.join_worklist(
        importer.read_worklist(audit / importer.WORKLIST),
        importer.suspects_by_item(json.loads((audit / "suspects.json").read_text())),
        importer.audit_revisions((audit / "boards.jsonl").read_bytes().splitlines()),
    )
    assert [board.item_id for board in joined] == ["p00001", "p00003", "p00000", "p00002"]
    wanted = {board.source_image_id: {1} for board in joined}
    nodes = importer.network_nodes(
        (audit / "network-0-of-1.jsonl").read_bytes().splitlines(), wanted
    )
    current = {
        UUID(int=2): importer.CurrentBoard(1, True),
        UUID(int=4): importer.CurrentBoard(2, True),  # corrected after the audit
        UUID(int=1): importer.CurrentBoard(1, False),  # no current review item
    }
    items = importer.build_items(joined, nodes, current)
    assert [(item.item_id, item.import_status) for item in items] == [
        ("p00001", GridAuditImportStatus.PROPOSAL),
        ("p00003", GridAuditImportStatus.STALE),
        ("p00000", GridAuditImportStatus.BOARD_MISSING),
        ("p00002", GridAuditImportStatus.BOARD_MISSING),
    ]
    assert items[0].proposal == proposal_grid_from_nodes(_nodes())
    assert all(item.proposal is None for item in items[1:])
    summary = importer.summary(items)
    assert summary["withSymbolDecisions"] == 2
    assert summary["symbolDecisionCells"] == 4

    disagreeing = [dict(row) for row in importer.read_worklist(audit / importer.WORKLIST)]
    disagreeing[0]["positionIndex"] = "7"
    with pytest.raises(importer.GridAuditImportError, match="disagree"):
        importer.join_worklist(
            disagreeing,
            importer.suspects_by_item({"paired": suspects}),
            {},
        )


def test_artifact_is_immutable_and_checksum_bound(tmp_path: Path) -> None:
    target = _write(tmp_path, _items([_worklist_board(0)]))
    manifest = json.loads((target / GRID_AUDIT_MANIFEST_FILE).read_text())
    assert manifest["file"] == GRID_AUDIT_PROPOSALS_FILE
    with pytest.raises(importer.GridAuditImportError, match="immutable"):
        _write(tmp_path, _items([_worklist_board(0)]))

    store = FileGridAuditProposalStore(tmp_path)
    assert store.load(GAME_ID).sha256 == manifest["sha256"]
    with pytest.raises(GridAuditProposalError) as missing:
        store.load(uuid4())
    assert missing.value.code == "GRID_AUDIT_PROPOSALS_NOT_FOUND"

    path = target / GRID_AUDIT_PROPOSALS_FILE
    path.write_bytes(path.read_bytes().replace(b'"S"', b'"B"'))
    with pytest.raises(GridAuditProposalError) as changed:
        FileGridAuditProposalStore(tmp_path).load(GAME_ID)
    assert changed.value.code == "GRID_AUDIT_PROPOSALS_CHECKSUM_MISMATCH"


def test_store_serves_the_newest_imported_list(tmp_path: Path) -> None:
    _write(tmp_path, _items([_worklist_board(0)]), audit_id="older", created_at="2026-10-01")
    _write(
        tmp_path,
        _items([_worklist_board(0), _worklist_board(1)]),
        audit_id="newer",
        created_at="2026-10-04",
    )
    artifact = FileGridAuditProposalStore(tmp_path).load(GAME_ID)
    assert artifact.audit_id == "newer"
    assert len(artifact.items) == 2


# --- service ----------------------------------------------------------------------------------


def test_queue_is_derived_from_current_revisions(tmp_path: Path) -> None:
    boards = [_worklist_board(index, decided=1 if index < 2 else 0) for index in range(5)]
    _write(tmp_path, _items(boards))
    revisions = {board.recognized_board_id: 1 for board in boards}
    revisions[boards[1].recognized_board_id] = 2  # corrected
    revisions[boards[3].recognized_board_id] = 0  # older than the audit
    del revisions[boards[4].recognized_board_id]  # gone
    reader = MemoryBoardReader(revisions)
    service = GridAuditProposalService(FileGridAuditProposalStore(tmp_path), reader)

    page = service.queue(game_id=GAME_ID, after_ordinal=None, limit=1)
    assert [entry.item.item_id for entry in page.items] == ["p00000"]
    assert page.next_after_ordinal == 0
    assert page.counts.total == 5
    assert page.counts.open == 2
    assert page.counts.corrected == 1
    assert page.counts.stale == 1
    assert page.counts.removed == 1
    assert page.counts.open_with_symbol_decisions == 1
    following = service.queue(game_id=GAME_ID, after_ordinal=0, limit=1)
    assert [entry.item.item_id for entry in following.items] == ["p00002"]
    assert following.next_after_ordinal is None
    assert service.queue(game_id=GAME_ID, after_ordinal=2, limit=1).items == ()
    with pytest.raises(GridAuditProposalError):
        service.queue(game_id=GAME_ID, after_ordinal=None, limit=0)

    # A save through the existing path gives the board a newer revision; the
    # next read (also after a restart: nothing is stored) drops it.
    revisions[boards[0].recognized_board_id] = 2
    again = GridAuditProposalService(FileGridAuditProposalStore(tmp_path), reader)
    page = again.queue(game_id=GAME_ID, after_ordinal=None, limit=5)
    assert [entry.item.item_id for entry in page.items] == ["p00002"]
    assert page.counts.corrected == 2


def test_proposal_is_served_only_for_the_audited_revision(tmp_path: Path) -> None:
    boards = [_worklist_board(0), _worklist_board(1)]
    _write(tmp_path, _items(boards))
    revisions = {boards[0].recognized_board_id: 1, boards[1].recognized_board_id: 2}
    service = GridAuditProposalService(
        FileGridAuditProposalStore(tmp_path), MemoryBoardReader(revisions)
    )

    open_view = service.proposal(game_id=GAME_ID, item_id="p00000")
    assert open_view.entry.status is GridAuditQueueStatus.OPEN
    assert open_view.proposal is not None
    assert open_view.review_item is not None
    corrected = service.proposal(game_id=GAME_ID, item_id="p00001")
    assert corrected.entry.status is GridAuditQueueStatus.CORRECTED
    assert corrected.proposal is None
    assert corrected.review_item is None

    # The board changes between the state read and the review item read.
    racing = GridAuditProposalService(
        FileGridAuditProposalStore(tmp_path), MemoryBoardReader(revisions, review_revision=2)
    )
    raced = racing.proposal(game_id=GAME_ID, item_id="p00000")
    assert raced.entry.status is GridAuditQueueStatus.CORRECTED
    assert raced.proposal is None
    assert raced.review_item is None
    with pytest.raises(GridAuditProposalError) as missing:
        service.proposal(game_id=GAME_ID, item_id="p09999")
    assert missing.value.code == "GRID_AUDIT_PROPOSAL_ITEM_NOT_FOUND"


# --- HTTP -------------------------------------------------------------------------------------


def _http(tmp_path: Path, revisions: dict[UUID, int]) -> TestClient:
    app = FastAPI()
    store = FileGridAuditProposalStore(tmp_path)
    app.include_router(
        create_grid_audit_proposals_router(
            lambda: GridAuditProposalService(
                store, MemoryBoardReader(revisions), FileGridAuditSymbolSuggestionStore(tmp_path)
            )
        ),
        prefix="/api/v1",
    )

    @app.exception_handler(ImageGridReviewError)
    async def handle(_request: Request, error: ImageGridReviewError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"code": error.code})

    return TestClient(app)


def test_http_queue_and_proposal_contract(tmp_path: Path) -> None:
    boards = [_worklist_board(0, decided=2), _worklist_board(1)]
    _write(tmp_path, _items(boards))
    client = _http(tmp_path, {board.recognized_board_id: 1 for board in boards})
    base = f"/api/v1/admin/games/{GAME_ID}/grid-audit-proposals"

    page = client.get(base)
    assert page.status_code == 200
    body = page.json()
    assert body["auditId"] == "silent-grid-777-20261004"
    assert body["counts"] == {
        "total": 2,
        "open": 2,
        "corrected": 0,
        "stale": 0,
        "removed": 0,
        "noProposal": 0,
        "openWithSymbolDecisions": 1,
    }
    assert [item["itemId"] for item in body["items"]] == ["p00000"]
    assert body["items"][0]["status"] == "open"
    assert body["nextAfterOrdinal"] == 0
    assert (
        client.get(base, params={"afterOrdinal": 0, "limit": 5}).json()["items"][0]["itemId"]
        == "p00001"
    )
    assert client.get(base, params={"limit": 51}).status_code == 422

    proposal = client.get(f"{base}/p00000")
    assert proposal.status_code == 200
    detail = proposal.json()
    assert detail["proposal"]["provenance"] == "audit-network-proposal"
    assert detail["proposal"]["coordinateSpace"] == "exif-normalized-rgb-pixels-v1"
    expected = proposal_grid_from_nodes(_nodes()).corners
    assert detail["proposal"]["corners"] == [
        {"x": int(point.x), "y": int(point.y)} for point in expected
    ]
    assert len(detail["proposal"]["nodes"]) == 24
    assert detail["reviewItem"]["recognizedBoardId"] == str(boards[0].recognized_board_id)
    assert detail["reviewItem"]["geometryRevision"] == 1
    assert client.get(f"{base}/not-an-item").status_code == 422


def test_app_maps_missing_and_tampered_lists_without_touching_the_database(
    tmp_path: Path,
) -> None:
    app = create_app(ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path)}))
    base = f"/api/v1/admin/games/{GAME_ID}/grid-audit-proposals"
    with TestClient(app) as client:
        missing = client.get(base)
        assert missing.status_code == 404
        assert missing.json()["code"] == "GRID_AUDIT_PROPOSALS_NOT_FOUND"

        target = _write(tmp_path, _items([_worklist_board(0)]))
        path = target / GRID_AUDIT_PROPOSALS_FILE
        path.write_bytes(path.read_bytes() + b" ")
        tampered = client.get(base)
        assert tampered.status_code == 409
        assert tampered.json()["code"] == "GRID_AUDIT_PROPOSALS_CHECKSUM_MISMATCH"


def test_openapi_exposes_two_read_only_operations() -> None:
    schema = create_app(ApiSettings.from_environment({})).openapi()
    queue = schema["paths"]["/api/v1/admin/games/{game_id}/grid-audit-proposals"]
    item = schema["paths"]["/api/v1/admin/games/{game_id}/grid-audit-proposals/{item_id}"]
    assert set(queue) == {"get"}
    assert set(item) == {"get"}
    assert queue["get"]["operationId"] == "listGridAuditProposals"
    assert item["get"]["operationId"] == "getGridAuditProposal"
