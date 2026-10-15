"""Closed transport, trusted provider installation and restart-safe evidence."""

import hashlib
import json
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from game_predictor_api.api.source_recording_groups import create_source_recording_groups_router
from game_predictor_api.application.source_recording_groups import RecordingManifestStore
from game_predictor_api.config import ApiSettings, ConfigurationError
from game_predictor_api.domain.source_recording_groups import (
    RecordingError,
    resolve_ancestor_references,
)
from game_predictor_api.schemas.source_recording_groups import SourceRecordingCommandRequest
from game_predictor_api.storage.source_recording_providers import (
    TrustedRecordingProviders,
    install_recording_provider,
)
from pydantic import ValidationError


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor", "local-owner"),
        ("byteSha256", "a" * 64),
        ("providerJSON", {}),
        ("path", "../foreign"),
    ],
)
def test_http_command_cannot_supply_trust(field, value):
    with pytest.raises(ValidationError):
        SourceRecordingCommandRequest.model_validate(
            {
                "kind": "declare",
                "idempotencyKey": str(uuid4()),
                "groupId": str(uuid4()),
                "independenceConfirmed": True,
                field: value,
            }
        )


def test_declared_independence_and_page_bounds_are_explicit():
    for command in (
        {"kind": "declare", "groupId": str(uuid4())},
        {"kind": "prepare", "selection": {"sourceIds": [str(uuid4()) for _ in range(201)]}},
        {"kind": "freeze", "groupId": str(uuid4()), "familyId": str(uuid4())},
    ):
        with pytest.raises(ValidationError):
            SourceRecordingCommandRequest.model_validate(
                {"idempotencyKey": str(uuid4()), **command}
            )


def test_providers_persist_and_do_not_assume_photo_only_is_whole_recording(tmp_path):
    version = str(uuid4())
    ancestor = {
        "versionId": version,
        "manifestSha256": "a" * 64,
        "snapshotId": "owned-fixture",
        "cohortId": None,
        "publicationEvidenceSha256": None,
        "historicalReportSha256": None,
        "evaluation": None,
    }
    lineage = {"ancestors": [ancestor]}
    assert not resolve_ancestor_references(lineage, {}).complete
    payload = {
        "schemaVersion": "recording-ancestor-provider-v1",
        "ancestor": ancestor,
        "complete": True,
        "recordingIdentityAvailable": False,
        "recordingGroups": [],
    }
    source = tmp_path / "provider.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    index_sha = install_recording_provider(
        tmp_path / "artifacts", source, hashlib.sha256(source.read_bytes()).hexdigest(), None
    )
    # Fresh object reads the durable, server-pinned index; no in-memory install state.
    registry = TrustedRecordingProviders(tmp_path / "artifacts", index_sha)
    assert not resolve_ancestor_references(lineage, registry.read(lineage)).complete
    payload["recordingIdentityAvailable"] = True
    source.write_text(json.dumps(payload), encoding="utf-8")
    next_sha = install_recording_provider(
        tmp_path / "artifacts", source, hashlib.sha256(source.read_bytes()).hexdigest(), index_sha
    )
    assert resolve_ancestor_references(
        lineage, TrustedRecordingProviders(tmp_path / "artifacts", next_sha).read(lineage)
    ).complete
    assert (
        install_recording_provider(
            tmp_path / "artifacts",
            source,
            hashlib.sha256(source.read_bytes()).hexdigest(),
            index_sha,
        )
        == next_sha
    )
    payload["recordingGroups"] = [{"groupId": str(uuid4()), "role": "TRAIN"}]
    assert resolve_ancestor_references(lineage, {version: payload}).complete
    payload["ancestor"]["sourcePath"] = "private-source-path"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RecordingError, match="invalid"):
        install_recording_provider(
            tmp_path / "artifacts",
            source,
            hashlib.sha256(source.read_bytes()).hexdigest(),
            next_sha,
        )
    with pytest.raises(RecordingError, match="checksum differs"):
        registry.read(lineage)
    with pytest.raises(RecordingError):
        install_recording_provider(tmp_path / "artifacts", source, "0" * 64, next_sha)


def test_membership_atomic_publish_never_replaces_prior_evidence(tmp_path):
    destination = tmp_path / "page.json"
    checksum = RecordingManifestStore.publish(destination, {"sources": ["one"]})
    assert RecordingManifestStore.publish(destination, {"sources": ["one"]}) == checksum
    with pytest.raises(RecordingError):
        RecordingManifestStore.publish(destination, {"sources": ["different"]})
    assert RecordingManifestStore.read(destination, checksum) == {"sources": ["one"]}


def test_provider_config_is_strict_and_optional():
    assert ApiSettings.from_environment({}).recording_provider_index_sha256 is None
    with pytest.raises(ConfigurationError):
        ApiSettings.from_environment({"GAME_PREDICTOR_RECORDING_PROVIDER_INDEX_SHA256": "wrong"})


def test_http_requires_trusted_actor_and_returns_committable_typed_refusal():
    game, group, manifest, key = (str(uuid4()) for _ in range(4))
    calls = []

    class Service:
        def execute(self, wanted, command, actor):
            calls.append((wanted, command, actor))
            return {
                "commandKind": "assign_role",
                "idempotencyKey": key,
                "statusCode": 409,
                "reasonCode": "RECORDING_PROTECTED",
                "group": {
                    "id": group,
                    "revision": 2,
                    "membershipComplete": True,
                    "expectedSources": 1,
                    "registeredSources": 1,
                    "manifestId": manifest,
                    "manifestSha256": "a" * 64,
                    "pageCount": 1,
                    "declared": True,
                    "independent": True,
                    "role": "TRAIN",
                    "qualification": "blocked",
                    "reasonCodes": ["RECORDING_PROTECTED"],
                },
            }

    application = FastAPI()

    @application.middleware("http")
    async def trusted_context(request: Request, call_next):
        if request.headers.get("x-test-trusted-proof") == "yes":
            request.state.local_admin_actor = "local-owner"
        return await call_next(request)

    @application.exception_handler(RecordingError)
    async def handle(_request, error):
        return JSONResponse(status_code=error.status, content={"code": error.code})

    application.include_router(create_source_recording_groups_router(lambda: Service()))
    client = TestClient(application)
    body = {
        "kind": "assign_role",
        "idempotencyKey": key,
        "groupId": group,
        "expectedRevision": 1,
        "familyId": str(uuid4()),
        "role": "TRAIN",
    }
    url = f"/api/v1/admin/games/{game}/source-recording-groups/commands"
    assert client.post(url, json=body).status_code == 403
    response = client.post(url, json=body, headers={"x-test-trusted-proof": "yes"})
    assert response.status_code == 409
    assert response.json()["details"]["receipt"]["idempotencyKey"] == key
    assert len(calls) == 1 and calls[0][2] == "local-owner"
