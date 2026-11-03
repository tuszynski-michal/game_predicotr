"""Metadata adapter integrates genuine-proof reader, solver pins and population fencing."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.image_geometry_v2 import sequence_attestation_checksum_sha256
from game_predictor_api.storage import grid_correction_split as adapter


def rows():
    import_id = str(uuid4())
    output = []
    for index in range(40):
        start = index * 9 + 1
        sha = f"{index + 1:064x}"
        source = {
            "id": str(uuid4()),
            "import_job_id": import_id,
            "checksum_sha256": sha,
            "normalized_pixel_checksum_sha256": sha,
            "oriented_width": 100,
            "oriented_height": 100,
            "coordinate_space": "pixels",
            "normalization_adapter_version": "fixture",
            "relative_path": sha + ".jpg",
        }
        revision = {
            "revision_id": str(uuid4()),
            "status": "active",
            "source_checksum_sha256": sha,
            "sequence_range_start": start,
            "sequence_range_end": start + 8,
            "active_board_slots": list(range(9)),
            "sequence_attestation_checksum_sha256": sequence_attestation_checksum_sha256(
                sequence_range_start=start,
                sequence_range_end=start + 8,
                active_board_slots=tuple(range(9)),
            ),
            **{
                k: source[k]
                for k in (
                    "normalized_pixel_checksum_sha256",
                    "normalization_adapter_version",
                    "oriented_width",
                    "oriented_height",
                    "coordinate_space",
                )
            },
        }
        output.append(
            {
                "source": source,
                "logicalName": sha + ".jpg",
                "approved": True,
                "revisions": [revision],
                "bindings": [(i, start + i) for i in range(9)],
            }
        )
    return output


def test_prepare_uses_proof_counts_and_preserves_all_sources_without_permanent_use(monkeypatch):
    population = rows()
    calls = []

    class Reader:
        def __init__(self, *args):
            pass

        def capture(self, game, source, ordinal, recording, mode):
            calls.append(source)
            assert mode == "grid-only"
            return {
                "boardEligibleCount": 3,
                "positions": [{"label": {"positionIndex": i}} for i in range(3)],
            }

    monkeypatch.setattr(adapter, "population", lambda *args: population)
    monkeypatch.setattr(adapter, "GridCohortEvidenceReader", Reader)
    monkeypatch.setattr(
        adapter,
        "contexts",
        lambda repo, game, ids, **kwargs: {
            key: {
                "componentIds": [],
                "allowedRoles": ["TRAIN", "VALIDATION", "REGRESSION"],
                "priorRoles": [],
                "proofSha256": "f" * 64,
            }
            for key in ids
        },
    )
    repo = SimpleNamespace(session=object(), artifact_root="unused")
    split = adapter.prepare_split(
        repo,
        uuid4(),
        [population[0]["source"]["import_job_id"]],
        SimpleNamespace(check=lambda *args: None),
    )
    assert len(calls) == 40
    assert len(split["sources"]) == 40
    assert sum(s["buffer"] for s in split["sources"]) == 20
    assert sum(c["photos"] for c in split["roleCounts"]) == 20
    assert all(o["method"] == "verified-attestation-order-v1" for o in split["importOrders"])
    assert split["evidenceLevel"] == "photo-only"
    adapter.validate_population(repo, uuid4(), split)
    population[0]["bindings"][0] = (0, 999)
    with pytest.raises(GridCohortError) as changed:
        adapter.validate_population(repo, uuid4(), split)
    assert changed.value.code == "GRID_CORRECTION_POPULATION_CHANGED"


def test_population_fence_ignores_symbol_status_but_not_source_membership():
    original = rows()
    changed = deepcopy(original)
    changed[0]["source"]["status"] = "corrected"
    assert adapter.population_sha(original) == adapter.population_sha(changed)
    assert adapter.population_sha(original) != adapter.population_sha(changed[:-1])


def test_pending_reserve_changes_fence_only_freeze_not_historical_currentness(monkeypatch):
    original = rows()
    original[0]["pendingCorrection"] = True
    split = {
        "schemaVersion": "grid-correction-split-v2",
        "importIds": [],
        "populationSha256": adapter.population_sha(original),
        "sources": [
            {
                "sourceId": original[0]["source"]["id"],
                "pendingCorrection": True,
                "role": "REGRESSION",
                "eligibleBoards": 0,
            }
        ],
    }
    original[0]["pendingCorrection"] = False
    monkeypatch.setattr(adapter, "population", lambda *args: original)
    adapter.validate_population(None, uuid4(), split)
    with pytest.raises(GridCohortError, match="no longer awaiting"):
        adapter.validate_population(None, uuid4(), split, for_freeze=True)


def test_population_fence_allows_new_geometry_revision_with_identical_attestation():
    original = rows()
    changed = deepcopy(original)
    changed[0]["revisions"][0].update(revision_id=str(uuid4()), status="superseded")
    assert adapter.population_sha(original) == adapter.population_sha(changed)
    changed[0]["revisions"][0]["status"] = "reverted"
    assert adapter.population_sha(original) != adapter.population_sha(changed)


@pytest.mark.parametrize("count,protected", [(1, False), (40, True)])
def test_infeasible_adapter_error_keeps_available_counts(monkeypatch, count, protected):
    population = rows()[:count]
    duplicate = deepcopy(population[0])
    duplicate["source"]["id"] = str(uuid4())
    population.append(duplicate)
    reads = []

    def read(*args):
        reads.append(1)
        return population

    monkeypatch.setattr(adapter, "population", read)
    monkeypatch.setattr(
        adapter,
        "contexts",
        lambda repo, game, ids, **kwargs: {
            key: {
                "componentIds": [],
                "allowedRoles": ["TRAIN"] if protected else ["TRAIN", "VALIDATION", "REGRESSION"],
                "priorRoles": [],
                "proofSha256": "f" * 64,
            }
            for key in ids
        },
    )
    monkeypatch.setattr(
        adapter,
        "GridCohortEvidenceReader",
        lambda *args: SimpleNamespace(
            capture=lambda *args: {
                "boardEligibleCount": 3,
                "positions": [{"label": {"positionIndex": i}} for i in range(3)],
            }
        ),
    )
    with pytest.raises(GridCohortError) as error:
        adapter.prepare_split(
            SimpleNamespace(session=None, artifact_root="unused"),
            uuid4(),
            [population[0]["source"]["import_job_id"]],
            SimpleNamespace(check=lambda *args: None),
        )
    assert error.value.code.startswith("GRID_CORRECTION_SPLIT_")
    assert f"Available photos: {count}; boards: {count * 3}" in str(error.value)
    assert error.value.data_availability == {
        "photos": count,
        "boards": count * 3,
        "minimumPhotos": 20,
        "minimumBoards": 60,
        "photoDeficit": max(0, 20 - count),
        "boardDeficit": max(0, 60 - count * 3),
        "splitStatus": "infeasible" if protected else "minima",
    }
    assert len(reads) == 1


def test_capture_rejects_labels_changed_since_split_before_publishing(monkeypatch):
    from game_predictor_api.application import grid_training_cohort_commands as commands

    key = uuid4()
    repo = SimpleNamespace(
        session=None,
        next_capture=lambda row: 0,
        members=lambda *args: [SimpleNamespace(source_id=key, ordinal=0)],
    )
    service = SimpleNamespace(repository=repo, artifacts=SimpleNamespace(root="unused"))
    row = SimpleNamespace(
        id=uuid4(),
        status="preparing",
        document={
            "policyVersion": adapter.CORRECTIONS_POLICY,
            "photoSplit": {},
            "mode": "grid-only",
        },
    )
    monkeypatch.setattr(commands, "validate_population", lambda *args: None)
    monkeypatch.setattr(
        commands,
        "split_mapping",
        lambda *args: {str(key): {"qualification": "eligible", "expectedBoardCount": 3}},
    )
    monkeypatch.setattr(
        commands,
        "GridCohortEvidenceReader",
        lambda *args: SimpleNamespace(capture=lambda *args: {"boardEligibleCount": 2}),
    )
    with pytest.raises(GridCohortError) as error:
        commands._capture(
            service, uuid4(), row, {"cursor": 0}, SimpleNamespace(check=lambda *args: None)
        )
    assert error.value.code == "GRID_CORRECTION_LABELS_CHANGED"


@pytest.mark.parametrize("roles", [["TRAIN", "VALIDATION"], ["VALIDATION"], []])
def test_ambiguous_or_roleless_external_protection_fails_closed(monkeypatch, roles):
    population = rows()[:1]
    monkeypatch.setattr(adapter, "population", lambda *args: population)
    monkeypatch.setattr(
        adapter,
        "contexts",
        lambda repo, game, ids, **kwargs: {
            ids[0]: {
                "componentIds": [],
                "allowedRoles": [],
                "priorRoles": roles,
                "proofSha256": "a" * 64,
            }
        },
    )
    monkeypatch.setattr(
        adapter,
        "GridCohortEvidenceReader",
        lambda *args: SimpleNamespace(
            capture=lambda *args: {
                "boardEligibleCount": 3,
                "positions": [{"label": {"positionIndex": i}} for i in range(3)],
            }
        ),
    )
    with pytest.raises(GridCohortError) as error:
        adapter.prepare_split(
            SimpleNamespace(session=None, artifact_root="unused"),
            uuid4(),
            [population[0]["source"]["import_job_id"]],
            SimpleNamespace(check=lambda *args: None),
        )
    assert error.value.code == "GRID_CORRECTION_PROTECTION_CONFLICT"


def test_used_train_targets_survive_changed_copy_representative_but_not_new_geometry():
    label = {"positionIndex": 0, "nodes": [[0, 0], [1, 1]], "revision": 1}
    alias = {"sourcePixelSha256": "a" * 64, "positionIndex": 0, "nodes": label["nodes"]}
    context = {"usedTrainAliasLabels": [alias], "usedTrainLabels": []}
    assert adapter.previously_used_train_boards([label], context, "a" * 64) == 1
    assert (
        adapter.previously_used_train_boards(
            [{**label, "nodes": [[-0.0, 0.0], [1.0, 1.0]]}], context, "a" * 64
        )
        == 1
    )
    assert adapter.previously_used_train_boards([label], context, "b" * 64) == 0
    assert (
        adapter.previously_used_train_boards([{**label, "nodes": [[0, 1]]}], context, "a" * 64) == 0
    )
    assert (
        adapter.previously_used_train_boards([{**label, "positionIndex": 1}], context, "a" * 64)
        == 0
    )
    # Own-source revision identity takes precedence over an identical alias target.
    context["usedTrainLabels"] = [label]
    assert adapter.previously_used_train_boards([label], context, "a" * 64) == 1
    assert adapter.previously_used_train_boards([{**label, "revision": 2}], context, "a" * 64) == 0
