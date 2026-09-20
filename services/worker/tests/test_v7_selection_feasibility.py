from __future__ import annotations

from pathlib import Path

import pytest
from game_predictor_worker.semi_automatic_selection import v7_feasibility


def _runtime(
    *,
    cuda: bool = False,
    gpu_device_count: int = 0,
) -> v7_feasibility.PaddleRuntimeProbe:
    return v7_feasibility.PaddleRuntimeProbe(
        available=True,
        compiled_with_cuda=cuda,
        device="gpu:0" if gpu_device_count else "cpu",
        error=None,
        gpu_device_count=gpu_device_count,
        version="3.3.1",
    )


def _successful_ocr(_: Path, source: Path) -> v7_feasibility.OcrExecutionProbe:
    return v7_feasibility.OcrExecutionProbe(
        attempted=True,
        elapsed_milliseconds=42,
        error=None,
        has_strong_local_proof=True,
        label_evidence=(
            v7_feasibility.OcrLabelProbe(
                confidence=0.99,
                position_index=4,
                sequence_number=5,
            ),
        ),
        ocr_batch_calls=1,
        observed_range=(1, 9),
        reason_codes=(),
        source=source,
        succeeded=True,
    )


def _complete_model(root: Path) -> Path:
    model = root / "model"
    model.mkdir()
    for name in ("inference.json", "inference.pdiparams", "inference.yml"):
        (model / name).write_text(name, encoding="utf-8")
    return model


def _corpus_with_jpeg(root: Path) -> Path:
    corpus = root / "corpus"
    source_directory = corpus / "sample"
    source_directory.mkdir(parents=True)
    (source_directory / "source.JPG").write_bytes(b"jpeg")
    return corpus


def _patch_ready_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "game_predictor_worker.semi_automatic_selection.v7_feasibility._probe_paddle_runtime",
        _runtime,
    )
    monkeypatch.setattr(
        "game_predictor_worker.semi_automatic_selection.v7_feasibility._probe_ocr_execution",
        _successful_ocr,
    )


def test_missing_model_blocks_without_writing_artifact_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "game_predictor_worker.semi_automatic_selection.v7_feasibility._probe_paddle_runtime",
        _runtime,
    )

    report = v7_feasibility.probe_v7_environment(
        checkout_root=tmp_path,
        artifact_root=tmp_path / ".runtime" / "v7",
        corpus_root=tmp_path / "corpus",
        model_root=tmp_path / "missing-model",
    )

    assert report.status == "blocked"
    assert report.blockers == ("CORPUS_ROOT_MISSING", "MODEL_MISSING")
    assert report.model_missing_files == (
        "inference.json",
        "inference.pdiparams",
        "inference.yml",
    )
    assert not report.ocr_execution.attempted
    assert not report.artifact_root.exists()


def test_empty_corpus_blocks_complete_model_without_attempting_ocr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_ready_environment(monkeypatch)
    corpus = tmp_path / "corpus"
    corpus.mkdir()

    report = v7_feasibility.probe_v7_environment(
        checkout_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        corpus_root=corpus,
        model_root=_complete_model(tmp_path),
    )

    assert report.blockers == ("CORPUS_EMPTY",)
    assert not report.ocr_execution.attempted


def test_incomplete_model_names_the_missing_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "game_predictor_worker.semi_automatic_selection.v7_feasibility._probe_paddle_runtime",
        _runtime,
    )
    model = tmp_path / "model"
    model.mkdir()
    (model / "inference.json").write_text("{}", encoding="utf-8")

    report = v7_feasibility.probe_v7_environment(
        checkout_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        corpus_root=_corpus_with_jpeg(tmp_path),
        model_root=model,
    )

    assert report.status == "blocked"
    assert report.blockers == ("MODEL_INCOMPLETE",)
    assert report.model_missing_files == ("inference.pdiparams", "inference.yml")


def test_cpu_runtime_is_warning_only_after_actual_ocr_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_ready_environment(monkeypatch)

    report = v7_feasibility.probe_v7_environment(
        checkout_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        corpus_root=_corpus_with_jpeg(tmp_path),
        model_root=_complete_model(tmp_path),
    )

    assert report.status == "warning"
    assert not report.blockers
    assert report.ocr_execution.succeeded
    assert report.ocr_execution.elapsed_milliseconds == 42
    assert report.ocr_execution.has_strong_local_proof
    assert report.ocr_execution.label_evidence[0].sequence_number == 5
    assert report.warnings == ("PADDLE_GPU_UNAVAILABLE",)


def test_failed_actual_ocr_blocks_complete_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "game_predictor_worker.semi_automatic_selection.v7_feasibility._probe_paddle_runtime",
        _runtime,
    )
    monkeypatch.setattr(
        "game_predictor_worker.semi_automatic_selection.v7_feasibility._probe_ocr_execution",
        lambda _model, source: v7_feasibility.OcrExecutionProbe(
            attempted=True,
            elapsed_milliseconds=10,
            error="SequenceOcrError: invalid model",
            has_strong_local_proof=False,
            label_evidence=(),
            ocr_batch_calls=0,
            observed_range=None,
            reason_codes=(),
            source=source,
            succeeded=False,
        ),
    )

    report = v7_feasibility.probe_v7_environment(
        checkout_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        corpus_root=_corpus_with_jpeg(tmp_path),
        model_root=_complete_model(tmp_path),
    )

    assert report.blockers == ("OCR_EXECUTION_UNAVAILABLE",)


def test_zero_ocr_batches_block_even_when_the_recognizer_returns_cleanly(tmp_path: Path) -> None:
    result = v7_feasibility._ocr_execution_result(
        elapsed_milliseconds=125,
        has_strong_local_proof=False,
        label_evidence=(
            v7_feasibility.OcrLabelProbe(
                confidence=0.95,
                position_index=3,
                sequence_number=4,
            ),
        ),
        source=tmp_path / "source.jpg",
        observed_range=None,
        reason_codes=("RANGE_ONLY_NO_VISIBLE_LABELS",),
        diagnostics={"ocrBatchCalls": 0},
    )

    assert result.attempted
    assert not result.succeeded
    assert result.ocr_batch_calls == 0
    assert result.error == "OCR inference did not process any candidate crop."
    assert result.elapsed_milliseconds == 125
    assert result.label_evidence[0].position_index == 3


def test_gpu_requirement_blocks_cuda_build_without_available_device(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_ready_environment(monkeypatch)
    monkeypatch.setattr(
        "game_predictor_worker.semi_automatic_selection.v7_feasibility._probe_paddle_runtime",
        lambda: _runtime(cuda=True, gpu_device_count=0),
    )

    report = v7_feasibility.probe_v7_environment(
        checkout_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        corpus_root=_corpus_with_jpeg(tmp_path),
        model_root=_complete_model(tmp_path),
        require_gpu=True,
    )

    assert report.blockers == ("PADDLE_GPU_UNAVAILABLE",)
    assert not report.ocr_execution.attempted


def test_artifact_root_outside_checkout_is_blocked_without_creating_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_ready_environment(monkeypatch)
    outside = tmp_path.parent / "outside-artifacts"

    report = v7_feasibility.probe_v7_environment(
        checkout_root=tmp_path,
        artifact_root=outside,
        corpus_root=_corpus_with_jpeg(tmp_path),
        model_root=_complete_model(tmp_path),
    )

    assert report.blockers == ("ARTIFACT_ROOT_NOT_ISOLATED",)
    assert not outside.exists()
    with pytest.raises(ValueError, match="strict child"):
        v7_feasibility.prepare_isolated_artifact_root(report)


def test_corpus_count_is_direct_case_insensitive_and_sorted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_ready_environment(monkeypatch)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    first = corpus / "Alpha"
    first.mkdir()
    (first / "one.JPG").write_bytes(b"jpeg")
    (first / "two.jpeg").write_bytes(b"jpeg")
    (first / "ignored.png").write_bytes(b"png")
    (first / "nested").mkdir()
    (first / "nested" / "hidden.jpg").write_bytes(b"jpeg")
    second = corpus / "beta"
    second.mkdir()
    (second / "three.JpEg").write_bytes(b"jpeg")

    report = v7_feasibility.probe_v7_environment(
        checkout_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        corpus_root=corpus,
        model_root=_complete_model(tmp_path),
    )

    assert [(item.name, item.jpeg_count) for item in report.corpus_directories] == [
        ("Alpha", 2),
        ("beta", 1),
    ]
    assert report.ocr_execution.source == first / "one.JPG"


def test_prepare_artifact_root_preserves_an_existing_control_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_ready_environment(monkeypatch)
    report = v7_feasibility.probe_v7_environment(
        checkout_root=tmp_path,
        artifact_root=tmp_path / ".runtime" / "v7",
        corpus_root=_corpus_with_jpeg(tmp_path),
        model_root=_complete_model(tmp_path),
    )
    report.artifact_root.mkdir(parents=True)
    preserved = report.artifact_root / ".v7-selection-write-check.tmp"
    preserved.write_bytes(b"operator-content")

    v7_feasibility.prepare_isolated_artifact_root(report)

    assert preserved.read_bytes() == b"operator-content"
    assert sorted(item.name for item in report.artifact_root.iterdir()) == [preserved.name]


def test_prepare_artifact_root_removes_its_file_after_write_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_ready_environment(monkeypatch)
    report = v7_feasibility.probe_v7_environment(
        checkout_root=tmp_path,
        artifact_root=tmp_path / ".runtime" / "v7",
        corpus_root=_corpus_with_jpeg(tmp_path),
        model_root=_complete_model(tmp_path),
    )
    monkeypatch.setattr(
        "game_predictor_worker.semi_automatic_selection.v7_feasibility._write_check",
        lambda _stream, _content: (_ for _ in ()).throw(OSError("write failed")),
    )

    with pytest.raises(OSError, match="write failed"):
        v7_feasibility.prepare_isolated_artifact_root(report)

    assert list(report.artifact_root.iterdir()) == []
