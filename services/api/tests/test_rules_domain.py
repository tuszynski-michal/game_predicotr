from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.rules import RulesRepository, RulesService
from game_predictor_api.domain.rules import (
    Payline,
    PayoutRule,
    RulesConflictError,
    RulesError,
    RulesSymbolDefinition,
    RulesVersion,
    RulesVersionStatus,
    RulesVersionSymbol,
)


class MemoryRulesRepository(RulesRepository):
    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id
        self.items: dict[UUID, RulesVersion] = {}
        self.paylines: dict[UUID, Payline] = {}
        self.symbols: dict[UUID, RulesSymbolDefinition] = {}
        self.rules_symbols: dict[tuple[UUID, UUID], RulesVersionSymbol] = {}
        self.payout_rules: dict[UUID, PayoutRule] = {}

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

    def get_rules_version_for_update(
        self,
        rules_version_id: UUID,
    ) -> RulesVersion | None:
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

    def payout_configuration_fits_columns(
        self,
        rules_version_id: UUID,
        *,
        columns: int,
    ) -> bool:
        return all(
            item.minimum_match_length is None or item.minimum_match_length <= columns
            for item in self.rules_symbols.values()
            if item.rules_version_id == rules_version_id
        ) and all(
            item.match_length <= columns
            for item in self.payout_rules.values()
            if item.rules_version_id == rules_version_id
        )

    def get_rules_symbol_definition(
        self,
        symbol_id: UUID,
    ) -> RulesSymbolDefinition | None:
        return self.symbols.get(symbol_id)

    def list_rules_version_symbols(
        self,
        rules_version_id: UUID,
    ) -> list[RulesVersionSymbol]:
        return sorted(
            (
                item
                for item in self.rules_symbols.values()
                if item.rules_version_id == rules_version_id
            ),
            key=lambda item: item.symbol_id,
        )

    def get_rules_version_symbol(
        self,
        rules_version_id: UUID,
        symbol_id: UUID,
    ) -> RulesVersionSymbol | None:
        return self.rules_symbols.get((rules_version_id, symbol_id))

    def save_rules_version_symbol(
        self,
        rules_version_symbol: RulesVersionSymbol,
    ) -> RulesVersionSymbol:
        self.rules_symbols[
            (
                rules_version_symbol.rules_version_id,
                rules_version_symbol.symbol_id,
            )
        ] = rules_version_symbol
        return rules_version_symbol

    def archive_payout_rules_below(
        self,
        rules_version_id: UUID,
        symbol_id: UUID,
        minimum_match_length: int,
    ) -> None:
        for payout_rule_id, item in tuple(self.payout_rules.items()):
            if (
                item.rules_version_id == rules_version_id
                and item.symbol_id == symbol_id
                and item.match_length < minimum_match_length
            ):
                self.payout_rules[payout_rule_id] = replace(
                    item,
                    is_active=False,
                )

    def list_payout_rules(self, rules_version_id: UUID) -> list[PayoutRule]:
        return sorted(
            (
                item
                for item in self.payout_rules.values()
                if item.rules_version_id == rules_version_id
            ),
            key=lambda item: (item.symbol_id, item.match_length, item.id),
        )

    def get_payout_rule(
        self,
        rules_version_id: UUID,
        payout_rule_id: UUID,
    ) -> PayoutRule | None:
        item = self.payout_rules.get(payout_rule_id)
        return item if item is not None and item.rules_version_id == rules_version_id else None

    def find_payout_rule(
        self,
        rules_version_id: UUID,
        symbol_id: UUID,
        match_length: int,
    ) -> PayoutRule | None:
        return next(
            (
                item
                for item in self.payout_rules.values()
                if item.rules_version_id == rules_version_id
                and item.symbol_id == symbol_id
                and item.match_length == match_length
            ),
            None,
        )

    def add_payout_rule(
        self,
        *,
        rules_version_id: UUID,
        symbol_id: UUID,
        match_length: int,
        payout_credits: int,
        is_active: bool,
    ) -> PayoutRule:
        item = PayoutRule(
            id=uuid4(),
            rules_version_id=rules_version_id,
            symbol_id=symbol_id,
            match_length=match_length,
            payout_credits=payout_credits,
            is_active=is_active,
        )
        self.payout_rules[item.id] = item
        return item

    def save_payout_rule(self, payout_rule: PayoutRule) -> PayoutRule:
        self.payout_rules[payout_rule.id] = payout_rule
        return payout_rule


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


def test_symbol_minimum_and_payout_lifecycle_preserve_reserved_length() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)
    service = RulesService(repository)
    rules_version = service.create_rules_version(
        game_id,
        rows=3,
        columns=5,
        spin_cost=10,
    )
    symbol_id = uuid4()
    repository.symbols[symbol_id] = RulesSymbolDefinition(
        id=symbol_id,
        game_id=game_id,
        is_wildcard=False,
    )

    configured = service.update_rules_version_symbol(
        rules_version.id,
        symbol_id,
        minimum_match_length=2,
        is_active=True,
    )
    short = service.create_payout_rule(
        rules_version.id,
        symbol_id=symbol_id,
        match_length=2,
        payout_credits=10,
        is_active=True,
    )
    long = service.create_payout_rule(
        rules_version.id,
        symbol_id=symbol_id,
        match_length=5,
        payout_credits=100,
        is_active=True,
    )

    assert configured.minimum_match_length == 2
    assert [item.id for item in service.list_payout_rules(rules_version.id)] == [
        short.id,
        long.id,
    ]
    service.update_rules_version_symbol(
        rules_version.id,
        symbol_id,
        minimum_match_length=3,
        is_active=True,
    )
    assert repository.payout_rules[short.id].is_active is False
    assert repository.payout_rules[long.id].is_active is True

    with pytest.raises(RulesError) as error:
        service.create_payout_rule(
            rules_version.id,
            symbol_id=symbol_id,
            match_length=2,
            payout_credits=15,
            is_active=True,
        )
    assert error.value.code == "INVALID_PAYOUT_MATCH_LENGTH"

    service.archive_payout_rule(rules_version.id, long.id)
    with pytest.raises(RulesConflictError) as duplicate_error:
        service.create_payout_rule(
            rules_version.id,
            symbol_id=symbol_id,
            match_length=5,
            payout_credits=150,
            is_active=True,
        )
    assert duplicate_error.value.code == "PAYOUT_RULE_ALREADY_EXISTS"


def test_wildcard_and_foreign_symbol_are_rejected_for_payouts() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)
    service = RulesService(repository)
    rules_version = service.create_rules_version(
        game_id,
        rows=3,
        columns=5,
        spin_cost=10,
    )
    wildcard_id = uuid4()
    repository.symbols[wildcard_id] = RulesSymbolDefinition(
        id=wildcard_id,
        game_id=game_id,
        is_wildcard=True,
    )
    foreign_id = uuid4()
    repository.symbols[foreign_id] = RulesSymbolDefinition(
        id=foreign_id,
        game_id=uuid4(),
        is_wildcard=False,
    )

    wildcard = service.update_rules_version_symbol(
        rules_version.id,
        wildcard_id,
        minimum_match_length=None,
        is_active=True,
    )
    assert wildcard.minimum_match_length is None
    with pytest.raises(RulesConflictError) as wildcard_error:
        service.create_payout_rule(
            rules_version.id,
            symbol_id=wildcard_id,
            match_length=3,
            payout_credits=10,
            is_active=True,
        )
    assert wildcard_error.value.code == "WILDCARD_PAYOUT_NOT_ALLOWED"

    with pytest.raises(RulesConflictError) as foreign_error:
        service.update_rules_version_symbol(
            rules_version.id,
            foreign_id,
            minimum_match_length=3,
            is_active=True,
        )
    assert foreign_error.value.code == "SYMBOL_NOT_IN_RULES_GAME"


def test_payout_configuration_protects_columns_and_non_draft_mutation() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)
    service = RulesService(repository)
    rules_version = service.create_rules_version(
        game_id,
        rows=3,
        columns=5,
        spin_cost=10,
    )
    symbol_id = uuid4()
    repository.symbols[symbol_id] = RulesSymbolDefinition(
        id=symbol_id,
        game_id=game_id,
        is_wildcard=False,
    )
    service.update_rules_version_symbol(
        rules_version.id,
        symbol_id,
        minimum_match_length=3,
        is_active=True,
    )
    service.create_payout_rule(
        rules_version.id,
        symbol_id=symbol_id,
        match_length=5,
        payout_credits=100,
        is_active=True,
    )

    with pytest.raises(RulesConflictError) as dimensions_error:
        service.update_rules_version(rules_version.id, columns=4)
    assert dimensions_error.value.code == "RULES_DIMENSIONS_IN_USE"

    repository.items[rules_version.id] = replace(
        rules_version,
        status=RulesVersionStatus.PUBLISHED,
        published_at=datetime.now(UTC),
    )
    with pytest.raises(RulesConflictError) as immutable_error:
        service.update_payout_rule(
            rules_version.id,
            next(iter(repository.payout_rules)),
            payout_credits=200,
        )
    assert immutable_error.value.code == "RULES_VERSION_IMMUTABLE"


def test_publication_readiness_reports_all_deterministic_blockers() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)
    service = RulesService(repository)
    rules_version = service.create_rules_version(
        game_id,
        rows=3,
        columns=3,
        spin_cost=10,
    )
    symbol_id = uuid4()
    repository.symbols[symbol_id] = RulesSymbolDefinition(
        id=symbol_id,
        game_id=game_id,
        is_wildcard=False,
    )
    service.update_rules_version_symbol(
        rules_version.id,
        symbol_id,
        minimum_match_length=2,
        is_active=True,
    )
    service.create_payout_rule(
        rules_version.id,
        symbol_id=symbol_id,
        match_length=2,
        payout_credits=20,
        is_active=True,
    )

    readiness = service.get_publication_readiness(rules_version.id)

    assert readiness.ready is False
    assert [issue.code for issue in readiness.issues] == [
        "NO_ACTIVE_PAYLINES",
        "INCOMPLETE_PAYOUT_RULES",
    ]
    assert readiness.issues[1].details["missingMatchLengths"] == [3]
    with pytest.raises(RulesConflictError) as error:
        service.publish_rules_version(rules_version.id)
    assert error.value.code == "RULES_VERSION_NOT_READY"
    assert repository.items[rules_version.id].status is RulesVersionStatus.DRAFT


def test_publication_requires_strictly_increasing_payouts() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)
    service = RulesService(repository)
    rules_version = service.create_rules_version(
        game_id,
        rows=3,
        columns=3,
        spin_cost=10,
    )
    service.create_payline(
        rules_version.id,
        code="middle",
        name="Middle",
        row_path=[1, 1, 1],
        display_order=0,
        is_active=True,
    )
    symbol_id = uuid4()
    repository.symbols[symbol_id] = RulesSymbolDefinition(
        id=symbol_id,
        game_id=game_id,
        is_wildcard=False,
    )
    service.update_rules_version_symbol(
        rules_version.id,
        symbol_id,
        minimum_match_length=2,
        is_active=True,
    )
    for match_length, credits in ((2, 20), (3, 20)):
        service.create_payout_rule(
            rules_version.id,
            symbol_id=symbol_id,
            match_length=match_length,
            payout_credits=credits,
            is_active=True,
        )

    readiness = service.get_publication_readiness(rules_version.id)

    assert [issue.code for issue in readiness.issues] == ["NON_INCREASING_PAYOUT"]


def test_publication_rejects_active_payouts_outside_symbol_membership() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)
    service = RulesService(repository)
    rules_version = service.create_rules_version(
        game_id,
        rows=3,
        columns=3,
        spin_cost=10,
    )
    service.create_payline(
        rules_version.id,
        code="middle",
        name="Middle",
        row_path=[1, 1, 1],
        display_order=0,
        is_active=True,
    )
    ordinary_id = UUID(int=1)
    wildcard_id = UUID(int=2)
    inactive_id = UUID(int=3)
    repository.symbols.update(
        {
            ordinary_id: RulesSymbolDefinition(
                id=ordinary_id,
                game_id=game_id,
                is_wildcard=False,
            ),
            wildcard_id: RulesSymbolDefinition(
                id=wildcard_id,
                game_id=game_id,
                is_wildcard=True,
            ),
            inactive_id: RulesSymbolDefinition(
                id=inactive_id,
                game_id=game_id,
                is_wildcard=False,
            ),
        }
    )
    service.update_rules_version_symbol(
        rules_version.id,
        ordinary_id,
        minimum_match_length=2,
        is_active=True,
    )
    service.update_rules_version_symbol(
        rules_version.id,
        wildcard_id,
        minimum_match_length=None,
        is_active=True,
    )
    service.update_rules_version_symbol(
        rules_version.id,
        inactive_id,
        minimum_match_length=2,
        is_active=False,
    )
    for match_length, credits in ((2, 20), (3, 50)):
        service.create_payout_rule(
            rules_version.id,
            symbol_id=ordinary_id,
            match_length=match_length,
            payout_credits=credits,
            is_active=True,
        )
    for symbol_id, match_length in (
        (ordinary_id, 4),
        (wildcard_id, 2),
        (inactive_id, 2),
    ):
        payout = PayoutRule(
            id=uuid4(),
            rules_version_id=rules_version.id,
            symbol_id=symbol_id,
            match_length=match_length,
            payout_credits=100,
            is_active=True,
        )
        repository.payout_rules[payout.id] = payout

    readiness = service.get_publication_readiness(rules_version.id)

    assert [issue.code for issue in readiness.issues] == [
        "INVALID_PAYOUT_MATCH_LENGTH",
        "WILDCARD_PAYOUT_NOT_ALLOWED",
        "PAYOUT_FOR_INACTIVE_SYMBOL",
    ]


def test_publish_is_atomic_immutable_and_archive_preserves_timestamp() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)
    service = RulesService(repository)
    rules_version = service.create_rules_version(
        game_id,
        rows=3,
        columns=3,
        spin_cost=10,
    )
    service.create_payline(
        rules_version.id,
        code="middle",
        name="Middle",
        row_path=[1, 1, 1],
        display_order=0,
        is_active=True,
    )
    symbol_id = uuid4()
    repository.symbols[symbol_id] = RulesSymbolDefinition(
        id=symbol_id,
        game_id=game_id,
        is_wildcard=False,
    )
    service.update_rules_version_symbol(
        rules_version.id,
        symbol_id,
        minimum_match_length=2,
        is_active=True,
    )
    for match_length, credits in ((2, 20), (3, 50)):
        service.create_payout_rule(
            rules_version.id,
            symbol_id=symbol_id,
            match_length=match_length,
            payout_credits=credits,
            is_active=True,
        )

    assert service.get_publication_readiness(rules_version.id).ready is True
    published = service.publish_rules_version(rules_version.id)
    assert published.status is RulesVersionStatus.PUBLISHED
    assert published.published_at is not None

    with pytest.raises(RulesConflictError) as second_publish:
        service.publish_rules_version(rules_version.id)
    assert second_publish.value.code == "RULES_VERSION_IMMUTABLE"
    with pytest.raises(RulesConflictError) as mutation:
        service.update_payout_rule(
            rules_version.id,
            next(iter(repository.payout_rules)),
            payout_credits=100,
        )
    assert mutation.value.code == "RULES_VERSION_IMMUTABLE"

    archived = service.archive_rules_version(rules_version.id)
    assert archived.status is RulesVersionStatus.ARCHIVED
    assert archived.published_at == published.published_at
    assert service.archive_rules_version(rules_version.id) == archived
