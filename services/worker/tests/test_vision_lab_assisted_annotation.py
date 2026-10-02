"""TASK-0824: assisted complete-photo annotation through the existing annotation store."""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab import assisted_annotation as assisted
from game_predictor_worker.vision_lab.annotation_contracts import (
    AnnotationRequest,
    AssistedRequest,
    GeometryAnnotation,
    PhotoReviewRequest,
)
from game_predictor_worker.vision_lab.annotations import (
    AnnotationStore,
    read_checked,
    write_atomic,
)
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.contracts import Point, Topology
from game_predictor_worker.vision_lab.neural_grid_data import grid_from_quad, load_samples
from game_predictor_worker.vision_lab.neural_grid_inference import BoardDetection
from game_predictor_worker.vision_lab.photo_review import board_revisions
from game_predictor_worker.vision_lab.rebase_annotations import _references
from game_predictor_worker.vision_lab.snapshot import import_folder
from PIL import Image

QUADS = (
    [[20.0, 20.0], [180.0, 22.0], [182.0, 112.0], [18.0, 110.0]],
    [[220.0, 20.0], [380.0, 20.0], [380.0, 110.0], [220.0, 110.0]],
)
HOST = {"host": "127.0.0.1:8105"}
WRITE = {**HOST, "origin": "http://127.0.0.1:8105"}


class FakeEngine:
    model_version = "fake-neural-grid"

    def __init__(self, empty: set[int] | None = None) -> None:
        self.calls = 0
        self.empty = empty or set()

    def analyse(self, rgb):
        self.calls += 1
        if int(rgb[0, 0, 0]) in self.empty:
            return []
        return [
            BoardDetection(
                score=0.9,
                screen_quad=np.asarray(q, np.float32),
                nodes=grid_from_quad(np.asarray(q, np.float32)),
                reasons=[],
            )
            for q in QUADS
        ]


def lab(tmp_path: Path):
    """Six games like the lab snapshot; the training folder mirrors three of them."""

    games = {"mumie": 4, "blazing": 2, "gang": 2, "reels": 1, "treasure": 1, "777": 1}
    for g, (game, count) in enumerate(games.items()):
        directory = tmp_path / "input" / game
        directory.mkdir(parents=True)
        for i in range(count):
            Image.new("RGB", (400, 300), (10 * i + 5, 40 * g, 90)).save(directory / f"p{i}.png")
    # A duplicate of mumie/p0 in a nested folder, as in the real addition import.
    (tmp_path / "input" / "mumie" / "addition").mkdir()
    shutil.copy(tmp_path / "input/mumie/p0.png", tmp_path / "input/mumie/addition/p0.png")
    catalog = Catalog(import_folder(tmp_path / "input", tmp_path / "snapshots"))
    training = tmp_path / "training"
    for game, names in {
        "mumie": ["p1", "p0", "p2"],
        "blazing": ["p0", "p1"],
        "gang": ["p1"],
    }.items():
        (training / game).mkdir(parents=True)
        for number, name in enumerate(names):
            shutil.copy(
                tmp_path / "input" / game / f"{name}.png",
                training / game / f"seq_{number * 9 + 1}.png",
            )
    # Holdout folders are never read: this file is unknown to the catalog.
    (training / "reels").mkdir()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(training / "reels" / "x.png")
    store = AnnotationStore(tmp_path / "annotations", catalog)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "bundle.json").write_text(
        json.dumps({"files": {"screen.onnx": "a" * 64}, "weights_sha256": "b" * 64})
    )
    return catalog, store, training, bundle


def source_of(catalog: Catalog, game: str, name: str):
    return next(
        s
        for s in catalog.sources.values()
        if s.game_name == game and s.filename == f"{game}/{name}.png"
    )


def lab_full(store: AnnotationStore, source_id: str, index: int, quad) -> None:
    corners = [Point(x=x, y=y, provenance="human") for x, y in quad]
    nodes = [
        Point(x=float(x), y=float(y), provenance="human")
        for x, y in grid_from_quad(np.asarray(quad, np.float32))
    ]
    for i, c in zip((0, 5, 23, 18), corners, strict=True):
        nodes[i] = c
    state = store.read()
    store.mutate(
        AnnotationRequest(
            request_id=f"lab-write-{state.revision}",
            expected_revision=state.revision,
            actor="lab-operator",
            annotation=GeometryAnnotation(
                source_id=source_id,
                board_index=index,
                topology=Topology(),
                corners=corners,
                nodes=nodes,
            ),
            action="approve_full",
            reviewed_all_nodes=True,
        )
    )


def lab_accept_photo(store: AnnotationStore, source_id: str) -> None:
    state = store.read()
    store.mutate(
        PhotoReviewRequest(
            request_id=f"review-write-{state.revision}",
            expected_revision=state.revision,
            actor="lab-operator",
            action="accept",
            source_id=source_id,
            source_sha256=store.catalog.sources[source_id].sha256,
            expected_board_revisions=board_revisions(state, source_id),
        )
    )


def publish(tmp_path: Path, catalog, store, training, bundle, engine=None):
    root = assisted.generate_proposals(
        catalog,
        store.read(),
        training,
        bundle,
        tmp_path / "proposals",
        engine=engine or FakeEngine(),
        log=lambda _: None,
    )
    return assisted.load_proposals(root, catalog)


def decide(workspace: assisted.Workspace, **fields):
    state = workspace.state()
    body = {
        "request_id": f"op-{state.revision}-{fields['action']}",
        "expected_revision": state.revision,
        **fields,
    }
    return workspace.decide(assisted.Decision(**body))


def first_photo(workspace: assisted.Workspace, index: int = 0):
    item = workspace.proposals.items[index]
    return item, assisted.photo_view(
        workspace.state(), workspace.catalog, workspace.proposals, item["source_id"]
    )


def test_queue_order_duplicates_and_holdout_guard(tmp_path):
    catalog, store, training, bundle = lab(tmp_path)
    annotated = source_of(catalog, "mumie", "p3")
    lab_full(store, annotated.id, 4, QUADS[0])
    queue = assisted.build_queue(catalog, store.read(), assisted.training_set_files(training))
    assert [item["game"] for item in queue] == ["mumie"] * 4 + ["blazing"] * 2 + ["gang"]
    assert [item["training_set_files"] for item in queue[:3]] == [
        ["mumie/seq_1.png"],
        ["mumie/seq_10.png"],
        ["mumie/seq_19.png"],
    ]
    # The duplicated SHA resolves deterministically to one catalog source.
    duplicate = [s for s in catalog.sources.values() if s.sha256 == queue[1]["sha256"]]
    assert (
        len(duplicate) == 2 and queue[1]["source_id"] == min(duplicate, key=lambda s: s.filename).id
    )
    assert queue[3]["source_id"] == annotated.id and queue[3]["training_set_files"] == []
    assert queue[3]["existing_boards"] == 1
    assert not {"reels", "treasure", "777"} & {item["game_name"] for item in queue}
    reels = source_of(catalog, "reels", "p0")
    treasure = source_of(catalog, "treasure", "p0")
    for source, code in (
        (reels, "HOLDOUT"),
        (treasure, "HOLDOUT"),
        (source_of(catalog, "777", "p0"), "GAME_FORBIDDEN"),
    ):
        with pytest.raises(ValueError, match=code):
            store.mutate(
                AssistedRequest(
                    request_id=f"guard-{source.id[:8]}",
                    expected_revision=store.read().revision,
                    actor="operator",
                    action="dismiss_proposal",
                    source_id=source.id,
                    source_sha256=source.sha256,
                    proposal_id="x",
                )
            )
    with pytest.raises(ValueError, match="GAME_FORBIDDEN"):
        assisted.build_queue(catalog, store.read(), {"reels": []})


def test_proposals_are_an_immutable_artifact_not_labels(tmp_path):
    catalog, store, training, bundle = lab(tmp_path)
    before = (
        (store.root / "state.json").read_bytes() if (store.root / "state.json").exists() else None
    )
    engine = FakeEngine()
    proposals = publish(tmp_path, catalog, store, training, bundle, engine)
    assert engine.calls == len(proposals.items) == 6  # holdouts never decoded
    assert (
        (store.root / "state.json").read_bytes() if (store.root / "state.json").exists() else None
    ) == before
    assert store.read().annotations == {} and store.read().assisted_photos == {}
    item = proposals.items[0]
    assert item["status"] == "detected" and len(item["proposals"]) == 2
    with pytest.raises(ValueError, match="PROPOSALS_EXIST"):
        publish(tmp_path, catalog, store, training, bundle)
    payload = read_checked(proposals.root / assisted.PROPOSALS_FILE)
    payload["items"][0]["proposals"][0]["nodes"][0][0] += 1
    write_atomic(proposals.root / assisted.PROPOSALS_FILE, payload)
    with pytest.raises(ValueError, match="PROPOSALS_INTEGRITY"):
        assisted.load_proposals(proposals.root, catalog)


def test_operator_decisions_record_provenance_and_completeness(tmp_path):
    catalog, store, training, bundle = lab(tmp_path)
    proposals = publish(tmp_path, catalog, store, training, bundle)
    workspace = assisted.Workspace(catalog, store.root, proposals.root)
    item, view = first_photo(workspace)
    source = catalog.sources[item["source_id"]]
    first, second = (p["proposal_id"] for p in view["proposals"])
    state = decide(
        workspace,
        action="accept_board",
        source_id=source.id,
        board_index=0,
        origin="proposal_unchanged",
        proposal_id=first,
        activity_intervals_ms=[1200, 40000],
    )
    annotation = state.annotations[f"{source.id}:0"]
    assert annotation.full_approved and all(p.provenance == "human" for p in annotation.nodes)
    assert [[p.x, p.y] for p in annotation.nodes] == proposals.by_id[first]["nodes"]
    record = state.assisted_photos[source.id]
    assert record.boards["0"].origin == "proposal_unchanged"
    assert record.boards["0"].proposal_sha256 == proposals.by_id[first]["sha256"]
    assert record.active_ms == 1200  # idle gaps above 30 s are not work
    assert not assisted.photo_complete(state, source)
    moved = [[x + 3, y] for x, y in QUADS[1]]
    state = decide(
        workspace,
        action="accept_board",
        source_id=source.id,
        board_index=1,
        origin="proposal_corrected",
        proposal_id=second,
        corners=moved,
    )
    assert state.assisted_photos[source.id].boards["1"].origin == "proposal_corrected"
    assert state.assisted_photos[source.id].boards["1"].max_corner_shift_px == pytest.approx(
        3, abs=1e-3
    )
    state = decide(
        workspace,
        action="accept_board",
        source_id=source.id,
        board_index=4,
        origin="manual",
        corners=[[30, 150], [170, 150], [170, 260], [30, 260]],
    )
    assert state.assisted_photos[source.id].boards["4"].proposal_id == ""
    with pytest.raises(ValueError, match="ALREADY_USED"):
        decide(
            workspace,
            action="accept_board",
            source_id=source.id,
            board_index=5,
            origin="proposal_unchanged",
            proposal_id=first,
        )
    revisions = board_revisions(state, source.id)
    for count, code in ((None, "COUNT_REQUIRED"), (2, "COUNT_MISMATCH")):
        with pytest.raises(ValueError, match=code):
            decide(
                workspace,
                action="complete_photo",
                source_id=source.id,
                confirmed_board_count=count,
                expected_board_revisions=revisions,
            )
    state = decide(
        workspace,
        action="complete_photo",
        source_id=source.id,
        confirmed_board_count=3,
        expected_board_revisions=revisions,
    )
    assert assisted.photo_complete(state, source)
    assert state.photo_reviews[source.id].accepted_board_revisions == revisions
    # Revoking one acceptance reopens the photo; re-accepting needs a new completion.
    state = decide(
        workspace,
        action="revoke_board",
        source_id=source.id,
        board_index=1,
        expected_board_revision=1,
    )
    assert not assisted.photo_complete(state, source)
    assert not state.annotations[f"{source.id}:1"].full_approved
    with pytest.raises(ValueError, match="NOT_ACCEPTED"):
        decide(
            workspace,
            action="complete_photo",
            source_id=source.id,
            confirmed_board_count=3,
            expected_board_revisions=board_revisions(state, source.id),
        )
    # Removing a false board leaves an absent slot and dismisses its proposal.
    state = decide(
        workspace,
        action="remove_board",
        source_id=source.id,
        board_index=1,
        expected_board_revision=2,
    )
    assert state.annotations[f"{source.id}:1"].presence == "absent"
    assert second in state.assisted_photos[source.id].dismissed_proposal_ids
    state = decide(
        workspace,
        action="complete_photo",
        source_id=source.id,
        confirmed_board_count=2,
        expected_board_revisions=board_revisions(state, source.id),
    )
    assert assisted.photo_complete(state, source)
    history = read_checked(store.root / "state.json")["history"]
    assert len(history) == state.revision
    assert all("assisted_photo" in event for event in history)
    assert history[0]["annotation"]["board_index"] == 0
    # Lost response: the identical request is answered from its receipt.
    body = {
        "request_id": "op-retry-x1",
        "expected_revision": state.revision,
        "action": "dismiss_proposal",
        "source_id": source.id,
        "proposal_id": second,
    }
    with pytest.raises(ValueError, match="STATE_UNCHANGED"):
        workspace.decide(assisted.Decision(**body))
    body["action"] = "restore_proposal"
    once = workspace.decide(assisted.Decision(**body))
    assert workspace.decide(assisted.Decision(**body)) == once


def test_existing_lab_work_is_preserved_locked_and_counted(tmp_path):
    catalog, store, training, bundle = lab(tmp_path)
    source = source_of(catalog, "mumie", "p3")
    lab_full(store, source.id, 0, QUADS[0])
    lab_accept_photo(store, source.id)
    old = store.read()
    proposals = publish(tmp_path, catalog, store, training, bundle)
    workspace = assisted.Workspace(catalog, store.root, proposals.root)
    item = proposals.by_source[source.id]
    view = assisted.photo_view(workspace.state(), catalog, proposals, source.id)
    assert view["boards"][0]["locked"] and view["boards"][0]["status"] == "lab_accepted"
    assert view["boards"][0]["origin"] == "existing_lab"
    assert view["proposals"][0]["covered_by"] == 0 and view["proposals"][1]["covered_by"] is None
    with pytest.raises(ValueError, match="EXISTING_BOARD_LOCKED"):
        decide(
            workspace,
            action="accept_board",
            source_id=source.id,
            board_index=0,
            expected_board_revision=1,
            origin="proposal_unchanged",
            proposal_id=item["proposals"][0]["proposal_id"],
        )
    with pytest.raises(ValueError, match="EXISTING_BOARD_LOCKED"):
        decide(
            workspace,
            action="remove_board",
            source_id=source.id,
            board_index=0,
            expected_board_revision=1,
        )
    state = decide(
        workspace,
        action="complete_photo",
        source_id=source.id,
        confirmed_board_count=1,
        expected_board_revisions={"0": 1},
    )
    assert assisted.photo_complete(state, source)
    assert state.annotations[f"{source.id}:0"] == old.annotations[f"{source.id}:0"]
    assert state.photo_reviews[source.id] == old.photo_reviews[source.id]  # not re-decided
    state = decide(
        workspace,
        action="accept_board",
        source_id=source.id,
        board_index=1,
        origin="proposal_unchanged",
        proposal_id=item["proposals"][1]["proposal_id"],
    )
    assert not assisted.photo_complete(state, source)  # a new board reopens the photo
    assert state.annotations[f"{source.id}:0"] == old.annotations[f"{source.id}:0"]
    rows = assisted.export_rows(catalog, state, proposals)
    assert rows == []


def test_work_survives_restart_and_old_state_reads(tmp_path):
    catalog, store, training, bundle = lab(tmp_path)
    proposals = publish(tmp_path, catalog, store, training, bundle)
    workspace = assisted.Workspace(catalog, store.root, proposals.root)
    item, view = first_photo(workspace)
    decide(
        workspace,
        action="accept_board",
        source_id=item["source_id"],
        board_index=0,
        origin="proposal_unchanged",
        proposal_id=view["proposals"][0]["proposal_id"],
    )
    restarted = assisted.Workspace(Catalog(catalog.root), store.root, proposals.root)
    again = assisted.photo_view(
        restarted.state(), restarted.catalog, restarted.proposals, item["source_id"]
    )
    assert (
        again["boards"][0]["status"] == "accepted"
        and again["boards"][0]["origin"] == "proposal_unchanged"
    )
    assert (
        assisted.queue_view(restarted.state(), restarted.catalog, restarted.proposals)["games"][
            "mumie"
        ]["started"]
        == 1
    )
    payload = read_checked(store.root / "state.json")
    payload["state"].pop("assisted_photos")
    write_atomic(store.root / "state.json", payload)
    assert store.read().assisted_photos == {}  # stores written before TASK-0824 still read
    with pytest.raises(ValueError, match="ASSISTED_PHOTOS_UNSUPPORTED"):
        _references(read_checked(store.root / "state.json"), catalog)


def test_export_checksums_and_neural_grid_reader_compatibility(tmp_path):
    catalog, store, training, bundle = lab(tmp_path)
    proposals = publish(tmp_path, catalog, store, training, bundle)
    workspace = assisted.Workspace(catalog, store.root, proposals.root)
    item, view = first_photo(workspace)
    source_id = item["source_id"]
    for index, proposal in enumerate(reversed(view["proposals"])):
        decide(
            workspace,
            action="accept_board",
            source_id=source_id,
            board_index=index,
            origin="proposal_unchanged",
            proposal_id=proposal["proposal_id"],
        )
    state = workspace.state()
    decide(
        workspace,
        action="complete_photo",
        source_id=source_id,
        confirmed_board_count=2,
        expected_board_revisions=board_revisions(state, source_id),
    )
    state = workspace.state()
    target = assisted.write_export(catalog, state, proposals, tmp_path / "exports")
    assert assisted.write_export(catalog, state, proposals, tmp_path / "exports") == target
    rows = assisted.read_export(target)
    assert len(rows) == 1 and rows[0]["confirmedBoardCount"] == 2
    row = rows[0]
    assert (
        row["gameKey"] == "mumie"
        and row["sourceChecksumSha256"] == catalog.sources[source_id].sha256
    )
    assert [b["readingOrder"] for b in row["boards"]] == [0, 1]
    assert row["boards"][0]["quad"][0] == pytest.approx(QUADS[0][0], abs=1e-3)  # left board first
    assert {b["origin"] for b in row["boards"]} == {"proposal_unchanged"}
    manifest = json.loads((target / assisted.EXPORT_MANIFEST).read_bytes())
    assert (
        manifest["photos"] == 1
        and manifest["boards"] == 2
        and manifest["games"] == {"mumie": {"photos": 1, "boards": 2}}
    )
    snapshot = assisted.write_reader_snapshot(
        rows, catalog, tmp_path / "reader", {source_id: "training"}
    )
    samples = load_samples(snapshot, ["training"])
    assert [s.image_id for s in samples] == [source_id]
    assert np.allclose(
        samples[0].boards[0].nodes, np.asarray(row["boards"][0]["nodes"], np.float32)
    )
    assert (samples[0].width, samples[0].height) == (400, 300)
    with (target / assisted.EXPORT_ROWS).open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(ValueError, match="CHECKSUM_MISMATCH"):
        assisted.read_export(target)


def test_loopback_page_and_api(tmp_path):
    catalog, store, training, bundle = lab(tmp_path)
    proposals = publish(tmp_path, catalog, store, training, bundle, FakeEngine(empty={15}))
    client = TestClient(
        assisted.create_app(assisted.Workspace(catalog, store.root, proposals.root))
    )
    assert "Kompletne zdjęcia" in client.get("/", headers=HOST).text
    assert client.get("/", headers={"host": "example.com"}).status_code == 403
    queue = client.get("/api/queue", headers=HOST).json()
    assert queue["total"] == 6 and queue["games"]["mumie"]["total"] == 3
    assert queue["items"][0]["proposals"] == 0  # the network found no board on this photo
    photo = client.get("/api/photos/1", headers=HOST).json()
    assert (
        client.get(f"/api/images/{photo['source_id']}", headers=HOST).headers["content-type"]
        == "image/jpeg"
    )
    reels = source_of(catalog, "reels", "p0")
    assert client.get(f"/api/images/{reels.id}", headers=HOST).status_code == 404
    body = {
        "request_id": "page-accept-1",
        "expected_revision": photo["revision"],
        "action": "accept_board",
        "source_id": photo["source_id"],
        "board_index": 0,
        "origin": "proposal_unchanged",
        "proposal_id": photo["proposals"][0]["proposal_id"],
    }
    assert client.post("/api/decisions", json=body, headers=HOST).status_code == 403
    saved = client.post("/api/decisions", json=body, headers=WRITE)
    assert saved.status_code == 200 and saved.json()["boards"][0]["origin"] == "proposal_unchanged"
    stale = client.post(
        "/api/decisions", json={**body, "request_id": "page-accept-2"}, headers=WRITE
    )
    assert stale.status_code == 409 and stale.json()["detail"] == "ANNOTATION_REVISION_CONFLICT"
    reels_body = {**body, "request_id": "page-reels-1", "source_id": reels.id}
    assert (
        client.post("/api/decisions", json=reels_body, headers=WRITE).json()["detail"]
        == "ASSISTED_SOURCE_NOT_IN_QUEUE"
    )
