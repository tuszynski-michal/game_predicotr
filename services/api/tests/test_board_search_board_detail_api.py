from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.board_search_board_detail import (
    BoardSearchBoardDetailService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search import BoardSearchAssetMode, BoardSearchError
from game_predictor_api.domain.board_search_board_detail import (
    BoardSearchBoardCell,
    BoardSearchBoardDocument,
    BoardSearchBoardViewSource,
    PaylineLabel,
    board_cell_quads,
    board_view,
    board_view_crop,
)
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.main import create_app
from game_predictor_worker.domain.contracts import (
    PaylineDefinition,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
    SymbolDefinition,
)
from game_predictor_worker.payouts.contracts import RulesPayoutConfiguration

_GAME_ID = uuid4()
_RULES_VERSION_ID = uuid4()
_REVIEW_ITEM_ID = uuid4()
A, B, W = 1, 2, 9
_ = None
_LATTICE = [
    {"x": 100.0, "y": 200.0},
    {"x": 600.0, "y": 200.0},
    {"x": 600.0, "y": 500.0},
    {"x": 100.0, "y": 500.0},
]


def _configuration() -> RulesPayoutConfiguration:
    symbols = (
        SymbolDefinition(mobile_code=A, code="A", name="A", is_wildcard=False, display_order=0),
        SymbolDefinition(mobile_code=B, code="B", name="B", is_wildcard=False, display_order=1),
        SymbolDefinition(mobile_code=W, code="W", name="Joker", is_wildcard=True, display_order=2),
    )
    rules = tuple(
        PayoutRuleDefinition(symbol_mobile_code=code, match_length=length, payout_credits=credits)
        for code in (A, B)
        for length, credits in zip((3, 4, 5), (10, 25, 50), strict=True)
    )
    return RulesPayoutConfiguration(
        rules_version_id=_RULES_VERSION_ID,
        rules_game_id=_GAME_ID,
        version=4,
        status=RulesVersionStatus.PUBLISHED,
        rows=3,
        columns=5,
        spin_cost=100,
        symbols=symbols,
        paylines=(
            PaylineDefinition(id="top", row_path=(0, 0, 0, 0, 0)),
            PaylineDefinition(id="middle", row_path=(1, 1, 1, 1, 1)),
        ),
        payout_symbols=(
            PayoutSymbolDefinition(symbol_mobile_code=A, minimum_match_length=3),
            PayoutSymbolDefinition(symbol_mobile_code=B, minimum_match_length=3),
        ),
        payout_rules=rules,
    )


def _document(
    codes: tuple[int | None, ...],
    *,
    sequence_number: int = 42,
    status: str = "pending",
) -> BoardSearchBoardDocument:
    return BoardSearchBoardDocument(
        sequence_number=sequence_number,
        status=status,
        board_checksum_sha256="c" * 64,
        mobile_codes=codes,
        asset_mode=BoardSearchAssetMode.OPERATIONAL_REVIEW,
        review_item_id=_REVIEW_ITEM_ID,
    )


class MemoryBoardDetailRepository:
    def __init__(
        self,
        *,
        document: BoardSearchBoardDocument | None,
        configuration: RulesPayoutConfiguration | None = None,
        geometry: Mapping[str, object] | None = None,
        current_checksum: str = "c" * 64,
    ) -> None:
        self._document = document
        self._configuration = configuration
        self._geometry = geometry
        self._current_checksum = current_checksum

    def latest_published_rules(self, game_id: UUID) -> RulesPayoutConfiguration | None:
        return self._configuration

    def board_document(
        self, *, game_id: UUID, sequence_number: int
    ) -> tuple[BoardSearchAssetMode, BoardSearchBoardDocument | None]:
        if game_id != _GAME_ID:
            raise BoardSearchError("GAME_NOT_FOUND", "The selected game does not exist.")
        document = self._document
        if document is not None and document.sequence_number != sequence_number:
            document = None
        return BoardSearchAssetMode.OPERATIONAL_REVIEW, document

    def board_view_source(
        self, *, game_id: UUID, document: BoardSearchBoardDocument
    ) -> BoardSearchBoardViewSource | None:
        return BoardSearchBoardViewSource(
            image_relative_path="imports/source.jpg",
            image_checksum_sha256="d" * 64,
            geometry=self._geometry,
            current_board_checksum_sha256=self._current_checksum,
        )

    def payline_labels(self, rules_version_id: UUID) -> Mapping[str, PaylineLabel]:
        return {
            "top": PaylineLabel("top", "L1", "Górna", 1, (0, 0, 0, 0, 0)),
            "middle": PaylineLabel("middle", "L0", "Środkowa", 0, (1, 1, 1, 1, 1)),
        }

    def symbol_codes(self, game_id: UUID) -> Mapping[int, str]:
        return {A: "A", B: "B", W: "W"}

    def refresh_board_document(self, *, game_id: UUID, document: BoardSearchBoardDocument) -> None:
        # The rebuilt document now matches the board's current identity.
        self.refreshed = [*getattr(self, "refreshed", []), document.sequence_number]
        self._current_checksum = document.board_checksum_sha256
        if getattr(self, "remove_on_refresh", False):
            self._document = None

    def board_cells(
        self, *, game_id: UUID, document: BoardSearchBoardDocument
    ) -> tuple[BoardSearchBoardCell, ...]:
        self.cell_reads = getattr(self, "cell_reads", 0) + 1
        return tuple(
            cell for cell in self._all_cells() if cell.cell_index < getattr(self, "cell_count", 15)
        )

    def _all_cells(self) -> tuple[BoardSearchBoardCell, ...]:
        return tuple(
            BoardSearchBoardCell(
                cell_index=index,
                cell_review_id=UUID(int=index + 1),
                revision=3,
                geometry_revision=2,
                crop_sample_id="a" * 64,
                crop_checksum_sha256="b" * 64,
                review_state="pending",
                quality_issue=None,
                assigned_symbol_code="A",
            )
            for index in range(15)
        )


def _client(repository: MemoryBoardDetailRepository) -> TestClient:
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
        ),
        board_search_board_detail_service_dependency=(
            lambda: BoardSearchBoardDetailService(repository)
        ),
    )
    return TestClient(app)


def _get(repository: MemoryBoardDetailRepository, sequence_number: int = 42):  # type: ignore[no-untyped-def]
    return _client(repository).get(
        f"/api/v1/admin/games/{_GAME_ID}/board-search/boards/{sequence_number}"
    )


def test_complete_board_returns_both_lines_in_payline_order_and_view_polygons() -> None:
    codes = (A, A, A, A, A, B, B, B, A, A, A, B, A, B, A)
    response = _get(
        MemoryBoardDetailRepository(
            document=_document(codes),
            configuration=_configuration(),
            geometry={"latticeBoundsQuad": _LATTICE},
        )
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["payoutKind"] == "exact"
    assert body["payoutCredits"] == 60
    assert [match["paylineCode"] for match in body["matches"]] == ["L0", "L1"]
    middle, top = body["matches"]
    assert middle["matchedCells"] == [5, 6, 7]
    assert middle["symbolCode"] == "B"
    assert middle["payoutCredits"] == 10
    assert top["matchedCells"] == [0, 1, 2, 3, 4]
    assert top["payoutCredits"] == 50
    assert sum(match["payoutCredits"] for match in body["matches"]) == body["payoutCredits"]
    assert body["symbolCodes"][:5] == ["A"] * 5
    assert body["rules"]["algorithmVersion"] == "payout-v3-unknown-prefix-stop"
    view = body["view"]
    assert view["width"] == 700 and view["height"] == 420
    assert len(view["revision"]) == 64
    assert len(view["cellPolygons"]) == 15
    first = view["cellPolygons"][0][0]
    assert abs(first["x"] - 100 / 700) < 1e-6 and abs(first["y"] - 60 / 420) < 1e-6


def test_board_cut_on_the_right_keeps_a_confirmed_minimum() -> None:
    codes = (A, A, A, A, _, B, A, B, A, B, B, A, B, A, B)
    body = _get(
        MemoryBoardDetailRepository(document=_document(codes), configuration=_configuration())
    ).json()
    assert body["payoutKind"] == "confirmed_minimum"
    assert [(match["paylineId"], match["matchedLength"]) for match in body["matches"]] == [
        ("top", 4)
    ]
    assert body["payoutCredits"] == 25
    assert body["symbolCodes"][4] is None


def test_board_cut_on_the_left_never_pays_even_with_a_run_in_columns_two_to_five() -> None:
    codes = (_, A, A, A, A, _, B, B, B, B, _, A, B, A, B)
    body = _get(
        MemoryBoardDetailRepository(document=_document(codes), configuration=_configuration())
    ).json()
    assert body["matches"] == []
    assert body["payoutCredits"] == 0
    assert body["payoutKind"] == "none"


def test_joker_cells_are_reported_inside_a_winning_line() -> None:
    codes = (W, A, A, B, B, B, A, B, A, B, A, B, A, B, A)
    body = _get(
        MemoryBoardDetailRepository(document=_document(codes), configuration=_configuration())
    ).json()
    assert [(match["matchedCells"], match["jokerCells"]) for match in body["matches"]] == [
        ([0, 1, 2], [0])
    ]


def test_board_without_payout_returns_no_lines() -> None:
    codes = (A, B, A, B, A, B, A, B, A, B, A, B, A, B, A)
    body = _get(
        MemoryBoardDetailRepository(document=_document(codes), configuration=_configuration())
    ).json()
    assert body["matches"] == [] and body["payoutKind"] == "none"
    assert body["view"] is None


def test_missing_document_is_not_found() -> None:
    response = _get(MemoryBoardDetailRepository(document=None, configuration=_configuration()))
    assert response.status_code == 404
    assert response.json()["code"] == "BOARD_SEARCH_BOARD_NOT_FOUND"


def test_missing_rules_and_symbols_outside_rules_are_conflicts() -> None:
    codes = (A,) * 15
    no_rules = _get(MemoryBoardDetailRepository(document=_document(codes)))
    assert no_rules.status_code == 409
    assert no_rules.json()["code"] == "APPROXIMATE_WIN_RULES_NOT_PUBLISHED"
    outside = _get(
        MemoryBoardDetailRepository(
            document=_document((7,) + (A,) * 14), configuration=_configuration()
        )
    )
    assert outside.status_code == 409
    assert outside.json()["code"] == "APPROXIMATE_WIN_BOARD_SYMBOL_OUTSIDE_RULES"


def test_a_stale_document_keeps_its_lines_without_photo_or_cell_editing() -> None:
    """TASK-0773: a grid revised after the search document was written. The
    lines still explain the table (both read the document), but no photo and
    no cells are offered until the board is refreshed."""

    repository = MemoryBoardDetailRepository(
        document=_document((A,) * 15),
        configuration=_configuration(),
        geometry={"latticeBoundsQuad": _LATTICE},
        current_checksum="e" * 64,
    )
    response = _get(repository)
    assert response.status_code == 200
    body = response.json()
    assert body["documentStale"] is True
    assert body["view"] is None
    assert body["cells"] is None
    assert len(body["matches"]) == 2
    assert getattr(repository, "cell_reads", 0) == 0


def test_refresh_rebuilds_one_stale_board_and_restores_its_view() -> None:
    repository = MemoryBoardDetailRepository(
        document=_document((A,) * 15),
        configuration=_configuration(),
        geometry={"latticeBoundsQuad": _LATTICE},
        current_checksum="e" * 64,
    )
    response = _client(repository).post(
        f"/api/v1/admin/games/{_GAME_ID}/board-search/boards/42/refresh"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert repository.refreshed == [42]  # type: ignore[attr-defined]
    assert body["documentRemoved"] is False
    assert body["detail"]["documentStale"] is False
    assert body["detail"]["view"] is not None
    assert len(body["detail"]["cells"]) == 15


def test_refresh_that_removes_the_document_is_reported_not_a_404() -> None:
    repository = MemoryBoardDetailRepository(
        document=_document((A,) * 15),
        configuration=_configuration(),
        current_checksum="e" * 64,
    )
    repository.remove_on_refresh = True  # type: ignore[attr-defined]
    response = _client(repository).post(
        f"/api/v1/admin/games/{_GAME_ID}/board-search/boards/42/refresh"
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"documentRemoved": True, "detail": None}


def test_refresh_of_a_missing_document_is_not_found() -> None:
    missing = _client(
        MemoryBoardDetailRepository(document=None, configuration=_configuration())
    ).post(f"/api/v1/admin/games/{_GAME_ID}/board-search/boards/42/refresh")
    assert missing.status_code == 404


def test_saved_cell_quads_win_over_the_derived_lattice() -> None:
    explicit = [
        {"x": 1.0, "y": 2.0},
        {"x": 3.0, "y": 2.0},
        {"x": 3.0, "y": 4.0},
        {"x": 1.0, "y": 4.0},
    ]
    quads = board_cell_quads(
        {
            "latticeBoundsQuad": _LATTICE,
            "cells": [{"rowIndex": 0, "columnIndex": 0, "sourceQuad": explicit}],
        }
    )
    assert quads is not None
    assert quads[0] == ((1.0, 2.0), (3.0, 2.0), (3.0, 4.0), (1.0, 4.0))
    assert quads[14][2] == (600.0, 500.0)


def test_malformed_geometry_never_invents_a_grid() -> None:
    assert board_cell_quads({}) is None
    assert board_cell_quads({"cells": [{"rowIndex": 3, "columnIndex": 0}]}) is None
    assert board_cell_quads({"latticeBoundsQuad": [{"x": 1, "y": 2}]}) is None
    assert board_cell_quads({"quad": [[0, 0], [0, 0], [0, 0], [0, 0]]}) is None
    assert board_cell_quads({"quad": [[0, 0], [10, 0], [10, float("nan")], [0, 10]]}) is None


def test_view_crop_is_independent_of_the_image_and_downscales_large_boards() -> None:
    quads = board_cell_quads({"latticeBoundsQuad": [[0, 0], [4000, 0], [4000, 2000], [0, 2000]]})
    assert quads is not None
    crop = board_view_crop(quads)
    assert crop is not None
    assert (crop.left, crop.top, crop.right, crop.bottom) == (-800, -400, 4800, 2400)
    assert (crop.width, crop.height) == (1280, 640)
    view = board_view(quads, crop, revision="r")
    assert view.cell_polygons[0][0] == (round(800 / 5600, 6), round(400 / 2800, 6))


def test_unknown_game_is_not_found_over_http() -> None:
    response = _client(
        MemoryBoardDetailRepository(document=None, configuration=_configuration())
    ).get(f"/api/v1/admin/games/{uuid4()}/board-search/boards/42")
    assert response.status_code == 404
    assert response.json()["code"] == "GAME_NOT_FOUND"


def test_absurd_geometry_yields_no_view_instead_of_an_error() -> None:
    body = _get(
        MemoryBoardDetailRepository(
            document=_document((A,) * 15),
            configuration=_configuration(),
            geometry={"quad": [[0, 0], [1e308, 0], [1e308, 1e308], [0, 1e308]]},
        )
    ).json()
    assert body["view"] is None
    huge = _get(
        MemoryBoardDetailRepository(
            document=_document((A,) * 15),
            configuration=_configuration(),
            geometry={"quad": [[0, 0], [100000, 0], [100000, 100000], [0, 100000]]},
        )
    ).json()
    assert huge["view"] is None


def test_the_first_present_lattice_key_decides_like_the_admin_client() -> None:
    assert board_cell_quads({"latticeBoundsQuad": [{"x": 1}], "quad": _LATTICE}) is None


def test_pending_board_exposes_its_cell_review_records_for_correction() -> None:
    body = _get(
        MemoryBoardDetailRepository(document=_document((A,) * 15), configuration=_configuration())
    ).json()
    cells = body["cells"]
    assert len(cells) == 15
    assert cells[3] == {
        "cellIndex": 3,
        "cellReviewId": str(UUID(int=4)),
        "revision": 3,
        "geometryRevision": 2,
        "cropSampleId": "a" * 64,
        "cropChecksumSha256": "b" * 64,
        "reviewState": "pending",
        "qualityIssue": None,
        "assignedSymbolCode": "A",
    }


def test_resolved_boards_have_no_editable_cells() -> None:
    accepted = MemoryBoardDetailRepository(
        document=_document((A,) * 15, status="accepted"), configuration=_configuration()
    )
    assert _get(accepted).json()["cells"] is None
    assert getattr(accepted, "cell_reads", 0) == 0


def test_a_partial_set_of_cell_records_is_not_offered_for_correction() -> None:
    repository = MemoryBoardDetailRepository(
        document=_document((A,) * 15), configuration=_configuration()
    )
    repository.cell_count = 14  # type: ignore[attr-defined]
    assert _get(repository).json()["cells"] is None
