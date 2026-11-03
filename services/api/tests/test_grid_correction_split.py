"""Exact correction split regressions on small constructed domain evidence."""

from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from hashlib import sha256

import pytest
from game_predictor_api.domain.grid_correction_split import (
    CorrectionSplitError,
    CorrectionSplitSource,
    solve_correction_split,
)
from game_predictor_api.domain.image_geometry_v2 import sequence_attestation_checksum_sha256


def source(index: int, *, import_id: str = "import", boards: int = 3) -> CorrectionSplitSource:
    digest = sha256(f"{import_id}-{index}".encode()).hexdigest()
    start, end = index * 9 + 1, index * 9 + 9
    return CorrectionSplitSource(
        source_id=f"{import_id}-{index:04}",
        import_id=import_id,
        byte_sha256=digest,
        pixel_sha256=None,
        logical_filename=f"originals/{digest}.jpg",
        eligible_boards=boards,
        attested_start=start,
        attested_end=end,
        attested_slots=tuple(range(9)),
        attestation_checksum_sha256=sequence_attestation_checksum_sha256(
            sequence_range_start=start,
            sequence_range_end=end,
            active_board_slots=tuple(range(9)),
        ),
        board_bindings=tuple((position, start + position) for position in range(9)),
    )


def independent_imports():
    return [
        source(i, import_id=name)
        for name, size in (("a", 24), ("b", 5), ("c", 5))
        for i in range(size)
    ]


def test_partial_sources_and_all_source_buffer_counts_are_deterministic():
    # 34 labeled photos plus 20 unlabeled photos; every source counts in a buffer.
    sources = [source(i, boards=0 if 24 <= i < 34 or 39 <= i < 49 else 3) for i in range(54)]
    sources = [
        replace(
            item,
            frozen_role=("TRAIN" if i < 24 else "VALIDATION" if i < 39 else "REGRESSION")
            if item.eligible_boards
            else None,
        )
        for i, item in enumerate(sources)
    ]
    result = solve_correction_split(sources)
    assert result == solve_correction_split(reversed(sources))
    assert len(result.buffers) == 20
    assert sum(count.photos for count in result.role_counts) == 34
    assert [(count.photos, count.boards) for count in result.role_counts] == [
        (24, 72),
        (5, 15),
        (5, 15),
    ]
    assert all(sources[int(key.rsplit("-", 1)[1])].eligible_boards == 0 for key in result.buffers)
    assert result.import_orders[0].method == "verified-attestation-order-v1"
    assert "PHOTO_ONLY_NO_PROVEN_SESSION_INDEPENDENCE" in result.limitations
    with pytest.raises(FrozenInstanceError):
        result.buffers = ()


def test_named_attestation_uses_existing_parser_and_rejects_conflict():
    sources = independent_imports()
    named = [
        replace(item, logical_filename=f"seq_{item.attested_start}-{item.attested_end}.jpg")
        for item in sources
    ]
    result = solve_correction_split(named)
    assert all(order.method == "attested-sequence-order-v1" for order in result.import_orders)
    named[0] = replace(named[0], logical_filename="seq_10-18.jpg")
    with pytest.raises(CorrectionSplitError) as error:
        solve_correction_split(named)
    assert error.value.code == "GRID_CORRECTION_SEQUENCE_CONFLICT"


@pytest.mark.parametrize("damage", ["checksum", "bindings", "overlap", "arbitrary_name"])
def test_unreliable_order_makes_whole_import_indivisible(damage):
    sources = [source(i) for i in range(54)]
    if damage == "checksum":
        sources[0] = replace(sources[0], attestation_checksum_sha256="0" * 64)
    elif damage == "bindings":
        sources[0] = replace(sources[0], board_bindings=((0, 99),))
    elif damage == "arbitrary_name":
        sources[0] = replace(sources[0], logical_filename="001.jpg")
    else:
        sources[1] = replace(
            sources[1],
            attested_start=1,
            attested_end=9,
            attestation_checksum_sha256=sources[0].attestation_checksum_sha256,
            board_bindings=sources[0].board_bindings,
        )
    with pytest.raises(CorrectionSplitError) as error:
        solve_correction_split(sources)
    assert error.value.code == "GRID_CORRECTION_SPLIT_INFEASIBLE"


def test_unknown_chronology_uses_whole_import_without_inventing_recording():
    sources = [replace(item, attestation_checksum_sha256=None) for item in independent_imports()]
    result = solve_correction_split(sources)
    assert all(order.method == "indivisible-import-v1" for order in result.import_orders)
    assert len(result.buffers) == 0
    assert tuple(count.photos for count in result.role_counts) == (24, 5, 5)


def test_byte_and_pixel_aliases_across_imports_never_inflate_minima():
    originals = [source(i, import_id="original") for i in range(15)]
    copies = [
        replace(item, source_id=f"copy-{i}", import_id="copy") for i, item in enumerate(originals)
    ]
    copies += [
        replace(
            item,
            source_id=f"pixel-{i}",
            import_id="pixel",
            byte_sha256=sha256(f"other-{i}".encode()).hexdigest(),
            pixel_sha256=item.byte_sha256,
        )
        for i, item in enumerate(originals)
    ]
    originals = [replace(item, pixel_sha256=item.byte_sha256) for item in originals]
    with pytest.raises(CorrectionSplitError) as error:
        solve_correction_split(originals + copies)
    assert error.value.code == "GRID_CORRECTION_SPLIT_MINIMA"
    assert error.value.photos == 15


def test_session_cross_import_closure_keeps_aliases_and_roles_together():
    sources = independent_imports()
    # A fourth import aliases a TRAIN photo; counts and global role remain unchanged.
    alias = replace(sources[0], source_id="copy", import_id="z-copy")
    result = solve_correction_split([*sources, alias])
    roles = dict(result.assignments)
    assert roles[alias.source_id] == roles[sources[0].source_id]
    assert sum(count.photos for count in result.role_counts) == 34
    # Connecting all imports as one known session destroys independence.
    with pytest.raises(CorrectionSplitError) as error:
        solve_correction_split(
            [replace(item, component_ids=("known-session",)) for item in sources]
        )
    assert error.value.code == "GRID_CORRECTION_SPLIT_INFEASIBLE"


def test_alias_representative_preserves_maximum_board_count_without_double_count():
    sources = independent_imports()
    alias = replace(sources[0], source_id="z-more-labels", import_id="z-copy", eligible_boards=9)
    result = solve_correction_split([*sources, alias])
    assert alias.source_id in result.representative_sources
    assert sources[0].source_id not in result.representative_sources
    assert sum(count.photos for count in result.role_counts) == 34
    assert sum(count.boards for count in result.role_counts) == 108


def test_sparse_479_source_import_and_309_unlabeled_sources_fit_default_work_budget():
    # Matches the measured import sizes, without operator labels or image contents.
    sources = [source(i, boards=3 if i < 445 and i % 5 == 0 else 0) for i in range(479)]
    sources += [source(i, import_id="unlabeled", boards=0) for i in range(309)]
    result = solve_correction_split(sources)
    assert all(
        count.photos >= minimum
        for count, minimum in zip(result.role_counts, (10, 5, 5), strict=True)
    )
    assert len(result.assignments) == 788


def test_prior_train_and_control_protection_cannot_be_reassigned():
    sources = independent_imports()
    frozen = [
        replace(
            item, frozen_role={"a": "TRAIN", "b": "VALIDATION", "c": "REGRESSION"}[item.import_id]
        )
        for item in sources
    ]
    result = solve_correction_split(frozen)
    assert all(dict(result.assignments)[item.source_id] == item.frozen_role for item in frozen)
    # Prior ancestor TRAIN is allowed only in TRAIN; it cannot become control.
    with pytest.raises(CorrectionSplitError) as error:
        solve_correction_split(
            [replace(item, allowed_roles=frozenset(("TRAIN",))) for item in sources]
        )
    assert error.value.code == "GRID_CORRECTION_SPLIT_INFEASIBLE"


def test_frozen_buffer_and_roles_survive_another_solve():
    sources = [source(i) for i in range(54)]
    initial = solve_correction_split(sources)
    roles = dict(initial.assignments)
    pinned = [
        replace(
            item, frozen_role=roles[item.source_id], frozen_buffer=roles[item.source_id] is None
        )
        for item in sources
    ]
    assert solve_correction_split(pinned) == initial
    # A new alias of a protected buffer cannot enter TRAIN in a later import.
    buffer_source = next(item for item in sources if item.source_id in initial.buffers)
    bad_alias = replace(buffer_source, source_id="new-alias", import_id="new", frozen_role="TRAIN")
    with pytest.raises(CorrectionSplitError) as error:
        solve_correction_split([*pinned, bad_alias])
    assert error.value.code == "GRID_CORRECTION_PROTECTION_CONFLICT"


def test_known_session_spanning_buffer_cannot_be_split():
    sources = [replace(source(i), component_ids=("session",)) for i in range(54)]
    with pytest.raises(CorrectionSplitError) as error:
        solve_correction_split(sources)
    assert error.value.code == "GRID_CORRECTION_SPLIT_INFEASIBLE"


def test_new_source_inside_frozen_buffer_cannot_rewrite_boundary_history():
    sources = [source(2 * i) for i in range(54)]
    result = solve_correction_split(sources)
    roles = dict(result.assignments)
    pinned = [
        replace(
            item, frozen_role=roles[item.source_id], frozen_buffer=roles[item.source_id] is None
        )
        for item in sources
    ]
    first_buffer_index = int(result.buffers[0].rsplit("-", 1)[1])
    inserted = source(first_buffer_index + 1)
    with pytest.raises(CorrectionSplitError) as error:
        solve_correction_split([*pinned, inserted])
    assert error.value.code == "GRID_CORRECTION_SPLIT_INFEASIBLE"


def test_work_limit_is_not_reported_as_infeasible_or_a_partial_optimum():
    with pytest.raises(CorrectionSplitError) as error:
        solve_correction_split([source(i) for i in range(54)], max_work=10)
    assert error.value.code == "GRID_CORRECTION_SPLIT_WORK_LIMIT"


def test_ratio_is_global_minimum_for_contiguous_three_block_class():
    sources = [source(i, boards=1 + i % 4) for i in range(54)]
    result = solve_correction_split(sources)
    # Independent exhaustive oracle for this small single-import fixture.
    from itertools import permutations

    scores = []
    for roles in permutations(range(3)):
        for first in range(1, 33):
            for second in range(first + 11, 44):
                intervals = ((0, first), (first + 10, second), (second + 10, 54))
                photos, boards = [0] * 3, [0] * 3
                for role, (start, end) in zip(roles, intervals, strict=True):
                    photos[role] = end - start
                    boards[role] = sum(item.eligible_boards for item in sources[start:end])
                if all(
                    photos[i] >= (10, 5, 5)[i] and boards[i] >= (30, 15, 15)[i] for i in range(3)
                ):
                    total = sum(photos)
                    scores.append(
                        Fraction(
                            sum(abs(100 * photos[i] - (70, 15, 15)[i] * total) for i in range(3)),
                            100 * total,
                        )
                    )
    assert Fraction(result.objective_numerator, result.objective_denominator) == min(scores)
