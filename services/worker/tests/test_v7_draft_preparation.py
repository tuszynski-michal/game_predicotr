from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_worker.semi_automatic_selection import v7_draft_preparation as module
from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    build_local_source_manifest,
)
from game_predictor_worker.semi_automatic_selection.v7_run_state import V7RunFinalization


def test_worker_prepares_after_eof_and_restart_uses_bounded_marker(tmp_path):
    from game_predictor_worker.semi_automatic_selection.job import (
        SemiAutomaticImageSelectionJobHandler,
    )

    source = tmp_path / "source"
    source.mkdir()
    (source / "1.jpg").write_bytes(b"existing source")
    manifest = build_local_source_manifest(source, selection_id=uuid4(), display_name="source")
    finalization = V7RunFinalization(())
    scan = {"phase": "finalized", "finalization": finalization.as_dict(), "sourceDiagnostics": []}
    run = SimpleNamespace(
        id=uuid4(),
        v7_configuration=SimpleNamespace(
            output_directory=str(tmp_path / "output"),
            first_sequence_number=1,
            last_sequence_number=9,
        ),
    )
    context = SimpleNamespace(heartbeat=lambda: None)
    handler = object.__new__(SemiAutomaticImageSelectionJobHandler)
    handler._prepare_draft_outputs(context, run, manifest, {"scanState": scan}, finalization)

    def forbidden(_):
        raise AssertionError("Completed export must not fetch checkpoint history")

    handler._store = SimpleNamespace(_get_run=forbidden)
    handler._prepare_draft_outputs(context, run, manifest)


@pytest.mark.parametrize("label_count", [0, 4])
def test_interrupted_preparation_resumes_without_repeating_rejected_files(
    tmp_path, monkeypatch, label_count
):
    source = tmp_path / "source"
    source.mkdir()
    for number in range(2):
        (source / f"{number}.jpg").write_bytes(f"existing-{number}".encode())
    manifest = build_local_source_manifest(source, selection_id=uuid4(), display_name="source")
    finalization = V7RunFinalization(())
    scan = {
        "phase": "finalized",
        "finalization": finalization.as_dict(),
        "sourceDiagnostics": [
            {
                "sourceIndex": n,
                "proof": {"kind": "none"},
                "labels": [
                    {
                        "positionIndex": p,
                        "sequenceNumber": 1 + n * 9 + p,
                        "recognitionConfidence": 0.8,
                        "positionConfidence": 0.95,
                    }
                    for p in range(label_count)
                ],
            }
            for n in range(2)
        ],
    }
    output = tmp_path / "output"
    original = module.publish_draft
    count = 0

    def interrupted(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("interrupted publication")
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "publish_draft", interrupted)
    with pytest.raises(OSError):
        module.prepare_drafts(
            manifest, scan, finalization, output_directory=output, run_id="run", first=1, last=18
        )
    assert not module.drafts_ready(output, run_id="run", fingerprint=manifest.source_fingerprint)
    monkeypatch.setattr(module, "publish_draft", original)
    assert (
        module.prepare_drafts(
            manifest, scan, None, output_directory=output, run_id="run", first=1, last=18
        )
        == 2
    )
    assert len(list((output / "propozycje").glob("*.jpg"))) == 2
    (output / "propozycje/seq_1-9.jpg").unlink()
    assert (
        module.prepare_drafts(
            manifest, scan, None, output_directory=output, run_id="run", first=1, last=18
        )
        == 2
    )
    assert not (output / "propozycje/seq_1-9.jpg").exists()
    with pytest.raises(ValueError, match="another draft run"):
        module.drafts_ready(output, run_id="other", fingerprint=manifest.source_fingerprint)


def test_eof_copies_every_expected_group_without_recognized_digits(tmp_path):
    import hashlib
    import json

    source = tmp_path / "source"
    source.mkdir()
    for number in range(20):
        (source / f"{number:03}.jpg").write_bytes(f"source-{number}".encode())
    manifest = build_local_source_manifest(source, selection_id=uuid4(), display_name="source")
    finalization = V7RunFinalization(())
    scan = {"phase": "finalized", "finalization": finalization.as_dict(), "sourceDiagnostics": []}
    output = tmp_path / "output"
    assert (
        module.prepare_drafts(
            manifest, scan, finalization, output_directory=output, run_id="run", first=1, last=36
        )
        == 4
    )
    originals = {}
    for start, source_index in [(1, 2), (10, 7), (19, 12), (28, 17)]:
        file = output / "propozycje" / f"seq_{start}-{start + 8}.jpg"
        payload = json.loads(file.with_suffix(".jpg.json").read_text())
        assert payload["state"] == "estimated"
        assert payload["approved"] is False and payload["ocrProof"] is False
        assert payload["sourceIndex"] == source_index
        assert hashlib.sha256(file.read_bytes()).hexdigest() == payload["sha256"]
        originals[file] = (file.read_bytes(), file.with_suffix(".jpg.json").read_bytes())
    # Lost response/new invocation reuses the durable marker; no scan access needed.
    assert (
        module.prepare_drafts(
            manifest,
            {"phase": "finalized"},
            None,
            output_directory=output,
            run_id="run",
            first=1,
            last=36,
        )
        == 4
    )
    for file, content in originals.items():
        assert (file.read_bytes(), file.with_suffix(".jpg.json").read_bytes()) == content
