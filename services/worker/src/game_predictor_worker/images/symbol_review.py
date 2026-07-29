"""Local single-owner bootstrap review state for M6 symbol labels."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from PIL import Image, UnidentifiedImageError

from .rectification import BOARD_HEIGHT, BOARD_WIDTH, CELL_HEIGHT, CELL_WIDTH
from .symbol_dataset import (
    CALIBRATED_INVENTORY_VERSION,
    LABEL_SOURCE_VERSION,
    REVIEWED_INVENTORY_VERSION,
    ReviewedLabel,
    ReviewedLabelSource,
    ReviewedSymbol,
    SymbolCropSample,
    SymbolDatasetError,
    load_reviewed_label_source,
    load_symbol_crop_inventory,
)

BOOTSTRAP_GAME_ID_VERSION = "bootstrap-game-id-v1"
BOOTSTRAP_SYMBOL_ID_VERSION = "bootstrap-symbol-id-v1"
_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


class SymbolReviewError(ValueError):
    """Stable error returned by the local bootstrap review tool."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    decision: Literal["accepted", "rejected"]
    symbol_id: str | None = None
    symbol_code: str | None = None

    def to_label(self, sample_id: str) -> dict[str, object]:
        value: dict[str, object] = {
            "decision": self.decision,
            "sampleId": sample_id,
        }
        if self.decision == "accepted":
            value["symbolCode"] = self.symbol_code
            value["symbolId"] = self.symbol_id
        return value


def _stable_id(version: str, *parts: str) -> str:
    logical = "\0".join((version, *parts))
    return f"bootstrap-{hashlib.sha256(logical.encode()).hexdigest()}"


def _validate_code(value: str, label: str) -> str:
    normalized = value.strip()
    if not _CODE_PATTERN.fullmatch(normalized):
        raise SymbolReviewError(
            "SYMBOL_REVIEW_CODE_INVALID",
            f"{label} must match {_CODE_PATTERN.pattern}.",
        )
    return normalized


def _validate_reviewer(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 100:
        raise SymbolReviewError(
            "SYMBOL_REVIEW_REVIEWER_INVALID",
            "Reviewer must contain 1-100 characters.",
        )
    return normalized


class BootstrapSymbolReview:
    """Thread-safe, resumable state backed by reviewed-cell-labels-v1."""

    def __init__(
        self,
        inventory_path: Path,
        crop_root: Path,
        label_output_path: Path,
        *,
        require_calibrated: bool = False,
    ) -> None:
        try:
            _, inventory = load_symbol_crop_inventory(inventory_path)
        except SymbolDatasetError as error:
            raise SymbolReviewError(error.code, str(error)) from error
        try:
            resolved_crop_root = crop_root.resolve(strict=True)
        except OSError as error:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_CROP_ROOT_NOT_FOUND",
                "Crop root does not exist.",
            ) from error
        if not resolved_crop_root.is_dir():
            raise SymbolReviewError(
                "SYMBOL_REVIEW_CROP_ROOT_NOT_DIRECTORY",
                "Crop root must be a directory.",
            )
        output = label_output_path.resolve()
        if output == resolved_crop_root or output.is_relative_to(resolved_crop_root):
            raise SymbolReviewError(
                "SYMBOL_REVIEW_OUTPUT_IN_CROP_ROOT",
                "Review labels must be stored outside immutable crop artifacts.",
            )
        self.inventory_path = inventory_path.resolve(strict=True)
        self.inventory = inventory
        if require_calibrated and inventory.inventory_version not in {
            CALIBRATED_INVENTORY_VERSION,
            REVIEWED_INVENTORY_VERSION,
        }:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_CALIBRATED_INVENTORY_REQUIRED",
                "Whole-layout review requires an accepted versioned inventory.",
            )
        self.crop_root = resolved_crop_root
        self.label_output_path = output
        self._samples_by_id = {sample.sample_id: sample for sample in inventory.samples}
        self._samples_by_checksum: dict[str, tuple[str, ...]] = {}
        checksum_groups: dict[str, list[str]] = defaultdict(list)
        for sample in inventory.samples:
            checksum_groups[sample.crop_checksum_sha256].append(sample.sample_id)
        self._samples_by_checksum = {
            checksum: tuple(sample_ids) for checksum, sample_ids in checksum_groups.items()
        }
        board_groups: dict[str, list[SymbolCropSample]] = defaultdict(list)
        for sample in inventory.samples:
            if sample.board_id is not None:
                board_groups[sample.board_id].append(sample)
        self._boards = tuple(
            tuple(sorted(samples, key=lambda sample: sample.cell_index))
            for _, samples in sorted(
                board_groups.items(),
                key=lambda item: item[1][0].sequence_number,
            )
        )
        if require_calibrated and (
            len(self._boards) * 15 != len(inventory.samples)
            or any(len(board) != 15 for board in self._boards)
        ):
            raise SymbolReviewError(
                "SYMBOL_REVIEW_BOARD_GROUP_INVALID",
                "Accepted inventory must contain complete 5 x 3 boards.",
            )
        self._lock = threading.RLock()
        self._game_id: str | None = None
        self._game_code: str | None = None
        self._reviewed_by: str | None = None
        self._review_revision = 0
        self._symbols: dict[str, ReviewedSymbol] = {}
        self._decisions: dict[str, ReviewDecision] = {}
        if self.label_output_path.exists():
            self._resume()

    @property
    def configured(self) -> bool:
        return self._game_id is not None

    def _resume(self) -> None:
        try:
            _, source = load_reviewed_label_source(self.label_output_path)
        except SymbolDatasetError as error:
            raise SymbolReviewError(error.code, str(error)) from error
        if source.corpus_id != self.inventory.corpus_id:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_LABEL_SOURCE_DRIFT",
                "Existing labels refer to another corpus.",
            )
        unknown = {label.sample_id for label in source.labels} - set(self._samples_by_id)
        if unknown:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_SAMPLE_UNKNOWN",
                "Existing labels reference a sample outside the inventory.",
            )
        self._game_id = source.game_id
        self._game_code = source.game_code
        self._reviewed_by = source.reviewed_by
        self._review_revision = source.review_revision
        self._symbols = {symbol.symbol_code: symbol for symbol in source.symbols}
        self._decisions = {
            label.sample_id: ReviewDecision(
                decision=label.decision,
                symbol_id=label.symbol_id,
                symbol_code=label.symbol_code,
            )
            for label in source.labels
        }

    def configure(
        self,
        *,
        game_code: str,
        reviewed_by: str,
        symbol_codes: Iterable[str],
    ) -> bool:
        normalized_game = _validate_code(game_code, "gameCode")
        normalized_reviewer = _validate_reviewer(reviewed_by)
        normalized_symbols = sorted({_validate_code(code, "symbolCode") for code in symbol_codes})
        if not normalized_symbols:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_SYMBOLS_EMPTY",
                "At least one symbol code is required.",
            )
        with self._lock:
            used_symbols = {
                decision.symbol_code
                for decision in self._decisions.values()
                if decision.decision == "accepted"
            }
            if (
                self._game_code is not None
                and self._game_code != normalized_game
                and self._decisions
            ):
                raise SymbolReviewError(
                    "SYMBOL_REVIEW_GAME_IMMUTABLE",
                    "Game code cannot change after the first decision.",
                )
            if not used_symbols.issubset(set(normalized_symbols)):
                raise SymbolReviewError(
                    "SYMBOL_REVIEW_SYMBOL_IN_USE",
                    "A symbol used by an accepted decision cannot be removed.",
                )
            game_id = _stable_id(BOOTSTRAP_GAME_ID_VERSION, normalized_game)
            symbols = {
                code: ReviewedSymbol(
                    symbol_id=_stable_id(
                        BOOTSTRAP_SYMBOL_ID_VERSION,
                        normalized_game,
                        code,
                    ),
                    symbol_code=code,
                )
                for code in normalized_symbols
            }
            changed = (
                self._game_id != game_id
                or self._game_code != normalized_game
                or self._reviewed_by != normalized_reviewer
                or self._symbols != symbols
            )
            if not changed:
                return False
            self._game_id = game_id
            self._game_code = normalized_game
            self._reviewed_by = normalized_reviewer
            self._symbols = symbols
            self._review_revision += 1
            self._save()
            return True

    def decide(
        self,
        *,
        sample_id: str,
        decision: Literal["accepted", "rejected"],
        symbol_code: str | None = None,
        apply_to_identical: bool = False,
    ) -> int:
        with self._lock:
            if not self.configured:
                raise SymbolReviewError(
                    "SYMBOL_REVIEW_NOT_CONFIGURED",
                    "Configure the game and symbols before reviewing samples.",
                )
            sample = self._sample(sample_id)
            if decision == "accepted":
                if symbol_code is None:
                    raise SymbolReviewError(
                        "SYMBOL_REVIEW_SYMBOL_REQUIRED",
                        "Accepted decision requires a symbol code.",
                    )
                normalized_symbol = _validate_code(symbol_code, "symbolCode")
                symbol = self._symbols.get(normalized_symbol)
                if symbol is None:
                    raise SymbolReviewError(
                        "SYMBOL_REVIEW_SYMBOL_UNKNOWN",
                        "Accepted decision references an unknown symbol.",
                    )
                reviewed = ReviewDecision(
                    decision="accepted",
                    symbol_id=symbol.symbol_id,
                    symbol_code=symbol.symbol_code,
                )
            elif decision == "rejected":
                if symbol_code is not None:
                    raise SymbolReviewError(
                        "SYMBOL_REVIEW_REJECTED_HAS_SYMBOL",
                        "Rejected decision cannot carry a symbol.",
                    )
                reviewed = ReviewDecision(decision="rejected")
            else:
                raise SymbolReviewError(
                    "SYMBOL_REVIEW_DECISION_INVALID",
                    "Decision must be accepted or rejected.",
                )
            target_ids = (
                self._samples_by_checksum[sample.crop_checksum_sha256]
                if apply_to_identical
                else (sample.sample_id,)
            )
            if not apply_to_identical and reviewed.decision == "accepted":
                for duplicate_id in self._samples_by_checksum[sample.crop_checksum_sha256]:
                    existing = self._decisions.get(duplicate_id)
                    if (
                        existing is not None
                        and existing.decision == "accepted"
                        and existing.symbol_code != reviewed.symbol_code
                    ):
                        raise SymbolReviewError(
                            "SYMBOL_REVIEW_IDENTICAL_CONFLICT",
                            "Identical crop bytes already use another symbol.",
                        )
            changed = 0
            for target_id in target_ids:
                if self._decisions.get(target_id) != reviewed:
                    self._decisions[target_id] = reviewed
                    changed += 1
            if changed:
                self._review_revision += 1
                self._save()
            return changed

    def decide_board(
        self,
        *,
        board_id: str,
        decisions: Iterable[dict[str, object]],
        apply_to_identical: bool = False,
    ) -> int:
        """Atomically apply a set of explicit cell decisions from one board."""

        with self._lock:
            if not self.configured:
                raise SymbolReviewError(
                    "SYMBOL_REVIEW_NOT_CONFIGURED",
                    "Configure the game and symbols before reviewing samples.",
                )
            board = self._board(board_id)
            board_sample_ids = {sample.sample_id for sample in board}
            requested = list(decisions)
            if not requested or len(requested) > 15:
                raise SymbolReviewError(
                    "SYMBOL_REVIEW_BOARD_DECISIONS_INVALID",
                    "A board update must contain between 1 and 15 cell decisions.",
                )
            candidate = dict(self._decisions)
            touched: set[str] = set()
            for index, raw in enumerate(requested):
                sample_id = raw.get("sampleId")
                decision = raw.get("decision")
                symbol_code = raw.get("symbolCode")
                if not isinstance(sample_id, str) or sample_id not in board_sample_ids:
                    raise SymbolReviewError(
                        "SYMBOL_REVIEW_BOARD_SAMPLE_INVALID",
                        f"Decision {index} does not belong to the selected board.",
                    )
                if sample_id in touched or decision not in {"accepted", "rejected", "clear"}:
                    raise SymbolReviewError(
                        "SYMBOL_REVIEW_BOARD_DECISIONS_INVALID",
                        "Board decisions must use unique samples and valid actions.",
                    )
                touched.add(sample_id)
                sample = self._sample(sample_id)
                target_ids = (
                    self._samples_by_checksum[sample.crop_checksum_sha256]
                    if apply_to_identical
                    else (sample_id,)
                )
                if decision == "clear":
                    if symbol_code is not None:
                        raise SymbolReviewError(
                            "SYMBOL_REVIEW_BOARD_DECISIONS_INVALID",
                            "A clear action cannot carry a symbol.",
                        )
                    for target_id in target_ids:
                        candidate.pop(target_id, None)
                    continue
                reviewed = self._validated_decision(
                    decision=decision,
                    symbol_code=symbol_code if isinstance(symbol_code, str) else None,
                )
                for target_id in target_ids:
                    candidate[target_id] = reviewed
            accepted_by_checksum: dict[str, str] = {}
            for sample_id, decision in candidate.items():
                if decision.decision != "accepted":
                    continue
                sample = self._sample(sample_id)
                previous = accepted_by_checksum.get(sample.crop_checksum_sha256)
                if previous is not None and previous != decision.symbol_code:
                    raise SymbolReviewError(
                        "SYMBOL_REVIEW_IDENTICAL_CONFLICT",
                        "Identical crop bytes cannot use different symbols.",
                    )
                assert decision.symbol_code is not None
                accepted_by_checksum[sample.crop_checksum_sha256] = decision.symbol_code
            changed = sum(
                self._decisions.get(sample_id) != decision
                for sample_id, decision in candidate.items()
            ) + sum(sample_id not in candidate for sample_id in self._decisions)
            if changed:
                self._decisions = candidate
                self._review_revision += 1
                self._save()
            return changed

    def _validated_decision(
        self,
        *,
        decision: object,
        symbol_code: str | None,
    ) -> ReviewDecision:
        if decision == "accepted":
            if symbol_code is None:
                raise SymbolReviewError(
                    "SYMBOL_REVIEW_SYMBOL_REQUIRED",
                    "Accepted decision requires a symbol code.",
                )
            symbol = self._symbols.get(_validate_code(symbol_code, "symbolCode"))
            if symbol is None:
                raise SymbolReviewError(
                    "SYMBOL_REVIEW_SYMBOL_UNKNOWN",
                    "Accepted decision references an unknown symbol.",
                )
            return ReviewDecision(
                decision="accepted",
                symbol_id=symbol.symbol_id,
                symbol_code=symbol.symbol_code,
            )
        if decision == "rejected":
            if symbol_code is not None:
                raise SymbolReviewError(
                    "SYMBOL_REVIEW_REJECTED_HAS_SYMBOL",
                    "Rejected decision cannot carry a symbol.",
                )
            return ReviewDecision(decision="rejected")
        raise SymbolReviewError(
            "SYMBOL_REVIEW_DECISION_INVALID",
            "Decision must be accepted or rejected.",
        )

    def clear(
        self,
        *,
        sample_id: str,
        apply_to_identical: bool = False,
    ) -> int:
        with self._lock:
            sample = self._sample(sample_id)
            target_ids = (
                self._samples_by_checksum[sample.crop_checksum_sha256]
                if apply_to_identical
                else (sample.sample_id,)
            )
            changed = 0
            for target_id in target_ids:
                if target_id in self._decisions:
                    del self._decisions[target_id]
                    changed += 1
            if changed:
                self._review_revision += 1
                self._save()
            return changed

    def state(
        self,
        *,
        offset: int = 0,
        limit: int = 24,
        status: Literal["all", "pending", "accepted", "rejected"] = "pending",
    ) -> dict[str, object]:
        if offset < 0 or not 1 <= limit <= 100:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_PAGE_INVALID",
                "offset must be non-negative and limit must be between 1 and 100.",
            )
        if status not in {"all", "pending", "accepted", "rejected"}:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_FILTER_INVALID",
                "Unknown review status.",
            )
        with self._lock:
            filtered = [
                sample
                for sample in self.inventory.samples
                if status == "all" or self._sample_status(sample.sample_id) == status
            ]
            page = filtered[offset : offset + limit]
            return {
                "configuration": {
                    "configured": self.configured,
                    "gameCode": self._game_code,
                    "gameId": self._game_id,
                    "reviewRevision": self._review_revision,
                    "reviewedBy": self._reviewed_by,
                    "symbols": [
                        {
                            "shortcut": index + 1 if index < 9 else None,
                            "symbolCode": symbol.symbol_code,
                            "symbolId": symbol.symbol_id,
                        }
                        for index, symbol in enumerate(self._symbols.values())
                    ],
                },
                "filter": status,
                "limit": limit,
                "offset": offset,
                "pageCount": len(page),
                "progress": self.progress(),
                "samples": [self._sample_payload(sample) for sample in page],
                "totalFiltered": len(filtered),
            }

    def board_state(
        self,
        *,
        offset: int = 0,
        status: Literal["all", "pending", "accepted", "rejected"] = "pending",
        sequence_number: int | None = None,
    ) -> dict[str, object]:
        if offset < 0 or status not in {"all", "pending", "accepted", "rejected"}:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_PAGE_INVALID",
                "Board offset and status filter are invalid.",
            )
        with self._lock:
            filtered = [
                board
                for board in self._boards
                if (status == "all" or self._board_status(board) == status)
                and (
                    sequence_number is None
                    or board[0].sequence_number == sequence_number
                )
            ]
            board = filtered[offset] if offset < len(filtered) else None
            return {
                "board": self._board_payload(board) if board else None,
                "configuration": self.state(offset=0, limit=1)["configuration"],
                "filter": status,
                "offset": offset,
                "progress": self.board_progress(),
                "totalFiltered": len(filtered),
            }

    def board_progress(self) -> dict[str, object]:
        board_counts = Counter(self._board_status(board) for board in self._boards)
        cell_progress = self.progress()
        return {
            "boards": {
                "accepted": board_counts["accepted"],
                "pending": board_counts["pending"],
                "rejected": board_counts["rejected"],
                "total": len(self._boards),
            },
            "cells": cell_progress,
        }

    def resolve_board(self, board_id: str) -> tuple[Path, str]:
        board = self._board(board_id)
        sample = board[0]
        if sample.board_relative_path is None or sample.board_checksum_sha256 is None:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_BOARD_UNAVAILABLE",
                "Board artifact is not present in this inventory.",
            )
        path = self._resolve_artifact(sample.board_relative_path, "board")
        try:
            content = path.read_bytes()
            with Image.open(path) as image:
                image.load()
                valid = image.mode == "RGB" and image.size == (BOARD_WIDTH, BOARD_HEIGHT)
        except (OSError, UnidentifiedImageError) as error:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_BOARD_UNREADABLE",
                "Board is not a readable image.",
            ) from error
        if hashlib.sha256(content).hexdigest() != sample.board_checksum_sha256 or not valid:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_BOARD_DRIFT",
                "Board checksum or dimensions differ from the inventory.",
            )
        return path, sample.board_checksum_sha256

    def progress(self) -> dict[str, object]:
        counts = Counter(self._sample_status(sample.sample_id) for sample in self.inventory.samples)
        per_symbol = Counter(
            decision.symbol_code
            for decision in self._decisions.values()
            if decision.decision == "accepted"
        )
        return {
            "accepted": counts["accepted"],
            "pending": counts["pending"],
            "perSymbol": [
                {"sampleCount": per_symbol[code], "symbolCode": code} for code in self._symbols
            ],
            "rejected": counts["rejected"],
            "total": len(self.inventory.samples),
        }

    def resolve_crop(self, sample_id: str) -> tuple[Path, str]:
        sample = self._sample(sample_id)
        relative = PurePosixPath(sample.crop_relative_path)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise SymbolReviewError(
                "SYMBOL_REVIEW_CROP_PATH_UNSAFE",
                "Crop path is not a safe relative POSIX path.",
            )
        try:
            path = (self.crop_root / Path(*relative.parts)).resolve(strict=True)
        except OSError as error:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_CROP_UNREADABLE",
                "Crop cannot be resolved.",
            ) from error
        if not path.is_relative_to(self.crop_root):
            raise SymbolReviewError(
                "SYMBOL_REVIEW_CROP_PATH_UNSAFE",
                "Crop path escapes the crop root.",
            )
        try:
            content = path.read_bytes()
            with Image.open(path) as image:
                image.load()
                valid_image = image.mode == "RGB" and image.size == (
                    CELL_WIDTH,
                    CELL_HEIGHT,
                )
        except (OSError, UnidentifiedImageError) as error:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_CROP_UNREADABLE",
                "Crop is not a readable image.",
            ) from error
        if hashlib.sha256(content).hexdigest() != sample.crop_checksum_sha256 or not valid_image:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_CROP_DRIFT",
                "Crop checksum or dimensions differ from the inventory.",
            )
        return path, sample.crop_checksum_sha256

    def _resolve_artifact(self, relative_path: str, label: str) -> Path:
        relative = PurePosixPath(relative_path)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise SymbolReviewError(
                "SYMBOL_REVIEW_CROP_PATH_UNSAFE",
                f"{label} path is not a safe relative POSIX path.",
            )
        try:
            path = (self.crop_root / Path(*relative.parts)).resolve(strict=True)
        except OSError as error:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_CROP_UNREADABLE",
                f"{label} cannot be resolved.",
            ) from error
        if not path.is_relative_to(self.crop_root):
            raise SymbolReviewError(
                "SYMBOL_REVIEW_CROP_PATH_UNSAFE",
                f"{label} path escapes the crop root.",
            )
        return path

    def _sample(self, sample_id: str) -> SymbolCropSample:
        sample = self._samples_by_id.get(sample_id)
        if sample is None:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_SAMPLE_UNKNOWN",
                "Unknown sampleId.",
            )
        return sample

    def _board(self, board_id: str) -> tuple[SymbolCropSample, ...]:
        for board in self._boards:
            if board[0].board_id == board_id:
                return board
        raise SymbolReviewError(
            "SYMBOL_REVIEW_BOARD_UNKNOWN",
            "Unknown boardId.",
        )

    def _board_status(
        self,
        board: tuple[SymbolCropSample, ...],
    ) -> Literal["pending", "accepted", "rejected"]:
        decisions = [self._decisions.get(sample.sample_id) for sample in board]
        if any(decision is None for decision in decisions):
            return "pending"
        if all(decision is not None and decision.decision == "accepted" for decision in decisions):
            return "accepted"
        return "rejected"

    def _board_payload(
        self,
        board: tuple[SymbolCropSample, ...] | None,
    ) -> dict[str, object] | None:
        if board is None:
            return None
        first = board[0]
        return {
            "boardChecksumSha256": first.board_checksum_sha256,
            "boardId": first.board_id,
            "boardIndex": first.board_index,
            "boardUrl": f"/api/boards/{first.board_id}",
            "calibrationProfileId": first.calibration_profile_id,
            "calibrationProfileVersion": first.calibration_profile_version,
            "cells": [self._sample_payload(sample) for sample in board],
            "sequenceNumber": first.sequence_number,
            "sourceGroup": first.source_group,
            "status": self._board_status(board),
        }

    def _sample_status(
        self,
        sample_id: str,
    ) -> Literal["pending", "accepted", "rejected"]:
        decision = self._decisions.get(sample_id)
        return "pending" if decision is None else decision.decision

    def _sample_payload(self, sample: SymbolCropSample) -> dict[str, object]:
        decision = self._decisions.get(sample.sample_id)
        value = sample.to_dict()
        value.update(
            {
                "cropUrl": f"/api/crops/{sample.sample_id}",
                "decision": decision.decision if decision else "pending",
                "symbolCode": decision.symbol_code if decision else None,
            }
        )
        return value

    def _source(self) -> ReviewedLabelSource:
        if (
            self._game_id is None
            or self._game_code is None
            or self._reviewed_by is None
            or not self._symbols
        ):
            raise SymbolReviewError(
                "SYMBOL_REVIEW_NOT_CONFIGURED",
                "Review source is not configured.",
            )
        labels = tuple(
            ReviewedLabel(
                sample_id=sample.sample_id,
                decision=self._decisions[sample.sample_id].decision,
                symbol_id=self._decisions[sample.sample_id].symbol_id,
                symbol_code=self._decisions[sample.sample_id].symbol_code,
            )
            for sample in self.inventory.samples
            if sample.sample_id in self._decisions
        )
        return ReviewedLabelSource(
            corpus_id=self.inventory.corpus_id,
            game_id=self._game_id,
            game_code=self._game_code,
            review_revision=self._review_revision,
            reviewed_by=self._reviewed_by,
            symbols=tuple(self._symbols.values()),
            labels=labels,
        )

    def _save(self) -> None:
        source = self._source()
        content = _label_source_bytes(source)
        self.label_output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.label_output_path.with_name(f".{self.label_output_path.name}.tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(self.label_output_path)
        except OSError as error:
            raise SymbolReviewError(
                "SYMBOL_REVIEW_WRITE_FAILED",
                "Reviewed labels cannot be written atomically.",
            ) from error
        finally:
            if temporary.exists():
                temporary.unlink()


def _label_source_bytes(source: ReviewedLabelSource) -> bytes:
    value = {
        "corpusId": source.corpus_id,
        "gameCode": source.game_code,
        "gameId": source.game_id,
        "labelSourceVersion": LABEL_SOURCE_VERSION,
        "labels": [
            ReviewDecision(
                decision=label.decision,
                symbol_id=label.symbol_id,
                symbol_code=label.symbol_code,
            ).to_label(label.sample_id)
            for label in source.labels
        ],
        "reviewRevision": source.review_revision,
        "reviewedBy": source.reviewed_by,
        "schemaVersion": 1,
        "symbols": [
            {
                "symbolCode": symbol.symbol_code,
                "symbolId": symbol.symbol_id,
            }
            for symbol in source.symbols
        ],
    }
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
