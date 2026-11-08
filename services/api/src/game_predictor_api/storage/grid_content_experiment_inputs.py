"""Read trusted lineage providers and existing registry closure; never infer non-use."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.domain.grid_content_experiment_inputs import (
    build_inputs,
    training_eligibility,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.source_recording_groups import RecordingError

from .game_storage_routing import game_storage_scope
from .grid_correction_split import contexts
from .grid_training_cohort_repository import CohortDeadline, SqlAlchemyGridTrainingCohortRepository
from .source_recording_groups import SqlAlchemySourceRecordingRepository
from .source_recording_providers import TrustedRecordingProviders


def read_experiment_inputs(
    factory: sessionmaker[Session],
    root: Path,
    base: dict[str, Any],
    base_sha256: str,
    splits: Sequence[tuple[str, dict[str, Any]]],
    provider_index_sha256: str | None,
) -> dict[str, Any]:
    if provider_index_sha256 is None:
        raise GridCohortError(
            "CONTENT_BANK_ANCESTRY_UNRESOLVED", "Install and pin complete ancestry providers first."
        )
    proofs = []
    try:
        for game_id, split in splits:
            game = UUID(game_id)
            with game_storage_scope(game), factory() as session:
                repo = SqlAlchemyGridTrainingCohortRepository(session, root)
                repo.bind(game)
                CohortDeadline().check(session)
                lineage = SqlAlchemySourceRecordingRepository(session).lineage(
                    game, UUID(base["versionId"]), UUID(base["familyId"])
                )
                providers = TrustedRecordingProviders(root, provider_index_sha256).read(lineage)
                source_contexts = contexts(
                    repo, game, [p["sourceId"] for p in split["sources"]], purpose_aware=True
                )
                proofs.append(
                    training_eligibility(
                        game=game_id,
                        base=base,
                        base_sha256=base_sha256,
                        lineage=lineage,
                        providers=providers,
                        split=split,
                        contexts=source_contexts,
                    )
                )
    except RecordingError as error:
        raise GridCohortError("CONTENT_BANK_ANCESTRY_UNRESOLVED", str(error)) from error
    return build_inputs(proofs, splits)
