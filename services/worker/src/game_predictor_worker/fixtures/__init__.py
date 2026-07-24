"""Public API for deterministic build-time fixture generation."""

from game_predictor_worker.fixtures.contracts import (
    DuplicateFixture,
    FixtureValidationReport,
    GameFixtureValidation,
    GeneratedGameFixture,
    GeneratedLayout,
    M1Fixture,
    TargetGoldenFixture,
    UniquePrefixFixture,
)
from game_predictor_worker.fixtures.errors import (
    FixtureErrorCode,
    FixtureValidationError,
)
from game_predictor_worker.fixtures.generator import (
    M1_ALGORITHM_VERSION,
    M1_DATASET_VERSION,
    M1_DUPLICATE_GROUP_COUNT,
    M1_FIXTURE_VERSION,
    M1_LAYOUT_COUNT,
    M1_RULES_VERSION,
    generate_m1_fixture,
)
from game_predictor_worker.fixtures.validation import (
    fixture_fingerprint,
    validate_m1_fixture,
)

__all__ = [
    "DuplicateFixture",
    "FixtureErrorCode",
    "FixtureValidationError",
    "FixtureValidationReport",
    "GameFixtureValidation",
    "GeneratedGameFixture",
    "GeneratedLayout",
    "M1Fixture",
    "M1_ALGORITHM_VERSION",
    "M1_DATASET_VERSION",
    "M1_DUPLICATE_GROUP_COUNT",
    "M1_FIXTURE_VERSION",
    "M1_LAYOUT_COUNT",
    "M1_RULES_VERSION",
    "TargetGoldenFixture",
    "UniquePrefixFixture",
    "fixture_fingerprint",
    "generate_m1_fixture",
    "validate_m1_fixture",
]
