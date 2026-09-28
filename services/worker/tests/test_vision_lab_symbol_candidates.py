"""Queue is derived from approved geometry; batch approval is atomic."""

import pytest
from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab.annotation_contracts import FrozenSplit, PhotoReviewRequest
from game_predictor_worker.vision_lab.annotations import interpolate, read_checked, write_atomic
from game_predictor_worker.vision_lab.api import create_app
from game_predictor_worker.vision_lab.photo_review import board_revisions
from game_predictor_worker.vision_lab.symbol_contracts import (
    DictionaryApprove,
    DictionaryDraft,
    LabelCellsDecide,
    LabelDecide,
    LabelWithdraw,
    LabQueueRequest,
)
from game_predictor_worker.vision_lab.symbol_store import SymbolLabelStore
from test_vision_lab_annotations import request_for
from test_vision_lab_symbol_labels import dictionary, symbols


def queue(store, source, offset=0, token=None, limit=30):
    return store.preview(
        LabQueueRequest(
            kind="lab_queue", game_id=source.game_id, offset=offset, limit=limit, read_token=token
        )
    )


def add_board(store, source, index):
    request = request_for(store.annotations, source.id, action="approve_full")
    request.annotation.board_index = index
    request.reviewed_all_nodes = True
    request.annotation.nodes = interpolate(request.annotation.corners, request.annotation.topology)
    for node in request.annotation.nodes:
        node.provenance = "human"
    state = store.annotations.mutate(request)
    store.annotations.mutate(
        PhotoReviewRequest(
            request_id=f"photo-accept-{index}",
            expected_revision=state.revision,
            actor="operator",
            action="accept",
            source_id=source.id,
            source_sha256=source.sha256,
            expected_board_revisions=board_revisions(state, source.id),
        )
    )


def test_queue_before_dictionary_page_and_single_decode(tmp_path, monkeypatch):
    store, source = symbols(tmp_path)
    calls = 0
    original = store.catalog.image

    def image(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(store.catalog, "image", image)
    first = queue(store, source, limit=15)
    assert first.total == 15
    assert all(item.status == "unassigned" for item in first.items)
    assert calls == 1
    assert not store.root.exists()
    second = queue(store, source, offset=10, token=first.read_token, limit=5)
    assert [item.binding.cell_index for item in second.items] == list(range(10, 15))
    with pytest.raises(ValueError, match="PAGE_VIEW_CHANGED"):
        queue(store, source, offset=10, token="old")


def test_batch_exact_retry_and_no_partial_last_binding(tmp_path, monkeypatch):
    store, source = symbols(tmp_path)
    version = dictionary(store, source)
    first = queue(store, source)
    bindings = [item.binding for item in first.items[:3]]
    bad = bindings[-1].model_copy(update={"pixel_sha256": "0" * 64})
    invalid = LabelCellsDecide(
        op="label_cells_decide",
        request_id="bad",
        expected_revision=2,
        dictionary_version=1,
        dictionary_digest=version.digest,
        symbol_id="a",
        bindings=[*bindings[:-1], bad],
    )
    before = (store.root / "state.json").read_bytes()
    with pytest.raises(ValueError, match="SYMBOL_CROP_CHANGED"):
        store.mutate(invalid)
    assert (store.root / "state.json").read_bytes() == before

    calls = 0
    original = store.catalog.image

    def image(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(store.catalog, "image", image)
    request = LabelCellsDecide(
        op="label_cells_decide",
        request_id="batch",
        expected_revision=2,
        dictionary_version=1,
        dictionary_digest=version.digest,
        symbol_id="a",
        bindings=bindings,
    )
    result = store.mutate(request)
    assert result.label_valid and len(set(result.decision_ids)) == 3
    assert calls == 1
    restarted = SymbolLabelStore(store.root, store.annotations)
    assert restarted.mutate(request).replayed
    after = queue(store, source)
    assert after.total == 12
    assert all(item.binding.cell_index >= 3 for item in after.items)


def test_current_unknown_excluded_and_dictionary_stale_reviewable(tmp_path):
    store, source = symbols(tmp_path)
    version = dictionary(store, source)
    first = queue(store, source)
    store.mutate(
        LabelDecide(
            op="label_decide",
            request_id="unknown",
            expected_revision=2,
            binding=first.items[0].binding,
            dictionary_version=1,
            dictionary_digest=version.digest,
            action="unknown",
            symbol_id=None,
        )
    )
    assert queue(store, source).total == 14
    # The same cell becomes a candidate again only when its old binding is stale.
    payload = store.load()
    payload["decisions"][-1]["dictionary_digest"] = "0" * 64
    write_atomic(store.root / "state.json", payload)
    stale = queue(store, source)
    assert stale.items[0].status == "requires_review"
    assert stale.items[0].reason == "SYMBOL_DICTIONARY_STALE"


def test_thirty_plus_one_token_drift_and_cross_board_ids(tmp_path, monkeypatch):
    store, source = symbols(tmp_path)
    add_board(store, source, 1)
    add_board(store, source, 2)
    first = queue(store, source)
    assert first.total == 45 and len(first.items) == 30
    assert [(x.binding.board_index, x.binding.cell_index) for x in first.items[:16]] == [
        *((0, i) for i in range(15)),
        (1, 0),
    ]
    rest = queue(store, source, 30, first.read_token)
    assert len(rest.items) == 15 and rest.items[0].binding.board_index == 2
    version = dictionary(store, source)
    with pytest.raises(ValueError, match="PAGE_VIEW_CHANGED"):
        queue(store, source, 30, first.read_token)
    fresh = queue(store, source)
    selected = [fresh.items[0].binding, fresh.items[15].binding]
    original = store.catalog.image
    calls = 0

    def image(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(store.catalog, "image", image)
    request = LabelCellsDecide(
        op="label_cells_decide",
        request_id="two-boards",
        expected_revision=2,
        dictionary_version=1,
        dictionary_digest=version.digest,
        symbol_id="a",
        bindings=selected,
    )
    result = store.mutate(request)
    assert len(set(result.decision_ids)) == 2 and calls == 1
    assert queue(store, source).total == 43


def test_policy_unresolved_before_decode(tmp_path, monkeypatch):
    store, source = symbols(tmp_path)
    unseen = next(s for s in store.catalog.sources.values() if s.game_name == "unseen")
    path = store.annotations.root / "state.json"
    payload = read_checked(path)
    payload["state"]["split"] = FrozenSplit(
        policy_version="legacy",
        fingerprint="bad",
        revision=2,
        unseen_game_id=unseen.game_id,
        seed=1,
        assignments={source.id: "invalid_partition"},
        measurement={},
        annotation_fingerprints={},
        exclusions={},
    ).model_dump()
    write_atomic(path, payload)
    monkeypatch.setattr(store.catalog, "image", lambda _: pytest.fail("policy decoded pixels"))
    with pytest.raises(ValueError, match="HOLDOUT_POLICY_UNRESOLVED"):
        queue(store, source)


def test_retry_after_withdraw_recomputes_validity_and_backup(tmp_path):
    store, source = symbols(tmp_path)
    version = dictionary(store, source)
    bindings = [item.binding for item in queue(store, source).items[:2]]
    request = LabelCellsDecide(
        op="label_cells_decide",
        request_id="batch-withdraw",
        expected_revision=2,
        dictionary_version=1,
        dictionary_digest=version.digest,
        symbol_id="a",
        bindings=bindings,
    )
    original = store.mutate(request)
    store.mutate(
        LabelWithdraw(
            op="label_withdraw",
            request_id="withdraw-one",
            expected_revision=3,
            decision_id=original.decision_ids[0],
        )
    )
    replay = SymbolLabelStore(store.root, store.annotations).mutate(request)
    assert replay.replayed and replay.decision_ids == original.decision_ids
    assert not replay.label_valid
    backup = store.backup()
    restored = store.restore(backup.backup_id, tmp_path / "restored-queue")
    assert restored.mutate(request).replayed


def test_retry_after_dictionary_change_keeps_ids_but_rechecks_validity(tmp_path):
    store, source = symbols(tmp_path)
    version = dictionary(store, source)
    binding = queue(store, source).items[0].binding
    request = LabelCellsDecide(
        op="label_cells_decide",
        request_id="before-new-dictionary",
        expected_revision=2,
        dictionary_version=1,
        dictionary_digest=version.digest,
        symbol_id="a",
        bindings=[binding],
    )
    first = store.mutate(request)
    store.mutate(
        DictionaryDraft(
            op="dictionary_draft",
            request_id="draft-second",
            expected_revision=3,
            game_id=source.game_id,
            base_version=1,
            entries=version.entries or [],
        )
    )
    second = store.dictionary(source.game_id, 2)
    store.mutate(
        DictionaryApprove(
            op="dictionary_approve",
            request_id="approve-second",
            expected_revision=4,
            game_id=source.game_id,
            version=2,
            digest=second.digest,
        )
    )
    retry = store.mutate(request)
    assert retry.replayed and retry.revision == first.revision
    assert retry.decision_ids == first.decision_ids and not retry.label_valid
    assert "SYMBOL_DICTIONARY_STALE" in retry.reasons


def test_http_queue_and_selective_mutation_contract(tmp_path):
    store, source = symbols(tmp_path)
    version = dictionary(store, source)
    client = TestClient(
        create_app(store.catalog, store.annotations.root, symbol_root=store.root),
        base_url="http://127.0.0.1:8102",
    )
    headers = {"Origin": "http://127.0.0.1:3102"}
    preview = client.post(
        "/symbol-crops",
        json={
            "kind": "lab_queue",
            "game_id": source.game_id,
            "offset": 0,
            "limit": 2,
        },
        headers=headers,
    )
    assert preview.status_code == 200
    page = preview.json()
    assert page["kind"] == "lab_queue" and page["total"] == 15
    request = LabelCellsDecide(
        op="label_cells_decide",
        request_id="http-selective",
        expected_revision=page["revision"],
        dictionary_version=1,
        dictionary_digest=version.digest,
        symbol_id="a",
        bindings=[item["binding"] for item in page["items"]],
    )
    response = client.post("/symbols", json=request.model_dump(), headers=headers)
    assert response.status_code == 200
    assert len(response.json()["decision_ids"]) == 2
    assert client.post("/symbols", json=request.model_dump(), headers=headers).json()["replayed"]
