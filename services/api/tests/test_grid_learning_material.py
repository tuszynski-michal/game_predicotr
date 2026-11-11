"""Closed exclusions, source-counted material and pre-candidate strata."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.grid_content_sampling import fresh_regression_preview
from game_predictor_api.domain.grid_correction_incremental_split import solve_incremental_split
from game_predictor_api.domain.grid_correction_split import CorrectionSplitSource, _prepare
from game_predictor_api.domain.grid_learning_material import conflicting_groups, material_report
from game_predictor_api.domain.grid_learning_reference import baseline_reference, source_reference
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.storage import grid_correction_split as adapter


def source(key, import_id=None, **kwargs):
    return CorrectionSplitSource(
        str(key),
        import_id or f"import-{key}",
        f"{key:064x}",
        f"{key + 100:064x}",
        f"{key:064x}.jpg",
        9,
        **kwargs,
    )


def context(sources):
    return {
        s.source_id: {
            "priorRoles": [s.frozen_role] if s.frozen_role else [],
            "validationPurposes": [],
            "proofSha256": "a" * 64,
            "selectionExposed": False,
            "diagnosticExposed": False,
        }
        for s in sources
    }


def test_conflict_exclusion_closes_unordered_import_copies_sessions_and_other_imports():
    sources = [
        source(1, "bad", frozen_role="TRAIN"),
        source(2, "bad", frozen_role="REGRESSION"),
        source(3, "second", component_ids=("session",)),
        source(4, "third", component_ids=("session",)),
        source(5),
    ]
    sources[2] = replace(sources[2], pixel_sha256=sources[0].pixel_sha256)
    before = deepcopy(sources)
    facts = context(sources)
    with pytest.raises(ValueError, match="conflicting pins"):
        _prepare(tuple(sources))
    excluded = conflicting_groups(sources, facts)
    assert len(excluded) == 1
    assert excluded[0]["sourceIds"] == ["1", "2", "3", "4"]
    assert excluded[0]["photos"] == 3 and excluded[0]["boards"] == 27
    assert sources == before
    assert conflicting_groups(list(reversed(sources)), facts) == excluded
    _prepare(tuple(s for s in sources if s.source_id == "5"))


def test_purpose_conflict_is_excluded_as_one_group_without_changing_prior_roles():
    sources = [
        source(1, "same", frozen_role="VALIDATION"),
        source(2, "same", frozen_role="VALIDATION"),
    ]
    facts = context(sources)
    facts["1"]["validationPurposes"] = ["A"]
    facts["2"]["validationPurposes"] = ["B"]
    result = conflicting_groups(sources, facts)
    assert result[0]["reasonCodes"] == ["GRID_VALIDATION_PURPOSE_CONFLICT"]
    assert result[0]["priorRoles"] == ["VALIDATION"]


def test_material_counts_each_photo_and_board_once_but_photo_categories_can_overlap():
    a = source(1)
    b = replace(source(2), pixel_sha256=a.pixel_sha256)
    labels = [
        {"positionIndex": 0, "approval": {"origin": "human_corrected", "weight": 4}},
        {"positionIndex": 1, "approval": {"origin": "human_checked_unchanged", "weight": 1}},
    ]
    result = material_report(
        [a, b],
        {"1": labels, "2": labels},
        [],
        [{"sourceId": "1", "representative": True, "role": "TRAIN", "eligibleBoards": 2}],
    )
    assert result["roles"]["TRAIN"] == {
        "correctedBoards": 1,
        "goodBoards": 1,
        "unknownBoards": 0,
        "correctedPhotos": 1,
        "goodPhotos": 1,
        "unknownPhotos": 0,
        "photos": 1,
        "boards": 2,
        "photoCategoriesMayOverlap": True,
    }
    buffered = material_report(
        [a],
        {"1": labels},
        [],
        [
            {
                "sourceId": "1",
                "representative": True,
                "role": None,
                "eligibleBoards": 0,
                "buffer": True,
            }
        ],
    )
    assert buffered["roles"]["BUFFER"]["boards"] == 2


def test_ordinary_seed_roster_does_not_change_when_content_labels_or_difficulty_change():
    sources = [source(i) for i in range(1, 13)]
    facts = context(sources)
    first = fresh_regression_preview(
        sources, facts, frozenset(), ancestry_sha256="a" * 64, stratified=True
    )
    refs = {s.source_id: {"state": "hard", "boards": [], "categoryCounts": {}} for s in sources}
    second = fresh_regression_preview(
        list(reversed(sources)),
        facts,
        frozenset(facts),
        ancestry_sha256="a" * 64,
        stratified=True,
        references=refs,
    )
    assert first["strata"]["ordinary"]["sourceIds"] == second["strata"]["ordinary"]["sourceIds"]
    assert first["selectionState"] == "ready" and first["state"] == "not_evaluable"
    assert first["missingFullPhotos"] == 5
    assert second["strata"]["hard"]["geometryFullPhotos"] == 5
    assert not set(second["strata"]["ordinary"]["sourceIds"]) & set(
        second["strata"]["hard"]["sourceIds"]
    )
    assert len(second["unrepresentedCategories"]) == 6


def test_original_prediction_never_becomes_gt_and_other_base_is_unknown():
    nodes = [{"x": float(i), "y": 0.0} for i in range(24)]
    label = {"positionIndex": 0, "nodes": nodes, "approval": {"origin": "human_corrected"}}
    original = {"latticeNodes": [{"x": p["x"], "y": 3.0} for p in nodes]}
    producer = {"engineSnapshot": {"catalogueManifest": {"versionId": "base"}}}
    before = deepcopy(label)
    assert baseline_reference(label, original, producer, "other")["state"] == "unknown"
    result = baseline_reference(label, original, producer, "base")
    assert result["state"] == "hard" and result["categories"] == []
    assert result["categoryState"] == "unknown" and label == before
    assert source_reference([result], "base")["state"] == "hard"


def test_excluded_closure_is_rechecked_on_freeze_and_cold_currentness(monkeypatch):
    rows = []
    split = {
        "importIds": [],
        "populationSha256": adapter.population_sha(rows),
        "sources": [{"sourceId": "excluded", "newUseExcluded": True, "registryProofSha256": "old"}],
    }
    monkeypatch.setattr(adapter, "population", lambda *args: rows)
    monkeypatch.setattr(
        adapter, "contexts", lambda *args, **kwargs: {"excluded": {"proofSha256": "old"}}
    )
    adapter.validate_population(None, None, split)
    monkeypatch.setattr(
        adapter, "contexts", lambda *args, **kwargs: {"excluded": {"proofSha256": "new-alias"}}
    )
    for freeze in (False, True):
        with pytest.raises(GridCohortError, match="excluded component changed"):
            adapter.validate_population(None, None, split, for_freeze=freeze)


def test_content_partial_train_is_additional_to_ten_full_detector_photos():
    sources = [source(i, frozen_role="TRAIN") for i in range(1, 11)]
    sources += [source(i, frozen_role="VALIDATION") for i in range(11, 16)]
    sources += [source(i, frozen_role="REGRESSION") for i in range(16, 21)]
    partial = replace(source(21), eligible_boards=3)
    legacy = solve_incremental_split([*sources, partial], full_training=True)
    content = solve_incremental_split(
        [*sources, partial], full_training=True, include_partial_train=True
    )
    assert dict(legacy.assignments)[partial.source_id] is None
    assert dict(content.assignments)[partial.source_id] == "TRAIN"
    assert content.role_counts[0].photos == 10 and content.role_counts[0].boards == 90
    with pytest.raises(ValueError, match="minima"):
        solve_incremental_split(
            [*sources[1:], partial], full_training=True, include_partial_train=True
        )


def test_adapter_retains_excluded_population_and_reports_exact_new_use_counts(monkeypatch):
    from test_grid_correction_split_adapter import rows as make_rows

    population = make_rows()[:22]
    bad_import = str(uuid4())
    facts = {}
    for index, row in enumerate(population):
        row["source"]["import_job_id"] = str(uuid4()) if index < 20 else bad_import
        if index >= 20:
            row["revisions"] = []
        role = (
            "TRAIN" if index < 10 or index == 20 else "VALIDATION" if index < 15 else "REGRESSION"
        )
        facts[row["source"]["id"]] = {
            "priorRoles": [role],
            "allowedRoles": [role],
            "componentIds": [],
            "proofSha256": "a" * 64,
            "validationPurposes": ["A"] if role == "VALIDATION" else [],
        }
    monkeypatch.setattr(adapter, "population", lambda *args: population)
    monkeypatch.setattr(adapter, "contexts", lambda *args, **kwargs: facts)
    monkeypatch.setattr(
        adapter,
        "GridCohortEvidenceReader",
        lambda *args: SimpleNamespace(
            capture=lambda *args: {
                "boardEligibleCount": 9,
                "positions": [
                    {
                        "label": {
                            "positionIndex": i,
                            "nodes": [{"x": 0.0, "y": 0.0}] * 24,
                            "approval": {"origin": "human_corrected", "weight": 4},
                        }
                    }
                    for i in range(9)
                ],
            }
        ),
    )
    result = adapter.prepare_split(
        SimpleNamespace(session=None, artifact_root="unused"),
        uuid4(),
        sorted({r["source"]["import_job_id"] for r in population}),
        SimpleNamespace(check=lambda *args: None),
        policy="application-grid-corrections-v4",
        mode="grid-only",
    )
    assert len(result["sources"]) == 22
    excluded = [pin for pin in result["sources"] if pin.get("newUseExcluded")]
    assert len(excluded) == 2
    assert all(pin["role"] is None and not pin["buffer"] for pin in excluded)
    assert result["populationSha256"] == adapter.population_sha(population)
    report = result["learningMaterial"]
    assert report["excludedPhotos"] == 2 and report["excludedBoards"] == 18
    assert report["availablePhotos"] == 20 and report["roles"]["TRAIN"]["correctedBoards"] == 90
    assert report["roles"]["EXCLUDED"]["correctedBoards"] == 18
    assert {
        adapter.split_mapping(result)[pin["sourceId"]]["qualification"] for pin in excluded
    } == {"blocked"}


def test_excluded_neighbors_keep_original_order_alias_closure_and_unlabelled_positions():
    from game_predictor_api.domain.grid_correction_split import solve_correction_split
    from game_predictor_api.domain.grid_learning_material import protect_excluded_neighborhoods
    from game_predictor_api.domain.image_geometry_v2 import sequence_attestation_checksum_sha256

    def ordered(i, boards=9):
        start = i * 9 + 1
        return replace(
            source(100 + i, "ordered"),
            eligible_boards=boards,
            attested_start=start,
            attested_end=start + 8,
            attested_slots=tuple(range(9)),
            board_bindings=tuple((p, start + p) for p in range(9)),
            attestation_checksum_sha256=sequence_attestation_checksum_sha256(
                sequence_range_start=start,
                sequence_range_end=start + 8,
                active_board_slots=tuple(range(9)),
            ),
        )

    ordered_sources = [ordered(i, 0 if 1 <= i <= 9 else 9) for i in range(36)]
    bad = [source(1, "bad", frozen_role="TRAIN"), source(2, "bad", frozen_role="REGRESSION")]
    ordered_sources[0] = replace(ordered_sources[0], pixel_sha256=bad[0].pixel_sha256)
    # A session alias outside the ordered import must share its neighbor's exclusion.
    ordered_sources[10] = replace(ordered_sources[10], component_ids=("neighbor-session",))
    session_alias = source(3, component_ids=("neighbor-session",))
    controls = [
        source(i, frozen_role="VALIDATION" if i < 15 else "REGRESSION") for i in range(10, 20)
    ]
    values = [*bad, *ordered_sources, session_alias, *controls]
    facts = context(values)
    exclusions = conflicting_groups(values, facts)
    masked, exclusions = protect_excluded_neighborhoods(values, facts, exclusions)
    omitted = {s.source_id for s in masked if s.new_use_excluded}
    assert {str(i) for i in range(100, 111)} <= omitted
    assert "3" in omitted and "111" not in omitted  # exactly ten original photo positions
    assert sum(s.new_use_excluded for s in masked) == 14
    for solver in (solve_incremental_split, solve_correction_split):
        split = solver(masked)
        order = next(o for o in split.import_orders if o.import_id == "ordered")
        assert len(order.photo_keys) == 36
        assert all(dict(split.assignments)[key] is None for key in omitted)
        assert not omitted.intersection(split.buffers)
        assert not omitted.intersection(split.representative_sources)
    sample = fresh_regression_preview(
        masked, facts, frozenset(facts), ancestry_sha256="a" * 64, stratified=True
    )
    assert not omitted.intersection(sample["sourceIds"])
    assert set(sample["sourceIds"])  # free far-away groups remain available
    assert any("GRID_CORRECTION_EXCLUDED_NEIGHBORHOOD" in g["reasonCodes"] for g in exclusions)


def test_legacy_selection_state_keeps_full_content_photo_meaning():
    # Five geometry-full photos with only four fully content-labelled ones stay
    # not_evaluable in v1; stratified v2 reports geometry readiness separately.
    values = [source(i, "same") for i in range(1, 7)]
    labelled = frozenset(str(i) for i in range(1, 5))
    legacy = fresh_regression_preview(values, context(values), labelled, ancestry_sha256="a" * 64)
    assert legacy["fullPhotos"] == 4
    assert legacy["state"] == legacy["selectionState"] == "not_evaluable"
    stratified = fresh_regression_preview(
        values, context(values), labelled, ancestry_sha256="a" * 64, stratified=True
    )
    assert stratified["selectionState"] == "ready" and stratified["state"] == "not_evaluable"


def ordered_source(i, boards=9, import_id="ordered", **kwargs):
    from game_predictor_api.domain.image_geometry_v2 import sequence_attestation_checksum_sha256

    start = i * 9 + 1
    return replace(
        source(100 + i, import_id, **kwargs),
        eligible_boards=boards,
        attested_start=start,
        attested_end=start + 8,
        attested_slots=tuple(range(9)),
        board_bindings=tuple((p, start + p) for p in range(9)),
        attestation_checksum_sha256=sequence_attestation_checksum_sha256(
            sequence_range_start=start,
            sequence_range_end=start + 8,
            active_board_slots=tuple(range(9)),
        ),
    )


def test_excluded_historical_anchor_still_buffers_its_own_neighbors():
    from game_predictor_api.domain.grid_correction_split import solve_correction_split
    from game_predictor_api.domain.grid_learning_material import protect_excluded_neighborhoods

    roles = {5: "VALIDATION", 25: "TRAIN", 36: "REGRESSION"}
    ordered = [ordered_source(i, frozen_role=roles.get(i)) for i in range(40)]
    bad = [source(1, "bad", frozen_role="TRAIN"), source(2, "bad", frozen_role="REGRESSION")]
    ordered[0] = replace(ordered[0], pixel_sha256=bad[0].pixel_sha256)
    controls = [
        source(i, frozen_role="TRAIN" if i < 20 else "VALIDATION" if i < 25 else "REGRESSION")
        for i in range(10, 30)
    ]
    values = [*bad, *ordered, *controls]
    facts = context(values)
    exclusions = conflicting_groups(values, facts)
    masked, exclusions = protect_excluded_neighborhoods(values, facts, exclusions)
    by_id = {s.source_id: s for s in masked}
    omitted = {s.source_id for s in masked if s.new_use_excluded}
    # Seed alias 0 plus its ten neighbors; the anchor at 5 is excluded too.
    assert omitted == {"1", "2", *(str(100 + i) for i in range(11))}
    # The excluded VALIDATION anchor still restricts photos 11-14 to VALIDATION.
    assert by_id["112"].allowed_roles == frozenset({"VALIDATION"})
    # Photo 30 lies within ten of both TRAIN and REGRESSION: a forced buffer,
    # never reported as an excluded neighborhood.
    assert by_id["130"].allowed_roles == frozenset() and "130" not in omitted
    reasons = {key: g["reasonCodes"] for g in exclusions for key in g["sourceIds"]}
    assert reasons["105"] == ["GRID_CORRECTION_EXCLUDED_NEIGHBORHOOD"]
    for solver in (solve_incremental_split, solve_correction_split):
        assigned = dict(solver(masked).assignments)
        for anchor, role in roles.items():
            for i in range(max(0, anchor - 10), min(40, anchor + 11)):
                assert assigned[str(100 + i)] in (None, role), (solver, anchor, i)
    sample = fresh_regression_preview(
        masked, facts, frozenset(facts), ancestry_sha256="a" * 64, stratified=True
    )
    near = {str(100 + i) for anchor in (5, 25) for i in range(anchor - 10, anchor + 11)}
    assert not near.intersection(sample["sourceIds"])


def test_exclusion_does_not_widen_fresh_regression_buffer_to_twenty():
    ordered = [ordered_source(i) for i in range(21)]
    bad = [source(1, "bad", frozen_role="TRAIN"), source(2, "bad", frozen_role="REGRESSION")]
    ordered[0] = replace(ordered[0], pixel_sha256=bad[0].pixel_sha256)
    from game_predictor_api.domain.grid_learning_material import protect_excluded_neighborhoods

    values = [*bad, *ordered]
    facts = context(values)
    masked, _ = protect_excluded_neighborhoods(values, facts, conflicting_groups(values, facts))
    sample = fresh_regression_preview(
        masked, facts, frozenset(facts), ancestry_sha256="a" * 64, stratified=True
    )
    # Photos 11-20 have ten unique photos between them and the excluded seed.
    assert sample["selectionState"] == "ready"
    assert set(sample["sourceIds"]) <= {str(100 + i) for i in range(11, 21)}


@pytest.mark.parametrize(
    "requested,code",
    [(None, "GRID_VALIDATION_BUFFER_REQUIRED"), ("B", "GRID_COHORT_MINIMUM_NOT_MET")],
)
def test_excluded_b_anchor_keeps_its_purpose_buffer(requested, code):
    from game_predictor_api.domain.grid_validation_purpose import refine_validation_purposes

    values = [ordered_source(i) for i in range(12)]
    values[0] = replace(values[0], new_use_excluded=True, eligible_boards=0)
    facts = context(values)
    facts["100"].update(priorRoles=["VALIDATION"], validationPurposes=["B"])
    pins = [
        {
            "sourceId": s.source_id,
            "role": "VALIDATION" if s.source_id == "105" else None,
            "buffer": False,
            "representative": s.source_id != "100",
            "eligibleBoards": 9,
        }
        for s in values
    ]
    split = {"sources": pins, "sha256": "x"}
    with pytest.raises(GridCohortError) as error:
        refine_validation_purposes(
            split, values, facts, {"105": requested} if requested else {}, full_training=False
        )
    assert error.value.code == code


def test_content_capture_accepts_excluded_pins_recaptured_with_their_mapping(monkeypatch):
    # P1-1: excluded pins are recaptured in content mode before the preview is
    # sealed, so the real capture page sees the same content-qualified labels.
    from game_predictor_api.application import grid_training_cohort_commands as commands
    from game_predictor_api.storage import grid_content_sampling as sampling_storage
    from game_predictor_api.storage import grid_render_selection
    from test_grid_correction_split_adapter import rows as make_rows

    population = make_rows()[:22]
    bad_import = str(uuid4())
    facts = {}
    for index, row in enumerate(population):
        row["source"]["import_job_id"] = str(uuid4()) if index < 20 else bad_import
        if index >= 20:
            row["revisions"] = []
        role = (
            "TRAIN" if index < 10 or index == 20 else "VALIDATION" if index < 15 else "REGRESSION"
        )
        facts[row["source"]["id"]] = {
            "priorRoles": [role],
            "allowedRoles": [role],
            "componentIds": [],
            "proofSha256": "a" * 64,
            "validationPurposes": ["A"] if role == "VALIDATION" else [],
            "selectionExposed": False,
            "diagnosticExposed": False,
        }

    def capture(game, source_id, ordinal, recording, mode):
        content = "contentSamplingPolicy" in recording
        return {
            "boardEligibleCount": 9,
            "positions": [
                {
                    "positionIndex": i,
                    "reason": None,
                    "label": {
                        "positionIndex": i,
                        "nodes": [{"x": 0.0, "y": 0.0}] * 24,
                        "approval": {"origin": "human_corrected", "weight": 4},
                        **({"contentAnnotation": {"pin": str(source_id)}} if content else {}),
                    },
                }
                for i in range(9)
            ],
        }

    monkeypatch.setattr(adapter, "population", lambda *args: population)
    monkeypatch.setattr(adapter, "contexts", lambda *args, **kwargs: facts)
    reader = SimpleNamespace(capture=capture)
    monkeypatch.setattr(adapter, "GridCohortEvidenceReader", lambda *args: reader)
    monkeypatch.setattr(commands, "GridCohortEvidenceReader", lambda *args: reader)
    monkeypatch.setattr(
        sampling_storage,
        "constrain_content_regression",
        lambda repo, game, sources, contexts, policy, deadline, references=None: (
            sources,
            {"policy": policy["policy"], "state": "ready", "excludedLegacyRegressionSourceIds": []},
        ),
    )
    monkeypatch.setattr(grid_render_selection, "select_a_render_contract", lambda *args: None)
    deadline = SimpleNamespace(check=lambda *args: None)
    split = adapter.prepare_split(
        SimpleNamespace(session=None, artifact_root="unused"),
        uuid4(),
        sorted({r["source"]["import_job_id"] for r in population}),
        deadline,
        policy="application-grid-corrections-v4",
        mode="grid-only",
        content_sampling={"policy": "full-symbol-content-sampling-v1", "baseVersionId": "base"},
    )
    excluded = [pin for pin in split["sources"] if pin.get("newUseExcluded")]
    assert len(excluded) == 2 and all("qualifiedLabelsSha256" in pin for pin in excluded)
    mapping = adapter.split_mapping(split)
    assert all("contentSamplingPolicy" in mapping[pin["sourceId"]] for pin in excluded)

    class Published(Exception):
        pass

    def publish(*args):
        raise Published

    repo = SimpleNamespace(
        session=None,
        next_capture=lambda row: 0,
        members=lambda *args: [
            SimpleNamespace(source_id=UUID(pin["sourceId"]), ordinal=ordinal)
            for ordinal, pin in enumerate(split["sources"])
        ],
    )
    service = SimpleNamespace(
        repository=repo, artifacts=SimpleNamespace(root="unused", publish_json=publish)
    )
    row = SimpleNamespace(
        id=uuid4(),
        status="preparing",
        document={
            "policyVersion": "application-grid-corrections-v4",
            "photoSplit": split,
            "mode": "grid-only",
        },
    )
    # Reaching publication proves every member, including exclusions, matched.
    with pytest.raises(Published):
        commands._capture(service, uuid4(), row, {"cursor": 0}, deadline)


def test_malformed_historical_proof_is_unknown_with_reason_not_a_crash():
    from game_predictor_api.domain.neural_grid_proposal import NeuralGridProposalError
    from game_predictor_api.storage.grid_quality_observations import original_target

    revision = {
        "id": "r1",
        "revision": 1,
        "source_checksum_sha256": "a" * 64,
        "normalized_pixel_checksum_sha256": "b" * 64,
        "board_geometries": ["not-an-object", {"positionIndex": 0, "sequenceNumber": 5}],
        "geometry_source": "auto",
        "global_initialization": {"gridReinference": "corrupt"},
    }
    session = SimpleNamespace(
        execute=lambda *args: SimpleNamespace(scalar_one_or_none=lambda: revision)
    )
    metadata = {
        "id": "s",
        "checksum_sha256": "a" * 64,
        "normalized_pixel_checksum_sha256": "b" * 64,
    }
    target = {
        "board": {
            "source_geometry_revision_id": "r1",
            "geometry_revision": 1,
            "sequence_number": 5,
            "position_index": 0,
            "board_geometry": {},
        },
        "review": {"id": "v"},
    }
    with pytest.raises(NeuralGridProposalError) as error:
        original_target(session, uuid4(), metadata, target)
    assert error.value.code == "NEURAL_GRID_PROOF_INVALID"
    nodes = [{"x": float(i), "y": 0.0} for i in range(24)]
    label = {"positionIndex": 0, "nodes": nodes, "approval": {"origin": "human_corrected"}}
    producer = {"engineSnapshot": {"catalogueManifest": {"versionId": "base"}}}
    reference = baseline_reference(
        label, {"latticeNodes": nodes}, producer, "base", error.value.code
    )
    assert reference["state"] == "unknown"
    assert reference["reasonCode"] == "NEURAL_GRID_PROOF_INVALID"


def test_infeasible_split_reports_exact_protected_role_shortfalls():
    from game_predictor_api.domain.grid_correction_split import CorrectionSplitError
    from game_predictor_api.domain.grid_learning_material import role_shortfalls

    values = [source(i, frozen_role="TRAIN") for i in range(1, 11)]
    values += [source(i, frozen_role="VALIDATION") for i in range(11, 15)]
    values += [source(i, frozen_role="REGRESSION") for i in range(15, 20)]
    with pytest.raises(CorrectionSplitError) as error:
        solve_incremental_split(values)
    report = role_shortfalls(error.value.role_counts)
    assert report["roles"]["VALIDATION"] == {
        "photos": 4,
        "boards": 36,
        "minimumPhotos": 5,
        "minimumBoards": 15,
        "photoDeficit": 1,
        "boardDeficit": 0,
    }
    assert report["roles"]["TRAIN"]["photoDeficit"] == 0
