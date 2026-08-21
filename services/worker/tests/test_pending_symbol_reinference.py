from game_predictor_worker.images.pending_symbol_reinference import _checkpoint_payload


def test_pending_symbol_checkpoint_uses_the_runtime_schema() -> None:
    payload = _checkpoint_payload(processed=7, skipped=2)

    assert payload == {
        "schema_version": 1,
        "kind": "pending-symbol-reinference-v1",
        "processed": 7,
        "skippedConcurrentResolution": 2,
    }
