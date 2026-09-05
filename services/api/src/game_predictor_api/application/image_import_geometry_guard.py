"""Application workflow for resolving board-level large-import guard failures."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol, cast
from uuid import UUID, uuid4

from game_predictor_api.domain.image_import_geometry_guard import (
    ImageGeometryGuardBoardContext,
    ImageGeometryGuardBoardTarget,
    ImageGeometryGuardDecision,
    ImageGeometryGuardDecisionError,
    ImageGeometryGuardDisposition,
    ImageGeometryGuardResolutionManifest,
    ImageGeometryGuardScope,
    create_guard_decision,
    payload_checksum,
    resolution_manifest_payload,
)
from game_predictor_api.domain.jobs import JobConflictError, JobError


class ImageGeometryGuardRepository(Protocol):
    def get_scope(
        self,
        *,
        game_id: UUID,
        browser_selection_id: UUID,
        guard_job_id: UUID,
    ) -> ImageGeometryGuardScope | None: ...

    def latest_decisions(self, *, guard_job_id: UUID) -> tuple[ImageGeometryGuardDecision, ...]: ...

    def add_decisions(
        self, values: Sequence[ImageGeometryGuardDecision]
    ) -> tuple[ImageGeometryGuardDecision, ...]: ...

    def get_manifest_by_checksum(
        self, *, guard_job_id: UUID, manifest_checksum_sha256: str
    ) -> ImageGeometryGuardResolutionManifest | None: ...

    def get_manifest_by_id(
        self, *, manifest_id: UUID
    ) -> ImageGeometryGuardResolutionManifest | None: ...

    def add_manifest(
        self, value: ImageGeometryGuardResolutionManifest
    ) -> ImageGeometryGuardResolutionManifest: ...


@dataclass(frozen=True, slots=True)
class ImageGeometryGuardQueue:
    game_id: UUID
    browser_selection_id: UUID
    guard_job_id: UUID
    guard_report_checksum_sha256: str
    source_manifest_checksum_sha256: str
    page_geometry_manifest_checksum_sha256: str
    boards: tuple[ImageGeometryGuardBoardContext, ...]
    targets: tuple[ImageGeometryGuardBoardTarget, ...]
    decisions: tuple[ImageGeometryGuardDecision, ...]

    @property
    def unresolved_count(self) -> int:
        decided = {(item.source_checksum_sha256, item.position_index) for item in self.decisions}
        return sum(
            (item.source_checksum_sha256, item.position_index) not in decided
            for item in self.targets
        )


@dataclass(frozen=True, slots=True)
class ImageGeometryGuardDecisionCommand:
    source_checksum_sha256: str
    position_index: int
    sequence_number: int
    disposition: ImageGeometryGuardDisposition
    symbol_grid_quad: tuple[dict[str, int], ...] | None
    unavailable_cell_indices: tuple[int, ...]
    reason: str | None


@dataclass(frozen=True, slots=True)
class ImageGeometryGuardReportReconstructionInput:
    source_guard_job_id: UUID
    legacy_report_checksum_sha256: str
    source_manifest_checksum_sha256: str
    page_geometry_manifest_checksum_sha256: str


class ImageImportGeometryGuardService:
    def __init__(self, repository: ImageGeometryGuardRepository, artifact_root: Path) -> None:
        self._repository = repository
        self._artifact_root = artifact_root.resolve()

    def queue(
        self,
        *,
        game_id: UUID,
        browser_selection_id: UUID,
        guard_job_id: UUID,
    ) -> ImageGeometryGuardQueue:
        scope = self._scope(
            game_id=game_id,
            browser_selection_id=browser_selection_id,
            guard_job_id=guard_job_id,
        )
        report, report_checksum = self._report(scope, guard_job_id=guard_job_id)
        boards = _boards(report)
        targets = _targets(report)
        decisions = tuple(
            item
            for item in self._repository.latest_decisions(guard_job_id=guard_job_id)
            if item.guard_report_checksum_sha256 == report_checksum
        )
        return ImageGeometryGuardQueue(
            game_id=game_id,
            browser_selection_id=browser_selection_id,
            guard_job_id=guard_job_id,
            guard_report_checksum_sha256=report_checksum,
            source_manifest_checksum_sha256=_source_manifest_checksum(scope),
            page_geometry_manifest_checksum_sha256=_page_manifest_checksum(scope),
            boards=boards,
            targets=targets,
            decisions=decisions,
        )

    def save_decisions(
        self,
        *,
        game_id: UUID,
        browser_selection_id: UUID,
        guard_job_id: UUID,
        expected_guard_report_checksum_sha256: str,
        commands: tuple[ImageGeometryGuardDecisionCommand, ...],
        actor: str,
    ) -> tuple[ImageGeometryGuardDecision, ...]:
        queue = self.queue(
            game_id=game_id,
            browser_selection_id=browser_selection_id,
            guard_job_id=guard_job_id,
        )
        if queue.guard_report_checksum_sha256 != expected_guard_report_checksum_sha256:
            raise JobConflictError(
                "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT",
                "The geometry guard report changed before the decision was saved.",
            )
        if not commands:
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_DECISION_EMPTY",
                "At least one board decision is required.",
            )
        source_checksums = {item.source_checksum_sha256 for item in commands}
        if len(source_checksums) != 1:
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_DECISION_SOURCE_MIXED",
                "One atomic decision command may target boards from only one source image.",
            )
        command_keys = [(item.source_checksum_sha256, item.position_index) for item in commands]
        if len(command_keys) != len(set(command_keys)):
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_DECISION_DUPLICATE",
                "The same board slot cannot occur twice in one command.",
            )
        targets = {
            (item.source_checksum_sha256, item.position_index): item for item in queue.targets
        }
        current = {
            (item.source_checksum_sha256, item.position_index): item for item in queue.decisions
        }
        created: list[ImageGeometryGuardDecision] = []
        try:
            for command in commands:
                key = (command.source_checksum_sha256, command.position_index)
                target = targets.get(key)
                if target is None or target.sequence_number != command.sequence_number:
                    raise JobConflictError(
                        "IMAGE_GEOMETRY_GUARD_DECISION_TARGET_DRIFT",
                        "The selected board no longer matches the immutable guard report.",
                    )
                previous = current.get(key)
                created.append(
                    create_guard_decision(
                        game_id=game_id,
                        browser_selection_id=browser_selection_id,
                        guard_job_id=guard_job_id,
                        guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
                        target=target,
                        revision=1 if previous is None else previous.revision + 1,
                        disposition=command.disposition,
                        symbol_grid_quad=command.symbol_grid_quad,
                        unavailable_cell_indices=command.unavailable_cell_indices,
                        reason=command.reason,
                        actor=actor,
                    )
                )
        except ImageGeometryGuardDecisionError as error:
            raise JobError("IMAGE_GEOMETRY_GUARD_DECISION_INVALID", str(error)) from error
        return self._repository.add_decisions(created)

    def report_reconstruction_input(
        self,
        *,
        game_id: UUID,
        browser_selection_id: UUID,
        guard_job_id: UUID,
    ) -> ImageGeometryGuardReportReconstructionInput:
        scope = self._scope(
            game_id=game_id,
            browser_selection_id=browser_selection_id,
            guard_job_id=guard_job_id,
        )
        report, checksum = self._stored_report(scope)
        if report.get("schemaVersion") == "image-geometry-systemic-guard-report-v2":
            raise JobConflictError(
                "IMAGE_GEOMETRY_GUARD_RECONSTRUCTION_NOT_REQUIRED",
                "The geometry guard report already contains board-level diagnostics.",
            )
        selected = report.get("selectedSourceChecksums")
        if (
            not isinstance(selected, Sequence)
            or isinstance(selected, str | bytes)
            or not selected
            or any(not isinstance(value, str) or not value for value in selected)
        ):
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_REPORT_INVALID",
                "The legacy geometry guard report has no selected-source snapshot.",
            )
        return ImageGeometryGuardReportReconstructionInput(
            source_guard_job_id=guard_job_id,
            legacy_report_checksum_sha256=checksum,
            source_manifest_checksum_sha256=_source_manifest_checksum(scope),
            page_geometry_manifest_checksum_sha256=_page_manifest_checksum(scope),
        )

    def seal_manifest(
        self,
        *,
        game_id: UUID,
        browser_selection_id: UUID,
        guard_job_id: UUID,
        expected_guard_report_checksum_sha256: str,
        actor: str,
    ) -> ImageGeometryGuardResolutionManifest:
        queue = self.queue(
            game_id=game_id,
            browser_selection_id=browser_selection_id,
            guard_job_id=guard_job_id,
        )
        if queue.guard_report_checksum_sha256 != expected_guard_report_checksum_sha256:
            raise JobConflictError(
                "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT",
                "The geometry guard report changed before the manifest was sealed.",
            )
        if queue.unresolved_count:
            raise JobConflictError(
                "IMAGE_GEOMETRY_GUARD_DECISIONS_INCOMPLETE",
                "Every failed board must have an explicit decision before sealing.",
                details={"unresolvedCount": queue.unresolved_count},
            )
        target_keys = {(item.source_checksum_sha256, item.position_index) for item in queue.targets}
        decisions = tuple(
            item
            for item in queue.decisions
            if (item.source_checksum_sha256, item.position_index) in target_keys
        )
        try:
            payload = resolution_manifest_payload(
                game_id=game_id,
                browser_selection_id=browser_selection_id,
                guard_job_id=guard_job_id,
                guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
                source_manifest_checksum_sha256=queue.source_manifest_checksum_sha256,
                page_geometry_manifest_checksum_sha256=(
                    queue.page_geometry_manifest_checksum_sha256
                ),
                decisions=decisions,
            )
        except ImageGeometryGuardDecisionError as error:
            raise JobError("IMAGE_GEOMETRY_GUARD_MANIFEST_INVALID", str(error)) from error
        checksum = payload_checksum(payload)
        existing = self._repository.get_manifest_by_checksum(
            guard_job_id=guard_job_id,
            manifest_checksum_sha256=checksum,
        )
        if existing is not None:
            return existing
        relative_path = (
            PurePosixPath("data", "image-geometry-guard-resolutions", checksum[:2])
            / f"{checksum}.json"
        ).as_posix()
        _write_immutable(self._artifact_root, relative_path, payload)
        value = ImageGeometryGuardResolutionManifest(
            id=uuid4(),
            game_id=game_id,
            browser_selection_id=browser_selection_id,
            guard_job_id=guard_job_id,
            guard_report_checksum_sha256=queue.guard_report_checksum_sha256,
            source_manifest_checksum_sha256=queue.source_manifest_checksum_sha256,
            page_geometry_manifest_checksum_sha256=(queue.page_geometry_manifest_checksum_sha256),
            manifest_relative_path=relative_path,
            manifest_checksum_sha256=checksum,
            decision_count=len(decisions),
            sealed_by=actor.strip(),
            created_at=datetime.now(UTC),
        )
        if not value.sealed_by:
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_MANIFEST_ACTOR_REQUIRED",
                "The manifest actor is required.",
            )
        return self._repository.add_manifest(value)

    def require_manifest_descriptor(
        self,
        *,
        game_id: UUID,
        browser_selection_id: UUID,
        manifest_id: UUID,
        expected_manifest_checksum_sha256: str,
        source_manifest_checksum_sha256: str,
        page_geometry_manifest_checksum_sha256: str,
    ) -> dict[str, object]:
        value = self._repository.get_manifest_by_id(manifest_id=manifest_id)
        if value is None:
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_MANIFEST_NOT_FOUND",
                "The sealed geometry guard resolution manifest does not exist.",
            )
        if (
            value.game_id != game_id
            or value.browser_selection_id != browser_selection_id
            or value.manifest_checksum_sha256 != expected_manifest_checksum_sha256
            or value.source_manifest_checksum_sha256 != source_manifest_checksum_sha256
            or value.page_geometry_manifest_checksum_sha256
            != page_geometry_manifest_checksum_sha256
        ):
            raise JobConflictError(
                "IMAGE_GEOMETRY_GUARD_MANIFEST_INCOMPATIBLE",
                "The sealed geometry guard resolution manifest does not match this import.",
            )
        return {
            "id": str(value.id),
            "checksumSha256": value.manifest_checksum_sha256,
            "relativePath": value.manifest_relative_path,
            "guardJobId": str(value.guard_job_id),
            "guardReportChecksumSha256": value.guard_report_checksum_sha256,
            "sourceManifestChecksumSha256": value.source_manifest_checksum_sha256,
            "pageGeometryManifestChecksumSha256": (value.page_geometry_manifest_checksum_sha256),
        }

    def _scope(
        self, *, game_id: UUID, browser_selection_id: UUID, guard_job_id: UUID
    ) -> ImageGeometryGuardScope:
        scope = self._repository.get_scope(
            game_id=game_id,
            browser_selection_id=browser_selection_id,
            guard_job_id=guard_job_id,
        )
        if scope is None:
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_SCOPE_NOT_FOUND",
                "The guard job does not belong to this game and browser staging.",
            )
        return scope

    def _stored_report(self, scope: ImageGeometryGuardScope) -> tuple[dict[str, object], str]:
        checkpoint = scope.job_checkpoint_payload
        guard = None if checkpoint is None else checkpoint.get("geometry_systemic_guard")
        if not isinstance(guard, Mapping):
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_REPORT_UNAVAILABLE",
                "The import job has no persisted geometry guard report.",
            )
        relative = guard.get("reportRelativePath")
        expected_checksum = guard.get("reportChecksumSha256")
        if not isinstance(relative, str) or not isinstance(expected_checksum, str):
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_REPORT_INVALID",
                "The geometry guard checkpoint is invalid.",
            )
        path = _managed_path(self._artifact_root, relative, "image-geometry-guards")
        try:
            envelope = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError) as error:
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_REPORT_UNAVAILABLE",
                "The persisted geometry guard report is unavailable.",
            ) from error
        if not isinstance(envelope, Mapping) or not isinstance(envelope.get("report"), Mapping):
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_REPORT_INVALID",
                "The persisted geometry guard report envelope is invalid.",
            )
        report = dict(cast(Mapping[str, object], envelope["report"]))
        if payload_checksum(report) != expected_checksum:
            raise JobConflictError(
                "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT",
                "The persisted geometry guard report checksum changed.",
            )
        return report, expected_checksum

    def _report(
        self,
        scope: ImageGeometryGuardScope,
        *,
        guard_job_id: UUID,
    ) -> tuple[dict[str, object], str]:
        report, expected_checksum = self._stored_report(scope)
        if report.get("schemaVersion") == "image-geometry-systemic-guard-report-v2":
            return report, expected_checksum
        checkpoint = scope.derived_report_checkpoint
        if not isinstance(checkpoint, Mapping):
            raise JobConflictError(
                "IMAGE_GEOMETRY_GUARD_BOARD_REPORT_REQUIRED",
                "Board-level diagnostics must be reconstructed before decisions can be made.",
            )
        if (
            checkpoint.get("sourceGuardJobId") != str(guard_job_id)
            or checkpoint.get("legacyReportChecksumSha256") != expected_checksum
            or checkpoint.get("sourceManifestChecksumSha256") != _source_manifest_checksum(scope)
            or checkpoint.get("pageGeometryManifestChecksumSha256")
            != _page_manifest_checksum(scope)
        ):
            raise JobConflictError(
                "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT",
                "The reconstructed board report differs from the pinned legacy import.",
            )
        relative = checkpoint.get("reportRelativePath")
        reconstructed_checksum = checkpoint.get("reportChecksumSha256")
        if not isinstance(relative, str) or not isinstance(reconstructed_checksum, str):
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_REPORT_INVALID",
                "The reconstructed board report checkpoint is invalid.",
            )
        path = _managed_path(self._artifact_root, relative, "image-geometry-guards")
        try:
            envelope = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError) as error:
            raise JobError(
                "IMAGE_GEOMETRY_GUARD_REPORT_UNAVAILABLE",
                "The reconstructed board report is unavailable.",
            ) from error
        reconstructed = envelope.get("report") if isinstance(envelope, Mapping) else None
        envelope_checksum = (
            envelope.get("reportChecksumSha256") if isinstance(envelope, Mapping) else None
        )
        if (
            not isinstance(reconstructed, Mapping)
            or envelope_checksum != reconstructed_checksum
            or payload_checksum(reconstructed) != reconstructed_checksum
            or reconstructed.get("schemaVersion") != "image-geometry-systemic-guard-report-v2"
            or reconstructed.get("derivedFromReportChecksumSha256") != expected_checksum
            or reconstructed.get("jobId") != str(guard_job_id)
        ):
            raise JobConflictError(
                "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT",
                "The reconstructed board report content changed.",
            )
        return dict(cast(Mapping[str, object], reconstructed)), reconstructed_checksum


def _targets(report: Mapping[str, object]) -> tuple[ImageGeometryGuardBoardTarget, ...]:
    sources = report.get("sources")
    if not isinstance(sources, Sequence) or isinstance(sources, str | bytes):
        raise JobError("IMAGE_GEOMETRY_GUARD_REPORT_INVALID", "The report has no source list.")
    targets: list[ImageGeometryGuardBoardTarget] = []
    for raw_source in sources:
        if not isinstance(raw_source, Mapping):
            raise JobError("IMAGE_GEOMETRY_GUARD_REPORT_INVALID", "A report source is invalid.")
        source_checksum = raw_source.get("sourceChecksumSha256")
        source_path = raw_source.get("sourceRelativePath")
        boards = raw_source.get("boards")
        if (
            not isinstance(source_checksum, str)
            or not isinstance(source_path, str)
            or not isinstance(boards, Sequence)
            or isinstance(boards, str | bytes)
        ):
            raise JobError("IMAGE_GEOMETRY_GUARD_REPORT_INVALID", "A report source is incomplete.")
        for raw_board in boards:
            if not isinstance(raw_board, Mapping) or raw_board.get("status") != "deferred":
                continue
            position = raw_board.get("positionIndex")
            sequence_number = raw_board.get("sequenceNumber")
            reasons = raw_board.get("reasonCodes")
            if (
                not isinstance(position, int)
                or isinstance(position, bool)
                or not isinstance(sequence_number, int)
                or isinstance(sequence_number, bool)
                or not isinstance(reasons, Sequence)
                or isinstance(reasons, str | bytes)
                or any(not isinstance(reason, str) or not reason for reason in reasons)
            ):
                raise JobError(
                    "IMAGE_GEOMETRY_GUARD_REPORT_INVALID", "A deferred board is invalid."
                )
            targets.append(
                ImageGeometryGuardBoardTarget(
                    source_checksum_sha256=source_checksum,
                    source_relative_path=source_path,
                    position_index=position,
                    sequence_number=sequence_number,
                    reason_codes=tuple(cast(Sequence[str], reasons)),
                    page_geometry=(
                        dict(raw_board["pageGeometry"])
                        if isinstance(raw_board.get("pageGeometry"), Mapping)
                        else None
                    ),
                    analysis_quad=raw_board.get("analysisQuad"),
                    proposed_symbol_grid_quad=raw_board.get("symbolGridQuad"),
                    evidence=(
                        dict(raw_board["evidence"])
                        if isinstance(raw_board.get("evidence"), Mapping)
                        else None
                    ),
                )
            )
    return tuple(
        sorted(targets, key=lambda item: (item.source_checksum_sha256, item.position_index))
    )


def _boards(report: Mapping[str, object]) -> tuple[ImageGeometryGuardBoardContext, ...]:
    sources = report.get("sources")
    if not isinstance(sources, Sequence) or isinstance(sources, str | bytes):
        raise JobError("IMAGE_GEOMETRY_GUARD_REPORT_INVALID", "The report has no source list.")
    result: list[ImageGeometryGuardBoardContext] = []
    seen: set[tuple[str, int]] = set()
    for raw_source in sources:
        if not isinstance(raw_source, Mapping):
            raise JobError("IMAGE_GEOMETRY_GUARD_REPORT_INVALID", "A report source is invalid.")
        source_checksum = raw_source.get("sourceChecksumSha256")
        source_path = raw_source.get("sourceRelativePath")
        raw_boards = raw_source.get("boards")
        if (
            not isinstance(source_checksum, str)
            or not isinstance(source_path, str)
            or not isinstance(raw_boards, Sequence)
            or isinstance(raw_boards, str | bytes)
        ):
            raise JobError("IMAGE_GEOMETRY_GUARD_REPORT_INVALID", "A report source is incomplete.")
        for raw_board in raw_boards:
            if not isinstance(raw_board, Mapping):
                raise JobError("IMAGE_GEOMETRY_GUARD_REPORT_INVALID", "A report board is invalid.")
            position = raw_board.get("positionIndex")
            sequence_number = raw_board.get("sequenceNumber")
            status = raw_board.get("status")
            if (
                not isinstance(position, int)
                or isinstance(position, bool)
                or not 0 <= position <= 8
                or not isinstance(sequence_number, int)
                or isinstance(sequence_number, bool)
                or sequence_number < 1
                or status not in {"ready", "deferred"}
            ):
                raise JobError("IMAGE_GEOMETRY_GUARD_REPORT_INVALID", "A report board is invalid.")
            key = (source_checksum, position)
            if key in seen:
                raise JobError(
                    "IMAGE_GEOMETRY_GUARD_REPORT_INVALID", "A report board occurs more than once."
                )
            seen.add(key)
            result.append(
                ImageGeometryGuardBoardContext(
                    source_checksum_sha256=source_checksum,
                    source_relative_path=source_path,
                    position_index=position,
                    sequence_number=sequence_number,
                    page_geometry=(
                        dict(raw_board["pageGeometry"])
                        if isinstance(raw_board.get("pageGeometry"), Mapping)
                        else None
                    ),
                    requires_decision=status == "deferred",
                )
            )
    return tuple(
        sorted(result, key=lambda item: (item.source_checksum_sha256, item.position_index))
    )


def _source_manifest_checksum(scope: ImageGeometryGuardScope) -> str:
    value = scope.job_input_payload.get("source_manifest_sha256")
    if value != scope.browser_manifest_checksum_sha256:
        raise JobConflictError(
            "IMAGE_GEOMETRY_GUARD_SOURCE_MANIFEST_DRIFT",
            "The guard job source manifest differs from browser staging.",
        )
    return cast(str, value)


def _page_manifest_checksum(scope: ImageGeometryGuardScope) -> str:
    descriptor = scope.job_input_payload.get("page_geometry_manifest")
    value = descriptor.get("checksumSha256") if isinstance(descriptor, Mapping) else None
    if not isinstance(value, str):
        raise JobError(
            "IMAGE_GEOMETRY_GUARD_PAGE_MANIFEST_REQUIRED",
            "The guard job has no pinned page geometry manifest.",
        )
    return value


def _managed_path(root: Path, relative: str, namespace: str) -> Path:
    pure = PurePosixPath(relative)
    path = root.joinpath(*pure.parts).resolve()
    allowed = (root / "data" / namespace).resolve()
    if not path.is_relative_to(allowed) or not path.is_file():
        raise JobError(
            "IMAGE_GEOMETRY_GUARD_REPORT_UNAVAILABLE",
            "The guard report path is outside its managed namespace.",
        )
    return path


def _write_immutable(root: Path, relative: str, payload: object) -> None:
    path = root.joinpath(*PurePosixPath(relative).parts).resolve()
    allowed = (root / "data" / "image-geometry-guard-resolutions").resolve()
    if not path.is_relative_to(allowed):
        raise JobError(
            "IMAGE_GEOMETRY_GUARD_MANIFEST_PATH_INVALID",
            "The resolution manifest path is outside its managed namespace.",
        )
    content = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode(
        "ascii"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise JobConflictError(
                "IMAGE_GEOMETRY_GUARD_MANIFEST_COLLISION",
                "The content-addressed manifest path contains different bytes.",
            )
        return
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-resolution-")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise JobConflictError(
                    "IMAGE_GEOMETRY_GUARD_MANIFEST_COLLISION",
                    "The content-addressed manifest path contains different bytes.",
                ) from None
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "ImageGeometryGuardDecisionCommand",
    "ImageGeometryGuardQueue",
    "ImageGeometryGuardReportReconstructionInput",
    "ImageImportGeometryGuardService",
]
