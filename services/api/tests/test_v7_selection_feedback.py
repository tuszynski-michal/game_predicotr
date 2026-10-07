from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import pytest
from game_predictor_api.domain.v7_selection_delivery import V7OutputDecision, payload_fingerprint
from game_predictor_api.domain.v7_selection_feedback import V7FeedbackOwner, build_feedback_manifest
from game_predictor_api.storage.v7_selection_feedback import verify_feedback_source
from game_predictor_worker.semi_automatic_selection.v7_delivery import output_receipt
from test_v7_selection_delivery_api import decision_body, delivery_fixture

from scripts.export_v7_selection_feedback import publish_feedback_manifest


def feedback_operation(tmp_path):
    client, repository, _, run, manifest = delivery_fixture(tmp_path)
    item = repository.ranges[(run.id, 1)]
    repository.ranges[(run.id, 1)] = replace(
        item,
        v7_review={
            **item.v7_review,
            "candidate": {"sourceIndex": 0, "sourceId": "a" * 64, "proofKinds": [], "warnings": []},
        },
    )
    body = {**decision_body(run, manifest), "correctionReason": "occlusion"}
    response = client.post(
        f"/admin/semi-automatic-image-selections/{run.id}/ranges/1/output-acknowledgements",
        json=body,
    )
    assert response.status_code == 200, response.text
    operation = next(iter(repository.operations.values()))
    operation = replace(
        operation, state="committed", receipt=output_receipt(operation, "committed")
    )
    owner = V7FeedbackOwner(operation.operation_id, 0, manifest.sources[0].checksum_sha256, 0)
    return operation, owner, manifest


def compile_feedback(operations, owner):
    first = operations[0]
    return build_feedback_manifest(
        operations, {(first.run_id, first.range_id): owner}, validate_source=verify_feedback_source
    )


def test_empty_feedback_is_not_evaluable():
    report = build_feedback_manifest([], {}, validate_source=verify_feedback_source)["report"]
    assert report["status"] == "not_evaluable"
    assert report["agreementRate"] is None
    assert report["trainingStatus"] == "not_trained"


def test_receipt_retry_dedup_and_restart_of_immutable_export(tmp_path):
    operation, owner, _manifest = feedback_operation(tmp_path)
    manifest = compile_feedback([operation, operation], owner)
    assert len(manifest["history"]) == len(manifest["examples"]) == 1
    assert manifest["individualSymbolLabels"] is False
    assert manifest["report"]["manualWithoutOcrCount"] == 1
    target = publish_feedback_manifest(tmp_path / "feedback", manifest)
    assert publish_feedback_manifest(tmp_path / "feedback", manifest) == target
    # New interpreter reads the artifact, recalculates its digest and republishes exact bytes.
    script = (
        "import json,sys; from pathlib import Path; "
        "from scripts.export_v7_selection_feedback import publish_feedback_manifest; "
        "from game_predictor_api.domain.v7_selection_delivery import payload_fingerprint; "
        "p=Path(sys.argv[1]); v=json.loads(p.read_text(encoding='utf-8')); "
        "assert v['fingerprint']==payload_fingerprint(v['manifest']); "
        "assert publish_feedback_manifest(p.parent,v['manifest'])==p"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(target)], capture_output=True, timeout=20
    )
    assert result.returncode == 0, result.stderr.decode()
    target.write_text("foreign bytes", encoding="utf-8")
    with pytest.raises(ValueError, match="differs"):
        publish_feedback_manifest(target.parent, manifest)


@pytest.mark.parametrize("state", ["reserved", "recovery_required", "conflict", "failed"])
def test_non_committed_operation_never_becomes_example(tmp_path, state):
    operation, owner, _ = feedback_operation(tmp_path)
    manifest = compile_feedback([replace(operation, state=state)], owner)
    assert manifest["examples"] == []
    assert manifest["report"]["excludedOperations"] == {"operation_" + state: 1}


@pytest.mark.parametrize(
    "field", ["outputChecksumSha256", "ownerOperationId", "decisionGeneration", "confirmedRange"]
)
def test_receipt_must_match_entire_committed_decision(tmp_path, field):
    operation, owner, _ = feedback_operation(tmp_path)
    receipt = {**operation.receipt, field: "incorrect"}
    result = compile_feedback([replace(operation, receipt=receipt)], owner)
    assert result["report"]["excludedOperations"] == {"receipt_invalid": 1}
    assert result["examples"] == []


@pytest.mark.parametrize("field", ["sourceIndex", "decisionGeneration"])
def test_json_boolean_cannot_impersonate_integer_in_receipt(tmp_path, field):
    operation, owner, _ = feedback_operation(tmp_path)
    receipt = {**operation.receipt, field: False}
    result = compile_feedback([replace(operation, receipt=receipt)], owner)
    assert result["report"]["excludedOperations"] == {"receipt_invalid": 1}


def test_replacement_history_survives_but_only_current_owner_is_preference(tmp_path):
    first, _, _ = feedback_operation(tmp_path)
    request = {
        **first.request_payload,
        "operationId": str(uuid4()),
        "kind": "manual_replace",
        "expectedOwnerOperationId": str(first.operation_id),
        "expectedTargetChecksumSha256": first.decision.expected_source_checksum_sha256,
    }
    replacement = replace(
        first,
        operation_id=V7OutputDecision.from_payload(request).operation_id,
        request_payload=request,
        decision_generation=1,
    )
    replacement = replace(replacement, receipt=output_receipt(replacement, "committed"))
    owner = V7FeedbackOwner(
        replacement.operation_id, 0, first.decision.expected_source_checksum_sha256, 1
    )
    result = compile_feedback([replacement, first], owner)
    assert len(result["history"]) == 2
    assert [item["operationId"] for item in result["examples"]] == [str(replacement.operation_id)]
    assert result["report"]["replacementCount"] == 1
    assert result["history"][0]["decision"]["correctionReason"] == "occlusion"


def test_missing_snapshot_and_missing_receipt_are_explicit_exclusions(tmp_path):
    operation, owner, _ = feedback_operation(tmp_path)
    assert compile_feedback([replace(operation, context_payload={})], owner)["report"][
        "excludedOperations"
    ] == {"legacy_context_missing": 1}
    assert compile_feedback([replace(operation, receipt=None)], owner)["report"][
        "excludedOperations"
    ] == {"receipt_invalid": 1}


def test_source_drift_and_invalid_owner_are_excluded(tmp_path):
    operation, owner, manifest = feedback_operation(tmp_path)
    invalid_owner = replace(owner, checksum_sha256="a" * 64)
    assert compile_feedback([operation], invalid_owner)["report"]["excludedOperations"] == {
        "owner_invalid": 1
    }
    (manifest.source_root / "1.jpg").write_bytes(b"changed-source-content")
    result = compile_feedback([operation], owner)
    assert result["examples"] == []
    assert result["report"]["excludedOperations"] == {"source_changed": 1}


@pytest.mark.parametrize("path", ["../outside.jpg", "D:/outside.jpg", "/outside.jpg"])
def test_even_rehashed_snapshot_cannot_escape_source_root(tmp_path, path):
    operation, owner, _ = feedback_operation(tmp_path)
    context = deepcopy(operation.context_payload)
    context["feedbackSnapshot"]["selectedSource"]["relativePath"] = path
    context["sourceRelativePath"] = path
    context["feedbackFingerprint"] = payload_fingerprint(context["feedbackSnapshot"])
    result = compile_feedback([replace(operation, context_payload=context)], owner)
    assert result["report"]["excludedOperations"] == {"source_path_invalid": 1}


def test_snapshot_fingerprint_detects_mutated_diagnostics(tmp_path):
    operation, owner, _ = feedback_operation(tmp_path)
    context = deepcopy(operation.context_payload)
    context["feedbackSnapshot"]["selectedDiagnostics"]["sourceIndex"] = 9
    result = compile_feedback([replace(operation, context_payload=context)], owner)
    assert result["report"]["excludedOperations"] == {"snapshot_invalid": 1}


def test_no_proposal_is_separate_from_algorithm_agreement(tmp_path):
    operation, owner, _ = feedback_operation(tmp_path)
    context = deepcopy(operation.context_payload)
    context["feedbackSnapshot"]["proposal"] = None
    context["feedbackSnapshot"]["proposalSource"] = None
    context["feedbackFingerprint"] = payload_fingerprint(context["feedbackSnapshot"])
    result = compile_feedback([replace(operation, context_payload=context)], owner)
    assert result["report"]["outcomes"] == {"no_proposal": 1}
    assert result["report"]["agreementRate"] is None
    assert json.dumps(result, allow_nan=False)


def test_missing_replacement_predecessor_blocks_example(tmp_path):
    first, _, _ = feedback_operation(tmp_path)
    request = {
        **first.request_payload,
        "operationId": str(uuid4()),
        "kind": "manual_replace",
        "expectedOwnerOperationId": str(uuid4()),
        "expectedTargetChecksumSha256": first.decision.expected_source_checksum_sha256,
    }
    operation = replace(
        first,
        operation_id=V7OutputDecision.from_payload(request).operation_id,
        request_payload=request,
        decision_generation=1,
    )
    operation = replace(operation, receipt=output_receipt(operation, "committed"))
    owner = V7FeedbackOwner(
        operation.operation_id, 0, operation.decision.expected_source_checksum_sha256, 1
    )
    assert compile_feedback([operation], owner)["report"]["excludedOperations"] == {
        "replacement_chain_invalid": 1
    }


def test_storage_export_requires_consistent_read_only_and_never_silently_truncates(tmp_path):
    from game_predictor_api.storage.v7_selection_feedback import read_feedback_manifest

    operation, _, _ = feedback_operation(tmp_path)

    class Session:
        read_only = "off"
        rows = []

        def scalar(self, statement):
            return self.read_only if "read_only" in str(statement) else "repeatable read"

        def scalars(self, statement):
            assert "checkpoint" not in str(statement)
            return [operation.run_id]

        def execute(self, statement):
            assert "checkpoint" not in str(statement)
            return self

        def all(self):
            return self.rows

    session = Session()
    with pytest.raises(ValueError, match="REPEATABLE READ READ ONLY"):
        read_feedback_manifest(session, [operation.run_id])
    session.read_only = "on"
    assert (
        read_feedback_manifest(session, [operation.run_id])["report"]["status"] == "not_evaluable"
    )
    session.rows = [None, None]
    with pytest.raises(ValueError, match="limit exceeded"):
        read_feedback_manifest(session, [operation.run_id], maximum_operations=1)
