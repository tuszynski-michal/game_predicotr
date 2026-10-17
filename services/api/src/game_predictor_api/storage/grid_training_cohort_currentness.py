"""Read-only currentness; missing evidence does not prove human withdrawal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from game_predictor_api.domain.grid_training_cohorts import (
    GridCohortError,
    require_minima,
    target_fence,
)
from game_predictor_api.storage.grid_quality_observations import (
    current_targets,
    own_target,
    read_source,
)
from game_predictor_api.storage.grid_reinference import source_fence
from game_predictor_api.storage.grid_training_cohort_evidence import unchanged_approved_target
from game_predictor_api.storage.grid_training_cohort_repository import CohortDeadline


@dataclass(frozen=True)
class MemberCurrentness:
    used: bool
    live_source_linked: bool | None = None
    human_label_withdrawn: bool | None = None
    error: GridCohortError | None = None


def inspect_member(repo: Any, member: Any) -> MemberCurrentness:
    frozen = member.frozen
    if frozen.get("used") is not True:
        return MemberCurrentness(False)
    if member.live_source_image_id is None:
        return MemberCurrentness(
            True,
            False,
            None,
            GridCohortError(
                "SOURCE_REMOVED_NEW_USE_BLOCKED",
                "New use is blocked after removal of the live source; history is retained.",
            ),
        )
    source = read_source(repo.session, member.game_id, member.source_id)
    if source is None:
        return MemberCurrentness(
            True,
            False,
            None,
            GridCohortError("GRID_COHORT_SOURCE_CHANGED", "The live source is unavailable."),
        )
    if member.role is None or source_fence(source) != frozen["sourceFence"]:
        code = "RECORDING_ROLE_REQUIRED" if member.role is None else "GRID_COHORT_SOURCE_CHANGED"
        return MemberCurrentness(
            True, True, None, GridCohortError(code, "The selected source identity or role changed.")
        )
    targets = current_targets(repo.session, member.game_id, member.source_id)
    failure: GridCohortError | None = None
    human: list[bool | None] = []
    for position in frozen["positions"]:
        label = position["label"]
        if label is None:
            continue
        current = targets.get(position["positionIndex"])
        old = label["targetFence"]["board"]
        live = (current or {}).get("board") or {}
        same_board = bool(live and live.get("id") == old.get("id"))
        changed_geometry = same_board and (
            live.get("geometry_revision") != old.get("geometry_revision")
            or (live.get("board_geometry") or {}).get("latticeNodes")
            != (old.get("board_geometry") or {}).get("latticeNodes")
        )
        approval_lost = same_board and (
            live.get("approved_geometry_revision") != live.get("geometry_revision")
        )
        status = None
        if live.get("source_geometry_revision_id"):
            status = repo.session.execute(
                text(
                    "SELECT status FROM image_source_geometry_revisions WHERE game_id=:game "
                    "AND source_image_id=:source AND id=CAST(:revision AS uuid)"
                ),
                {
                    "game": member.game_id,
                    "source": member.source_id,
                    "revision": live["source_geometry_revision_id"],
                },
            ).scalar_one_or_none()
        positive_withdrawal = bool(changed_geometry or approval_lost or status == "reverted")
        approval_fields = (
            "approved_geometry_revision",
            "geometry_approved_by",
            "geometry_approved_at",
        )
        available = (
            current is not None and own_target(current) and not target_fence(current)["rejected"]
        )
        approved = available and all(live.get(key) == old.get(key) for key in approval_fields)
        valid = bool(
            current is not None
            and approved
            and not approval_lost
            and status is not None
            and status != "reverted"
            and (
                target_fence(current) == label["targetFence"]
                or unchanged_approved_target(
                    repo.session,
                    member.game_id,
                    member.source_id,
                    label["approvalFence"],
                    current,
                    render_proof=label["render"],
                    source_row=source,
                )
            )
        )
        human.append(True if positive_withdrawal else False if valid else None)
        if not valid:
            failure = GridCohortError(
                "GRID_COHORT_LABEL_STALE",
                "The exact current human label, source revision or owner changed.",
            )
    withdrawn = (
        True
        if True in human
        else (False if human and all(value is False for value in human) else None)
    )
    if not human:
        failure = GridCohortError(
            "GRID_COHORT_LABEL_UNRESOLVED", "A used source has no proven human target."
        )
    return MemberCurrentness(True, True, withdrawn, failure)


def check_member(repo: Any, member: Any) -> None:
    result = inspect_member(repo, member)
    if result.error:
        raise result.error


def eligibility(repo: Any, row: Any, assets: Any) -> dict[str, Any]:
    deadline = CohortDeadline()
    reasons: set[str] = set()
    used_count = 0
    missing_link = unknown_link = withdrawn_label = unknown_label = False
    connection = repo.session.connection()

    def budget(
        _connection: Any, cursor: Any, _statement: Any, _parameters: Any, _context: Any, _many: Any
    ) -> None:
        deadline.apply_statement_timeout(_connection, cursor, _statement)

    event.listen(connection, "before_cursor_execute", budget)
    try:
        if row.status != "frozen":
            reasons.add("COHORT_NOT_FROZEN")
        for member in repo.iter_members(row.game_id, row.id):
            deadline.check()
            try:
                state = inspect_member(repo, member)
            except GridCohortError as error:
                if error.status == 503:
                    raise
                reasons.add(error.code)
                used_count += 1
                unknown_link = unknown_label = True
                continue
            if state.used:
                used_count += 1
                missing_link |= state.live_source_linked is False
                unknown_link |= state.live_source_linked is None
                withdrawn_label |= state.human_label_withdrawn is True
                unknown_label |= state.human_label_withdrawn is None
            if state.error:
                reasons.add(state.error.code)
        if not used_count:
            reasons.add("COHORT_NO_USED_TARGETS")
        try:
            require_minima(row.summary)
            if row.status == "frozen":
                repo.recording_command(
                    row.game_id,
                    {
                        "kind": "validate_cohort_use",
                        "cohortId": str(row.id),
                        "expectedRevision": row.revision,
                        "manifestSha256": row.manifest_sha256,
                    },
                    "server:grid-cohort-currentness",
                )
        except GridCohortError as error:
            if error.status == 503:
                raise
            reasons.add(error.code)
    except DBAPIError as error:
        raise GridCohortError(
            "GRID_COHORT_DEPENDENCY_UNRESOLVED",
            "The bounded metadata proof could not be read.",
            503,
        ) from error
    finally:
        event.remove(connection, "before_cursor_execute", budget)
    linked = False if missing_link else True if used_count and not unknown_link else None
    withdrawn = True if withdrawn_label else False if used_count and not unknown_label else None
    unresolved = any(
        "UNRESOLVED" in reason or reason in ("COHORT_NOT_FROZEN", "COHORT_NO_USED_TARGETS")
        for reason in reasons
    )
    qualification = "eligible" if not reasons else "unresolved" if unresolved else "blocked"
    if "SOURCE_REMOVED_NEW_USE_BLOCKED" in reasons:
        qualification = "blocked"
    return {
        "qualification": qualification,
        "reasons": sorted(set(reasons)),
        "manifestSha256": row.manifest_sha256,
        "humanLabelWithdrawn": withdrawn,
        "liveSourceLinked": linked,
        "snapshotBytesAvailable": None,
    }
