"""Exact reviewed raster qualification, immutable retry and full recording gates."""

import hashlib
import io
import subprocess
import sys
from types import SimpleNamespace

import pytest
from game_predictor_worker.vision_lab import symbol_feedback as module
from game_predictor_worker.vision_lab.annotations import digest, read_checked, write_atomic
from game_predictor_worker.vision_lab.snapshot import sha
from game_predictor_worker.vision_lab.symbol_training_manifest import SymbolTrainingAdapter
from PIL import Image
from test_vision_lab_symbol_batch_labels import pack as review_pack
from test_vision_lab_symbol_batch_labels import request

LEGACY_VALIDATE = SymbolTrainingAdapter.validate


@pytest.fixture
def pack(tmp_path, monkeypatch):
    return review_pack.__wrapped__(tmp_path, monkeypatch)


@pytest.fixture
def cohort(pack, tmp_path, monkeypatch):
    store, source, _policy, _payload, _evidence = pack
    store.mutate(request(store))
    feedback = module.prepare(store, tmp_path / "feedback")
    dictionary = module.verify_pack(feedback)["dictionary"]
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "manifest.json").write_text("catalog")
    base = tmp_path / "base" / "manifests" / "original.json"
    base.parent.mkdir(parents=True)
    base.write_text("qualified base")
    bundle = tmp_path / "base" / "bundle"
    (bundle / "crops").mkdir(parents=True)
    samples = []
    for index, (sid, symbol) in enumerate(
        [("train", "a"), ("train", "b"), ("val", "a"), ("val", "b"), ("diag", "a")]
    ):
        image = Image.new("RGB", (96, 96), (index * 21, 50, 100))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        byte_sha = hashlib.sha256(stream.getvalue()).hexdigest()
        (bundle / "crops" / (byte_sha + ".png")).write_bytes(stream.getvalue())
        samples.append(
            {
                "decision": {
                    "symbol_id": symbol,
                    "decision_id": digest([sid, symbol]),
                    "binding": {
                        "source_id": sid,
                        "byte_sha256": byte_sha,
                        "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                    },
                }
            }
        )
    sources = {
        sid: SimpleNamespace(sha256=digest(sid), role="data", game_id="mumie")
        for sid in ["train", "val", "diag", "protected"]
    }
    inputs = SimpleNamespace(
        manifest_id="base",
        bundle=bundle,
        preparation={"dictionary": dictionary, "samples": samples},
        payload={
            "graph": {sid: [sid] for sid in sources},
            "component_evidence": [
                {"source": {"id": sid}, "family": {"family_id": sid + "-family"}}
                for sid in ["train", "val", "diag"]
            ],
            "assignments": {"train": "development", "val": "validation", "diag": "development"},
            "live_bindings": {str(catalog / "manifest.json"): sha(catalog / "manifest.json")},
            "protected_source_ids": ["protected"],
            "game_id": "mumie",
            "photo_pixel_groups": {},
        },
    )

    def validate(adapter, request=None):
        if adapter.manifest == base:
            return inputs
        return LEGACY_VALIDATE(adapter, request)

    monkeypatch.setattr(SymbolTrainingAdapter, "validate", validate)
    monkeypatch.setattr(module, "Catalog", lambda _path: SimpleNamespace(sources=sources))
    qualification = module.FeedbackQualification(
        accepted=True,
        reference="explicit operator continuation",
        recording_reference=str(source.parent),
        independent_from_validation=True,
        independent_from_diagnostic=True,
        diagnostic_family_id="diag-family",
    )
    return SimpleNamespace(
        store=store,
        source=source,
        pack=feedback,
        base=base,
        inputs=inputs,
        catalog=catalog,
        sources=sources,
        qualification=qualification,
        output=tmp_path / "qualified",
    )


def freeze(c):
    return module.freeze(c.base, c.pack, c.catalog, c.qualification, c.output)


def test_create_only_retry_and_dispatch_preserve_raw_labels(cohort):
    c = cohort
    original = (c.store.root / "state.json").read_bytes()
    reference = (c.store.reference / "reference.json").read_bytes()
    path = freeze(c)
    assert freeze(c) == path
    first = path.read_bytes()
    reopened = module.training_adapter(path).validate()
    assert reopened.payload["counts"]["parts"] == {
        "development": 3,
        "validation": 2,
        "diagnostic_test": 1,
    }
    assert reopened.payload["assignments"]["diag"] == "diagnostic_test"
    feedback = [s for s in reopened.preparation["samples"] if s.get("feedback")]
    assert len(feedback) == 1
    assert feedback[0]["decision"]["trainable"] is False
    assert feedback[0]["decision"]["binding"]["geometry_scope"] == "exact_reviewed_crop"
    assert path.read_bytes() == first
    assert (c.store.root / "state.json").read_bytes() == original
    assert (c.store.reference / "reference.json").read_bytes() == reference
    with pytest.raises(ValueError, match="SYMBOL_TRAINING_MANIFEST_INVALID"):
        SymbolTrainingAdapter(path).validate()


def test_pack_latest_replacement_and_nonclass_exclusion(pack, tmp_path):
    store, source, *_ = pack
    store.mutate(request(store))
    store.mutate(request(store, request_id="replace", symbol_id="b"))
    path = module.prepare(store, tmp_path / "feedback")
    payload = module.verify_pack(path)
    assert len(payload["decisions"]) == 1 and payload["decisions"][0]["symbol_id"] == "b"
    assert len(read_checked(path / "decisions.json")["decisions"]) == 2
    assert module.prepare(store, tmp_path / "feedback") == path
    fresh = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; "
            "from game_predictor_worker.vision_lab.symbol_feedback import verify_pack; "
            "print(len(verify_pack(Path(sys.argv[1]))['decisions']))",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert fresh.stdout.strip() == "1"
    with pytest.raises(ValueError, match="DIRECTORY_OVERLAP"):
        module.prepare(store, source.parent / "bad-output")
    store.mutate(request(store, request_id="withdraw", action="unreadable", symbol_id=None))
    with pytest.raises(ValueError, match="SYMBOL_FEEDBACK_EMPTY"):
        module.prepare(store, tmp_path / "next-feedback")


@pytest.mark.parametrize("change", ["receipt", "revision", "origin", "trainable", "class"])
def test_history_cannot_be_forged(pack, change):
    store, *_ = pack
    store.mutate(request(store))
    state = read_checked(store.root / "state.json")
    if change == "receipt":
        state["receipts"].clear()
    elif change == "revision":
        state["revision"] += 1
    else:
        state["decisions"][0][{"class": "symbol_id"}.get(change, change)] = "forged"
    with pytest.raises(ValueError):
        module.latest_decisions(state, store.reference_payload())


@pytest.mark.parametrize("alias", ["val", "diag", "protected", "comparison", "other-game"])
def test_whole_recording_alias_gate_precedes_feedback_pixels(cohort, monkeypatch, alias):
    c = cohort
    # An unreviewed image still belongs to the full capture component.
    hidden = c.source.parent / "seq_2-2.png"
    Image.new("RGB", (96, 96), "red").save(hidden)
    c.sources[alias] = SimpleNamespace(
        sha256=sha(hidden),
        role="comparison" if alias == "comparison" else "data",
        game_id="other" if alias == "other-game" else "mumie",
    )

    def decode(*_args):
        raise AssertionError("metadata-rejected feedback pixels were decoded")

    monkeypatch.setattr(module, "read_crop", decode)
    with pytest.raises(ValueError, match="PARTITIONS|HOLDOUT|ROLE_INVALID"):
        freeze(c)
    assert not c.output.exists()


def test_full_diagnostic_component_and_qualification_are_required(cohort):
    c = cohort
    c.inputs.payload["graph"]["diag"].append("train")
    with pytest.raises(ValueError, match="CROSSES_PARTITIONS"):
        freeze(c)
    with pytest.raises(ValueError):
        module.FeedbackQualification.model_validate(
            {
                **c.qualification.model_dump(),
                "independent_from_validation": False,
            }
        )


def test_pixel_photo_duplicates_and_class_conflicts(cohort):
    c = cohort
    image = module.load_photo(module.verify_pack(c.pack)["cases"][0]["source"], [])
    pixel = digest([image.size, hashlib.sha256(image.tobytes()).hexdigest()])
    c.inputs.payload["photo_pixel_groups"][pixel] = ["val"]
    with pytest.raises(ValueError, match="PHOTO_CONFLICT"):
        freeze(c)
    samples = c.inputs.preparation["samples"]
    samples[2]["decision"]["binding"]["pixel_sha256"] = samples[0]["decision"]["binding"][
        "pixel_sha256"
    ]
    with pytest.raises(ValueError, match="PIXEL_CONFLICT"):
        module.counts(samples, c.inputs.payload["assignments"], c.inputs.preparation["dictionary"])


@pytest.mark.parametrize("change", ["source", "labels", "png", "inventory", "counts"])
def test_input_or_inventory_drift_cannot_train(cohort, change):
    c = cohort
    path = freeze(c)
    payload = read_checked(path)
    if change == "source":
        c.source.write_bytes(b"changed")
    elif change == "labels":
        c.store.mutate(request(c.store, request_id="new-label", symbol_id="b"))
    elif change == "png":
        next((c.pack / "crops").glob("*.png")).write_bytes(b"changed")
    elif change == "inventory":
        (module.SymbolFeedbackAdapter(path).validate().bundle / "extra").write_text("extra")
    elif change == "counts":
        payload["counts"]["parts"]["development"] += 1
        path = path.parent / (digest(payload) + ".json")
        write_atomic(path, payload)
    with pytest.raises(ValueError, match="DRIFT|INTEGRITY|INVENTORY|OUTSIDE_RECORDING"):
        module.SymbolFeedbackAdapter(path).validate()


def test_incomplete_publication_can_be_retried(cohort, monkeypatch):
    c = cohort
    publish = module.publish_file

    def lost_reply(path, data):
        publish(path, data)
        if path.parent.name == "manifests":
            raise OSError("lost publication reply")

    monkeypatch.setattr(module, "publish_file", lost_reply)
    with pytest.raises(OSError, match="lost publication reply"):
        freeze(c)
    monkeypatch.setattr(module, "publish_file", publish)
    path = freeze(c)
    assert (
        module.SymbolFeedbackAdapter(path).validate().payload["counts"]["parts"]["development"] == 3
    )
