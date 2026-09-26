"""Photo-wide human review, separate from individual geometry approvals."""

from .annotation_contracts import AnnotationState, BoardReviewIssue, PhotoReview, PhotoReviewRequest
from .contracts import Source


def board_revisions(state: AnnotationState, source_id: str) -> dict[str, int]:
    return {
        str(item.board_index): item.revision
        for item in state.annotations.values()
        if item.source_id == source_id
    }


def photo_accepted(state: AnnotationState, source: Source) -> bool:
    review = state.photo_reviews.get(source.id)
    return bool(
        review
        and review.source_sha256 == source.sha256
        and review.accepted_board_revisions
        and review.accepted_board_revisions == board_revisions(state, source.id)
        and not review.issues
        and any(
            a.source_id == source.id and a.full_approved and a.presence == "present"
            for a in state.annotations.values()
        )
    )


def apply_photo_review(
    state: AnnotationState, source: Source, request: PhotoReviewRequest, now: str
) -> None:
    revisions = board_revisions(state, source.id)
    if request.source_sha256 != source.sha256:
        raise ValueError("PHOTO_REVIEW_SOURCE_CHANGED")
    if request.expected_board_revisions != revisions:
        raise ValueError("PHOTO_REVIEW_GEOMETRY_CHANGED")
    rows = {str(a.board_index): a for a in state.annotations.values() if a.source_id == source.id}
    review = state.photo_reviews.get(
        source.id, PhotoReview(source_id=source.id, source_sha256=source.sha256)
    )
    indices = [str(i) for i in request.board_indices]
    if request.action != "accept" and (
        not indices or len(set(indices)) != len(indices) or any(i not in rows for i in indices)
    ):
        raise ValueError("PHOTO_REVIEW_SAVED_POSITIONS_REQUIRED")
    if request.action == "mark":
        for index in indices:
            review.issues[index] = BoardReviewIssue(
                status="needs_correction",
                note=request.note.strip(),
                board_revision=rows[index].revision,
                actor=request.actor,
                decided_at=now,
            )
        review.accepted_board_revisions = {}
    elif request.action == "withdraw":
        if any(i not in review.issues for i in indices):
            raise ValueError("PHOTO_REVIEW_ISSUE_NOT_FOUND")
        for index in indices:
            del review.issues[index]
        review.accepted_board_revisions = {}
    else:
        if indices or request.note:
            raise ValueError("PHOTO_ACCEPT_ENTIRE_SET_REQUIRED")
        if not any(a.full_approved and a.presence == "present" for a in rows.values()):
            raise ValueError("PHOTO_ACCEPT_FULL_GEOMETRY_REQUIRED")
        if any(issue.status == "needs_correction" for issue in review.issues.values()):
            raise ValueError("PHOTO_CORRECTIONS_REQUIRED")
        if any(
            index not in rows
            or not rows[index].full_approved
            or rows[index].presence != "present"
            or issue.board_revision != rows[index].revision
            for index, issue in review.issues.items()
        ):
            raise ValueError("PHOTO_CORRECTION_FULL_APPROVAL_REQUIRED")
        review.issues = {}
        review.accepted_board_revisions = revisions
    review.actor, review.decided_at = request.actor, now
    state.photo_reviews[source.id] = review
    if state.split is not None:
        state.split_stale = True


def geometry_changed(
    state: AnnotationState, source_id: str, board_index: int, revision: int
) -> None:
    review = state.photo_reviews.get(source_id)
    if review is None:
        return
    review.accepted_board_revisions = {}
    issue = review.issues.get(str(board_index))
    if issue:
        issue.status = "needs_review"
        issue.board_revision = revision
