from __future__ import annotations

import pytest
import torch
from game_predictor_worker.images.symbol_classifier import (
    EvaluationMetrics,
    SymbolClassifierError,
)
from game_predictor_worker.images.symbol_model_benchmark import (
    SPATIAL_AUGMENTED_VARIANT,
    SPATIAL_VARIANT,
    ValidationCandidate,
    augment_training_tensor,
    build_benchmark_model,
    select_validation_candidate,
)


def _metrics(
    *,
    macro_recall: float,
    accuracy: float,
    loss: float,
) -> EvaluationMetrics:
    return EvaluationMetrics(
        loss=loss,
        accuracy=accuracy,
        macro_recall=macro_recall,
        confusion_matrix=((1, 0), (0, 1)),
        per_class=(
            {"symbolCode": "a", "support": 1},
            {"symbolCode": "b", "support": 1},
        ),
    )


@pytest.mark.parametrize("variant", [SPATIAL_VARIANT, SPATIAL_AUGMENTED_VARIANT])
def test_spatial_variants_keep_expected_output_contract(variant: str) -> None:
    model = build_benchmark_model(variant, 8)

    output = model(torch.zeros((2, 3, 64, 64), dtype=torch.float32))

    assert output.shape == (2, 8)
    assert torch.isfinite(output).all()


def test_train_augmentation_is_deterministic_per_sample_and_epoch() -> None:
    tensor = torch.linspace(-1.0, 1.0, 3 * 64 * 64).reshape(3, 64, 64)

    first = augment_training_tensor(
        tensor,
        "a" * 64,
        seed=61061,
        epoch=3,
    )
    repeated = augment_training_tensor(
        tensor,
        "a" * 64,
        seed=61061,
        epoch=3,
    )
    next_epoch = augment_training_tensor(
        tensor,
        "a" * 64,
        seed=61061,
        epoch=4,
    )

    assert torch.equal(first, repeated)
    assert not torch.equal(first, next_epoch)
    assert first.min() >= -1.0
    assert first.max() <= 1.0


def test_selection_uses_validation_macro_recall_before_accuracy() -> None:
    higher_accuracy = ValidationCandidate(
        "higher-accuracy",
        _metrics(macro_recall=0.80, accuracy=0.90, loss=0.3),
        10,
    )
    higher_macro_recall = ValidationCandidate(
        "higher-macro",
        _metrics(macro_recall=0.81, accuracy=0.85, loss=0.4),
        20,
    )

    selected = select_validation_candidate((higher_accuracy, higher_macro_recall))

    assert selected.candidate_id == "higher-macro"


def test_selection_rejects_duplicate_candidate_ids() -> None:
    candidate = ValidationCandidate(
        "duplicate",
        _metrics(macro_recall=0.8, accuracy=0.8, loss=0.5),
        10,
    )

    with pytest.raises(SymbolClassifierError) as error:
        select_validation_candidate((candidate, candidate))

    assert error.value.code == "SYMBOL_MODEL_BENCHMARK_CANDIDATE_DUPLICATE"
