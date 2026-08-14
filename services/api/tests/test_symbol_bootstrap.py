from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.api.symbol_bootstrap import _resolve_candidate_asset
from game_predictor_api.application.symbol_bootstrap import SymbolBootstrapService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import (
    CatalogConflictError,
    CatalogNotFoundError,
    Symbol,
    SymbolStatus,
)
from game_predictor_api.domain.symbol_bootstrap import (
    SymbolBootstrapCandidate,
    SymbolBootstrapDefinition,
    SymbolBootstrapObservation,
    SymbolBootstrapRun,
    SymbolBootstrapStatus,
    SymbolImageCandidate,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.models import SymbolBootstrapRunModel
from sqlalchemy.dialects import postgresql


class MemoryBootstrapRepository:
    def __init__(self, game_id: UUID, observations: list[SymbolBootstrapObservation]) -> None:
        self.game_id = game_id
        self.observations = observations
        self.runs: dict[UUID, SymbolBootstrapRun] = {}
        self.has_symbols = False
        self.apply_count = 0
        self.image_candidates: list[SymbolImageCandidate] = []
        self.symbols: dict[UUID, Symbol] = {}

    def game_exists(self, game_id: UUID) -> bool:
        return game_id == self.game_id

    def game_has_symbols(self, game_id: UUID) -> bool:
        return game_id == self.game_id and self.has_symbols

    def list_observations(self, game_id: UUID) -> list[SymbolBootstrapObservation]:
        return list(self.observations) if game_id == self.game_id else []

    def get_latest_run(self, game_id: UUID) -> SymbolBootstrapRun | None:
        values = [run for run in self.runs.values() if run.game_id == game_id]
        return values[-1] if values else None

    def get_run(self, game_id: UUID, run_id: UUID) -> SymbolBootstrapRun | None:
        run = self.runs.get(run_id)
        return run if run is not None and run.game_id == game_id else None

    def add_run(
        self,
        *,
        game_id: UUID,
        expected_symbol_count: int,
        source_state_sha256: str,
        status: SymbolBootstrapStatus,
        candidates: tuple[SymbolBootstrapCandidate, ...],
        created_by: str,
        created_at: datetime,
    ) -> SymbolBootstrapRun:
        run = SymbolBootstrapRun(
            id=uuid4(),
            game_id=game_id,
            expected_symbol_count=expected_symbol_count,
            detected_cluster_count=len(candidates),
            source_state_sha256=source_state_sha256,
            status=status,
            candidates=candidates,
            resolution=(),
            created_by=created_by,
            created_at=created_at,
            applied_at=None,
        )
        self.runs[run.id] = run
        return run

    def apply_run(
        self,
        run: SymbolBootstrapRun,
        definitions: tuple[SymbolBootstrapDefinition, ...],
        *,
        applied_at: datetime,
    ) -> SymbolBootstrapRun:
        applied = replace(
            run,
            status=SymbolBootstrapStatus.APPLIED,
            resolution=definitions,
            applied_at=applied_at,
        )
        self.runs[run.id] = applied
        self.has_symbols = True
        self.apply_count += 1
        return applied

    def list_image_candidates(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        after_key: tuple[float, str, str] | None,
        limit: int,
    ) -> list[SymbolImageCandidate]:
        del symbol_id
        if game_id != self.game_id:
            return []
        values = sorted(self.image_candidates, key=lambda item: item.cursor_key)
        if after_key is not None:
            values = [item for item in values if item.cursor_key > after_key]
        return values[:limit]

    def get_image_candidate(
        self, *, game_id: UUID, symbol_id: UUID, observation_id: UUID
    ) -> SymbolImageCandidate | None:
        del symbol_id
        return next(
            (
                item
                for item in self.image_candidates
                if game_id == self.game_id and item.observation_id == observation_id
            ),
            None,
        )

    def get_selected_image_candidate(
        self, *, game_id: UUID, symbol_id: UUID
    ) -> SymbolImageCandidate | None:
        symbol = self.symbols.get(symbol_id)
        if symbol is None or symbol.game_id != game_id or symbol.image_path is None:
            return None
        return next(
            (
                item
                for item in self.image_candidates
                if item.crop_relative_path == symbol.image_path
            ),
            None,
        )

    def select_image_candidate(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        candidate: SymbolImageCandidate,
        name: str,
    ) -> Symbol:
        symbol = self.symbols[symbol_id]
        assert symbol.game_id == game_id
        updated = replace(symbol, image_path=candidate.crop_relative_path, name=name)
        self.symbols[symbol_id] = updated
        return updated


def _observation(code: str, number: int, confidence: float = 0.9) -> SymbolBootstrapObservation:
    return SymbolBootstrapObservation(
        crop_checksum_sha256=f"{number:064x}",
        crop_relative_path=f"data/crops/{number}.png",
        predicted_symbol_code=code,
        confidence=confidence,
    )


def test_optional_bootstrap_resolution_binds_none_as_sql_null() -> None:
    resolution_type = SymbolBootstrapRunModel.__table__.c.resolution.type
    processor = resolution_type.bind_processor(postgresql.dialect())

    assert processor is not None
    assert processor(None) is None


def test_matching_cluster_count_applies_once_and_preserves_actual_crops() -> None:
    game_id = uuid4()
    repository = MemoryBootstrapRepository(
        game_id,
        [_observation("lemon", 1), _observation("orange", 2), _observation("lemon", 3)],
    )
    service = SymbolBootstrapService(repository)

    first = service.start(game_id, expected_symbol_count=2, created_by="admin")
    second = service.start(game_id, expected_symbol_count=2, created_by="admin")

    assert first.status is SymbolBootstrapStatus.APPLIED
    assert second.id == first.id
    assert repository.apply_count == 1
    assert [item.name for item in first.resolution] == ["Lemon", "Orange"]
    assert first.resolution[0].image_path.startswith("data/crops/")


def test_conflict_does_not_create_catalog_and_can_be_resolved_by_merge() -> None:
    game_id = uuid4()
    repository = MemoryBootstrapRepository(
        game_id,
        [_observation("lemon", 1), _observation("lemon_dark", 2), _observation("orange", 3)],
    )
    service = SymbolBootstrapService(repository)
    run = service.start(game_id, expected_symbol_count=2, created_by="admin")

    assert run.status is SymbolBootstrapStatus.CONFLICT
    assert repository.has_symbols is False
    by_code = {candidate.predicted_symbol_code: candidate for candidate in run.candidates}
    resolved = service.resolve(
        game_id,
        run.id,
        definitions=(
            SymbolBootstrapDefinition(
                mobile_code=1,
                code="lemon",
                name="Lemon",
                candidate_ids=(
                    by_code["lemon"].candidate_id,
                    by_code["lemon_dark"].candidate_id,
                ),
                image_path=by_code["lemon"].representative_crop_relative_path,
            ),
            SymbolBootstrapDefinition(
                mobile_code=2,
                code="orange",
                name="Orange",
                candidate_ids=(by_code["orange"].candidate_id,),
                image_path=by_code["orange"].representative_crop_relative_path,
            ),
        ),
    )
    assert resolved.status is SymbolBootstrapStatus.APPLIED
    assert repository.has_symbols is True


def test_http_contract_exposes_conflict_and_resolution() -> None:
    game_id = uuid4()
    repository = MemoryBootstrapRepository(
        game_id,
        [_observation("lemon", 1), _observation("orange", 2)],
    )
    service = SymbolBootstrapService(repository)
    app = create_app(
        ApiSettings.from_environment({}),
        symbol_bootstrap_service_dependency=lambda: service,
    )
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-bootstrap",
            json={"expectedSymbolCount": 3, "createdBy": "admin"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "conflict"
        assert payload["detectedClusterCount"] == 2
        candidate_ids = [item["candidateId"] for item in payload["candidates"]]
        resolution = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-bootstrap/{payload['id']}/resolution",
            json={
                "symbols": [
                    {
                        "mobileCode": 1,
                        "code": "lemon",
                        "name": "Lemon",
                        "candidateIds": [candidate_ids[0]],
                    },
                    {
                        "mobileCode": 2,
                        "code": "orange",
                        "name": "Orange",
                        "candidateIds": [candidate_ids[1]],
                    },
                    {
                        "mobileCode": 3,
                        "code": "seven",
                        "name": "Seven",
                        "candidateIds": [candidate_ids[0]],
                    },
                ]
            },
        )
        assert resolution.status_code == 200
        assert resolution.json()["status"] == "applied"


def test_image_candidate_cursor_is_scope_bound_and_does_not_repeat_items() -> None:
    game_id = uuid4()
    symbol_id = uuid4()
    repository = MemoryBootstrapRepository(game_id, [_observation("lemon", 1)])
    repository.image_candidates = [
        SymbolImageCandidate(uuid4(), f"data/crops/{index}.png", f"{index:064x}", 1 - index / 10)
        for index in range(1, 5)
    ]
    service = SymbolBootstrapService(repository)
    first = service.image_candidates(game_id, symbol_id, after_cursor=None, limit=2)
    second = service.image_candidates(game_id, symbol_id, after_cursor=first.next_cursor, limit=2)
    assert len(first.items) == 2
    assert len(second.items) == 2
    assert {item.observation_id for item in first.items}.isdisjoint(
        item.observation_id for item in second.items
    )


def test_candidate_asset_is_confined_to_data_and_checksum_verified(tmp_path) -> None:
    content = b"actual-crop"
    path = tmp_path / "data" / "crops" / "one.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    assert _resolve_candidate_asset(tmp_path, "data/crops/one.png", checksum) == path


def test_candidate_asset_rejects_traversal_checksum_mismatch_and_unsupported_type(
    tmp_path,
) -> None:
    with pytest.raises(CatalogConflictError, match="unsafe"):
        _resolve_candidate_asset(tmp_path, "data/../secret.png", "0" * 64)

    path = tmp_path / "data" / "crops" / "one.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"actual-crop")
    with pytest.raises(CatalogConflictError, match="checksum"):
        _resolve_candidate_asset(tmp_path, "data/crops/one.png", "0" * 64)

    text_path = tmp_path / "data" / "crops" / "one.txt"
    text_path.write_bytes(b"actual-crop")
    with pytest.raises(CatalogConflictError, match="PNG or JPEG"):
        _resolve_candidate_asset(
            tmp_path,
            "data/crops/one.txt",
            hashlib.sha256(b"actual-crop").hexdigest(),
        )


def test_selecting_candidate_changes_only_symbol_image_path() -> None:
    game_id = uuid4()
    symbol_id = uuid4()
    observation_id = uuid4()
    repository = MemoryBootstrapRepository(game_id, [_observation("lemon", 1)])
    original = Symbol(
        id=symbol_id,
        game_id=game_id,
        mobile_code=7,
        code="lemon",
        name="Lemon",
        image_path="data/crops/old.png",
        is_wildcard=False,
        display_order=6,
        status=SymbolStatus.ACTIVE,
    )
    repository.symbols[symbol_id] = original
    repository.image_candidates = [
        SymbolImageCandidate(
            observation_id,
            "data/crops/new.png",
            "1" * 64,
            0.98,
        )
    ]

    selected = SymbolBootstrapService(repository).select_image_candidate(
        game_id,
        symbol_id,
        observation_id,
        name="Fresh Lemon",
    )

    assert selected.image_path == "data/crops/new.png"
    assert selected.name == "Fresh Lemon"
    assert selected.code == original.code
    assert selected.mobile_code == original.mobile_code


def test_selecting_candidate_from_another_scope_is_rejected() -> None:
    game_id = uuid4()
    repository = MemoryBootstrapRepository(game_id, [_observation("lemon", 1)])
    with pytest.raises(CatalogNotFoundError):
        SymbolBootstrapService(repository).select_image_candidate(
            game_id,
            uuid4(),
            uuid4(),
            name="Lemon",
        )


def test_http_image_picker_lists_reads_and_selects_scoped_crop(tmp_path) -> None:
    game_id = uuid4()
    symbol_id = uuid4()
    observation_id = uuid4()
    content = b"actual-symbol-crop"
    crop = tmp_path / "data" / "crops" / "lemon.png"
    crop.parent.mkdir(parents=True)
    crop.write_bytes(content)
    repository = MemoryBootstrapRepository(game_id, [_observation("lemon", 1)])
    repository.symbols[symbol_id] = Symbol(
        id=symbol_id,
        game_id=game_id,
        mobile_code=1,
        code="lemon",
        name="Lemon",
        image_path="data/crops/lemon.png",
        is_wildcard=False,
        display_order=0,
        status=SymbolStatus.ACTIVE,
    )
    repository.image_candidates = [
        SymbolImageCandidate(
            observation_id,
            "data/crops/lemon.png",
            hashlib.sha256(content).hexdigest(),
            0.97,
        )
    ]
    settings = replace(ApiSettings.from_environment({}), artifact_root=tmp_path)
    app = create_app(
        settings,
        symbol_bootstrap_service_dependency=lambda: SymbolBootstrapService(repository),
    )

    with TestClient(app) as client:
        page = client.get(f"/api/v1/admin/games/{game_id}/symbols/{symbol_id}/image-candidates")
        asset = client.get(
            f"/api/v1/admin/games/{game_id}/symbols/{symbol_id}/"
            f"image-candidates/{observation_id}/asset"
        )
        selected = client.post(
            f"/api/v1/admin/games/{game_id}/symbols/{symbol_id}/"
            f"image-candidates/{observation_id}/selection",
            json={"name": "Fresh Lemon"},
        )

    assert page.status_code == 200
    assert page.json()["items"][0]["observationId"] == str(observation_id)
    assert asset.status_code == 200
    assert asset.content == content
    assert selected.status_code == 200
    assert selected.json()["name"] == "Fresh Lemon"
    assert selected.json()["code"] == "lemon"
    assert selected.json()["mobileCode"] == 1
