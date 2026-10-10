"""Import immutable managed candidates without inventing training cohorts."""

from pathlib import Path
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.jobs import Job, JobConflictError
from game_predictor_api.domain.lab_symbol_candidate import (
    LabSymbolCandidate,
    load_lab_symbol_candidate,
)
from game_predictor_api.domain.symbol_model_iterations import SymbolModelIteration

LAB_IMPORT_KIND = "symbol_model_lab_import"


class LabSymbolCandidateImportRepository(Protocol):
    def require_game(self, game_id: UUID) -> None: ...
    def require_catalog(self, candidate: LabSymbolCandidate) -> None: ...
    def start(
        self, *, game_id: UUID, fingerprint: str, idempotency_key: UUID, artifact_root: Path
    ) -> tuple[SymbolModelIteration, Job, bool]: ...


class LabSymbolCandidateImportService:
    def __init__(self, repository: LabSymbolCandidateImportRepository, artifact_root: Path) -> None:
        self._repository = repository
        self._root = artifact_root.absolute()

    def inventory(self, game_id: UUID) -> tuple[LabSymbolCandidate, ...]:
        self._repository.require_game(game_id)
        directory = self._root / "models" / "lab-symbol-candidates"
        if not directory.exists():
            return ()
        candidates = []
        # Bound inventory independently of arbitrary filesystem contents.
        for path in sorted(directory.iterdir())[:200]:
            if not path.is_dir() or len(path.name) != 64:
                continue
            try:
                candidate = self._load(game_id, path.name)
            except JobConflictError:
                continue
            candidates.append(candidate)
        return tuple(candidates)

    def preview(self, game_id: UUID, fingerprint: str) -> LabSymbolCandidate:
        self._repository.require_game(game_id)
        candidate = self._load(game_id, fingerprint)
        self._repository.require_catalog(candidate)
        return candidate

    def _load(self, game_id: UUID, fingerprint: str) -> LabSymbolCandidate:
        try:
            candidate = load_lab_symbol_candidate(self._root, fingerprint)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise JobConflictError("LAB_CANDIDATE_INVALID", "Managed candidate changed.") from error
        if candidate.game_id != game_id:
            raise JobConflictError(
                "LAB_CANDIDATE_GAME_MISMATCH", "Candidate belongs to another game."
            )
        return candidate

    def start(
        self, *, game_id: UUID, fingerprint: str, idempotency_key: UUID
    ) -> tuple[SymbolModelIteration, Job, bool]:
        # Receipt replay must precede today's artifact/catalog checks.
        return self._repository.start(
            game_id=game_id,
            fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            artifact_root=self._root,
        )
