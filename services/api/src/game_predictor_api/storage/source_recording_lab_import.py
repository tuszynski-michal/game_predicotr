"""Explicit owner-only deployment of bounded, checksum-pinned LAB metadata.

No images are opened and no file paths enter the registry. Callers commit each
page and the final receipt separately, then publish the provider file index.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import text
from sqlalchemy.engine import Connection

from game_predictor_api.domain.source_recording_groups import (
    PROTECTED_ROLES,
    RecordingError,
    canonical_recording_json,
    recording_sha256,
)
from game_predictor_api.storage.source_recording_providers import _ancestor_is_closed, read_provider

_SHA = re.compile(r"[0-9a-f]{64}")
_ALGORITHM = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,99}")
_ACTOR = "deployment:recording-provider"
_MAX_BYTES = 1_048_576
_MAX_PAGES = 512
_MAX_GROUPS = 4096


def _invalid(message: str) -> RecordingError:
    return RecordingError("RECORDING_LAB_IMPORT_INVALID", message, 422)


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise _invalid("Metadata reference must be an exact SHA256.")
    return value


def lab_group_id(provider_identity_sha256: str, recording_ref_sha256: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"recording-lab:{_sha(provider_identity_sha256)}:{_sha(recording_ref_sha256)}",
    )


def lab_photo_group_id(provider_identity_sha256: str, source_ref_sha256: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"recording-lab:{_sha(provider_identity_sha256)}:photo:{_sha(source_ref_sha256)}",
    )


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid("Metadata has duplicate JSON fields.")
        result[key] = value
    return result


@dataclass(frozen=True)
class MetadataPin:
    path: Path
    sha256: str


def _read_metadata(pin: MetadataPin) -> dict[str, Any]:
    try:
        if (
            pin.path.is_symlink()
            or pin.path.is_junction()
            or not pin.path.is_file()
            or pin.path.suffix.lower() != ".json"
        ):
            raise _invalid("Pinned metadata must be a regular JSON file.")
        with pin.path.open("rb") as source:
            content = source.read(_MAX_BYTES + 1)
        if len(content) > _MAX_BYTES or hashlib.sha256(content).hexdigest() != _sha(pin.sha256):
            raise _invalid("Pinned metadata size or checksum differs.")
        payload = json.loads(
            content,
            object_pairs_hook=_json_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                _invalid("Metadata has a non-finite JSON number.")
            ),
        )
        if not isinstance(payload, dict):
            raise _invalid("Metadata must be a JSON object.")
        return cast(dict[str, Any], payload)
    except (OSError, ValueError, TypeError) as error:
        if isinstance(error, RecordingError):
            raise
        raise _invalid("Pinned metadata is unavailable or invalid.") from error


def _pin(root: Path, value: object) -> MetadataPin:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise _invalid("Metadata file reference is invalid.")
    relative = value["path"]
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise _invalid("Metadata reference must remain inside its manifest directory.")
    path = root / relative
    if ".." in Path(relative).parts or not path.resolve().is_relative_to(root.resolve()):
        raise _invalid("Metadata reference escapes its manifest directory.")
    current = path
    while current != root:
        if current.is_symlink() or current.is_junction():
            raise _invalid("Metadata reference crosses a link.")
        current = current.parent
    return MetadataPin(path, _sha(value["sha256"]))


@dataclass(frozen=True)
class LabGroup:
    reference_sha256: str
    expected_sources: int
    role: str
    independent: bool


@dataclass(frozen=True)
class LabImportManifest:
    manifest_sha256: str
    provider_identity_sha256: str
    provider: dict[str, Any]
    provider_pin: MetadataPin
    descriptor_pin: MetadataPin
    split_pin: MetadataPin
    groups: tuple[LabGroup, ...]
    pages: tuple[MetadataPin, ...]

    @property
    def provider_sha256(self) -> str:
        return recording_sha256(self.provider)


def read_lab_import_manifest(path: Path, sha256: str) -> LabImportManifest:
    """Read the closed v1 format and pin actual metadata files, never rasters."""
    payload = _read_metadata(MetadataPin(path, _sha(sha256)))
    if set(payload) != {
        "schemaVersion",
        "providerIdentitySha256",
        "provider",
        "descriptor",
        "split",
        "groups",
        "pages",
    } or payload["schemaVersion"] != ("recording-lab-import-v1"):
        raise _invalid("Unknown LAB import manifest fields or version.")
    identity = _sha(payload["providerIdentitySha256"])
    provider_pin, descriptor_pin, split_pin = (
        _pin(path.parent, payload[name]) for name in ("provider", "descriptor", "split")
    )
    # Metadata is checked now and again before mutation, including finalization.
    _read_metadata(descriptor_pin)
    _read_metadata(split_pin)
    provider = read_provider(provider_pin.path, provider_pin.sha256)
    rows, page_refs = payload["groups"], payload["pages"]
    if (
        not isinstance(rows, list)
        or len(rows) > _MAX_GROUPS
        or not isinstance(page_refs, list)
        or not 1 <= len(page_refs) <= _MAX_PAGES
    ):
        raise _invalid("LAB import group or page limit exceeded.")
    groups = []
    seen = set()
    for item in rows:
        if not isinstance(item, dict) or set(item) != {
            "recordingRefSha256",
            "expectedSources",
            "role",
            "independenceConfirmed",
        }:
            raise _invalid("LAB group metadata fields are invalid.")
        reference = _sha(item["recordingRefSha256"])
        count, role, independent = (
            item[name] for name in ("expectedSources", "role", "independenceConfirmed")
        )
        if (
            reference in seen
            or type(count) is not int
            or not 1 <= count <= 102400
            or not isinstance(role, str)
            or role not in {"TRAIN", *PROTECTED_ROLES}
            or type(independent) is not bool
        ):
            raise _invalid("LAB group count, role or declaration is invalid.")
        seen.add(reference)
        groups.append(LabGroup(reference, count, role, independent))
    pages = tuple(_pin(path.parent, value) for value in page_refs)
    if len({(pin.path.resolve(), pin.sha256) for pin in pages}) != len(pages):
        raise _invalid("LAB import repeats a page.")
    manifest = LabImportManifest(
        sha256, identity, provider, provider_pin, descriptor_pin, split_pin, tuple(groups), pages
    )
    mapping = _provider_mapping(provider)
    for group in groups:
        if mapping.get(str(lab_group_id(identity, group.reference_sha256))) != group.role:
            raise _invalid("Provider mapping differs from the supplied recording groups.")
    return manifest


def _provider_mapping(provider: dict[str, Any]) -> dict[str, str]:
    # Public read_provider supplies structural validation. Keep the DB adapter
    # closed too, since MAIN deployment may pass a parsed provider directly.
    if set(provider) != {
        "schemaVersion",
        "ancestor",
        "complete",
        "recordingIdentityAvailable",
        "recordingGroups",
    } or provider["schemaVersion"] != ("recording-ancestor-provider-v1"):
        raise _invalid("Provider schema differs.")
    if (
        type(provider["complete"]) is not bool
        or type(provider["recordingIdentityAvailable"]) is not bool
        or not isinstance(provider["ancestor"], dict)
        or not _ancestor_is_closed(provider["ancestor"])
    ):
        raise _invalid("Provider completeness must be explicit.")
    try:
        UUID(provider["ancestor"]["versionId"])
        rows = provider["recordingGroups"]
        if not isinstance(rows, list) or len(rows) > _MAX_GROUPS:
            raise ValueError("groups")
        result: dict[str, str] = {}
        for row in rows:
            if (
                not isinstance(row, dict)
                or set(row) != {"groupId", "role"}
                or row["role"] not in {"TRAIN", *PROTECTED_ROLES}
            ):
                raise ValueError("role")
            identifier = str(UUID(row["groupId"]))
            if identifier in result:
                raise ValueError("duplicate")
            result[identifier] = row["role"]
        return result
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise _invalid("Provider group mapping is invalid.") from error


def read_lab_import_page(manifest: LabImportManifest, page_index: int) -> list[dict[str, Any]]:
    if type(page_index) is not int or not 0 <= page_index < len(manifest.pages):
        raise _invalid("LAB page index is invalid.")
    page = _read_metadata(manifest.pages[page_index])
    if set(page) != {"schemaVersion", "sources"} or page["schemaVersion"] != (
        "recording-lab-import-page-v1"
    ):
        raise _invalid("Unknown LAB page fields or version.")
    rows = page["sources"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise _invalid("Each LAB page requires 1 to 200 sources.")
    known = {group.reference_sha256 for group in manifest.groups}
    mapping = _provider_mapping(manifest.provider)
    seen = set()
    for source in rows:
        if not isinstance(source, dict) or set(source) != {
            "sourceRefSha256",
            "recordingRefSha256",
            "byteSha256",
            "pixelSha256",
            "pixelAlgorithm",
            "width",
            "height",
        }:
            raise _invalid("LAB source metadata fields are invalid.")
        reference = _sha(source["sourceRefSha256"])
        _sha(source["byteSha256"])
        _sha(source["pixelSha256"])
        recording = source["recordingRefSha256"]
        if recording is not None and (_sha(recording) not in known):
            raise _invalid("Source recording mapping was not supplied.")
        if (
            reference in seen
            or not isinstance(source["pixelAlgorithm"], str)
            or _ALGORITHM.fullmatch(source["pixelAlgorithm"]) is None
            or any(
                type(source[name]) is not int or not 1 <= source[name] <= 100000
                for name in ("width", "height")
            )
        ):
            raise _invalid("LAB source identity or dimensions are invalid.")
        if (
            recording is None
            and str(lab_photo_group_id(manifest.provider_identity_sha256, reference)) not in mapping
        ):
            raise _invalid("Photo-only source lacks an exact provider role mapping.")
        seen.add(reference)
    return cast(list[dict[str, Any]], rows)


def _guard(connection: Connection) -> None:
    connection.exec_driver_sql("SET LOCAL lock_timeout='5s'")
    connection.exec_driver_sql("SET LOCAL statement_timeout='30s'")
    allowed = connection.execute(
        text("""
        SELECT r.rolsuper OR d.datdba=r.oid FROM pg_catalog.pg_roles r
        CROSS JOIN pg_catalog.pg_database d
        WHERE r.rolname=current_user AND d.datname=current_database()
    """)
    ).scalar_one()
    if not allowed:
        raise RecordingError(
            "RECORDING_DEPLOYMENT_OWNER_REQUIRED",
            "Provider installation requires the deployment owner.",
            403,
        )
    connection.execute(text("SELECT pg_catalog.pg_advisory_xact_lock(9910994)"))
    connection.execute(text("SELECT pg_catalog.pg_advisory_xact_lock(9921002)"))


def _verify_pins(manifest: LabImportManifest) -> None:
    _read_metadata(manifest.descriptor_pin)
    _read_metadata(manifest.split_pin)
    if read_provider(manifest.provider_pin.path, manifest.provider_pin.sha256) != manifest.provider:
        raise _invalid("Pinned provider differs from the import manifest.")


def _replay(
    connection: Connection, namespace: str, kind: str, key: UUID, body: dict[str, Any]
) -> dict[str, Any] | None:
    row = connection.execute(
        text("""
        SELECT command_sha256, receipt FROM public.recording_commands
        WHERE origin='LAB_DESCRIPTOR' AND external_ref_sha256=:namespace
          AND kind=:kind AND idempotency_key=:key
    """),
        {"namespace": namespace, "kind": kind, "key": key},
    ).one_or_none()
    if row is None:
        return None
    if row[0] != recording_sha256(body):
        raise RecordingError("RECORDING_COMMAND_CONFLICT", "Deployment command body differs.")
    return cast(dict[str, Any], row[1])


def _receipt(
    connection: Connection,
    namespace: str,
    kind: str,
    key: UUID,
    body: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    connection.execute(
        text("""
        INSERT INTO public.recording_commands(origin,external_ref_sha256,kind,idempotency_key,
          command_json,command_sha256,actor,receipt)
        VALUES('LAB_DESCRIPTOR',:namespace,:kind,:key,CAST(:body AS jsonb),:sha,:actor,
          CAST(:receipt AS jsonb))
    """),
        {
            "namespace": namespace,
            "kind": kind,
            "key": key,
            "body": canonical_recording_json(body),
            "sha": recording_sha256(body),
            "actor": _ACTOR,
            "receipt": canonical_recording_json(result),
        },
    )
    return result


def _event(connection: Connection, kind: str, groups: list[UUID], payload: dict[str, Any]) -> UUID:
    identifier = uuid4()
    connection.execute(
        text("""
        INSERT INTO public.recording_evidence(id,kind,group_ids,payload,payload_sha256,actor)
        VALUES(:id,:kind,CAST(:groups AS uuid[]),CAST(:payload AS jsonb),
          public.recording_digest_v1(CAST(:payload AS jsonb)),:actor)
    """),
        {
            "id": identifier,
            "kind": kind,
            "groups": sorted(set(groups)),
            "payload": canonical_recording_json(payload),
            "actor": _ACTOR,
        },
    )
    connection.execute(
        text("SELECT public.recording_invalidate_dependents_v1(:id)"),
        {
            "id": identifier,
        },
    )
    return identifier


def _group(
    connection: Connection,
    manifest: LabImportManifest,
    identifier: UUID,
    reference: str,
    expected: int,
) -> None:
    connection.execute(
        text("""
        INSERT INTO public.recording_groups(id,origin,external_ref_sha256,origin_provider_sha256,
          revision,manifest_id,manifest_sha256,expected_sources,page_count)
        VALUES(:id,'LAB_DESCRIPTOR',:reference,:identity,1,:manifest,:sha,:count,:pages)
        ON CONFLICT (id) DO NOTHING
    """),
        {
            "id": identifier,
            "reference": reference,
            "identity": manifest.provider_identity_sha256,
            "manifest": uuid5(identifier, "recording-membership"),
            "sha": manifest.manifest_sha256,
            "count": expected,
            "pages": len(manifest.pages),
        },
    )
    row = connection.execute(
        text("""
        SELECT origin, external_ref_sha256,origin_provider_sha256,expected_sources
        FROM public.recording_groups WHERE id=:id
    """),
        {"id": identifier},
    ).one()
    if tuple(row) != ("LAB_DESCRIPTOR", reference, manifest.provider_identity_sha256, expected):
        raise RecordingError("RECORDING_LAB_IDENTITY_CONFLICT", "Existing LAB group differs.")


def import_lab_page(
    connection: Connection, manifest: LabImportManifest, page_index: int, key: UUID
) -> dict[str, Any]:
    """Append one bounded page and its receipt in the caller's transaction."""
    if type(page_index) is not int or not 0 <= page_index < len(manifest.pages):
        raise _invalid("LAB page index is invalid.")
    _verify_pins(manifest)
    sources = read_lab_import_page(manifest, page_index)
    _guard(connection)
    provider_sha = manifest.provider_sha256
    body = {
        "manifestSha256": manifest.manifest_sha256,
        "pageIndex": page_index,
        "pageSha256": manifest.pages[page_index].sha256,
        "providerSha256": provider_sha,
    }
    namespace = manifest.provider_identity_sha256
    replay = _replay(connection, namespace, "lab_import_page", key, body)
    if replay is not None:
        return replay
    groups = {group.reference_sha256: group for group in manifest.groups}
    mapping = _provider_mapping(manifest.provider)
    touched: set[UUID] = set()
    membership = []
    for source in sources:
        reference, recording = source["sourceRefSha256"], source["recordingRefSha256"]
        identifier = (
            lab_photo_group_id(namespace, reference)
            if recording is None
            else lab_group_id(namespace, recording)
        )
        _group(
            connection,
            manifest,
            identifier,
            reference if recording is None else recording,
            1 if recording is None else groups[recording].expected_sources,
        )
        identities = (
            source["byteSha256"],
            source["pixelSha256"],
            source["pixelAlgorithm"],
            source["width"],
            source["height"],
        )
        previous = connection.execute(
            text("""
            SELECT source_sha256,pixel_sha256,pixel_algorithm,width,height
            FROM public.recording_occurrences
            WHERE origin='LAB_DESCRIPTOR' AND origin_provider_sha256=:identity
              AND external_ref_sha256=:reference
        """),
            {"identity": namespace, "reference": reference},
        )
        if any(tuple(row) != identities for row in previous):
            raise RecordingError("RECORDING_LAB_IDENTITY_CONFLICT", "LAB source identity changed.")
        connection.execute(
            text("""
            INSERT INTO public.recording_occurrences(id,group_id,origin,external_ref_sha256,
              origin_provider_sha256,source_sha256,pixel_sha256,pixel_algorithm,width,height,
              attestation)
            VALUES(:id,:group,'LAB_DESCRIPTOR',:reference,:identity,:byte,:pixel,:algorithm,
              :width,:height,CAST(:attestation AS jsonb)) ON CONFLICT (id) DO NOTHING
        """),
            {
                "id": uuid5(identifier, reference),
                "group": identifier,
                "reference": reference,
                "identity": namespace,
                "byte": identities[0],
                "pixel": identities[1],
                "algorithm": identities[2],
                "width": identities[3],
                "height": identities[4],
                "attestation": canonical_recording_json(
                    {
                        "providerSha256": provider_sha,
                        "descriptorSha256": manifest.descriptor_pin.sha256,
                        "splitSha256": manifest.split_pin.sha256,
                    }
                ),
            },
        )
        if recording is not None:
            placeholder = lab_photo_group_id(namespace, reference)
            if connection.execute(
                text("SELECT EXISTS(SELECT 1 FROM public.recording_groups WHERE id=:id)"),
                {"id": placeholder},
            ).scalar_one():
                _event(
                    connection,
                    "alias",
                    [placeholder, identifier],
                    {
                        "sourceRefSha256": reference,
                        "providerSha256": provider_sha,
                        "mappingManifestSha256": manifest.manifest_sha256,
                    },
                )
        role = mapping[str(identifier)]
        if role != "TRAIN":
            # Known protection survives a partial deployment. Independence and
            # TRAIN-use still require full membership verification below.
            _install_role(
                connection,
                identifier,
                role,
                provider_sha,
                manifest.provider["ancestor"],
            )
        touched.add(identifier)
        membership.append({"groupId": str(identifier), "sourceRefSha256": reference})
    event = _event(connection, "membership", list(touched), body)
    return _receipt(
        connection,
        namespace,
        "lab_import_page",
        key,
        body,
        {
            **body,
            "eventId": str(event),
            "registeredSources": len(sources),
            "sources": membership,
        },
    )


def _install_role(
    connection: Connection, group: UUID, role: str, provider_sha256: str, ancestor: dict[str, Any]
) -> None:
    if (
        role == "TRAIN"
        and connection.execute(
            text("""
        SELECT EXISTS(SELECT 1 FROM public.recording_evidence
          WHERE kind IN ('holdout','ancestor','use')
            AND group_ids && public.recording_closure_v1(ARRAY[CAST(:group AS uuid)])
            AND payload->>'role'=ANY(CAST(:roles AS text[])))
    """),
            {"group": group, "roles": sorted(PROTECTED_ROLES)},
        ).scalar_one()
    ):
        raise RecordingError("RECORDING_PROTECTED", "A retained holdout cannot become TRAIN.")
    payload = {"role": role, "providerSha256": provider_sha256, "ancestor": ancestor}
    present = connection.execute(
        text("""
        SELECT EXISTS(SELECT 1 FROM public.recording_evidence
          WHERE kind=:kind AND group_ids=ARRAY[CAST(:group AS uuid)]
            AND payload=CAST(:payload AS jsonb))
    """),
        {
            "kind": "use" if role == "TRAIN" else "holdout",
            "group": group,
            "payload": canonical_recording_json(payload),
        },
    ).scalar_one()
    if not present:
        _event(connection, "use" if role == "TRAIN" else "holdout", [group], payload)


def _deployment_payload(manifest: LabImportManifest) -> dict[str, Any]:
    return {
        "providerSha256": manifest.provider_sha256,
        "provider": manifest.provider,
        "descriptorSha256": manifest.descriptor_pin.sha256,
        "splitSha256": manifest.split_pin.sha256,
        "manifestSha256": manifest.manifest_sha256,
    }


def _membership_counts(connection: Connection, manifest: LabImportManifest) -> dict[UUID, int]:
    """Validate committed bounded page receipts in SQL; return only group counts."""
    rows = (
        connection.execute(
            text("""
        WITH required AS (
          SELECT * FROM jsonb_to_recordset(CAST(:pages AS jsonb))
            AS p("pageIndex" integer,"pageSha256" text)),
        receipts AS MATERIALIZED (
          SELECT DISTINCT ON (p."pageIndex") p."pageIndex",c.receipt
          FROM required p JOIN public.recording_commands c ON
            c.origin='LAB_DESCRIPTOR' AND c.external_ref_sha256=:identity
            AND c.kind='lab_import_page' AND c.command_json->>'manifestSha256'=:manifest
            AND c.command_json->>'pageIndex'=p."pageIndex"::text
            AND c.command_json->>'pageSha256'=p."pageSha256"
            AND c.command_json->>'providerSha256'=:provider
          ORDER BY p."pageIndex",c.id),
        members AS MATERIALIZED (
          SELECT (source->>'groupId')::uuid group_id,source->>'sourceRefSha256' source_ref
          FROM receipts CROSS JOIN LATERAL jsonb_array_elements(receipt->'sources') source),
        totals AS (
          SELECT (SELECT count(*) FROM receipts) page_count,count(*) source_count,
            count(DISTINCT source_ref) unique_count FROM members)
        SELECT m.group_id,count(*) member_count,count(o.id) matched_count,
          (SELECT count(*) FROM public.recording_occurrences a WHERE a.group_id=m.group_id)
            actual_count,t.page_count,t.source_count,t.unique_count
        FROM members m LEFT JOIN public.recording_occurrences o ON o.group_id=m.group_id
          AND o.origin='LAB_DESCRIPTOR' AND o.origin_provider_sha256=:identity
          AND o.external_ref_sha256=m.source_ref CROSS JOIN totals t
        GROUP BY m.group_id,t.page_count,t.source_count,t.unique_count
        ORDER BY m.group_id LIMIT 4097
    """),
            {
                "identity": manifest.provider_identity_sha256,
                "manifest": manifest.manifest_sha256,
                "provider": manifest.provider_sha256,
                "pages": canonical_recording_json(
                    [
                        {"pageIndex": index, "pageSha256": pin.sha256}
                        for index, pin in enumerate(manifest.pages)
                    ]
                ),
            },
        )
        .mappings()
        .all()
    )
    if not rows or any(int(row["page_count"]) != len(manifest.pages) for row in rows):
        raise RecordingError("RECORDING_LAB_PAGE_MISSING", "Every pinned LAB page is required.")
    if len(rows) > _MAX_GROUPS:
        raise _invalid("LAB group limit exceeded.")
    if any(row["source_count"] != row["unique_count"] for row in rows):
        raise _invalid("LAB import repeats a source across pages.")
    if any(
        row["member_count"] != row["matched_count"] or row["member_count"] != row["actual_count"]
        for row in rows
    ):
        raise RecordingError(
            "RECORDING_LAB_MEMBERSHIP_CONFLICT",
            "LAB recording membership differs from committed pages.",
        )
    return {UUID(str(row["group_id"])): int(row["member_count"]) for row in rows}


def finalize_lab_import(
    connection: Connection, manifest: LabImportManifest, key: UUID
) -> dict[str, Any]:
    """Verify every exact page, complete real recordings, retain photo-only blockers."""
    # Read only three bounded pinned metadata files before acquiring global locks.
    # Pages are verified from immutable receipts below, never reread under locks.
    _verify_pins(manifest)
    body = _deployment_payload(manifest)
    _guard(connection)
    namespace = manifest.provider_identity_sha256
    replay = _replay(connection, namespace, "lab_import_finalize", key, body)
    if replay is not None:
        return replay
    mapping = _provider_mapping(manifest.provider)
    expected = _membership_counts(connection, manifest)
    if set(map(str, expected)) != set(mapping):
        raise _invalid("Provider groups must exactly match the complete supplied membership.")
    declared = {lab_group_id(namespace, group.reference_sha256): group for group in manifest.groups}
    if not set(declared) <= set(expected):
        raise _invalid("Declared recording has no verified source membership.")
    for identifier, count in expected.items():
        if (identifier in declared and declared[identifier].expected_sources != count) or (
            identifier not in declared and count != 1
        ):
            raise RecordingError(
                "RECORDING_LAB_MEMBERSHIP_CONFLICT",
                "LAB recording membership differs from the exact manifest.",
            )
    # Persist roles before completing groups. Any TRAIN/holdout conflict rolls
    # back this entire final transaction, leaving page receipts safely resumable.
    for identifier_text, role in mapping.items():
        _install_role(
            connection,
            UUID(identifier_text),
            role,
            body["providerSha256"],
            manifest.provider["ancestor"],
        )
    for identifier, group in declared.items():
        connection.execute(
            text("""
            UPDATE public.recording_groups SET membership_complete=true,declared=true,
              independent=:independent,revision=revision+1 WHERE id=:id
              AND (NOT membership_complete OR NOT declared OR independent<>:independent)
        """),
            {"id": identifier, "independent": group.independent},
        )
        _event(
            connection,
            "declaration",
            [identifier],
            {
                "manifestSha256": manifest.manifest_sha256,
                "independenceConfirmed": group.independent,
            },
        )
    # Only a fully mapped and complete recording can resolve an old photo-only
    # placeholder. Original occurrences, holdouts and receipts stay immutable.
    mappings = connection.execute(
        text("""
        SELECT DISTINCT old.group_id,old.external_ref_sha256,mapped.group_id
        FROM public.recording_occurrences old JOIN public.recording_occurrences mapped
          ON old.origin='LAB_DESCRIPTOR' AND mapped.origin='LAB_DESCRIPTOR'
          AND old.origin_provider_sha256=mapped.origin_provider_sha256
          AND old.external_ref_sha256=mapped.external_ref_sha256
        WHERE mapped.origin_provider_sha256=:identity
          AND mapped.group_id=ANY(CAST(:groups AS uuid[])) AND old.group_id<>mapped.group_id
        ORDER BY old.group_id,old.external_ref_sha256,mapped.group_id LIMIT 4097
    """),
        {"identity": namespace, "groups": list(declared)},
    ).all()
    if len(mappings) > _MAX_GROUPS:
        raise _invalid("LAB placeholder mapping limit exceeded.")
    for old_id, reference, identifier in mappings:
        placeholder = lab_photo_group_id(namespace, str(reference))
        if UUID(str(old_id)) != placeholder:
            continue
        identifier = UUID(str(identifier))
        updated = connection.execute(
            text("""
            UPDATE public.recording_groups SET membership_complete=true,declared=true,
              independent=:independent,revision=revision+1
            WHERE id=:id AND origin='LAB_DESCRIPTOR' AND origin_provider_sha256=:identity
              AND (NOT membership_complete OR NOT declared OR independent<>:independent)
            RETURNING id
        """),
            {
                "id": placeholder,
                "identity": namespace,
                "independent": declared[identifier].independent,
            },
        ).scalar_one_or_none()
        if updated is not None:
            _event(
                connection,
                "alias",
                [placeholder, identifier],
                {
                    "mappingResolved": True,
                    "sourceRefSha256": reference,
                    "manifestSha256": manifest.manifest_sha256,
                },
            )
    event = _event(connection, "membership", list(expected), body)
    return _receipt(
        connection,
        namespace,
        "lab_import_finalize",
        key,
        body,
        {
            "providerSha256": body["providerSha256"],
            "manifestSha256": manifest.manifest_sha256,
            "eventId": str(event),
            "completeRecordings": len(declared),
            "unresolvedPhotos": len(expected) - len(declared),
        },
    )


def install_provider_proof(
    connection: Connection, provider: dict[str, Any], sha: str
) -> dict[str, Any]:
    """Install a trusted MAIN provider proof in an explicit owner transaction.

    ``sha`` is the canonical provider SHA used by resolution, not the hash of
    arbitrary whitespace in its source file. LAB metadata uses finalize instead.
    """
    _guard(connection)
    if recording_sha256(provider) != _sha(sha):
        raise _invalid("Provider canonical checksum differs.")
    mapping = _provider_mapping(provider)
    body = {"providerSha256": sha, "provider": provider}
    key = uuid5(NAMESPACE_URL, f"recording-provider-install:{sha}")
    replay = _replay(connection, sha, "provider_install", key, body)
    if replay is not None:
        return replay
    for identifier in mapping:
        group = connection.execute(
            text("""
            SELECT origin,membership_complete,declared FROM public.recording_groups WHERE id=:id
        """),
            {"id": UUID(identifier)},
        ).one_or_none()
        if group is None or tuple(group) != ("MAIN", True, True):
            raise RecordingError(
                "RECORDING_PROVIDER_UNRESOLVED",
                "MAIN provider requires complete declared MAIN groups.",
                422,
            )
    for identifier, role in mapping.items():
        _install_role(connection, UUID(identifier), role, sha, provider["ancestor"])
    event = _event(connection, "membership", [UUID(value) for value in mapping], body)
    return _receipt(
        connection,
        sha,
        "provider_install",
        key,
        body,
        {
            "providerSha256": sha,
            "eventId": str(event),
        },
    )
