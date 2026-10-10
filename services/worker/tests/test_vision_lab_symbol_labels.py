"""Symbol tools never infer operator approval or training eligibility."""

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from game_predictor_worker.vision_lab.annotation_contracts import PhotoReviewRequest
from game_predictor_worker.vision_lab.annotations import exclusive, interpolate
from game_predictor_worker.vision_lab.photo_review import board_revisions
from game_predictor_worker.vision_lab.symbol_contracts import (
    DictionaryApprove,
    DictionaryDraft,
    DictionaryEntry,
    LabCropRequest,
    LabelDecide,
)
from game_predictor_worker.vision_lab.symbol_store import SymbolLabelStore
from test_vision_lab_annotations import request_for, setup_store


def symbols(tmp_path: Path, columns: int = 5):
    geometry = setup_store(tmp_path)
    source = next(s for s in geometry.catalog.sources.values() if s.game_name == "ordinary")
    request = request_for(geometry, source.id, columns=columns, action="approve_full")
    request.reviewed_all_nodes = True
    request.annotation.nodes = interpolate(request.annotation.corners, request.annotation.topology)
    for node in request.annotation.nodes:
        node.provenance = "human"
    state = geometry.mutate(request)
    geometry.mutate(
        PhotoReviewRequest(
            request_id="photo-accept",
            expected_revision=state.revision,
            actor="operator",
            action="accept",
            source_id=source.id,
            source_sha256=source.sha256,
            expected_board_revisions=board_revisions(state, source.id),
        )
    )
    return SymbolLabelStore(tmp_path / "symbols", geometry), source


def test_symbol_reads_wait_for_short_geometry_lock_contention(tmp_path):
    store, source = symbols(tmp_path)
    acquired = Event()

    def hold_geometry_lock():
        with exclusive(store.annotations.root):
            acquired.set()
            time.sleep(0.15)

    with ThreadPoolExecutor(max_workers=2) as pool:
        holder = pool.submit(hold_geometry_lock)
        assert acquired.wait(2)
        page = store.list_dictionaries(source.game_id)
        holder.result(timeout=2)
    assert page.total == 0


def dictionary(store, source):
    draft = DictionaryDraft(
        op="dictionary_draft",
        request_id="draft",
        expected_revision=0,
        game_id=source.game_id,
        entries=[DictionaryEntry(id="a", code="A", display_name="Symbol A")],
    )
    store.mutate(draft)
    version = store.dictionary(source.game_id, 1)
    store.mutate(
        DictionaryApprove(
            op="dictionary_approve",
            request_id="approve",
            expected_revision=1,
            game_id=source.game_id,
            version=1,
            digest=version.digest,
        )
    )
    return store.dictionary(source.game_id, 1)


def label(store, source):
    version = dictionary(store, source)
    preview = store.preview(
        LabCropRequest(
            kind="lab_cell",
            source_id=source.id,
            board_index=0,
            cell_index=0,
            expected_geometry_revision=1,
        )
    )
    return LabelDecide(
        op="label_decide",
        request_id="label",
        expected_revision=2,
        binding=preview.binding,
        dictionary_version=1,
        dictionary_digest=version.digest,
        action="approve",
        symbol_id="a",
    )


def test_bootstrap_dictionary_label_and_retry(tmp_path):
    store, source = symbols(tmp_path)
    assert store.list_labels().total == 0
    assert not store.root.exists()
    before = (store.annotations.root / "state.json").read_bytes()
    request = label(store, source)
    result = store.mutate(request)
    assert result.label_valid and not result.trainable
    assert "SYMBOL_PROVENANCE_UNRESOLVED" in result.training_blockers
    data = (store.root / "state.json").read_bytes()
    assert store.mutate(request).replayed
    assert (store.root / "state.json").read_bytes() == data
    assert (store.annotations.root / "state.json").read_bytes() == before
    assert SymbolLabelStore(store.root, store.annotations).list_labels().items[0].label_valid


def test_dictionary_version_drift_and_history_ids(tmp_path):
    store, source = symbols(tmp_path)
    store.mutate(label(store, source))
    draft = DictionaryDraft(
        op="dictionary_draft",
        request_id="draft2",
        expected_revision=3,
        game_id=source.game_id,
        base_version=1,
        entries=[DictionaryEntry(id="a", code="B", display_name="Changed")],
    )
    with pytest.raises(ValueError, match="CLASS_CONFLICT"):
        store.mutate(draft)
    draft.entries[0].code = "A"
    store.mutate(draft)
    assert store.list_labels().items[0].label_valid
    version = store.dictionary(source.game_id, 2)
    store.mutate(
        DictionaryApprove(
            op="dictionary_approve",
            request_id="approve2",
            expected_revision=4,
            game_id=source.game_id,
            version=2,
            digest=version.digest,
        )
    )
    assert not store.list_labels().items[0].label_valid
    with pytest.raises(ValueError, match="VERSION_CONFLICT"):
        store.mutate(
            DictionaryApprove(
                op="dictionary_approve",
                request_id="old",
                expected_revision=5,
                game_id=source.game_id,
                version=1,
                digest=store.dictionary(source.game_id, 1).digest,
            )
        )


def test_preview_role_guard_before_decode(tmp_path, monkeypatch):
    store, _ = symbols(tmp_path)
    source = next(s for s in store.catalog.sources.values() if s.game_name == "777")
    monkeypatch.setattr(store.catalog, "image", lambda _: pytest.fail("must not decode"))
    with pytest.raises(ValueError, match="ROLE_EXCLUDED"):
        store.preview(
            LabCropRequest(
                kind="lab_cell",
                source_id=source.id,
                board_index=0,
                cell_index=0,
                expected_geometry_revision=1,
            )
        )


def test_changed_geometry_rejects_previous_crop_and_page(tmp_path):
    store, source = symbols(tmp_path)
    request = label(store, source)
    page = store.list_labels()
    geometry_request = request_for(store.annotations, source.id, action="draft")
    store.annotations.mutate(geometry_request)
    with pytest.raises(ValueError, match="PAGE_VIEW_CHANGED"):
        store.list_labels(offset=1, read_token=page.read_token)
    with pytest.raises(ValueError, match="GEOMETRY_STALE"):
        store.mutate(request)


@pytest.mark.parametrize("action", ["unknown", "unreadable", "grid_issue"])
def test_nonclasses_are_not_approval(tmp_path, action):
    store, source = symbols(tmp_path)
    request = label(store, source)
    request.action, request.symbol_id = action, None
    assert not store.mutate(request).label_valid


def test_holdout_including_unassigned_and_malformed_policy(tmp_path, monkeypatch):
    from game_predictor_worker.vision_lab.annotation_contracts import FrozenSplit, StoredFamily
    from game_predictor_worker.vision_lab.symbol_labels import guard_pixels

    store, source = symbols(tmp_path)
    state = store.annotations.read()
    unseen = next(s for s in store.catalog.sources.values() if s.game_name == "unseen")
    state.split = FrozenSplit(
        fingerprint="x",
        revision=2,
        unseen_game_id=unseen.game_id,
        seed=1,
        assignments={},
        measurement={},
        annotation_fingerprints={},
        exclusions={},
    )
    from game_predictor_worker.vision_lab.annotations import digest

    state.split.fingerprint = digest(
        [
            state.snapshot_id,
            state.split.model_dump(
                include={
                    "revision",
                    "unseen_game_id",
                    "seed",
                    "assignments",
                    "measurement",
                    "annotation_fingerprints",
                    "exclusions",
                }
            ),
        ]
    )
    monkeypatch.setattr(store.catalog, "image", lambda _: pytest.fail("holdout decode"))
    with pytest.raises(ValueError, match="HOLDOUT_NOT_RELEASED"):
        guard_pixels(state, store.catalog, unseen.id)
    for sid in (source.id, unseen.id):
        state.families[sid] = StoredFamily(
            source_ids=[source.id, unseen.id],
            family_id="connected",
            evidence="operator declaration",
            actor="operator",
            decided_at="now",
        )
    with pytest.raises(ValueError, match="HOLDOUT_NOT_RELEASED"):
        guard_pixels(state, store.catalog, source.id)
    state.split.policy_version = "lab-geometry-whole-game-pilot-v1"
    state.split.game_partitions = {source.game_id: "development"}
    with pytest.raises(ValueError, match="HOLDOUT_POLICY_UNRESOLVED"):
        guard_pixels(state, store.catalog, source.id)


def test_malformed_legacy_split_blocks_real_preview_before_decode(tmp_path, monkeypatch):
    from game_predictor_worker.vision_lab.annotation_contracts import FrozenSplit
    from game_predictor_worker.vision_lab.annotations import read_checked, write_atomic

    store, source = symbols(tmp_path)
    path = store.annotations.root / "state.json"
    payload = read_checked(path)
    unseen = next(s for s in store.catalog.sources.values() if s.game_name == "unseen")
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
    monkeypatch.setattr(store.catalog, "image", lambda _: pytest.fail("malformed split decoded"))
    with pytest.raises(ValueError, match="HOLDOUT_POLICY_UNRESOLVED"):
        store.preview(
            LabCropRequest(
                kind="lab_cell",
                source_id=source.id,
                board_index=0,
                cell_index=0,
                expected_geometry_revision=1,
            )
        )


@pytest.mark.parametrize("columns", [3, 5])
def test_topologies_and_pixel_byte_hashes(tmp_path, columns):
    import base64
    import hashlib
    import io

    from PIL import Image

    store, source = symbols(tmp_path, columns)
    request = label(store, source)
    preview = store.preview(
        LabCropRequest(
            kind="lab_cell",
            source_id=source.id,
            board_index=0,
            cell_index=columns * 3 - 1,
            expected_geometry_revision=1,
        )
    )
    data = base64.b64decode(preview.png_base64)
    assert hashlib.sha256(data).hexdigest() == preview.binding.byte_sha256
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (96, 96)
        assert hashlib.sha256(image.tobytes()).hexdigest() == preview.binding.pixel_sha256
    request.binding.byte_sha256 = "f" * 64
    with pytest.raises(ValueError, match="CROP_CHANGED"):
        store.mutate(request)
