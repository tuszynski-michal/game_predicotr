"""Read-only feasibility checks for a semi-automatic-selection v7 checkout."""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import BinaryIO, Literal
from uuid import uuid4

from game_predictor_worker.images.sequence_ocr import MODEL_FILES

ProbeStatus = Literal["ready", "warning", "blocked"]
ModelStatus = Literal["available", "incomplete", "missing"]


@dataclass(frozen=True, slots=True)
class CorpusDirectoryProbe:
    """One direct child of the operator-provided corpus directory."""

    name: str
    jpeg_count: int

    def as_dict(self) -> dict[str, object]:
        return {"jpegCount": self.jpeg_count, "name": self.name}


@dataclass(frozen=True, slots=True)
class PaddleRuntimeProbe:
    """Runtime facts collected before creating an OCR inference predictor."""

    available: bool
    compiled_with_cuda: bool | None
    device: str | None
    error: str | None
    gpu_device_count: int | None
    version: str | None

    @property
    def gpu_available(self) -> bool:
        return self.compiled_with_cuda is True and (self.gpu_device_count or 0) > 0

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "compiledWithCuda": self.compiled_with_cuda,
            "device": self.device,
            "error": self.error,
            "gpuDeviceCount": self.gpu_device_count,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class OcrLabelProbe:
    """One locally observed number, retained even when it cannot prove a range."""

    confidence: float
    position_index: int
    sequence_number: int

    def as_dict(self) -> dict[str, object]:
        return {
            "confidence": self.confidence,
            "positionIndex": self.position_index,
            "sequenceNumber": self.sequence_number,
        }


@dataclass(frozen=True, slots=True)
class OcrExecutionProbe:
    """One actual v6-compatible OCR invocation on a corpus JPEG."""

    attempted: bool
    elapsed_milliseconds: int
    error: str | None
    has_strong_local_proof: bool
    label_evidence: tuple[OcrLabelProbe, ...]
    ocr_batch_calls: int
    observed_range: tuple[int, int] | None
    reason_codes: tuple[str, ...]
    source: Path | None
    succeeded: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "attempted": self.attempted,
            "elapsedMilliseconds": self.elapsed_milliseconds,
            "error": self.error,
            "hasStrongLocalProof": self.has_strong_local_proof,
            "labelEvidence": [item.as_dict() for item in self.label_evidence],
            "ocrBatchCalls": self.ocr_batch_calls,
            "observedRange": None if self.observed_range is None else list(self.observed_range),
            "reasonCodes": list(self.reason_codes),
            "source": None if self.source is None else str(self.source),
            "succeeded": self.succeeded,
        }


@dataclass(frozen=True, slots=True)
class V7EnvironmentProbe:
    """Serializable result and activation gate for the T00 environment check."""

    artifact_root: Path
    artifact_root_is_isolated: bool
    blockers: tuple[str, ...]
    corpus_directories: tuple[CorpusDirectoryProbe, ...]
    corpus_root: Path
    model_missing_files: tuple[str, ...]
    model_root: Path
    model_status: ModelStatus
    ocr_execution: OcrExecutionProbe
    paddle_runtime: PaddleRuntimeProbe
    warnings: tuple[str, ...]
    checkout_root: Path

    @property
    def corpus_jpeg_count(self) -> int:
        return sum(item.jpeg_count for item in self.corpus_directories)

    @property
    def status(self) -> ProbeStatus:
        if self.blockers:
            return "blocked"
        if self.warnings:
            return "warning"
        return "ready"

    def as_dict(self) -> dict[str, object]:
        return {
            "artifactRoot": str(self.artifact_root),
            "artifactRootIsIsolated": self.artifact_root_is_isolated,
            "blockers": list(self.blockers),
            "checkoutRoot": str(self.checkout_root),
            "corpusDirectories": [item.as_dict() for item in self.corpus_directories],
            "corpusJpegCount": self.corpus_jpeg_count,
            "corpusRoot": str(self.corpus_root),
            "model": {
                "missingFiles": list(self.model_missing_files),
                "root": str(self.model_root),
                "status": self.model_status,
            },
            "ocrExecution": self.ocr_execution.as_dict(),
            "paddleRuntime": self.paddle_runtime.as_dict(),
            "schemaVersion": 1,
            "status": self.status,
            "warnings": list(self.warnings),
        }


def probe_v7_environment(
    *,
    checkout_root: Path,
    artifact_root: Path,
    corpus_root: Path,
    model_root: Path,
    require_gpu: bool = False,
) -> V7EnvironmentProbe:
    """Inspect prerequisites and execute OCR once only when all inputs are ready."""

    resolved_checkout = checkout_root.resolve()
    resolved_artifact = artifact_root.resolve()
    resolved_corpus = corpus_root.resolve()
    resolved_model = model_root.resolve()
    artifact_is_isolated = _is_strict_child(resolved_artifact, resolved_checkout)
    blockers: list[str] = []
    warnings: list[str] = []
    if not artifact_is_isolated:
        blockers.append("ARTIFACT_ROOT_NOT_ISOLATED")
    corpus_directories = _probe_corpus(resolved_corpus)
    corpus_jpeg_count = sum(item.jpeg_count for item in corpus_directories)
    if not resolved_corpus.is_dir():
        blockers.append("CORPUS_ROOT_MISSING")
    elif corpus_jpeg_count == 0:
        blockers.append("CORPUS_EMPTY")
    model_status, missing_files = _probe_model(resolved_model)
    if model_status == "missing":
        blockers.append("MODEL_MISSING")
    elif model_status == "incomplete":
        blockers.append("MODEL_INCOMPLETE")
    runtime = _probe_paddle_runtime()
    if not runtime.available:
        blockers.append("PADDLE_RUNTIME_UNAVAILABLE")
    elif not runtime.gpu_available:
        if require_gpu:
            blockers.append("PADDLE_GPU_UNAVAILABLE")
        else:
            warnings.append("PADDLE_GPU_UNAVAILABLE")
    ocr_execution = OcrExecutionProbe(
        attempted=False,
        elapsed_milliseconds=0,
        error=None,
        has_strong_local_proof=False,
        label_evidence=(),
        ocr_batch_calls=0,
        observed_range=None,
        reason_codes=(),
        source=None,
        succeeded=False,
    )
    can_run_ocr = (
        corpus_jpeg_count > 0
        and model_status == "available"
        and runtime.available
        and (not require_gpu or runtime.gpu_available)
    )
    if can_run_ocr:
        source = _first_corpus_jpeg(resolved_corpus)
        if source is None:
            blockers.append("CORPUS_EMPTY")
        else:
            ocr_execution = _probe_ocr_execution(resolved_model, source)
            if not ocr_execution.succeeded:
                blockers.append("OCR_EXECUTION_UNAVAILABLE")
    return V7EnvironmentProbe(
        artifact_root=resolved_artifact,
        artifact_root_is_isolated=artifact_is_isolated,
        blockers=tuple(blockers),
        checkout_root=resolved_checkout,
        corpus_directories=corpus_directories,
        corpus_root=resolved_corpus,
        model_missing_files=missing_files,
        model_root=resolved_model,
        model_status=model_status,
        ocr_execution=ocr_execution,
        paddle_runtime=runtime,
        warnings=tuple(warnings),
    )


def prepare_isolated_artifact_root(report: V7EnvironmentProbe) -> None:
    """Prove reversible write access with an exclusive, owned temporary file."""

    artifact_root = report.artifact_root.resolve()
    if not _is_strict_child(artifact_root, report.checkout_root.resolve()):
        raise ValueError("Artifact root must be a strict child of the checkout.")
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_root = artifact_root.resolve(strict=True)
    if not _is_strict_child(artifact_root, report.checkout_root.resolve()):
        raise ValueError("Artifact root resolved outside the checkout.")
    check_path = artifact_root / f".v7-selection-write-check-{uuid4().hex}.tmp"
    content = b"v7-selection-write-check\n"
    created_identity: tuple[int, int] | None = None
    stream: BinaryIO | None = None
    try:
        stream = check_path.open("xb")
        stat = check_path.stat()
        created_identity = (stat.st_dev, stat.st_ino)
        _write_check(stream, content)
        stream.close()
        stream = None
        if check_path.read_bytes() != content:
            raise OSError("Artifact write check has different content.")
    finally:
        if stream is not None:
            stream.close()
        if created_identity is not None and check_path.exists():
            current = check_path.stat()
            if (current.st_dev, current.st_ino) == created_identity:
                check_path.unlink()


def _write_check(stream: BinaryIO, content: bytes) -> None:
    stream.write(content)


def _is_strict_child(path: Path, parent: Path) -> bool:
    return path != parent and path.is_relative_to(parent)


def _probe_corpus(corpus_root: Path) -> tuple[CorpusDirectoryProbe, ...]:
    if not corpus_root.is_dir():
        return ()
    rows: list[CorpusDirectoryProbe] = []
    for directory in sorted(
        (item for item in corpus_root.iterdir() if item.is_dir()),
        key=lambda item: (item.name.casefold(), item.name),
    ):
        jpeg_count = sum(
            1
            for item in directory.iterdir()
            if item.is_file() and item.suffix.casefold() in {".jpg", ".jpeg"}
        )
        rows.append(CorpusDirectoryProbe(name=directory.name, jpeg_count=jpeg_count))
    return tuple(rows)


def _first_corpus_jpeg(corpus_root: Path) -> Path | None:
    for directory in sorted(
        (item for item in corpus_root.iterdir() if item.is_dir()),
        key=lambda item: (item.name.casefold(), item.name),
    ):
        candidates = sorted(
            (
                item
                for item in directory.iterdir()
                if item.is_file() and item.suffix.casefold() in {".jpg", ".jpeg"}
            ),
            key=lambda item: (item.name.casefold(), item.name),
        )
        if candidates:
            return candidates[0]
    return None


def _probe_model(model_root: Path) -> tuple[ModelStatus, tuple[str, ...]]:
    if not model_root.exists():
        return "missing", tuple(MODEL_FILES)
    if not model_root.is_dir():
        return "incomplete", tuple(MODEL_FILES)
    missing = tuple(name for name in MODEL_FILES if not (model_root / name).is_file())
    return ("available" if not missing else "incomplete"), missing


def _probe_paddle_runtime() -> PaddleRuntimeProbe:
    try:
        paddle = importlib.import_module("paddle")
        compiled_with_cuda = bool(paddle.is_compiled_with_cuda())
        gpu_device_count = int(paddle.device.cuda.device_count()) if compiled_with_cuda else 0
        return PaddleRuntimeProbe(
            available=True,
            compiled_with_cuda=compiled_with_cuda,
            device=str(paddle.device.get_device()),
            error=None,
            gpu_device_count=gpu_device_count,
            version=str(paddle.__version__),
        )
    except (ImportError, RuntimeError) as error:
        return PaddleRuntimeProbe(
            available=False,
            compiled_with_cuda=None,
            device=None,
            error=f"{type(error).__name__}: {error}",
            gpu_device_count=None,
            version=None,
        )


def _probe_ocr_execution(model_root: Path, source: Path) -> OcrExecutionProbe:
    started_at = perf_counter()
    try:
        import numpy as np
        from PIL import Image, ImageOps

        from .range_only_ocr import build_paddle_range_only_recognizer_v3

        with Image.open(source) as image:
            rgb_image = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
        recognizer = build_paddle_range_only_recognizer_v3(model_root)
        recognition = recognizer.recognize(rgb_image)
        observed = recognition.observed_range
        return _ocr_execution_result(
            elapsed_milliseconds=_elapsed_milliseconds(started_at),
            has_strong_local_proof=recognition.has_strong_local_proof,
            label_evidence=tuple(
                OcrLabelProbe(
                    confidence=evidence.confidence,
                    position_index=evidence.position_index,
                    sequence_number=evidence.sequence_number,
                )
                for evidence in recognition.label_evidence
            ),
            source=source,
            observed_range=None if observed is None else (observed.start, observed.end),
            reason_codes=recognition.reason_codes,
            diagnostics=getattr(recognizer, "last_diagnostics", {}),
        )
    except Exception as error:
        return OcrExecutionProbe(
            attempted=True,
            elapsed_milliseconds=_elapsed_milliseconds(started_at),
            error=f"{type(error).__name__}: {error}",
            has_strong_local_proof=False,
            label_evidence=(),
            ocr_batch_calls=0,
            observed_range=None,
            reason_codes=(),
            source=source,
            succeeded=False,
        )


def _ocr_execution_result(
    *,
    elapsed_milliseconds: int = 0,
    has_strong_local_proof: bool = False,
    label_evidence: tuple[OcrLabelProbe, ...] = (),
    source: Path,
    observed_range: tuple[int, int] | None,
    reason_codes: tuple[str, ...],
    diagnostics: object,
) -> OcrExecutionProbe:
    values = diagnostics if isinstance(diagnostics, Mapping) else {}
    batch_calls = values.get("ocrBatchCalls")
    ocr_batch_calls = batch_calls if isinstance(batch_calls, int) and batch_calls > 0 else 0
    if ocr_batch_calls == 0:
        return OcrExecutionProbe(
            attempted=True,
            elapsed_milliseconds=elapsed_milliseconds,
            error="OCR inference did not process any candidate crop.",
            has_strong_local_proof=has_strong_local_proof,
            label_evidence=label_evidence,
            ocr_batch_calls=0,
            observed_range=observed_range,
            reason_codes=reason_codes,
            source=source,
            succeeded=False,
        )
    return OcrExecutionProbe(
        attempted=True,
        elapsed_milliseconds=elapsed_milliseconds,
        error=None,
        has_strong_local_proof=has_strong_local_proof,
        label_evidence=label_evidence,
        ocr_batch_calls=ocr_batch_calls,
        observed_range=observed_range,
        reason_codes=reason_codes,
        source=source,
        succeeded=True,
    )


def _elapsed_milliseconds(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))
