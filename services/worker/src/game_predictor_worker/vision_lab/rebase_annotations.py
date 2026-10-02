"""Preflight or atomically copy unchanged-source annotations to a new snapshot."""

import argparse
import copy
import json
import shutil
import tempfile
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from .annotation_contracts import (
    AnnotationRequest,
    AnnotationState,
    GeometryAnnotation,
    PhotoReview,
    PhotoReviewRequest,
)
from .annotations import (
    AnnotationStore,
    annotation_key,
    digest,
    exclusive,
    read_checked,
    write_atomic,
)
from .catalog import Catalog
from .snapshot import reject_links


def _references(payload: dict[str, Any], catalog: Catalog) -> set[str]:
    """Only the known annotation-only format has a safe rebinding policy."""
    if set(payload) != {"state", "history", "receipts"}:
        raise ValueError("REBASE_PAYLOAD_UNSUPPORTED")
    state = AnnotationState.model_validate(payload["state"])
    if state.geometry_qualifications or any(
        isinstance(event, dict) and "geometry_qualifications" in event
        for event in payload["history"]
    ):
        raise ValueError("REBASE_GEOMETRY_QUALIFICATIONS_UNSUPPORTED")
    if state.families or state.split is not None or state.split_stale:
        raise ValueError("REBASE_FAMILIES_OR_SPLIT_UNSUPPORTED")
    if state.assisted_photos or any(
        isinstance(event, dict) and "assisted_photo" in event for event in payload["history"]
    ):
        raise ValueError("REBASE_ASSISTED_PHOTOS_UNSUPPORTED")
    references: set[str] = set()

    def check_review(review: PhotoReview) -> None:
        source = catalog.sources.get(review.source_id)
        if source is None or review.source_sha256 != source.sha256:
            raise ValueError(f"REBASE_REVIEW_SOURCE_INVALID:{review.source_id}")
        references.add(review.source_id)

    for key, review in state.photo_reviews.items():
        if key != review.source_id:
            raise ValueError("REBASE_REVIEW_KEY_INVALID")
        check_review(review)

    def check_annotation(item: GeometryAnnotation, *, stored: bool) -> None:
        source = catalog.sources.get(item.source_id)
        if source is None or (
            (stored or item.source_sha256) and item.source_sha256 != source.sha256
        ):
            raise ValueError(f"REBASE_SOURCE_INTEGRITY:{item.source_id}")
        references.add(item.source_id)

    for key, item in state.annotations.items():
        if key != annotation_key(item.source_id, item.board_index):
            raise ValueError("REBASE_ANNOTATION_KEY_INVALID")
        check_annotation(item, stored=True)
    for timing in state.timings:
        source = catalog.sources.get(timing.source_id)
        if source is None or timing.game_id != source.game_id:
            raise ValueError(f"REBASE_TIMING_SOURCE_INVALID:{timing.source_id}")
        references.add(timing.source_id)
    if not isinstance(payload["history"], list) or not isinstance(payload["receipts"], dict):
        raise ValueError("REBASE_HISTORY_UNSUPPORTED")
    receipts: dict[str, Any] = {}
    for event in payload["history"]:
        required = {
            "request",
            "at",
            "revision",
            "split",
            "annotation",
            "family",
        }
        if not isinstance(event, dict) or set(event) not in (required, required | {"photo_review"}):
            raise ValueError("REBASE_HISTORY_UNSUPPORTED")
        if event["family"] is not None or event["split"] is not None:
            raise ValueError("REBASE_FAMILIES_OR_SPLIT_UNSUPPORTED")
        if "photo_review" in event:
            review_request = PhotoReviewRequest.model_validate(event["request"])
            historical_review = PhotoReview.model_validate(event["photo_review"])
            check_review(historical_review)
            if (review_request.source_id, review_request.source_sha256) != (
                historical_review.source_id,
                historical_review.source_sha256,
            ) or event["annotation"] is not None:
                raise ValueError("REBASE_HISTORY_SOURCE_INVALID")
            request_id = review_request.request_id
        else:
            request = AnnotationRequest.model_validate(event["request"])
            check_annotation(request.annotation, stored=False)
            historical = GeometryAnnotation.model_validate(event["annotation"])
            check_annotation(historical, stored=True)
            if (historical.source_id, historical.board_index) != (
                request.annotation.source_id,
                request.annotation.board_index,
            ):
                raise ValueError("REBASE_HISTORY_SOURCE_INVALID")
            request_id = request.request_id
        receipts[request_id] = {"fingerprint": digest(event["request"])}
    if receipts != payload["receipts"]:
        raise ValueError("REBASE_RECEIPTS_UNSUPPORTED")
    return references


def _prepare(
    old: Catalog, new: Catalog, annotations: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = read_checked(annotations / "state.json")
    old_id = AnnotationStore(annotations, old).snapshot_id
    new_id = AnnotationStore(annotations, new).snapshot_id
    if payload["state"]["snapshot_id"] != old_id:
        raise ValueError("ANNOTATION_SNAPSHOT_CONFLICT")
    references = _references(payload, old)
    for source_id in sorted(references):
        replacement = new.sources.get(source_id)
        if replacement is None or replacement.model_dump() != old.sources[source_id].model_dump():
            raise ValueError(f"REBASE_REFERENCED_SOURCE_CHANGED:{source_id}")
    rebound = copy.deepcopy(payload)
    rebound["state"]["snapshot_id"] = new_id
    report = {
        "format": "vision-lab-annotation-rebase-v1",
        "old_catalog_digest": old_id,
        "new_catalog_digest": new_id,
        "input_payload_digest": digest(payload),
        "output_payload_digest": digest(rebound),
        "revision": payload["state"]["revision"],
        "referenced_source_ids": sorted(references),
        "old_source_count": len(old.sources),
        "new_source_count": len(new.sources),
        "preserved_annotations": len(payload["state"]["annotations"]),
        "preserved_history_events": len(payload["history"]),
    }
    return rebound, report


def rebase_annotations(
    old_snapshot: Path,
    new_snapshot: Path,
    annotations: Path,
    destination: Path,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Never mutate the old payload, a snapshot, or an existing destination."""
    paths = [old_snapshot, new_snapshot, annotations, destination]
    for path in paths:
        reject_links(path.absolute())
    old_snapshot, new_snapshot, annotations, destination = [path.resolve() for path in paths]
    for protected in (old_snapshot, new_snapshot, annotations):
        if destination.is_relative_to(protected) or protected.is_relative_to(destination):
            raise ValueError("REBASE_PATH_OVERLAP")
    if not (annotations / "state.json").is_file():
        raise ValueError("REBASE_SOURCE_STATE_REQUIRED")
    old, new = Catalog(old_snapshot), Catalog(new_snapshot)
    # Snapshot verification happens before the short annotation lock. API must be
    # stopped for the final apply and restarted against the reported new paths.
    with exclusive(annotations) if apply else nullcontext():
        rebound, report = _prepare(old, new, annotations)
        if destination.exists():
            if (
                not (destination / "rebase-report.json").is_file()
                or not (destination / "state.json").is_file()
            ):
                raise ValueError("REBASE_DESTINATION_CONFLICT")
            with exclusive(destination) if apply else nullcontext():
                if (
                    not (destination / "rebase-report.json").is_file()
                    or not (destination / "state.json").is_file()
                    or read_checked(destination / "rebase-report.json") != report
                    or read_checked(destination / "state.json") != rebound
                ):
                    raise ValueError("REBASE_DESTINATION_CONFLICT")
            return {**report, "status": "already_applied", "destination": str(destination)}
        if not apply:
            return {**report, "status": "ready", "destination": str(destination)}
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".rebase-", dir=destination.parent))
        try:
            write_atomic(stage / "state.json", rebound)
            write_atomic(stage / "rebase-report.json", report)
            # Recheck immediately before publication; rename never targets a
            # live annotation store. A concurrently initialized store has .lock.
            if destination.exists():
                raise ValueError("REBASE_DESTINATION_CONFLICT")
            stage.rename(destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        return {**report, "status": "applied", "destination": str(destination)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-snapshot", required=True, type=Path)
    parser.add_argument("--new-snapshot", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Publish after a successful preflight")
    args = parser.parse_args()
    result = rebase_annotations(
        args.old_snapshot, args.new_snapshot, args.annotations, args.destination, apply=args.apply
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
