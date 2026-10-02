from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest
from game_predictor_worker.vision_lab import production_split as split
from lab_production_fixtures import Dataset, jpeg_bytes, standard_dataset


def facts(data: Dataset) -> dict[str, split.ImageFacts]:
    collector = split.ImageFactsCollector()
    for row in reversed(data.rows):
        collector.add(row)
    return collector.images()


def ok(_image_id: str) -> str | None:
    return None


CONFIG = split.SplitConfig(seed=7, training_per_level=8, development_per_level=2)


def test_production_split_filter_rejects_whole_photo(tmp_path: Path) -> None:
    images = facts(standard_dataset(tmp_path))
    assert split.filter_reasons(images["reject-filter"]) == (split.REJECT_SYMBOL_FILTER,)
    assert split.REJECT_UNCLASSIFIED in split.filter_reasons(images["reject-u"])
    assert split.filter_reasons(images["reject-incomplete"]) == (split.REJECT_INCOMPLETE,)
    plan = split.plan_split(images, CONFIG, ok)
    for rejected in ("reject-filter", "reject-u", "reject-incomplete"):
        assert rejected not in plan.roles
        assert rejected in plan.filter_rejections
    summary = split.split_summary(plan, images)
    assert summary["filterRejectionsByPrimaryReason"] == {
        split.REJECT_INCOMPLETE: 1,
        split.REJECT_SYMBOL_FILTER: 1,
        split.REJECT_UNCLASSIFIED: 1,
    }


def test_production_split_gold_first_and_unit_is_photo(tmp_path: Path) -> None:
    images = facts(standard_dataset(tmp_path))
    plan = split.plan_split(images, CONFIG, ok)
    assert plan.roles["gold-full"] == split.ROLE_GOLD
    assert plan.roles["gold-mixed"] == split.ROLE_GOLD
    assert plan.gold_basis["gold-mixed"] == split.GOLD_BASIS_BOARD
    summary = split.split_summary(plan, images)
    assert summary["gold"]["goldBoards"] == 4
    assert summary["roles"]["training"]["imagesByLevel"] == {"B": 8, "S": 8}
    assert summary["roles"]["development"]["imagesByLevel"] == {"B": 2, "S": 2}
    # Every photo has exactly one role: boards cannot be split between roles.
    assert len(plan.roles) == len(set(plan.roles))
    assert set(plan.family_seen_in_training) == {"gold-full", "gold-mixed"}


def test_production_split_disjoint_families_shas_and_photos(tmp_path: Path) -> None:
    images = facts(standard_dataset(tmp_path))
    plan = split.plan_split(images, CONFIG, ok)

    def of(role: str, key: str) -> set[str]:
        ids = [i for i, r in plan.roles.items() if r == role]
        if key == "sha":
            return {images[i].sha256 for i in ids}
        return {plan.family_group_of[images[i].family_id] for i in ids}

    assert not of("development", "family") & of("training", "family")
    assert not of("development", "sha") & of("training", "sha")
    assert not of("gold", "sha") & (of("training", "sha") | of("development", "sha"))
    assert set(plan.development_groups).isdisjoint(plan.training_groups)


def test_production_split_seed_is_deterministic_and_order_independent(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path)
    first = split.plan_split(facts(data), CONFIG, ok).roles
    data.rows.reverse()
    second = split.plan_split(facts(data), CONFIG, ok).roles
    assert first == second
    other = split.plan_split(
        facts(data), split.SplitConfig(seed=8, training_per_level=8, development_per_level=2), ok
    ).roles
    assert other != first


def test_production_split_sha_group_goes_whole_to_gold(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path)
    shared = jpeg_bytes(999)
    data.photo("selection:fam4", ["G"], image_id="gold-twin-a", data=shared)
    data.photo("selection:fam5", ["S", "S", "S"], image_id="silver-twin-b", data=shared)
    images = facts(data)
    plan = split.plan_split(images, CONFIG, ok)
    assert plan.roles["silver-twin-b"] == split.ROLE_GOLD
    assert plan.gold_basis["silver-twin-b"] == split.GOLD_BASIS_SHA_TWIN
    assert split.split_summary(plan, images)["gold"]["shaTwinImages"] == 1


def test_production_split_shared_sha_outside_gold_joins_families(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path)
    shared = jpeg_bytes(555)
    data.photo("selection:fam5", ["B", "B", "B"], image_id="twin-a", data=shared)
    data.photo("selection:fam6", ["B", "B", "B"], image_id="twin-b", data=shared)
    plan = split.plan_split(facts(data), CONFIG, ok)
    assert plan.family_group_of["selection:fam5"] == plan.family_group_of["selection:fam6"]


def test_production_split_family_cap_limits_share(tmp_path: Path) -> None:
    data = Dataset(tmp_path)
    for family, count in (
        ("selection:big", 30),
        ("selection:a", 6),
        ("selection:b", 6),
        ("selection:c", 6),
        ("selection:d", 6),
        ("selection:e", 6),
    ):
        for _ in range(count):
            data.photo(family, ["S", "S", "S"])
            data.photo(family, ["B", "B", "B"])
    images = facts(data)
    plan = split.plan_split(
        images, split.SplitConfig(seed=3, training_per_level=12, development_per_level=2), ok
    )
    summary = split.split_summary(plan, images)
    assert summary["maxTrainingFamilyShare"] <= 0.25
    assert summary["roles"]["training"]["imagesByLevel"] == {"B": 12, "S": 12}


def test_production_split_integrity_exclusion_is_recorded_and_replaced(tmp_path: Path) -> None:
    images = facts(standard_dataset(tmp_path))
    broken = {i for i in images if i.startswith("img-")}
    broken = set(sorted(broken)[:5]) | {"gold-full"}

    def check(image_id: str) -> str | None:
        return "SOURCE_FILE_MISSING" if image_id in broken else None

    plan = split.plan_split(images, CONFIG, check)
    assert "gold-full" not in plan.roles
    assert plan.integrity_exclusions["gold-full"] == "SOURCE_FILE_MISSING"
    assert not broken & set(plan.roles)


def test_production_split_refuses_leaks(tmp_path: Path) -> None:
    images = facts(standard_dataset(tmp_path))
    plan = split.plan_split(images, CONFIG, ok)
    training = next(i for i, r in plan.roles.items() if r == split.ROLE_TRAINING)
    plan.roles["reject-filter"] = split.ROLE_TRAINING
    with pytest.raises(ValueError, match="UNFILTERED_PHOTO"):
        split.assert_disjoint(plan, images)
    del plan.roles["reject-filter"]
    plan.development_groups.append(plan.family_group_of[images[training].family_id])
    with pytest.raises(ValueError, match="FAMILY_GROUP_IN_TWO_ROLES"):
        split.assert_disjoint(plan, images)


def test_production_split_development_pool_insufficient_stops(tmp_path: Path) -> None:
    data = Dataset(tmp_path)
    data.photo("selection:only", ["S", "S", "S"])
    data.photo("selection:only", ["B", "B", "B"])
    with pytest.raises(ValueError, match="DEVELOPMENT_POOL_INSUFFICIENT"):
        split.plan_split(
            facts(data),
            split.SplitConfig(seed=1, training_per_level=1, development_per_level=2),
            ok,
        )


def test_production_split_capped_allocation() -> None:
    assert split.capped_allocation({"a": 10, "b": 10}, 5, {"a": 10, "b": 10}) == {"a": 3, "b": 2}
    assert split.capped_allocation({"a": 100, "b": 1, "c": 1}, 6, {"a": 3, "b": 1, "c": 1}) == {
        "a": 3,
        "b": 1,
        "c": 1,
    }
    allocation = split.capped_allocation(
        {"a": 90, "b": 30, "c": 30, "d": 30}, 40, {"a": 10, "b": 30, "c": 30, "d": 30}
    )
    assert allocation["a"] == 10 and sum(allocation.values()) == 40
    assert split.SplitConfig(seed=0, family_cap_fraction=Fraction(1, 4)).family_cap() == 750
