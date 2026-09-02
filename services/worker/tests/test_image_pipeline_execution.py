from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from game_predictor_worker.images.orchestration import (
    ImageBatchCandidate,
    ImageFileExecution,
    ImageFileRegistration,
    ImageStageExecutionResult,
    initial_file_checkpoint,
)
from game_predictor_worker.images.pipeline_execution import (
    AUTOMATED_IMAGE_STAGES,
    ContinuityIssue,
    ImageDirectoryBatchSeeder,
    ImagePipelineExecutionError,
    ImagePipelineStageExecutor,
    ImageStageContext,
    ManifestDiscoveryStageAdapter,
    StoredImageStageResult,
    continuity_issues,
    validate_stage_payload,
)
from game_predictor_worker.images.pipeline_store import (
    SqlAlchemyImagePipelineStore,
    _append_prediction_revision,
)
from PIL import Image

CHECKSUM = "a" * 64
PIPELINE = "b" * 64
NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


@dataclass
class FakeAdapter:
    stage: str
    version: str
    payload: dict[str, object]
    call_count: int = 0
    replay_count: int = 0

    def execute(self, context: ImageStageContext) -> dict[str, object]:
        self.call_count += 1
        assert context.source_checksum_sha256 == CHECKSUM
        return self.payload

    def replay(self, context: ImageStageContext, payload: dict[str, object]) -> None:
        assert context.source_checksum_sha256 == CHECKSUM
        assert payload == self.payload
        self.replay_count += 1


class FakeProjectionStore:
    def __init__(self) -> None:
        self.results: dict[str, StoredImageStageResult] = {}
        self.source_projection_count = 0
        self.source_metadata_projection_count = 0
        self.source_geometry_projection_count = 0
        self.recognition_projection_count = 0
        self.pending = 1
        self.materialized = 0
        self.issues: tuple[ContinuityIssue, ...] = ()

    def stage_results(self, file_execution_key: str) -> dict[str, StoredImageStageResult]:
        assert len(file_execution_key) == 64
        return dict(self.results)

    def save_stage_result(
        self,
        candidate: ImageBatchCandidate,
        *,
        stage: str,
        adapter_version: str,
        payload: dict[str, object],
    ) -> StoredImageStageResult:
        stored = StoredImageStageResult(adapter_version, dict(payload))
        existing = self.results.get(stage)
        if existing is not None:
            assert existing == stored
            return existing
        self.results[stage] = stored
        return stored

    def project_source(
        self,
        candidate: ImageBatchCandidate,
        *,
        discovery: dict[str, object],
    ) -> None:
        assert discovery["sourceChecksumSha256"] == CHECKSUM
        self.source_projection_count += 1

    def project_recognition(
        self,
        candidate: ImageBatchCandidate,
        *,
        stage_results: dict[str, StoredImageStageResult],
    ) -> None:
        assert set(AUTOMATED_IMAGE_STAGES).issubset(stage_results)
        self.recognition_projection_count += 1

    def project_source_metadata(
        self,
        candidate: ImageBatchCandidate,
        *,
        normalization: StoredImageStageResult,
    ) -> None:
        del candidate, normalization
        self.source_metadata_projection_count += 1

    def project_source_geometry(
        self,
        candidate: ImageBatchCandidate,
        *,
        stage_results: dict[str, StoredImageStageResult],
    ) -> None:
        del candidate, stage_results
        self.source_geometry_projection_count += 1

    def pending_review_count(self, candidate: ImageBatchCandidate) -> int:
        return self.pending

    def materialize_resolved_staging(self, candidate: ImageBatchCandidate) -> int:
        self.materialized += 1
        return 1

    def reopen_continuity_conflicts(
        self,
        candidate: ImageBatchCandidate,
    ) -> tuple[ContinuityIssue, ...]:
        return self.issues


class FakeRegistrar:
    def __init__(self) -> None:
        self.registered: list[dict[str, object]] = []

    def register_file(self, job_id: UUID, **values: object) -> ImageFileExecution:
        self.registered.append({"job_id": job_id, **values})
        checksum = cast(str, values["source_checksum_sha256"])
        pipeline = cast(str, values["pipeline_fingerprint"])
        return ImageFileExecution(
            file_execution_key="e" * 64,
            source_checksum_sha256=checksum,
            pipeline_fingerprint=pipeline,
            checkpoint_payload=initial_file_checkpoint(checksum, pipeline),
            status="processing",
            review_required=False,
        )

    def register_files(
        self,
        job_id: UUID,
        *,
        registrations: Sequence[ImageFileRegistration],
        pipeline_fingerprint: str,
        registered_at: datetime,
    ) -> None:
        for registration in registrations:
            self.registered.append(
                {
                    "job_id": job_id,
                    "order_index": registration.order_index,
                    "pipeline_fingerprint": pipeline_fingerprint,
                    "registered_at": registered_at,
                    "source_checksum_sha256": registration.source_checksum_sha256,
                    "source_relative_path": registration.source_relative_path,
                }
            )


def _board_cells() -> list[dict[str, object]]:
    return [
        {
            "cropChecksumSha256": f"{index + 1:064x}",
            "cropRelativePath": f"crops/board-0/r{index // 5}-c{index % 5}.png",
            "columnIndex": index % 5,
            "rowIndex": index // 5,
        }
        for index in range(15)
    ]


def _symbol_cells() -> list[dict[str, object]]:
    return [
        {
            "alternatives": [{"confidence": 0.9, "symbolCode": "lemon"}],
            "columnIndex": index % 5,
            "confidence": 0.9,
            "rowIndex": index // 5,
            "symbolCode": "lemon",
        }
        for index in range(15)
    ]


def _virtual_board(position: int) -> dict[str, object]:
    cells = [
        {
            "assetMode": "virtual_source",
            "columnIndex": index % 5,
            "cropChecksumSha256": f"{100 + index:064x}",
            "extractorVersion": "virtual-cell-renderer-source-direct-v1",
            "logicalCellKeySha256": f"{200 + index:064x}",
            "logicalCellKeyV2Sha256": f"{300 + index:064x}",
            "renderIdentityV2Sha256": f"{400 + index:064x}",
            "renderSpec": {"cellIndex": index},
            "renderSpecChecksumSha256": f"{500 + index:064x}",
            "renderedPixelChecksumSha256": f"{600 + index:064x}",
            "rowIndex": index // 5,
        }
        for index in range(15)
    ]
    return {
        "assetMode": "virtual_source",
        "cells": cells,
        "cropperVersion": "virtual-cell-renderer-source-direct-v1",
        "geometryChecksumSha256": "7" * 64,
        "geometryEngineName": "structured_opencv_v1",
        "geometryEngineVersion": "structured-opencv-independent-board-refinement-v2",
        "positionIndex": position,
    }


def test_structured_crops_partition_verified_and_deferred_geometry() -> None:
    context = ImageStageContext(
        job_id=uuid4(),
        file_execution_key="f" * 64,
        source_checksum_sha256=CHECKSUM,
        source_relative_path="batch/page.jpg",
        pipeline_fingerprint=PIPELINE,
        previous_results={
            "board_cell_geometry": {
                "boards": [
                    {"positionIndex": 0, "status": "verified"},
                    {"positionIndex": 1, "status": "deferred"},
                ]
            }
        },
    )
    payload = {
        "assetMode": "virtual_source",
        "boards": [_virtual_board(0)],
        "deferredBoards": [
            {
                "positionIndex": 1,
                "reasonCode": "incomplete_lattice",
                "sequenceNumber": 2,
            }
        ],
    }

    assert validate_stage_payload("board_crops", payload, context) == payload


def test_structured_crops_allow_a_fully_deferred_source() -> None:
    context = ImageStageContext(
        job_id=uuid4(),
        file_execution_key="f" * 64,
        source_checksum_sha256=CHECKSUM,
        source_relative_path="batch/page.jpg",
        pipeline_fingerprint=PIPELINE,
        previous_results={
            "board_cell_geometry": {
                "boards": [
                    {"positionIndex": position, "status": "deferred"} for position in range(3)
                ]
            }
        },
    )
    payload = {
        "assetMode": "virtual_source",
        "boards": [],
        "deferredBoards": [
            {
                "positionIndex": position,
                "reasonCode": "incomplete_lattice",
                "sequenceNumber": position + 1,
            }
            for position in range(3)
        ],
    }

    assert validate_stage_payload("board_crops", payload, context) == payload


def _adapters() -> list[FakeAdapter]:
    return [
        FakeAdapter(
            "discovery",
            "image-discovery-v1",
            {
                "height": 1280,
                "sourceChecksumSha256": CHECKSUM,
                "sourceRelativePath": "batch/page-001.jpg",
                "width": 960,
            },
        ),
        FakeAdapter(
            "normalization",
            "image-normalization-v1",
            {
                "height": 1280,
                "normalizedChecksumSha256": "c" * 64,
                "normalizedRelativePath": "working/normalized.png",
                "width": 960,
            },
        ),
        FakeAdapter(
            "board_detection",
            "page-board-detector-v3-unique-partial-grid-v1",
            {
                "boards": [
                    {
                        "confidence": 0.98,
                        "geometry": {"quad": [[1, 1], [10, 1], [10, 10], [1, 10]]},
                        "positionIndex": 0,
                    }
                ]
            },
        ),
        FakeAdapter(
            "board_crops",
            "board-cell-crops-v17-source-direct-model-input-v1",
            {
                "boards": [
                    {
                        "boardChecksumSha256": "d" * 64,
                        "boardRelativePath": "crops/board-0/board.png",
                        "cells": _board_cells(),
                        "cropperVersion": ("board-cell-crops-v17-source-direct-model-input-v1"),
                        "positionIndex": 0,
                    }
                ]
            },
        ),
        FakeAdapter(
            "sequence_ocr",
            "sequence-number-ocr-v2-page-continuity-v1",
            {
                "boards": [
                    {
                        "confidence": 0.64,
                        "normalizedNumber": 29,
                        "positionIndex": 0,
                        "rawText": "29",
                        "reviewReasons": ["SEQUENCE_OCR_MANUAL_REVIEW_REQUIRED"],
                    }
                ]
            },
        ),
        FakeAdapter(
            "symbol_inference",
            "local-symbol-onnx-runtime-v1",
            {
                "boards": [
                    {
                        "cells": _symbol_cells(),
                        "positionIndex": 0,
                    }
                ],
                "modelIterationId": None,
                "modelManifestChecksumSha256": "e" * 64,
                "modelVersion": "bootstrap-symbol-cnn-onnx-v1",
            },
        ),
    ]


def _candidate() -> ImageBatchCandidate:
    checkpoint = initial_file_checkpoint(CHECKSUM, PIPELINE)
    execution = ImageFileExecution(
        file_execution_key=cast(str, checkpoint["fileExecutionKey"]),
        source_checksum_sha256=CHECKSUM,
        pipeline_fingerprint=PIPELINE,
        checkpoint_payload=checkpoint,
        status="processing",
        review_required=False,
    )
    return ImageBatchCandidate(
        execution=execution,
        order_index=0,
        source_relative_path="batch/page-001.jpg",
        job_id=uuid4(),
        lease_token=uuid4(),
        executed_at=NOW,
    )


def test_storage_bounded_normalization_payload_is_source_bound() -> None:
    candidate = _candidate()
    context = ImageStageContext(
        job_id=uuid4(),
        file_execution_key=candidate.execution.file_execution_key,
        source_checksum_sha256=CHECKSUM,
        source_relative_path="batch/page-001.jpg",
        pipeline_fingerprint=PIPELINE,
        previous_results={},
    )
    payload = {
        "height": 960,
        "normalizedPixelChecksumSha256": "c" * 64,
        "orientationAction": "rotate_90_clockwise",
        "sourceChecksumSha256": CHECKSUM,
        "sourceHeight": 960,
        "sourceMode": "RGB",
        "sourceRelativePath": "batch/page-001.jpg",
        "sourceWidth": 1280,
        "width": 1280,
    }

    assert validate_stage_payload("normalization", payload, context) == payload
    payload["sourceRelativePath"] = "batch/other.jpg"
    with pytest.raises(ImagePipelineExecutionError) as raised:
        validate_stage_payload("normalization", payload, context)
    assert raised.value.code == "IMAGE_STAGE_RESULT_INVALID"


class _ScalarSequenceSession:
    def __init__(self, values: Sequence[object]) -> None:
        self._values = iter(values)

    def __enter__(self) -> _ScalarSequenceSession:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def scalar(self, _statement: object) -> object:
        return next(self._values)


class _PredictionRevisionSession:
    def __init__(self, existing: object = None) -> None:
        self.existing = existing
        self.added: list[object] = []

    def scalar(self, _statement: object) -> object:
        return self.existing

    def add(self, value: object) -> None:
        self.added.append(value)


def test_virtual_prediction_revision_keeps_full_render_provenance() -> None:
    session = _PredictionRevisionSession()
    review_item_id = uuid4()
    board_id = uuid4()
    crops = [
        {
            "assetMode": "virtual_source",
            "columnIndex": index % 5,
            "cropChecksumSha256": f"{100 + index:064x}",
            "extractorVersion": "virtual-cell-renderer-source-direct-v1",
            "logicalCellKeySha256": f"{200 + index:064x}",
            "logicalCellKeyV2Sha256": f"{250 + index:064x}",
            "renderIdentityV2Sha256": f"{275 + index:064x}",
            "renderSpec": {"cellIndex": index},
            "renderSpecChecksumSha256": f"{300 + index:064x}",
            "renderedPixelChecksumSha256": f"{400 + index:064x}",
            "rowIndex": index // 5,
        }
        for index in range(15)
    ]
    predictions = _symbol_cells()

    _append_prediction_revision(
        cast(object, session),
        game_id=uuid4(),
        job_id=uuid4(),
        review_item=cast(object, SimpleNamespace(id=review_item_id)),
        board=cast(object, SimpleNamespace(id=board_id)),
        crop_board={
            "assetMode": "virtual_source",
            "cells": crops,
            "geometryChecksumSha256": "e" * 64,
            "positionIndex": 0,
        },
        symbol_board={"cells": predictions, "positionIndex": 0},
        symbol_payload={
            "modelChecksumSha256": "f" * 64,
            "modelIterationId": None,
            "modelVersion": "symbol-model-test-v1",
        },
        created_at=NOW,
    )

    assert len(session.added) == 1
    revision = session.added[0]
    assert revision.review_item_id == review_item_id  # type: ignore[attr-defined]
    assert revision.recognized_board_id == board_id  # type: ignore[attr-defined]
    virtual = revision.predictions[0]["virtualCell"]  # type: ignore[attr-defined]
    assert virtual == {
        "cropChecksumSha256": crops[0]["cropChecksumSha256"],
        "extractorVersion": "virtual-cell-renderer-source-direct-v1",
        "logicalCellKeySha256": crops[0]["logicalCellKeySha256"],
        "logicalCellKeyV2Sha256": crops[0]["logicalCellKeyV2Sha256"],
        "renderIdentityV2Sha256": crops[0]["renderIdentityV2Sha256"],
        "renderSpec": {"cellIndex": 0},
        "renderSpecChecksumSha256": crops[0]["renderSpecChecksumSha256"],
        "renderedPixelChecksumSha256": crops[0]["renderedPixelChecksumSha256"],
    }


def test_pending_review_count_includes_deferred_board_cell_geometry() -> None:
    source = SimpleNamespace(id=uuid4())
    session = _ScalarSequenceSession((source, 2, 8))
    store = SqlAlchemyImagePipelineStore(cast(object, lambda: session))

    assert store.pending_review_count(_candidate()) == 10


def test_pipeline_executes_all_adapters_then_stages_only_after_review() -> None:
    store = FakeProjectionStore()
    adapters = _adapters()
    executor = ImagePipelineStageExecutor(store, adapters)
    candidate = _candidate()

    for stage in AUTOMATED_IMAGE_STAGES:
        assert executor.execute_stage(candidate, stage) is ImageStageExecutionResult.COMPLETED

    assert store.source_projection_count == 1
    assert store.source_metadata_projection_count == 1
    assert store.source_geometry_projection_count == 0
    assert store.recognition_projection_count == 1
    assert executor.execute_stage(candidate, "manual_review") == "waiting_for_review"
    assert store.materialized == 0

    store.pending = 0
    assert executor.execute_stage(candidate, "manual_review") == "completed"
    assert store.materialized == 1
    assert executor.execute_stage(candidate, "validation") == "completed"
    assert [adapter.call_count for adapter in adapters] == [1, 1, 1, 1, 1, 1]


def test_completed_results_rehydrate_job_local_state_without_inference() -> None:
    store = FakeProjectionStore()
    adapters = _adapters()
    for adapter in adapters:
        store.results[adapter.stage] = StoredImageStageResult(
            adapter.version,
            adapter.payload,
        )
    executor = ImagePipelineStageExecutor(store, adapters)

    executor.rehydrate(_candidate())

    assert store.source_projection_count == 1
    assert store.source_metadata_projection_count == 1
    assert store.source_geometry_projection_count == 0
    assert store.recognition_projection_count == 1
    assert all(adapter.call_count == 0 for adapter in adapters)


def test_replayed_immutable_stage_does_not_call_adapter_twice() -> None:
    store = FakeProjectionStore()
    adapters = _adapters()
    executor = ImagePipelineStageExecutor(store, adapters)
    candidate = _candidate()

    assert executor.execute_stage(candidate, "discovery") == "completed"
    assert executor.execute_stage(candidate, "discovery") == "completed"

    assert adapters[0].call_count == 1
    assert store.source_projection_count == 2


def test_v20_geometry_substage_is_persisted_and_replayed_before_crops() -> None:
    store = FakeProjectionStore()
    adapters = _adapters()
    geometry = FakeAdapter(
        "board_cell_geometry",
        "board-cell-processing-v20-verified-v19-v1",
        {
            "boards": [
                {
                    "cellGeometry": {
                        "cells": [
                            {
                                "columnIndex": index % 5,
                                "quad": [
                                    {"x": 1.0, "y": 1.0},
                                    {"x": 2.0, "y": 1.0},
                                    {"x": 2.0, "y": 2.0},
                                    {"x": 1.0, "y": 2.0},
                                ],
                                "rowIndex": index // 5,
                            }
                            for index in range(15)
                        ]
                    },
                    "confidence": 0.98,
                    "geometry": {"quad": [[1, 1], [10, 1], [10, 10], [1, 10]]},
                    "positionIndex": 0,
                    "sequenceNumber": 1,
                    "status": "verified",
                }
            ],
            "configurationFingerprintSha256": "f" * 64,
            "processingVersion": "board-cell-processing-v20-verified-v19-v1",
        },
    )
    adapters.insert(3, geometry)
    executor = ImagePipelineStageExecutor(store, adapters)
    candidate = _candidate()

    for stage in AUTOMATED_IMAGE_STAGES[:3]:
        executor.execute_stage(candidate, stage)
    executor.execute_stage(candidate, "board_crops")
    replay_adapters = _adapters()
    replay_geometry = FakeAdapter(
        geometry.stage,
        geometry.version,
        geometry.payload,
    )
    replay_adapters.insert(3, replay_geometry)
    ImagePipelineStageExecutor(store, replay_adapters).execute_stage(candidate, "board_crops")

    assert geometry.call_count == 1
    assert adapters[4].call_count == 1
    assert replay_geometry.call_count == 0
    assert replay_adapters[4].call_count == 0
    assert replay_geometry.replay_count == 1
    assert "board_cell_geometry" in store.results
    assert store.source_metadata_projection_count == 1
    assert store.source_geometry_projection_count == 2


def test_incomplete_symbol_board_fails_closed_without_projection() -> None:
    store = FakeProjectionStore()
    adapters = _adapters()
    symbol_boards = cast(list[dict[str, object]], adapters[-1].payload["boards"])
    symbol_boards[0]["cells"] = _symbol_cells()[:-1]
    executor = ImagePipelineStageExecutor(store, adapters)
    candidate = _candidate()

    for stage in AUTOMATED_IMAGE_STAGES[:-1]:
        executor.execute_stage(candidate, stage)
    with pytest.raises(ImagePipelineExecutionError) as caught:
        executor.execute_stage(candidate, "symbol_inference")

    assert caught.value.code == "IMAGE_STAGE_RESULT_INVALID"
    assert store.recognition_projection_count == 0


def test_continuity_reports_duplicates_and_gaps_without_rewriting_numbers() -> None:
    assert continuity_issues([10, 11, 11, 13]) == (
        ContinuityIssue("IMAGE_SEQUENCE_DUPLICATE", 11, 2),
        ContinuityIssue("IMAGE_SEQUENCE_GAP", 12, 0),
    )


def test_validation_rejects_unresolved_continuity() -> None:
    store = FakeProjectionStore()
    store.issues = (ContinuityIssue("IMAGE_SEQUENCE_GAP", 12, 0),)
    executor = ImagePipelineStageExecutor(store, _adapters())

    with pytest.raises(ImagePipelineExecutionError) as caught:
        executor.execute_stage(_candidate(), "validation")

    assert caught.value.code == "IMAGE_SEQUENCE_REVIEW_REOPENED"


def test_registry_requires_every_automated_stage_once() -> None:
    with pytest.raises(ImagePipelineExecutionError) as caught:
        ImagePipelineStageExecutor(FakeProjectionStore(), _adapters()[:-1])

    assert caught.value.code == "IMAGE_PIPELINE_ADAPTER_MISSING"


def test_directory_seeder_uses_real_discovery_and_manifest_adapter(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(
        source_root / "page.jpg",
        format="JPEG",
    )
    registrar = FakeRegistrar()
    job_id = uuid4()

    manifest = ImageDirectoryBatchSeeder(registrar).seed(
        job_id,
        source_root=source_root,
        pipeline_fingerprint=PIPELINE,
        registered_at=NOW,
    )

    assert len(registrar.registered) == 1
    image = manifest.images[0]
    context = ImageStageContext(
        job_id=job_id,
        file_execution_key="e" * 64,
        source_checksum_sha256=image.checksum_sha256,
        source_relative_path="page.jpg",
        pipeline_fingerprint=PIPELINE,
        previous_results={},
    )
    assert ManifestDiscoveryStageAdapter(manifest).execute(context) == {
        "height": 24,
        "sourceChecksumSha256": image.checksum_sha256,
        "sourceRelativePath": "page.jpg",
        "width": 32,
    }
