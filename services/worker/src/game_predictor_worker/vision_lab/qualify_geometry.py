"""Preview or atomically apply an explicit D-453 qualification request."""

import argparse
import json
from pathlib import Path
from typing import Any

from .annotation_contracts import AnnotationState, GeometryQualificationRequest
from .annotations import AnnotationStore, digest, read_checked
from .catalog import Catalog
from .geometry_qualification import validate_qualification_request
from .snapshot import reject_links


def qualify_geometry(
    snapshot: Path,
    annotations: Path,
    request: GeometryQualificationRequest,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    catalog = Catalog(snapshot)
    store = AnnotationStore(annotations, catalog)
    if apply:
        state = store.mutate(request)
        status = "applied"
    else:
        # No read(), exclusive(), mkdir() or lock-file side effect in preview.
        payload = read_checked(annotations / "state.json")
        state = AnnotationState.model_validate(payload["state"])
        if state.snapshot_id != store.snapshot_id:
            raise ValueError("ANNOTATION_SNAPSHOT_CONFLICT")
        receipt = payload["receipts"].get(request.request_id)
        if receipt is not None:
            if receipt["fingerprint"] != digest(request.model_dump()):
                raise ValueError("REQUEST_ID_CONFLICT")
            status = "already_applied"
        else:
            if request.expected_revision != state.revision:
                raise ValueError("ANNOTATION_REVISION_CONFLICT")
            if not request.actor.strip():
                raise ValueError("ACTOR_REQUIRED")
            validate_qualification_request(state, catalog.sources, request)
            status = "ready"
    return {
        "status": status,
        "snapshot_id": state.snapshot_id,
        "revision": state.revision,
        "request_fingerprint": digest(request.model_dump()),
        "source_ids": [binding.source_id for binding in request.bindings],
        "purpose": request.purpose,
        "policy_version": request.policy_version,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    reject_links(args.request)
    with args.request.open("rb") as stream:
        data = stream.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("GEOMETRY_QUALIFICATION_REQUEST_TOO_LARGE")
    request = GeometryQualificationRequest.model_validate_json(data)
    print(json.dumps(qualify_geometry(args.snapshot, args.annotations, request, apply=args.apply)))


if __name__ == "__main__":
    main()
