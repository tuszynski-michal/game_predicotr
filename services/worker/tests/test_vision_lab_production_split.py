from __future__ import annotations

import dataclasses
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


V2 = split.SplitConfig(
    seed=7,
    training_per_level=8,
    development_per_level=2,
    policy_version=split.POLICY_VERSION_V2,
)


def test_production_split_v1_description_is_unchanged() -> None:
    v1 = split.SplitConfig(seed=801).describe()
    assert v1["policyVersion"] == split.POLICY_VERSION
    assert "heldoutGoldFamilies" not in v1
    v2 = split.SplitConfig(seed=801, policy_version=split.POLICY_VERSION_V2).describe()
    assert v2["policyVersion"] == split.POLICY_VERSION_V2
    assert v2["heldoutGoldFamilies"]["goldShareBelow"] == "3/10"
    assert v2["heldoutGoldFamilies"]["maxTrainingPoolLoss"] == "1/5"
    assert {k: v for k, v in v2.items() if k not in ("policyVersion", "heldoutGoldFamilies")} == {
        k: v for k, v in v1.items() if k != "policyVersion"
    }
    with pytest.raises(ValueError, match="SPLIT_POLICY_UNSUPPORTED"):
        split.SplitConfig(seed=1, policy_version="production-geometry-split-v9")


def test_production_split_v2_holds_gold_family_out_of_training(tmp_path: Path) -> None:
    images = facts(standard_dataset(tmp_path))
    plan = split.plan_split(images, V2, ok)
    # fam0: 3 G boards over 8 filter-passing photos ranks first and alone holds 75% of G.
    assert plan.heldout_groups == ["selection:fam0"]
    assert plan.development_groups[0] == "selection:fam0"
    assert plan.heldout_selection["stopReason"] == "GOLD_SHARE_REACHED"
    assert plan.heldout_selection["goldBoardsHeldOut"] == 3
    trained = {
        plan.family_group_of[images[i].family_id]
        for i, role in plan.roles.items()
        if role == split.ROLE_TRAINING
    }
    assert "selection:fam0" not in trained
    developed = {
        plan.family_group_of[images[i].family_id]
        for i, role in plan.roles.items()
        if role == split.ROLE_DEVELOPMENT
    }
    assert developed == {"selection:fam0"}
    assert plan.family_seen_in_training == {"gold-full": False, "gold-mixed": True}
    summary = split.split_summary(plan, images)
    assert summary["gold"]["goldBoardsInFamiliesUnseenInTraining"] == 3
    assert summary["gold"]["goldBoardsInFamiliesSeenInTraining"] == 1
    assert summary["roles"]["training"]["imagesByLevel"] == {"B": 8, "S": 8}
    assert summary["roles"]["development"]["imagesByLevel"] == {"B": 2, "S": 2}
    assert summary["heldoutGoldFamilies"]["additionalDevelopmentFamilyGroups"] == []


def selection_dataset(root: Path) -> Dataset:
    """fam-b and fam-c tie at 2 G boards per 20 photos; fam-a has 1 G per 20 photos."""

    data = Dataset(root)
    for family, gold in (
        ("fam-a", 1),
        ("fam-b", 2),
        ("fam-c", 2),
        *((f"fam-{n}", 0) for n in "defgh"),
    ):
        for _ in range(10):
            data.photo(family, ["S", "S", "S"])
            data.photo(family, ["B", "B", "B"])
        if gold:
            data.photo(family, ["G"] * gold + ["U"], image_id=f"gold-{family}")
    return data


def test_production_split_v2_rule_order_tie_break_and_stop(tmp_path: Path) -> None:
    images = facts(selection_dataset(tmp_path))
    config = split.SplitConfig(
        seed=5,
        training_per_level=10,
        development_per_level=2,
        policy_version=split.POLICY_VERSION_V2,
        heldout_gold_share=Fraction(1, 2),
        heldout_max_pool_loss=Fraction(3, 10),
    )
    plan = split.plan_split(images, config, ok)
    order = [row["familyGroup"] for row in plan.heldout_selection["candidates"]]
    assert order == ["fam-b", "fam-c", "fam-a"]
    # fam-b holds 40% < 50% of G, fam-c raises the loss to 40/160 = 25% <= 30%: taken.
    assert plan.heldout_groups == ["fam-b", "fam-c"]
    assert plan.heldout_selection["stopReason"] == "GOLD_SHARE_REACHED"
    assert plan.heldout_selection["trainingPoolLoss"] == 0.25
    assert plan.family_seen_in_training["gold-fam-a"] is True
    assert plan.family_seen_in_training["gold-fam-b"] is False
    assert plan.family_seen_in_training["gold-fam-c"] is False


def test_production_split_v2_irreconcilable_thresholds_stop(tmp_path: Path) -> None:
    images = facts(selection_dataset(tmp_path))
    # fam-b alone holds 40% of G; adding fam-c would lose 25% > 20% of the pool.
    config = split.SplitConfig(
        seed=5,
        training_per_level=10,
        development_per_level=2,
        policy_version=split.POLICY_VERSION_V2,
        heldout_gold_share=Fraction(1, 2),
    )
    with pytest.raises(ValueError, match="HELDOUT_GOLD_THRESHOLDS_IRRECONCILABLE"):
        split.plan_split(images, config, ok)
    # The first group is always taken, but not past the loss cap.
    strict = split.SplitConfig(
        seed=5,
        training_per_level=10,
        development_per_level=2,
        policy_version=split.POLICY_VERSION_V2,
        heldout_max_pool_loss=Fraction(1, 10),
    )
    with pytest.raises(ValueError, match="HELDOUT_GOLD_THRESHOLDS_IRRECONCILABLE"):
        split.plan_split(images, strict, ok)


def test_production_split_v2_tops_up_development_in_seeded_order(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path)
    data.photo("selection:goldonly", ["G", "G"], image_id="gold-only")
    images = facts(data)
    plan = split.plan_split(images, V2, ok)
    # A gold group without filter-passing photos ranks first; it cannot fill development.
    assert plan.heldout_selection["candidates"][0]["familyGroup"] == "selection:goldonly"
    assert plan.heldout_groups[0] == "selection:goldonly"
    assert plan.development_groups[: len(plan.heldout_groups)] == plan.heldout_groups
    summary = split.split_summary(plan, images)
    assert summary["roles"]["development"]["imagesByLevel"] == {"B": 2, "S": 2}
    assert plan.family_seen_in_training["gold-only"] is False
    split.assert_disjoint(plan, images)


def test_production_split_v2_disjoint_and_deterministic(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path)
    first = split.plan_split(facts(data), V2, ok)
    data.rows.reverse()
    images = facts(data)
    second = split.plan_split(images, V2, ok)
    assert first.roles == second.roles
    assert first.heldout_selection == second.heldout_selection
    # The held-out choice does not depend on the seed; the draws do.
    reseeded = split.plan_split(images, dataclasses.replace(V2, seed=8), ok)
    assert reseeded.heldout_groups == second.heldout_groups
    assert reseeded.roles != second.roles
    second.roles[
        next(i for i in images if images[i].family_id == "selection:fam0" and i.startswith("img-"))
    ] = split.ROLE_TRAINING
    with pytest.raises(ValueError, match="HELDOUT_FAMILY_IN_TRAINING"):
        split.assert_disjoint(second, images)
