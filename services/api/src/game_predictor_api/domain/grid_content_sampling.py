"""Seeded metadata-only fresh REG selection using the existing solver's closure."""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .grid_cell_content import REGRESSION_SEED, ContentError
from .grid_correction_split import BUFFER_PHOTOS, CorrectionSplitSource, _prepare
from .grid_training_cohorts import digest

CONTENT_SAMPLING_POLICY = "full-symbol-content-sampling-v1"


def fresh_regression_preview(
    sources: Sequence[CorrectionSplitSource],
    contexts: Mapping[str, Mapping[str, Any]],
    fully_labelled_sources: frozenset[str],
    *,
    ancestry_sha256: str | None,
    source_content_counts: Mapping[str, tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """The storage adapter supplies complete authority facts; this does not assign roles.

    Selection is over closed components, preserving all ten-photo buffers. A fresh
    component has no historical role or selection/diagnostic exposure. Missing
    ancestors are a measured shortage, never inferred independent recordings.
    """
    if {s.source_id for s in sources} != set(contexts):
        raise ContentError(
            "CONTENT_REG_CONTEXT_MISSING", "Every source needs current registry closure."
        )
    copies, components, orders, allowed, _boards, _owners = _prepare(tuple(sources))
    members: dict[str, list[CorrectionSplitSource]] = defaultdict(list)
    for source in sources:
        members[components.find(source.source_id)].append(source)
    reasons: Counter[str] = Counter()
    eligible: list[str] = []
    positions: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for order_index, order in enumerate(orders):
        for index, photo in enumerate(order.photo_keys):
            positions[components.find(photo)].append((order_index, index))
    for key, entries in members.items():
        blocked = set()
        if ancestry_sha256 is None:
            blocked.add("CONTENT_REG_ANCESTRY_UNRESOLVED")
        if 2 not in allowed[key]:
            blocked.add("CONTENT_REG_ROLE_PROTECTED")
        for entry in entries:
            facts = contexts[entry.source_id]
            if (
                entry.frozen_role is not None
                or entry.frozen_buffer
                or facts.get("priorRoles")
                or facts.get("validationPurposes")
            ):
                blocked.add("CONTENT_REG_HISTORY_PROTECTED")
            if (
                facts.get("selectionExposed") is not False
                or facts.get("diagnosticExposed") is not False
            ):
                blocked.add("CONTENT_REG_EXPOSURE_OR_UNKNOWN")
            if not facts.get("proofSha256") or not entry.pixel_sha256:
                blocked.add("CONTENT_REG_IDENTITY_UNRESOLVED")
        for order_index, index in positions[key]:
            order = orders[order_index]
            for photo in order.photo_keys[
                max(0, index - BUFFER_PHOTOS) : index + BUFFER_PHOTOS + 1
            ]:
                neighbor = components.find(photo)
                if any(
                    s.frozen_role in {"TRAIN", "VALIDATION"} or s.frozen_buffer
                    for s in members[neighbor]
                ):
                    blocked.add("CONTENT_REG_BUFFER_PROTECTED")
        if not any(
            s.source_id in fully_labelled_sources and s.eligible_boards == 9 for s in entries
        ):
            blocked.add("CONTENT_REG_FULL_LABELS_MISSING")
        if blocked:
            reasons.update(blocked)
        else:
            eligible.append(key)
    # Hash-ranked seed avoids runtime/library-specific shuffle behavior.
    eligible.sort(
        key=lambda key: digest(
            ["fresh-reg-components-v1", REGRESSION_SEED, sorted(s.source_id for s in members[key])]
        )
    )
    chosen: list[str] = []
    photos: set[str] = set()
    for key in eligible:
        if len(photos) >= 5:
            break
        chosen.append(key)
        photos.update(
            copies.find(s.source_id)
            for s in members[key]
            if s.source_id in fully_labelled_sources and s.eligible_boards == 9
        )
    selected = {s.source_id for key in chosen for s in members[key]}
    # Whole components remain in the denominator, including unlabelled photos.
    # Copies count once; missing source geometry conservatively retains nine slots.
    population_cells: dict[str, tuple[int, int]] = {}
    for entry in sources:
        if entry.source_id not in selected:
            continue
        slots = len(entry.attested_slots) or len(entry.board_bindings) or 9
        total = 15 * slots
        known = total if entry.source_id in fully_labelled_sources else 0
        if source_content_counts is not None:
            total, known = source_content_counts[entry.source_id]
        if not 0 <= known <= total or total <= 0:
            raise ContentError("CONTENT_REG_COUNTS_INVALID", "Invalid content population counts.")
        photo = copies.find(entry.source_id)
        old_total, old_known = population_cells.get(photo, (0, 0))
        population_cells[photo] = max(total, old_total), max(known, old_known)
    total_cells = sum(total for total, _ in population_cells.values())
    unknown_cells = sum(total - known for total, known in population_cells.values())
    unknown_excess = bool(total_cells and unknown_cells / total_cells > 0.10)
    if unknown_excess:
        reasons.update(["CONTENT_UNKNOWN_LIMIT"])
    buffers: set[str] = set()
    for key in chosen:
        for order_index, index in positions[key]:
            order = orders[order_index]
            for photo in order.photo_keys[
                max(0, index - BUFFER_PHOTOS) : index + BUFFER_PHOTOS + 1
            ]:
                neighbor = components.find(photo)
                if neighbor in chosen:
                    continue
                buffers.update(
                    s.source_id
                    for s in members[neighbor]
                    if s.frozen_role is None and not s.frozen_buffer
                )
    body = {
        "version": "fresh-content-regression-selection-v1",
        "seed": REGRESSION_SEED,
        "state": "ready" if len(photos) >= 5 and not unknown_excess else "not_evaluable",
        "selectionState": "ready" if len(photos) >= 5 else "not_evaluable",
        "populationCellSlots": total_cells,
        "unknownCellSlots": unknown_cells,
        "sourceIds": sorted(selected),
        "bufferSourceIds": sorted(buffers),
        "fullPhotos": len(photos),
        "missingFullPhotos": max(0, 5 - len(photos)),
        "reasonCounts": dict(sorted(reasons.items())),
        "ancestrySha256": ancestry_sha256,
        "populationSha256": digest(
            sorted(
                (
                    s.source_id,
                    s.byte_sha256,
                    s.pixel_sha256,
                    contexts[s.source_id].get("proofSha256"),
                )
                for s in sources
            )
        ),
        "recordingIndependence": "not_claimed",
        "roleWrites": False,
    }
    return {**body, "sha256": digest(body)}
