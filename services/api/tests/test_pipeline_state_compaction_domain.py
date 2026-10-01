from datetime import UTC, datetime

from game_predictor_api.domain.pipeline_state_compaction import (
    GameExecutionReferences,
    manifest_checksum,
    merge_game_execution_references,
    stage_digest,
    terminal_manifest_payload,
)


def _game(
    *,
    owned: tuple[str, ...],
    blocked: tuple[str, ...] = (),
    active: bool = True,
    sources: dict[str, tuple[str, ...]] | None = None,
    boards: dict[str, tuple[str, ...]] | None = None,
) -> GameExecutionReferences:
    return GameExecutionReferences(
        storage_active=active,
        owned_keys=frozenset(owned),
        blocked_keys=frozenset(blocked),
        source_image_ids=sources or {},
        recognized_board_ids=boards or {},
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


def test_merge_compacts_only_keys_owned_by_a_game_and_blocked_by_none() -> None:
    merged = merge_game_execution_references(
        (
            _game(owned=("plain", "shared", "guarded"), blocked=("guarded",)),
            _game(owned=("shared",), blocked=("shared",)),
        )
    )

    # "shared" is blocked by the second game only; "orphan" has no game at all.
    assert merged.compactable_keys == frozenset({"plain"})
    assert "orphan" not in merged.compactable_keys


def test_merge_fails_closed_for_non_active_game_stores() -> None:
    merged = merge_game_execution_references(
        (
            _game(owned=("shared", "plain")),
            _game(owned=("shared",), active=False),
        )
    )

    assert merged.compactable_keys == frozenset({"plain"})


def test_merge_unions_final_ids_across_games_in_stable_order() -> None:
    merged = merge_game_execution_references(
        (
            _game(owned=("k",), sources={"k": ("s-b",)}, boards={"k": ("b-2",)}),
            _game(owned=("k",), sources={"k": ("s-a",)}, boards={"k": ("b-1",)}),
        )
    )

    assert merged.source_image_ids == {"k": ("s-a", "s-b")}
    assert merged.recognized_board_ids == {"k": ("b-1", "b-2")}


def test_merge_without_games_compacts_nothing() -> None:
    assert merge_game_execution_references(()).compactable_keys == frozenset()
