"""AI-origin consensus, immutable composition and protected human references."""

import hashlib
import io
from types import SimpleNamespace

import numpy as np
import pytest
from game_predictor_worker.vision_lab import symbol_ai_experiment as module
from game_predictor_worker.vision_lab.annotations import digest, read_checked, write_atomic
from game_predictor_worker.vision_lab.geometry import crop_cell
from game_predictor_worker.vision_lab.snapshot import canonical, sha
from game_predictor_worker.vision_lab.symbol_batch_labels import BatchReviewStore
from game_predictor_worker.vision_lab.symbol_crops import render_spec
from game_predictor_worker.vision_lab.symbol_feedback import SymbolFeedbackAdapter, training_adapter
from game_predictor_worker.vision_lab.symbol_training_manifest import SymbolTrainingAdapter
from PIL import Image


@pytest.fixture
def cohort(tmp_path, monkeypatch):
    folder = tmp_path / "photos"
    folder.mkdir()
    rows = []
    rng = np.random.default_rng(1234)
    for index in range(2):
        path = folder / f"seq_{index + 1}-{index + 1}.png"
        Image.fromarray(rng.integers(0, 255, (150, 150, 3), dtype=np.uint8)).save(path)
        rows.append(
            {
                "path": str(path),
                "filename": path.name,
                "sha256": sha(path),
                "start": index + 1,
                "end": index + 1,
            }
        )
    policy = tmp_path / "policy"
    policy.mkdir()
    base = policy / "base.json"
    base.write_text("qualified human inputs")
    bundle = tmp_path / "base-bundle"
    (bundle / "crops").mkdir(parents=True)
    write_atomic(base, {"bundle": str(bundle)})
    dictionary = {
        "game_id": "mumie",
        "version": 1,
        "digest": "a" * 64,
        "status": "approved",
        "active": True,
        "entries": [
            {"id": "a", "code": "A", "display_name": "A"},
            {"id": "b", "code": "B", "display_name": "B"},
        ],
    }
    samples = []
    for sid, _part, symbol in [
        ("train", "development", "a"),
        ("val", "validation", "b"),
        ("diagnostic", "diagnostic_test", "a"),
    ]:
        pixels = rng.integers(0, 255, (96, 96, 3), dtype=np.uint8)
        stream = io.BytesIO()
        Image.fromarray(pixels).save(stream, format="PNG")
        data = stream.getvalue()
        checksum = hashlib.sha256(data).hexdigest()
        (bundle / "crops" / (checksum + ".png")).write_bytes(data)
        samples.append(
            {
                "decision": {
                    "decision_id": sid,
                    "symbol_id": symbol,
                    "binding": {
                        "source_id": sid,
                        "byte_sha256": checksum,
                        "pixel_sha256": hashlib.sha256(pixels.tobytes()).hexdigest(),
                    },
                }
            }
        )
    inputs = SimpleNamespace(
        manifest_id="base",
        bundle=bundle,
        preparation={"dictionary": dictionary, "samples": samples},
        payload={
            "assignments": {
                "train": "development",
                "val": "validation",
                "diagnostic": "diagnostic_test",
            },
            "feedback_sample_ids": ["train"],
            "counts": {"parts": {"development": 1, "validation": 1, "diagnostic_test": 1}},
            "catalog": str(policy),
            "graph": {s: [s] for s in ["train", "val", "diagnostic"]},
            "protected_source_ids": [],
        },
    )
    batch = tmp_path / "batch"
    batch.mkdir()
    payload = {
        "training_manifest": str(base),
        "generation": 3,
        "folder": str(folder),
        "rows": rows,
        "excluded_source_ids": sorted(["train", "val", "diagnostic"]),
        "excluded_sha256": sorted(digest(s) for s in ["train", "val", "diagnostic"]),
        "training_photo_pixel_groups": ["f" * 64],
        "live_bindings": {str(base): sha(base)},
    }
    write_atomic(batch / "manifest.json", payload)
    ref_payload = {
        "format": "lab-symbol-batch-review-v1",
        "batch_id": digest(payload),
        "dictionary": dictionary,
        "cases": [],
        "live_bindings": {str(base): sha(base)},
        "guard_roots": [],
        "render_spec": render_spec(),
        "forbidden_photo_pixels": ["f" * 64],
        "trainable": False,
    }
    pngs = {}
    for index in range(24):
        photo = 0 if index < 21 else 1
        x = float(2 + index)
        quad = [[x, 2.0], [x + 90, 2.0], [x + 90, 92.0], [x, 92.0]]
        with Image.open(rows[photo]["path"]) as image:
            crop = crop_cell(np.asarray(image), np.asarray(quad, dtype=np.float32))
        stream = io.BytesIO()
        Image.fromarray(crop).save(stream, format="PNG", compress_level=6)
        data = stream.getvalue()
        checksum = hashlib.sha256(data).hexdigest()
        case = {
            "case_id": digest([index]),
            "source": rows[photo],
            "quad": quad,
            "pixel_sha256": hashlib.sha256(crop.tobytes()).hexdigest(),
            "byte_sha256": checksum,
            "board": index // 15 + 1,
            "field": index % 15 + 1,
            "category": "blind",
            "photo_url": "http://localhost/review",
        }
        ref_payload["cases"].append(case)
        pngs[checksum] = data
    reference = tmp_path / "references" / digest(ref_payload)
    (reference / "crops").mkdir(parents=True)
    write_atomic(reference / "reference.json", ref_payload)
    for checksum, data in pngs.items():
        (reference / "crops" / (checksum + ".png")).write_bytes(data)
    reviews = []
    (tmp_path / "reviews").mkdir()
    for name in ("a", "b"):
        path = tmp_path / "reviews" / (name + ".json")
        write_atomic(
            path,
            {
                "format": module.REVIEW_FORMAT,
                "origin": "ai_visual_assessment",
                "reviewer": name,
                "model": "gpt-6.1-sol",
                "reference_id": reference.name,
                "human_approved": False,
                "items": [
                    {
                        "index": i + 1,
                        "case_id": c["case_id"],
                        "byte_sha256": c["byte_sha256"],
                        "pixel_sha256": c["pixel_sha256"],
                        "class": "A",
                        "status": "readable",
                        "confidence": "high",
                        "gold_frame": "absent",
                        "reason": "visible A",
                    }
                    for i, c in enumerate(ref_payload["cases"])
                ],
            },
        )
        reviews.append(path)
    selection = tmp_path / "selection" / "selection.json"
    selection.parent.mkdir()
    write_atomic(
        selection,
        {
            "format": "mumie-ai-pretraining-selection-v1",
            "base": str(base),
            "batch": str(batch),
            "reference": str(reference),
            "human_labels_written": 0,
            "accuracy": None,
            "recording_reference": "operator confirms different film",
            "withheld_photo_indices": [0],
            "training_photo_indices": [1],
        },
    )
    monkeypatch.setattr(
        module,
        "batch_inputs",
        lambda *_: SimpleNamespace(
            inputs=inputs,
            live={str(base): sha(base)},
            protected=[],
            photo_pixels=["f" * 64],
            external_sources={},
        ),
    )
    monkeypatch.setattr(
        module,
        "Catalog",
        lambda *_: SimpleNamespace(
            sources={s: SimpleNamespace(sha256=digest(s)) for s in ["train", "val", "diagnostic"]}
        ),
    )
    monkeypatch.setattr(module, "validate_batch", lambda *_: payload)
    return SimpleNamespace(
        selection=selection,
        reviews=reviews,
        ref=ref_payload,
        reference=reference,
        inputs=inputs,
        output=tmp_path / "experiment",
        batch=payload,
        base=base,
    )


def test_immutable_retry_preserves_human_inputs_and_separate_ai_origin(cohort):
    c = cohort
    before = canonical(c.inputs.preparation)
    manifest = module.freeze(c.selection, c.reviews, c.output)
    assert module.freeze(c.selection, c.reviews, c.output) == manifest
    reopened = training_adapter(manifest).validate()
    assert reopened.payload["counts"]["ai_development"] == 3
    assert reopened.payload["counts"]["ai_audit"] == 21
    assert reopened.preparation["samples"][:3] == c.inputs.preparation["samples"]
    assert canonical(c.inputs.preparation) == before
    assert all(
        s["decision"]["origin"] == "ai_visual_assessment" and not s["decision"]["human_approved"]
        for s in reopened.preparation["samples"][3:]
    )
    for adapter, error in [
        (SymbolTrainingAdapter, "SYMBOL_TRAINING_MANIFEST_INVALID"),
        (SymbolFeedbackAdapter, "SYMBOL_FEEDBACK_MANIFEST_INVALID"),
    ]:
        with pytest.raises(ValueError, match=error):
            adapter(manifest).validate()


@pytest.mark.parametrize(
    "change",
    [
        {"class": "unknown"},
        {"case_id": "unknown"},
        {"byte_sha256": "a" * 64},
        {"pixel_sha256": "b" * 64},
        {"status": "unreadable"},
        {"index": 2},
    ],
)
def test_review_target_binding_rejects_drift(cohort, change):
    data = read_checked(cohort.reviews[0])
    data["items"][0].update(change)
    write_atomic(cohort.reviews[0], data)
    with pytest.raises(ValueError, match="REVIEW_BINDING_INVALID"):
        module.compose(cohort.selection, cohort.reviews)


def test_disagreement_uncertainty_and_same_reviewer_cannot_be_training_targets(cohort):
    data = read_checked(cohort.reviews[1])
    data["items"][21]["class"] = "B"
    data["items"][22]["confidence"] = "medium"
    write_atomic(cohort.reviews[1], data)
    result = module.consensus(cohort.ref, cohort.reviews)
    assert sum(r["accepted"] for r in result) == 22
    data["reviewer"] = "a"
    write_atomic(cohort.reviews[1], data)
    with pytest.raises(ValueError, match="TWO_REVIEWERS_REQUIRED"):
        module.consensus(cohort.ref, cohort.reviews)


def test_source_crop_and_partition_drift_block(cohort):
    data = read_checked(cohort.selection)
    data["training_photo_indices"] = [0, 1]
    write_atomic(cohort.selection, data)
    with pytest.raises(ValueError, match="WITHHELD_SELECTION_INVALID"):
        module.compose(cohort.selection, cohort.reviews)
    data["training_photo_indices"] = [1]
    write_atomic(cohort.selection, data)
    case = cohort.ref["cases"][0]
    path = cohort.reference / "crops" / (case["byte_sha256"] + ".png")
    path.write_bytes(b"drift")
    with pytest.raises(ValueError, match="CROP_INTEGRITY_ERROR"):
        module.compose(cohort.selection, cohort.reviews)


def test_complete_recording_alias_blocks_before_crop_read(cohort, monkeypatch):
    row = {"path": cohort.batch["rows"][1]["path"], "sha256": cohort.batch["rows"][1]["sha256"]}
    monkeypatch.setattr(module, "folder_rows", lambda *_: [row, row])
    monkeypatch.setattr(
        BatchReviewStore, "png", lambda *_a, **_k: pytest.fail("pixels before aliases")
    )
    with pytest.raises(ValueError, match="RECORDING_ALIAS_CONFLICT"):
        module.compose(cohort.selection, cohort.reviews)


def test_reopened_manifest_rejects_resigned_changed_review(cohort):
    manifest = module.freeze(cohort.selection, cohort.reviews, cohort.output)
    data = read_checked(cohort.reviews[0])
    data["items"][21]["class"] = "B"
    write_atomic(cohort.reviews[0], data)
    with pytest.raises(ValueError, match="INPUT_DRIFT"):
        module.SymbolAiExperimentAdapter(manifest).validate()


def test_publication_cannot_write_inside_source_folder(cohort):
    from pathlib import Path

    folder = Path(cohort.batch["folder"])
    before = {p.name for p in folder.iterdir()}
    with pytest.raises(ValueError, match="DIRECTORY_OVERLAP"):
        module.freeze(cohort.selection, cohort.reviews, folder / "output")
    assert {p.name for p in folder.iterdir()} == before


def test_human_priority_unreadable_and_current_history(cohort):
    from game_predictor_worker.vision_lab import symbol_feedback
    from test_vision_lab_symbol_batch_labels import request

    c = cohort
    labels = c.selection.parent.parent / "human-labels"
    store = BatchReviewStore(c.reference, labels)
    approved = c.ref["cases"][21]
    unreadable = c.ref["cases"][22]
    store.mutate(request(store, case_id=approved["case_id"], symbol_id="b"))
    store.mutate(
        request(
            store,
            case_id=unreadable["case_id"],
            action="unreadable",
            symbol_id=None,
            request_id="human-unreadable",
        )
    )
    pack = symbol_feedback.prepare(store, c.selection.parent.parent / "human-packs")
    selected = read_checked(c.selection)
    selected["human_pack"] = str(pack)
    write_atomic(c.selection, selected)
    before = (store.root / "state.json").read_bytes()
    manifest = module.freeze(c.selection, c.reviews, c.output)
    inputs = module.SymbolAiExperimentAdapter(manifest).validate()
    assert (store.root / "state.json").read_bytes() == before
    assert inputs.payload["counts"]["new_human_development"] == 1
    assert inputs.payload["counts"]["ai_development"] == 1
    human = [
        s
        for s in inputs.preparation["samples"]
        if s["decision"].get("origin") == "batch_crop_review"
    ]
    assert len(human) == 1 and human[0]["decision"]["symbol_id"] == "b"
    assert human[0]["decision"]["decision_id"] in inputs.payload["feedback_sample_ids"]
    assert not any(
        s["decision"]["binding"]["pixel_sha256"] == unreadable["pixel_sha256"]
        for s in inputs.preparation["samples"]
    )
    store.mutate(
        request(store, case_id=approved["case_id"], symbol_id="a", request_id="changed-human")
    )
    with pytest.raises(ValueError, match="INPUT_DRIFT"):
        module.SymbolAiExperimentAdapter(manifest).validate()


@pytest.mark.parametrize(
    "field", ["excluded_source_ids", "excluded_sha256", "training_photo_pixel_groups"]
)
def test_resigned_batch_cannot_weaken_authoritative_exclusions(cohort, monkeypatch, field):
    cohort.batch[field] = []
    monkeypatch.setattr(
        BatchReviewStore,
        "png",
        lambda *_a, **_k: pytest.fail("pixels before authoritative exclusions"),
    )
    with pytest.raises(ValueError, match="EXCLUSION_BINDING_INVALID"):
        module.compose(cohort.selection, cohort.reviews)
