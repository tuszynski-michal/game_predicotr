from __future__ import annotations

from dataclasses import replace

import pytest
from game_predictor_worker.images.grid_symbol_diagnosis import CellPrediction
from game_predictor_worker.images.v19_symbol_residuals import (
    EvaluatedCell,
    ResidualBoard,
    ResidualCell,
    V19SymbolResidualError,
    build_cohort_document,
    build_evaluation_document,
    document_checksum_sha256,
)

STAGINGS = tuple(f"staging-{index}" for index in range(6))
MODEL = {
    "classCodes": ["lemon", "star"],
    "inferenceFingerprintSha256": "a" * 64,
}
TRAINING = {
    "manifestChecksumSha256": "b" * 64,
    "sourceFamilies": ["1" * 64, "2" * 64, "3" * 64, "4" * 64],
    "symbols": [
        {"sampleCount": 100, "sourceFamilyCount": 4, "symbolCode": "lemon"},
        {"sampleCount": 100, "sourceFamilyCount": 4, "symbolCode": "star"},
    ],
}


def _cell(index: int, *, symbol: str = "lemon", checksum: str | None = None) -> ResidualCell:
    digest = checksum or f"{index + 1:064x}"
    return ResidualCell(
        cell_index=index,
        symbol_code=symbol,
        crop_checksum_sha256=digest,
        crop_relative_path=f"crops/{digest[:2]}/{digest}.png",
    )


def _board(index: int) -> ResidualBoard:
    source = f"{index // 9 + 1000:064x}"
    cells = tuple(
        _cell(
            cell,
            checksum=f"{index * 15 + cell + 10_000:064x}",
        )
        for cell in range(15)
    )
    return ResidualBoard(
        board_id=f"board-{index:04d}",
        review_item_id=f"review-{index:04d}",
        import_job_id=f"job-{index % 6}",
        decision_status="corrected",
        resolution_revision=1,
        sequence_number=index + 1,
        position_index=index % 9,
        staging_label=STAGINGS[index % 6],
        source_image_id=f"source-{index // 9}",
        source_checksum_sha256=source,
        source_relative_path=f"originals/{source[:2]}/{source}.jpg",
        geometry_provenance="persisted_v19",
        cells=cells,
    )


def _cohort(boards: tuple[ResidualBoard, ...] | None = None) -> dict[str, object]:
    return build_cohort_document(
        boards or tuple(_board(index) for index in range(300)),
        game_id="game",
        required_stagings=STAGINGS,
        model=MODEL,
        training_dataset=TRAINING,
    )


def _evaluated_cells(
    cohort: dict[str, object],
    *,
    mistakes: dict[tuple[str, int], tuple[str, float]] | None = None,
    parity_failure: tuple[str, int] | None = None,
) -> tuple[EvaluatedCell, ...]:
    result: list[EvaluatedCell] = []
    mistakes = mistakes or {}
    for raw_board in cohort["boards"]:
        source = raw_board["sourceFamily"]
        for raw_cell in raw_board["cells"]:
            identity = (raw_board["boardId"], raw_cell["cellIndex"])
            predicted, confidence = mistakes.get(identity, (raw_cell["symbolCode"], 0.98))
            result.append(
                EvaluatedCell(
                    board_id=raw_board["boardId"],
                    sequence_number=raw_board["sequenceNumber"],
                    cell_index=raw_cell["cellIndex"],
                    staging_label=raw_board["stagingLabel"],
                    source_family=source,
                    expected_symbol=raw_cell["symbolCode"],
                    prediction=CellPrediction(predicted, confidence),
                    crop_checksum_sha256=raw_cell["cropChecksumSha256"],
                    preprocessing_parity=identity != parity_failure,
                )
            )
    return tuple(result)


def test_cohort_is_deterministic_and_split_has_no_source_leakage() -> None:
    boards = tuple(_board(index) for index in range(300))

    first = _cohort(boards)
    second = _cohort(tuple(reversed(boards)))

    assert document_checksum_sha256(first) == document_checksum_sha256(second)
    split = first["split"]["sourceFamilies"]
    assigned = [source for sources in split.values() for source in sources]
    assert len(assigned) == len(set(assigned))
    assert first["scope"] == {
        "boardCount": 300,
        "minimumBoardCount": 300,
        "sourceFamilyCount": 34,
        "stagingCount": 6,
        "stagingLabels": list(STAGINGS),
    }


def test_cohort_records_audited_label_conflicts_without_adding_them_to_boards() -> None:
    conflicts = (
        {
            "evidenceCropChecksumsSha256": ["f" * 64],
            "reason": "visual_label_or_slot_conflict",
            "sequenceNumber": 901,
        },
    )

    cohort = build_cohort_document(
        tuple(_board(index) for index in range(300)),
        game_id="game",
        required_stagings=STAGINGS,
        model=MODEL,
        training_dataset=TRAINING,
        audited_label_conflicts=conflicts,
    )

    assert cohort["auditedLabelConflicts"] == list(conflicts)

    with pytest.raises(V19SymbolResidualError) as included_error:
        build_cohort_document(
            tuple(_board(index) for index in range(300)),
            game_id="game",
            required_stagings=STAGINGS,
            model=MODEL,
            training_dataset=TRAINING,
            audited_label_conflicts=(
                {**conflicts[0], "sequenceNumber": 1},
            ),
        )

    assert included_error.value.code == "V19_SYMBOL_COHORT_AUDITED_CONFLICT_INCLUDED"


def test_cohort_rejects_too_few_boards_and_missing_staging() -> None:
    with pytest.raises(V19SymbolResidualError) as error:
        _cohort(tuple(_board(index) for index in range(299)))

    assert error.value.code == "V19_SYMBOL_COHORT_TOO_SMALL"


def test_cohort_rejects_conflicting_labels_for_identical_crop() -> None:
    boards = list(_board(index) for index in range(300))
    conflicting = replace(
        boards[1],
        cells=(
            _cell(0, symbol="star", checksum=boards[0].cells[0].crop_checksum_sha256),
            *boards[1].cells[1:],
        ),
    )
    boards[1] = conflicting

    with pytest.raises(V19SymbolResidualError) as error:
        _cohort(tuple(boards))

    assert error.value.code == "V19_SYMBOL_COHORT_LABEL_CONFLICT"


def test_cohort_rejects_unknown_symbol_and_unsafe_crop_path() -> None:
    boards = list(_board(index) for index in range(300))
    boards[0] = replace(
        boards[0],
        cells=(_cell(0, symbol="unknown"), *boards[0].cells[1:]),
    )

    with pytest.raises(V19SymbolResidualError) as symbol_error:
        _cohort(tuple(boards))

    assert symbol_error.value.code == "V19_SYMBOL_COHORT_SYMBOL_UNKNOWN"
    with pytest.raises(V19SymbolResidualError) as path_error:
        ResidualCell(
            cell_index=0,
            symbol_code="lemon",
            crop_checksum_sha256="f" * 64,
            crop_relative_path="../outside.png",
        )

    assert path_error.value.code == "V19_SYMBOL_COHORT_CROP_PATH_INVALID"


def test_evaluation_classifies_unseen_source_confusion_as_m2_and_retrain() -> None:
    cohort = _cohort()
    boards = cohort["boards"]
    mistakes = {
        (board["boardId"], 0): ("star", 0.995)
        for board in boards[:50]
    }

    report = build_evaluation_document(
        cohort,
        _evaluated_cells(cohort, mistakes=mistakes),
    )

    assert report["decision"] == {
        "reasons": ["VERIFIED_V19_MODEL_RESIDUAL_EXCEEDS_GATE"],
        "value": "retrain",
    }
    residual = report["residuals"][0]
    assert residual["classification"] == "M2"
    assert residual["expectedSymbolCode"] == "lemon"
    assert residual["predictedSymbolCode"] == "star"
    assert len(report["highConfidenceErrors"]) == 50


def test_audited_label_conflict_is_open_and_does_not_become_model_error() -> None:
    cohort = build_cohort_document(
        tuple(_board(index) for index in range(300)),
        game_id="game",
        required_stagings=STAGINGS,
        model=MODEL,
        training_dataset=TRAINING,
        audited_label_conflicts=(
            {
                "evidenceCropChecksumsSha256": ["f" * 64],
                "reason": "visual_label_or_slot_conflict",
                "sequenceNumber": 901,
            },
        ),
    )

    report = build_evaluation_document(cohort, _evaluated_cells(cohort))

    assert report["decision"]["value"] == "no-retrain"
    assert report["residuals"] == [
        {
            "classification": "OPEN",
            "evidenceCropCount": 1,
            "kind": "audited_label_conflict",
            "sequenceNumbers": [901],
            "status": "excluded_from_model_evaluation",
        }
    ]


def test_preprocessing_failure_is_p1_and_blocks_retrain() -> None:
    cohort = _cohort()
    first = cohort["boards"][0]
    identity = (first["boardId"], 0)

    report = build_evaluation_document(
        cohort,
        _evaluated_cells(cohort, parity_failure=identity),
    )

    assert report["preprocessingParity"]["status"] == "failed"
    assert report["residuals"][0]["classification"] == "P1"
    assert report["decision"] == {
        "reasons": ["PREPROCESSING_PARITY_MUST_BE_FIXED_FIRST"],
        "value": "no-retrain",
    }


def test_clean_evaluation_issues_no_retrain_decision() -> None:
    cohort = _cohort()

    report = build_evaluation_document(cohort, _evaluated_cells(cohort))

    assert report["decision"]["value"] == "no-retrain"
    assert report["metrics"]["accuracy"] == 1.0
    assert report["preprocessingParity"]["failureCount"] == 0
