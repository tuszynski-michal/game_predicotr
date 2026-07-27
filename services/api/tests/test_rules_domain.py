from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.rules import RulesRepository, RulesService
from game_predictor_api.domain.rules import (
    Payline,
    RulesConflictError,
    RulesError,
    RulesVersion,
    RulesVersionStatus,
)


class MemoryRulesRepository(RulesRepository):
    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id
        self.items: dict[UUID, RulesVersion] = {}
        self.paylines: dict[UUID, Payline] = {}

    def game_exists(self, game_id: UUID) -> bool:
        return game_id == self.game_id

    def list_rules_versions(self, game_id: UUID) -> list[RulesVersion]:
        return sorted(
            (item for item in self.items.values() if item.game_id == game_id),
            key=lambda item: item.version,
            reverse=True,
        )

    def get_rules_version(self, rules_version_id: UUID) -> RulesVersion | None:
        return self.items.get(rules_version_id)

    def add_next_rules_version(
        self,
        *,
        game_id: UUID,
        rows: int,
        columns: int,
        spin_cost: int,
    ) -> RulesVersion | None:
        if not self.game_exists(game_id):
            return None
        item = RulesVersion(
            id=uuid4(),
            game_id=game_id,
            version=max((item.version for item in self.items.values()), default=0) + 1,
            rows=rows,
            columns=columns,
            spin_cost=spin_cost,
            status=RulesVersionStatus.DRAFT,
            created_at=datetime.now(UTC),
            published_at=None,
        )
        self.items[item.id] = item
        return item

    def save_rules_version(self, rules_version: RulesVersion) -> RulesVersion:
        self.items[rules_version.id] = rules_version
        return rules_version

    def paylines_fit_dimensions(
        self,
        rules_version_id: UUID,
        *,
        rows: int,
        columns: int,
    ) -> bool:
        return all(
            len(item.row_path) == columns and max(item.row_path) < rows
            for item in self.paylines.values()
            if item.rules_version_id == rules_version_id
        )

    def list_paylines(self, rules_version_id: UUID) -> list[Payline]:
        return sorted(
            (item for item in self.paylines.values() if item.rules_version_id == rules_version_id),
            key=lambda item: (item.display_order, item.code, item.id),
        )

    def get_payline(
        self,
        rules_version_id: UUID,
        payline_id: UUID,
    ) -> Payline | None:
        item = self.paylines.get(payline_id)
        return item if item is not None and item.rules_version_id == rules_version_id else None

    def find_payline_by_code(
        self,
        rules_version_id: UUID,
        code: str,
    ) -> Payline | None:
        return next(
            (
                item
                for item in self.paylines.values()
                if item.rules_version_id == rules_version_id and item.code == code
            ),
            None,
        )

    def find_payline_by_row_path(
        self,
        rules_version_id: UUID,
        row_path: tuple[int, ...],
    ) -> Payline | None:
        return next(
            (
                item
                for item in self.paylines.values()
                if item.rules_version_id == rules_version_id and item.row_path == row_path
            ),
            None,
        )

    def add_payline(
        self,
        *,
        rules_version_id: UUID,
        code: str,
        name: str,
        row_path: tuple[int, ...],
        display_order: int,
        is_active: bool,
    ) -> Payline:
        item = Payline(
            id=uuid4(),
            rules_version_id=rules_version_id,
            code=code,
            name=name,
            row_path=row_path,
            display_order=display_order,
            is_active=is_active,
        )
        self.paylines[item.id] = item
        return item

    def save_payline(self, payline: Payline) -> Payline:
        self.paylines[payline.id] = payline
        return payline


def test_service_assigns_increasing_version_and_lists_newest_first() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)
    service = RulesService(repository)

    first = service.create_rules_version(game_id, rows=3, columns=5, spin_cost=10)
    second = service.create_rules_version(game_id, rows=4, columns=6, spin_cost=20)

    assert first.version == 1
    assert second.version == 2
    assert second.status is RulesVersionStatus.DRAFT
    assert [item.id for item in service.list_rules_versions(game_id)] == [
        second.id,
        first.id,
    ]


@pytest.mark.parametrize(
    ("rows", "columns", "spin_cost", "code"),
    [
        (0, 5, 10, "INVALID_RULES_ROWS"),
        (3, 0, 10, "INVALID_RULES_COLUMNS"),
        (3, 5, -1, "INVALID_SPIN_COST"),
    ],
)
def test_service_validates_dimensions_and_spin_cost(
    rows: int,
    columns: int,
    spin_cost: int,
    code: str,
) -> None:
    game_id = uuid4()
    service = RulesService(MemoryRulesRepository(game_id))

    with pytest.raises(RulesError) as error:
        service.create_rules_version(
            game_id,
            rows=rows,
            columns=columns,
            spin_cost=spin_cost,
        )

    assert error.value.code == code


def test_non_draft_rules_version_is_immutable() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)
    service = RulesService(repository)
    draft = service.create_rules_version(game_id, rows=3, columns=5, spin_cost=10)
    repository.items[draft.id] = replace(
        draft,
        status=RulesVersionStatus.PUBLISHED,
        published_at=datetime.now(UTC),
    )

    with pytest.raises(RulesConflictError) as error:
        service.update_rules_version(draft.id, spin_cost=20)

    assert error.value.code == "RULES_VERSION_IMMUTABLE"


def test_payline_validation_order_and_archive_preserve_row_path() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)
    service = RulesService(repository)
    rules_version = service.create_rules_version(
        game_id,
        rows=3,
        columns=5,
        spin_cost=10,
    )
    later = service.create_payline(
        rules_version.id,
        code="line-v",
        name=" V ",
        row_path=[0, 1, 2, 1, 0],
        display_order=20,
        is_active=True,
    )
    earlier = service.create_payline(
        rules_version.id,
        code="line-top",
        name="Top",
        row_path=[0, 0, 0, 0, 0],
        display_order=10,
        is_active=True,
    )

    assert later.name == "V"
    assert later.row_path == (0, 1, 2, 1, 0)
    assert [item.id for item in service.list_paylines(rules_version.id)] == [
        earlier.id,
        later.id,
    ]
    assert service.archive_payline(rules_version.id, later.id).is_active is False

    with pytest.raises(RulesConflictError) as error:
        service.create_payline(
            rules_version.id,
            code="line-v-copy",
            name="Copy",
            row_path=[0, 1, 2, 1, 0],
            display_order=30,
            is_active=True,
        )
    assert error.value.code == "DUPLICATE_PAYLINE"
    assert error.value.details == {"existingPaylineId": str(later.id)}


@pytest.mark.parametrize(
    ("row_path", "code"),
    [
        ([0, 1, 2, 1], "INVALID_PAYLINE_LENGTH"),
        ([0, 1, 3, 1, 0], "INVALID_PAYLINE_ROW"),
        ([-1, 1, 2, 1, 0], "INVALID_PAYLINE_ROW"),
    ],
)
def test_payline_rejects_incomplete_and_out_of_range_paths(
    row_path: list[int],
    code: str,
) -> None:
    game_id = uuid4()
    service = RulesService(MemoryRulesRepository(game_id))
    rules_version = service.create_rules_version(
        game_id,
        rows=3,
        columns=5,
        spin_cost=10,
    )

    with pytest.raises(RulesError) as error:
        service.create_payline(
            rules_version.id,
            code="line",
            name="Line",
            row_path=row_path,
            display_order=0,
            is_active=True,
        )

    assert error.value.code == code


def test_existing_payline_protects_dimensions_that_would_invalidate_it() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)
    service = RulesService(repository)
    rules_version = service.create_rules_version(
        game_id,
        rows=3,
        columns=5,
        spin_cost=10,
    )
    service.create_payline(
        rules_version.id,
        code="line-v",
        name="V",
        row_path=[0, 1, 2, 1, 0],
        display_order=0,
        is_active=True,
    )

    for change in ({"columns": 6}, {"rows": 2}):
        with pytest.raises(RulesConflictError) as error:
            service.update_rules_version(rules_version.id, **change)
        assert error.value.code == "RULES_DIMENSIONS_IN_USE"

    assert service.update_rules_version(rules_version.id, rows=4).rows == 4
