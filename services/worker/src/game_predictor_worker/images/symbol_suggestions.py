"""Frozen, auditable symbol suggestions for the manual M6 review tool."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import torch
from torch import Tensor
from torch.nn import functional

from .symbol_classifier import (
    CLASSIFIER_VERSION,
    ClassifierSample,
    PreparedTrainingData,
    SmallSymbolCnn,
    SymbolClassifierError,
    load_classifier_artifact,
    load_image_tensor,
    prepare_training_data,
)
from .symbol_dataset import (
    SymbolCropSample,
    SymbolDatasetError,
    load_reviewed_label_source,
    load_symbol_crop_inventory,
)

SUGGESTION_VERSION = "bootstrap-symbol-suggestions-v1"
DEFAULT_MINIMUM_SIMILARITY = 0.9975
MAX_SUGGESTIONS = 3


class SymbolSuggestionError(ValueError):
    """Stable suggestion input or inference failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ReferenceEmbedding:
    sample_id: str
    source_image_checksum: str
    symbol_code: str
    embedding: Tensor


@dataclass(frozen=True, slots=True)
class RankedSuggestion:
    symbol_code: str
    similarity: float
    classifier_confidence: float
    reference_sample_id: str

    def to_dict(self, rank: int) -> dict[str, object]:
        return {
            "classifierConfidence": round(self.classifier_confidence, 6),
            "cosineDistance": round(1.0 - self.similarity, 6),
            "cosineSimilarity": round(self.similarity, 6),
            "rank": rank,
            "referenceSampleId": self.reference_sample_id,
            "symbolCode": self.symbol_code,
        }


def _normalized_embedding(model: SmallSymbolCnn, tensor: Tensor) -> Tensor:
    with torch.inference_mode():
        encoded = model.encode(tensor.unsqueeze(0))
    return functional.normalize(encoded, dim=1).squeeze(0).cpu()


def rank_symbol_suggestions(
    *,
    target_embedding: Tensor,
    classifier_probabilities: Tensor,
    class_codes: Sequence[str],
    references: Sequence[ReferenceEmbedding],
    target_sample_id: str,
    target_source_image_checksum: str,
    minimum_similarity: float = DEFAULT_MINIMUM_SIMILARITY,
) -> tuple[RankedSuggestion, ...]:
    """Rank one nearest accepted reference per class with stable tie-breaking."""

    if not 0.0 <= minimum_similarity <= 1.0:
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_THRESHOLD_INVALID",
            "Minimum similarity must be between zero and one.",
        )
    confidence_by_code = {
        code: float(classifier_probabilities[index].item())
        for index, code in enumerate(class_codes)
    }
    best_by_symbol: dict[str, RankedSuggestion] = {}
    normalized_target = functional.normalize(target_embedding.unsqueeze(0), dim=1).squeeze(0)
    for reference in references:
        if (
            reference.sample_id == target_sample_id
            or reference.source_image_checksum == target_source_image_checksum
        ):
            continue
        similarity = float(torch.dot(normalized_target, reference.embedding).item())
        candidate = RankedSuggestion(
            symbol_code=reference.symbol_code,
            similarity=similarity,
            classifier_confidence=confidence_by_code.get(reference.symbol_code, 0.0),
            reference_sample_id=reference.sample_id,
        )
        current = best_by_symbol.get(reference.symbol_code)
        if current is None or (-candidate.similarity, candidate.reference_sample_id) < (
            -current.similarity,
            current.reference_sample_id,
        ):
            best_by_symbol[reference.symbol_code] = candidate
    ranked = sorted(
        best_by_symbol.values(),
        key=lambda value: (-value.similarity, value.symbol_code, value.reference_sample_id),
    )
    if not ranked or ranked[0].similarity < minimum_similarity:
        return ()
    return tuple(ranked[:MAX_SUGGESTIONS])


def _verified_crop_path(root: Path, sample: SymbolCropSample) -> Path:
    relative = PurePosixPath(sample.crop_relative_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_CROP_PATH_UNSAFE",
            "Suggestion crop path is unsafe.",
        )
    root_resolved = root.resolve(strict=True)
    try:
        path = root_resolved.joinpath(*relative.parts).resolve(strict=True)
    except OSError as error:
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_CROP_MISSING",
            "Suggestion crop cannot be resolved.",
        ) from error
    if not path.is_relative_to(root_resolved):
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_CROP_PATH_UNSAFE",
            "Suggestion crop escapes its artifact root.",
        )
    try:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_CROP_MISSING",
            "Suggestion crop cannot be read.",
        ) from error
    if checksum != sample.crop_checksum_sha256:
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_CROP_DRIFT",
            "Suggestion crop checksum differs from the approved inventory.",
        )
    return path


class FrozenSymbolSuggestionService:
    """Read-only inference over an immutable training-reference index."""

    def __init__(
        self,
        *,
        model: SmallSymbolCnn,
        class_codes: tuple[str, ...],
        input_size: int,
        references: tuple[ReferenceEmbedding, ...],
        crop_root: Path,
        previous_labels_by_observation: Mapping[str, tuple[str, str]],
        minimum_similarity: float = DEFAULT_MINIMUM_SIMILARITY,
    ) -> None:
        self._model = model
        self._class_codes = class_codes
        self._input_size = input_size
        self._references = references
        self._crop_root = crop_root.resolve(strict=True)
        self._previous_labels = dict(previous_labels_by_observation)
        self._minimum_similarity = minimum_similarity
        self._cache: dict[str, dict[str, object]] = {}

    @property
    def reference_count(self) -> int:
        return len(self._references)

    def for_sample(self, sample: SymbolCropSample) -> dict[str, object]:
        cached = self._cache.get(sample.sample_id)
        if cached is not None:
            return cached
        path = _verified_crop_path(self._crop_root, sample)
        tensor = load_image_tensor(path, self._input_size)
        with torch.inference_mode():
            logits = self._model(tensor.unsqueeze(0)).squeeze(0)
            probabilities = torch.softmax(logits, dim=0).cpu()
        embedding = _normalized_embedding(self._model, tensor)
        ranked = rank_symbol_suggestions(
            target_embedding=embedding,
            classifier_probabilities=probabilities,
            class_codes=self._class_codes,
            references=self._references,
            target_sample_id=sample.sample_id,
            target_source_image_checksum=sample.source_image_checksum_sha256,
            minimum_similarity=self._minimum_similarity,
        )
        previous = (
            self._previous_labels.get(sample.observation_id)
            if sample.observation_id is not None
            else None
        )
        value: dict[str, object] = {
            "suggestionEvidence": {
                "minimumCosineSimilarity": self._minimum_similarity,
                "referenceCount": len(self._references),
                "referencePartition": "train",
                "sameSourceExcluded": True,
                "version": SUGGESTION_VERSION,
            },
            "suggestionStatus": "suggested" if ranked else "no_suggestion",
            "suggestions": [
                suggestion.to_dict(rank) for rank, suggestion in enumerate(ranked, start=1)
            ],
        }
        if previous is not None:
            symbol_code, previous_sample_id = previous
            value["previousGeometryLabel"] = {
                "previousSampleId": previous_sample_id,
                "source": "previous_crop_version",
                "symbolCode": symbol_code,
            }
        self._cache[sample.sample_id] = value
        return value


def _reference_embeddings(
    model: SmallSymbolCnn,
    samples: Sequence[ClassifierSample],
    input_size: int,
) -> tuple[ReferenceEmbedding, ...]:
    references: list[ReferenceEmbedding] = []
    for sample in sorted(samples, key=lambda value: value.sample_id):
        tensor = load_image_tensor(sample.asset_path, input_size)
        references.append(
            ReferenceEmbedding(
                embedding=_normalized_embedding(model, tensor),
                sample_id=sample.sample_id,
                source_image_checksum=sample.source_image_checksum,
                symbol_code=sample.symbol_code,
            )
        )
    return tuple(references)


def validate_classifier_provenance(
    report_path: Path,
    artifact_path: Path,
    data: PreparedTrainingData,
) -> None:
    """Bind inference to the exact immutable TASK-0061 report and checkpoint."""

    try:
        report_value = json.loads(report_path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_CLASSIFIER_REPORT_INVALID",
            "The classifier report cannot be read.",
        ) from error
    if not isinstance(report_value, Mapping):
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_CLASSIFIER_REPORT_INVALID",
            "The classifier report must contain an object.",
        )
    artifact_value = report_value.get("artifact")
    if not isinstance(artifact_value, Mapping):
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_CLASSIFIER_REPORT_INVALID",
            "The classifier report artifact contract is missing.",
        )
    try:
        artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    except OSError as error:
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_CLASSIFIER_ARTIFACT_MISSING",
            "The classifier artifact cannot be read.",
        ) from error
    if (
        report_value.get("classifierVersion") != CLASSIFIER_VERSION
        or report_value.get("datasetSha256") != data.dataset_sha256
        or report_value.get("splitSha256") != data.split_sha256
        or artifact_value.get("sha256") != artifact_sha256
    ):
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_CLASSIFIER_PROVENANCE_DRIFT",
            "Classifier report, dataset, split or artifact checksum differs.",
        )


def load_previous_labels_by_observation(
    inventory_path: Path | None,
    labels_path: Path | None,
) -> dict[str, tuple[str, str]]:
    if inventory_path is None or labels_path is None:
        return {}
    try:
        _, inventory = load_symbol_crop_inventory(inventory_path)
        _, labels = load_reviewed_label_source(labels_path)
    except SymbolDatasetError as error:
        raise SymbolSuggestionError(error.code, str(error)) from error
    samples = {sample.sample_id: sample for sample in inventory.samples}
    result: dict[str, tuple[str, str]] = {}
    for label in labels.labels:
        sample = samples.get(label.sample_id)
        if (
            label.decision == "accepted"
            and label.symbol_code is not None
            and sample is not None
            and sample.observation_id is not None
        ):
            result[sample.observation_id] = (label.symbol_code, label.sample_id)
    return result


def build_frozen_suggestion_service(
    *,
    dataset_path: Path,
    split_path: Path,
    asset_root: Path,
    artifact_path: Path,
    classifier_report_path: Path,
    crop_root: Path,
    previous_inventory_path: Path | None = None,
    previous_labels_path: Path | None = None,
    minimum_similarity: float = DEFAULT_MINIMUM_SIMILARITY,
) -> tuple[FrozenSymbolSuggestionService, PreparedTrainingData]:
    """Validate immutable inputs and create the frozen train-only service."""

    try:
        data = prepare_training_data(dataset_path, split_path, asset_root)
        validate_classifier_provenance(
            classifier_report_path,
            artifact_path,
            data,
        )
        model, class_codes, input_size = load_classifier_artifact(artifact_path)
    except SymbolClassifierError as error:
        raise SymbolSuggestionError(error.code, str(error)) from error
    if class_codes != data.class_codes:
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_CLASS_DRIFT",
            "Classifier classes differ from the approved dataset.",
        )
    references = _reference_embeddings(model, data.train, input_size)
    if not references:
        raise SymbolSuggestionError(
            "SYMBOL_SUGGESTION_REFERENCES_EMPTY",
            "The immutable training reference index is empty.",
        )
    return (
        FrozenSymbolSuggestionService(
            model=model,
            class_codes=class_codes,
            input_size=input_size,
            references=references,
            crop_root=crop_root,
            previous_labels_by_observation=load_previous_labels_by_observation(
                previous_inventory_path,
                previous_labels_path,
            ),
            minimum_similarity=minimum_similarity,
        ),
        data,
    )


def evaluate_validation_suggestions(
    service_model: SmallSymbolCnn,
    data: PreparedTrainingData,
    input_size: int,
    *,
    minimum_similarity: float = DEFAULT_MINIMUM_SIMILARITY,
) -> dict[str, object]:
    """Evaluate source-disjoint validation targets against train references."""

    references = _reference_embeddings(service_model, data.train, input_size)
    suggested = 0
    top1_correct = 0
    top3_correct = 0
    rows: list[dict[str, object]] = []
    for sample in sorted(data.validation, key=lambda value: value.sample_id):
        tensor = load_image_tensor(sample.asset_path, input_size)
        with torch.inference_mode():
            probabilities = torch.softmax(
                service_model(tensor.unsqueeze(0)).squeeze(0), dim=0
            ).cpu()
        ranked = rank_symbol_suggestions(
            target_embedding=_normalized_embedding(service_model, tensor),
            classifier_probabilities=probabilities,
            class_codes=data.class_codes,
            references=references,
            target_sample_id=sample.sample_id,
            target_source_image_checksum=sample.source_image_checksum,
            minimum_similarity=minimum_similarity,
        )
        codes = [value.symbol_code for value in ranked]
        if ranked:
            suggested += 1
            top1_correct += int(codes[0] == sample.symbol_code)
            top3_correct += int(sample.symbol_code in codes)
        rows.append(
            {
                "expectedSymbolCode": sample.symbol_code,
                "sampleId": sample.sample_id,
                "status": "suggested" if ranked else "no_suggestion",
                "suggestedSymbolCodes": codes,
                "topClassifierConfidence": round(ranked[0].classifier_confidence, 6)
                if ranked
                else None,
                "topCosineSimilarity": round(ranked[0].similarity, 6) if ranked else None,
            }
        )
    count = len(data.validation)
    return {
        "coverage": round(suggested / count, 8) if count else 0.0,
        "noSuggestionCount": count - suggested,
        "referenceCount": len(references),
        "sameSourceLeakageCount": 0,
        "sampleCount": count,
        "suggestedCount": suggested,
        "top1AccuracyAtCoverage": round(top1_correct / suggested, 8) if suggested else 0.0,
        "top3AccuracyAtCoverage": round(top3_correct / suggested, 8) if suggested else 0.0,
        "targets": rows,
    }


def suggestion_report_json_bytes(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
