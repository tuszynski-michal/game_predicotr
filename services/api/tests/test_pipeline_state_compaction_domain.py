from datetime import UTC, datetime

from game_predictor_api.domain.pipeline_state_compaction import (
    manifest_checksum,
    stage_digest,
    terminal_manifest_payload,
)


def test_terminal_manifest_is_deterministic_and_marks_disposable_stages() -> None:
    first = stage_digest(
        stage="symbol_inference",
        adapter_version="symbols-v1",
        payload={"symbols": [2, 1]},
    )
    second = stage_digest(
        stage="board_detection",
        adapter_version="boards-v1",
        payload={"boards": []},
    )
    values = dict(
        file_execution_key="a" * 64,
        source_checksum_sha256="b" * 64,
        pipeline_fingerprint="c" * 64,
        execution_status="waiting_for_review",
        execution_updated_at=datetime(2026, 8, 28, tzinfo=UTC),
        source_image_ids=("source-b", "source-a"),
        recognized_board_ids=("board-b", "board-a"),
    )

    payload = terminal_manifest_payload(stages=(first, second), **values)
    reordered = terminal_manifest_payload(stages=(second, first), **values)

    assert payload == reordered
    assert manifest_checksum(payload) == manifest_checksum(reordered)
    stages = {item["stage"]: item for item in payload["stages"]}
    assert stages["symbol_inference"]["disposable"] is True
    assert stages["board_detection"]["disposable"] is False
