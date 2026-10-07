from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_worker.semi_automatic_selection.contracts import SemiAutomaticSelectionRange
from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    build_local_source_manifest,
)
from game_predictor_worker.semi_automatic_selection.v7_occurrences import (
    V7OccurrenceObservation,
    V7OccurrenceTracker,
)
from game_predictor_worker.semi_automatic_selection.v7_partial_lattice import partial_lattice_policy
from game_predictor_worker.semi_automatic_selection.v7_partial_profile_bound_observer import (
    V7_PARTIAL_PROFILE_BOUND_OBSERVER_VERSION,
    V7PartialProfileBoundObserverFactory,
    v7_partial_profile_bound_localizer_fingerprint,
)
from game_predictor_worker.semi_automatic_selection.v7_profile_bound_observer import (
    V7ProfileBoundObserverFactory,
    v7_profile_bound_localizer_fingerprint,
)
from game_predictor_worker.semi_automatic_selection.v7_range_proof import V7RangeProofKind
from game_predictor_worker.semi_automatic_selection.v7_run_state import V7RunStateError
from game_predictor_worker.semi_automatic_selection.v7_worker_runtime import (
    V7WorkerRuntime,
    V7WorkerRuntimeError,
)
from PIL import Image
from test_v7_partial_label_locator import partial_grid_rgb
from test_v7_profile_bound_observer import (
    _configuration,
    _profile,
    _Recognition,
    _request,
    _ScriptedRecognizer,
    _source,
)


def _partial_configuration():
    profile = _profile(dynamic=True)
    return replace(
        _configuration(profile),
        localizer_fingerprint=v7_partial_profile_bound_localizer_fingerprint(profile),
    )


def _content(positions: tuple[int, ...] = tuple(range(9)), *, inverted: bool = False) -> bytes:
    stream = BytesIO()
    Image.fromarray(partial_grid_rgb(positions, inverted=inverted)).save(
        stream, format="JPEG", quality=95
    )
    return stream.getvalue()


def _responses(positions: tuple[int, ...], labels: dict[int, int]) -> tuple[_Recognition, ...]:
    return tuple(_Recognition(str(labels.get(position, "")), 0.99) for position in positions)


def test_partial_observer_reports_only_observed_labels_and_keeps_nine_unknown_qualities() -> None:
    positions = (1, 2, 3, 4, 5, 6, 7, 8)
    own_labels = {1: 2, 2: 3, 3: 4, 5: 6, 8: 9}
    recognizer = _ScriptedRecognizer([_responses(positions, own_labels)])
    observer = V7PartialProfileBoundObserverFactory(
        _profile(dynamic=True), lambda: recognizer
    ).create(_partial_configuration(), object())
    content = _content(positions)
    result = observer.observe(_request(_source(73, content), content))
    assert result.proof.kind is V7RangeProofKind.STRONG_FIVE_LABEL
    assert result.proof.sequence_range == SemiAutomaticSelectionRange(1, 9)
    assert result.observed_position_indices == positions
    assert [(label.position_index, label.sequence_number) for label in result.labels] == list(
        own_labels.items()
    )
    assert recognizer.crop_counts == [8]
    assert result.quality is not None
    assert len(result.quality.boards) == 9
    assert all(board.visibility.value == "unknown" for board in result.quality.boards)


@pytest.mark.parametrize(
    "second_count,conflict,accepted", [(3, False, True), (2, False, False), (3, True, False)]
)
def test_partial_observer_preserves_exact_three_plus_three_after_tracker_restart(
    second_count: int, conflict: bool, accepted: bool
) -> None:
    positions = tuple(range(1, 9))
    first_labels = {1: 2, 4: 5, 8: 9}
    second_labels = {2: 3, 3: 4, 7: 8}
    if second_count == 2:
        second_labels.pop(7)
    if conflict:
        second_labels[6] = 99
    recognizer = _ScriptedRecognizer(
        [_responses(positions, first_labels), _responses(positions, second_labels)]
    )
    observer = V7PartialProfileBoundObserverFactory(
        _profile(dynamic=True), lambda: recognizer
    ).create(_partial_configuration(), object())
    tracker = V7OccurrenceTracker((SemiAutomaticSelectionRange(1, 9),))
    for index in range(2):
        content = _content(positions, inverted=bool(index))
        source = _source(index, content)
        result = observer.observe(_request(source, content))
        tracker.consume(
            V7OccurrenceObservation(index, source.source_id, result.proof, result.weak_evidence)
        )
        tracker = V7OccurrenceTracker(
            (SemiAutomaticSelectionRange(1, 9),), checkpoint=tracker.checkpoint()
        )
    assert bool(tracker.finish()) is accepted


def test_sixth_conflicting_label_vetoes_strong_partial_proof() -> None:
    positions = tuple(range(1, 9))
    recognizer = _ScriptedRecognizer([_responses(positions, {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 99})])
    observer = V7PartialProfileBoundObserverFactory(
        _profile(dynamic=True), lambda: recognizer
    ).create(_partial_configuration(), object())
    content = _content(positions)
    result = observer.observe(_request(_source(0, content), content))
    assert result.proof.kind is V7RangeProofKind.NONE
    assert result.proof.reason_codes == ("CONFLICTING_RELIABLE_LABEL",)
    assert result.weak_evidence is None
    assert len(result.labels) == 6


def test_unresolved_photo_does_not_call_ocr_and_corrupt_photo_has_no_diagnostics() -> None:
    recognizer = _ScriptedRecognizer([])
    observer = V7PartialProfileBoundObserverFactory(
        _profile(dynamic=True), lambda: recognizer
    ).create(_partial_configuration(), object())
    content = _content((0, 1, 2))
    result = observer.observe(_request(_source(0, content), content))
    assert result.proof.kind is V7RangeProofKind.NONE
    assert "V7_LABEL_COMPONENTS_INSUFFICIENT" in result.proof.reason_codes
    assert result.labels == result.observed_position_indices == ()
    content = b"invalid-jpeg"
    corrupt = observer.observe(_request(_source(1, content), content))
    assert corrupt.source_error_code == "SOURCE_DECODE_ERROR"
    assert corrupt.labels == corrupt.observed_position_indices == ()
    assert recognizer.crop_counts == []


@pytest.mark.parametrize("dynamic", [False, True])
def test_historical_fingerprint_payload_is_unchanged_and_partial_is_distinct(dynamic: bool) -> None:
    profile = _profile(dynamic=dynamic)
    historical = {
        "geometryFamilyId": profile.calibration.geometry_family_id,
        "locatorConfig": profile.calibration.locator_config.as_dict(),
        "profileFingerprint": profile.profile_fingerprint,
        "version": "v7-profile-bound-observer-v1",
    }
    expected = hashlib.sha256(
        json.dumps(historical, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    assert v7_profile_bound_localizer_fingerprint(profile) == expected
    assert v7_partial_profile_bound_localizer_fingerprint(profile) != expected


def test_partial_factory_rejects_legacy_binding_before_ocr_construction() -> None:
    called = False

    def factory():
        nonlocal called
        called = True
        return _ScriptedRecognizer([])

    for dynamic in (False, True):
        profile = _profile(dynamic=dynamic)
        with pytest.raises(V7WorkerRuntimeError):
            V7PartialProfileBoundObserverFactory(profile, factory).create(
                _configuration(profile), object()
            )
    assert called is False
    with pytest.raises(V7WorkerRuntimeError, match="locator"):
        V7ProfileBoundObserverFactory(_profile(dynamic=True), factory).create(
            _partial_configuration(), object()
        )
    assert called is False


def test_partial_fingerprint_covers_profile_and_every_crop_setting() -> None:
    profile = _profile(dynamic=True)
    original = v7_partial_profile_bound_localizer_fingerprint(profile)
    changed = replace(
        profile,
        calibration=replace(
            profile.calibration,
            locator_config=replace(
                profile.calibration.locator_config, crop_width_spacing_ratio=0.59
            ),
        ),
    )
    assert v7_partial_profile_bound_localizer_fingerprint(changed) != original
    assert (
        v7_partial_profile_bound_localizer_fingerprint(
            replace(profile, profile_fingerprint="d" * 64)
        )
        != original
    )


def test_v2_partial_binding_invalidates_the_previous_partial_policy_before_ocr() -> None:
    profile = _profile(dynamic=True)
    policy = partial_lattice_policy()
    assert policy["version"] == "v7-partial-lattice-v2"
    assert policy["initialAssignment"] == "mutual_nearest_v1"
    assert policy["initialAssignmentTieSpacingRatio"] == 1e-6
    assert policy["collisionHypotheses"] == "competitive_blocker_v1"
    assert policy["initialCollisionHypotheses"] == "competitive_seed_blocker_v1"
    assert V7_PARTIAL_PROFILE_BOUND_OBSERVER_VERSION == "v7-partial-profile-bound-observer-v2"
    old_policy = {
        key: value
        for key, value in policy.items()
        if key
        not in {
            "initialAssignment",
            "initialAssignmentTieSpacingRatio",
            "collisionHypotheses",
            "initialCollisionHypotheses",
        }
    }
    old_policy["version"] = "v7-partial-lattice-v1"
    payload = {
        "version": "v7-partial-profile-bound-observer-v1",
        "geometryFamilyId": profile.calibration.geometry_family_id,
        "profileFingerprint": profile.profile_fingerprint,
        "locatorConfig": profile.calibration.locator_config.as_dict(),
        "partialLatticePolicy": old_policy,
    }
    old_fingerprint = hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    assert old_fingerprint != v7_partial_profile_bound_localizer_fingerprint(profile)

    def forbidden_backend():
        pytest.fail("A stale partial binding must fail before OCR construction.")

    with pytest.raises(V7WorkerRuntimeError, match="locator"):
        V7PartialProfileBoundObserverFactory(profile, forbidden_backend).create(
            replace(_partial_configuration(), localizer_fingerprint=old_fingerprint), object()
        )


def test_optional_diagnostics_validate_duplicates_bounds_and_error_observations() -> None:
    positions = tuple(range(1, 9))
    recognizer = _ScriptedRecognizer([_responses(positions, {1: 2, 4: 5, 8: 9})])
    observer = V7PartialProfileBoundObserverFactory(
        _profile(dynamic=True), lambda: recognizer
    ).create(_partial_configuration(), object())
    content = _content(positions)
    result = observer.observe(_request(_source(0, content), content))
    for invalid in ((1, 1), (9,), (-1,), (True,), ()):
        with pytest.raises(V7RunStateError):
            replace(result, observed_position_indices=invalid)
    with pytest.raises(V7RunStateError):
        replace(result, labels=(result.labels[0], result.labels[0]))
    with pytest.raises(V7RunStateError):
        replace(result, source_error_code="SOURCE_DECODE_ERROR", quality=None, weak_evidence=None)


def test_partial_runtime_resumes_with_fresh_observer_and_rejects_legacy_adapter(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    positions = tuple(range(1, 9))
    (source_root / "1.jpg").write_bytes(_content(positions))
    (source_root / "2.jpg").write_bytes(_content())
    manifest = build_local_source_manifest(source_root, selection_id=uuid4(), display_name="source")
    persisted = []

    class StopAfterFirst(RuntimeError):
        pass

    def stop(progress):
        persisted.append(progress)
        raise StopAfterFirst()

    first_recognizer = _ScriptedRecognizer([_responses(positions, {1: 2, 2: 3, 3: 4, 5: 6, 8: 9})])
    with pytest.raises(StopAfterFirst):
        V7WorkerRuntime(
            V7PartialProfileBoundObserverFactory(_profile(dynamic=True), lambda: first_recognizer)
        ).run(
            manifest=manifest, configuration=_partial_configuration(), checkpoint={}, persist=stop
        )
    checkpoint = json.loads(json.dumps(persisted[-1].checkpoint))
    with pytest.raises(V7WorkerRuntimeError):
        V7WorkerRuntime(
            V7ProfileBoundObserverFactory(_profile(dynamic=True), lambda: _ScriptedRecognizer([]))
        ).run(
            manifest=manifest,
            configuration=_configuration(_profile(dynamic=True)),
            checkpoint=checkpoint,
            persist=lambda progress: None,
        )
    resumed_recognizer = _ScriptedRecognizer(
        [_responses(tuple(range(9)), {0: 1, 1: 2, 3: 4, 5: 6, 8: 9})]
    )
    result = V7WorkerRuntime(
        V7PartialProfileBoundObserverFactory(_profile(dynamic=True), lambda: resumed_recognizer)
    ).run(
        manifest=manifest,
        configuration=_partial_configuration(),
        checkpoint=checkpoint,
        persist=lambda progress: None,
    )
    assert first_recognizer.crop_counts == [8]
    assert resumed_recognizer.crop_counts == [9]
    assert result.checkpoint["scanState"]["phase"] == "finalized"
    assert not (tmp_path / "source cut").exists()
