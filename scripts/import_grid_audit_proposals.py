"""Import a silent-grid audit worklist as an immutable grid-audit proposal list (TASK-0840).

Reads ``review/correction-worklist.csv`` (the boards the operator, or the rule built
on the operator's verdicts, judged as a wrong saved grid), finds each board in
``suspects.json`` (network board index, audited geometry revision) and its 24
network lattice nodes in ``network-*.jsonl``, verifies every board against the
current database in one ``REPEATABLE READ READ ONLY`` transaction and writes

    <artifact-root>/grid-audit-proposals/<gameId>/<auditId>/proposals.json
    <artifact-root>/grid-audit-proposals/<gameId>/<auditId>/manifest.json

``manifest.json`` (written last) names the SHA-256 of ``proposals.json``. A board
whose current geometry revision differs from the audited one is written as
``stale`` without a proposal; a board without a current review item as
``board_missing``. Items keep the worklist order with boards that carry human
symbol decisions first. The command never writes to the database and refuses to
overwrite an existing audit directory (the artifact is immutable).

Usage (PowerShell, main checkout, API artifact root)::

    .\\.venv\\Scripts\\python.exe scripts\\import_grid_audit_proposals.py `
      --audit 'C:\\...\\silent-grid-audit\\777-20261004' `
      --game-id bfc4f949-5c14-4850-b02a-db99610bcfa5 --artifact-root .\\artifacts
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.application.grid_audit_proposals import (
    GRID_AUDIT_MANIFEST_FILE,
    GRID_AUDIT_PROPOSALS_DIRECTORY,
    GRID_AUDIT_PROPOSALS_FILE,
)
from game_predictor_api.domain.grid_audit_proposals import (
    GRID_AUDIT_COORDINATE_SPACE,
    GRID_AUDIT_PROPOSALS_MANIFEST_SCHEMA,
    GRID_AUDIT_PROPOSALS_SCHEMA,
    GridAuditImportStatus,
    GridAuditProposalItem,
    grid_audit_proposal_item_document,
    parse_grid_audit_proposal_document,
    proposal_grid_from_nodes,
)

WORKLIST = Path("review") / "correction-worklist.csv"
SUSPECTS = "suspects.json"
BOARDS = "boards.jsonl"
NETWORK_IDENTITY = "network-identity.json"
NETWORK_GLOB = "network-*-of-*.jsonl"
_IMAGE_ID = re.compile(rb'"imageId"\s*:\s*"([0-9a-f-]{36})"')
_STATEMENT_TIMEOUT_MS = 30_000


class GridAuditImportError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorklistBoard:
    """One worklist row joined with its audit facts (no database state yet)."""

    item_id: str
    verdict_source: str
    audit_class: str
    level: str | None
    human_decided_cells: int
    recognized_board_id: UUID
    source_image_id: UUID
    import_job_id: UUID
    sequence_number: int
    position_index: int
    audit_geometry_revision: int
    network_index: int | None


@dataclass(frozen=True, slots=True)
class CurrentBoard:
    geometry_revision: int
    current_review_item: bool


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_worklist(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise GridAuditImportError("The correction worklist is empty")
    return rows


def suspects_by_item(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    found: dict[str, Mapping[str, Any]] = {}
    for key in ("paired", "savedOnly"):
        for item in document.get(key) or ():
            found[str(item["itemId"])] = item
    return found


def audit_revisions(lines: Iterable[bytes]) -> dict[str, int]:
    """The saved geometry revision each compared board had (``boards.jsonl``)."""

    revisions: dict[str, int] = {}
    for line in lines:
        if not line.strip():
            continue
        board = json.loads(line).get("board")
        if isinstance(board, Mapping) and board.get("recognizedBoardId"):
            revisions[str(board["recognizedBoardId"])] = int(board["geometryRevision"])
    return revisions


def join_worklist(
    rows: Sequence[Mapping[str, str]],
    suspects: Mapping[str, Mapping[str, Any]],
    revisions: Mapping[str, int],
) -> list[WorklistBoard]:
    """Worklist rows with their audit facts; boards with symbol decisions first.

    Any disagreement between the worklist and the audit files stops the import.
    """

    boards: list[WorklistBoard] = []
    seen: set[UUID] = set()
    for row in rows:
        item_id = row["itemId"]
        suspect = suspects.get(item_id)
        if suspect is None or not suspect.get("correction"):
            raise GridAuditImportError(f"{item_id}: not in suspects.json with a correction")
        correction = suspect["correction"]
        board_id = UUID(row["recognizedBoardId"])
        if (
            UUID(str(correction["recognizedBoardId"])) != board_id
            or UUID(str(suspect["imageId"])) != UUID(row["sourceImageId"])
            or int(correction["positionIndex"]) != int(row["positionIndex"])
            or int(correction["sequenceNumber"]) != int(row["sequenceNumber"])
        ):
            raise GridAuditImportError(f"{item_id}: worklist and suspects.json disagree")
        if board_id in seen:
            raise GridAuditImportError(f"{item_id}: board listed twice")
        seen.add(board_id)
        compared = revisions.get(str(board_id))
        referenced = correction.get("currentGeometryRevision")
        if compared is None:
            if referenced is None:
                raise GridAuditImportError(f"{item_id}: no audited geometry revision")
            compared = int(referenced)
        elif referenced is not None and int(referenced) != compared:
            raise GridAuditImportError(
                f"{item_id}: the board changed between the audit comparison and its cell refs"
            )
        network_index = suspect.get("networkIndex")
        boards.append(
            WorklistBoard(
                item_id=item_id,
                verdict_source=row["verdictSource"],
                audit_class=row["class"],
                level=row.get("level") or None,
                human_decided_cells=int(row["humanDecidedCells"] or 0),
                recognized_board_id=board_id,
                source_image_id=UUID(row["sourceImageId"]),
                import_job_id=UUID(row["importJobId"]),
                sequence_number=int(row["sequenceNumber"]),
                position_index=int(row["positionIndex"]),
                audit_geometry_revision=compared,
                network_index=None if network_index is None else int(network_index),
            )
        )
    # Stable: the worklist order inside each group.
    return sorted(boards, key=lambda board: board.human_decided_cells == 0)


def network_nodes(
    lines: Iterable[bytes], wanted: Mapping[UUID, set[int]]
) -> dict[tuple[UUID, int], list[list[float]] | None]:
    """24 nodes of each wanted ``(imageId, networkIndex)`` from ``network-*.jsonl``."""

    keys = {str(image_id).encode("ascii") for image_id in wanted}
    found: dict[tuple[UUID, int], list[list[float]] | None] = {}
    for line in lines:
        match = _IMAGE_ID.search(line)
        if match is None or match.group(1) not in keys:
            continue
        record = json.loads(line)
        image_id = UUID(str(record["imageId"]))
        boards = record.get("boards") or []
        for index in wanted[image_id]:
            nodes = boards[index].get("nodes") if 0 <= index < len(boards) else None
            found[(image_id, index)] = nodes
    return found


def build_items(
    boards: Sequence[WorklistBoard],
    nodes: Mapping[tuple[UUID, int], list[list[float]] | None],
    current: Mapping[UUID, CurrentBoard],
) -> list[GridAuditProposalItem]:
    """Items in queue order; only a board with the audited revision gets a proposal."""

    items: list[GridAuditProposalItem] = []
    for ordinal, board in enumerate(boards):
        state = current.get(board.recognized_board_id)
        board_nodes = (
            None
            if board.network_index is None
            else nodes.get((board.source_image_id, board.network_index))
        )
        if state is None or not state.current_review_item:
            status = GridAuditImportStatus.BOARD_MISSING
        elif state.geometry_revision != board.audit_geometry_revision:
            status = GridAuditImportStatus.STALE
        elif board_nodes is None:
            status = GridAuditImportStatus.NO_NETWORK_GRID
        else:
            status = GridAuditImportStatus.PROPOSAL
        items.append(
            GridAuditProposalItem(
                ordinal=ordinal,
                item_id=board.item_id,
                verdict_source=board.verdict_source,
                audit_class=board.audit_class,
                level=board.level,
                human_decided_cells=board.human_decided_cells,
                recognized_board_id=board.recognized_board_id,
                source_image_id=board.source_image_id,
                import_job_id=board.import_job_id,
                sequence_number=board.sequence_number,
                position_index=board.position_index,
                audit_geometry_revision=board.audit_geometry_revision,
                import_geometry_revision=None if state is None else state.geometry_revision,
                import_status=status,
                proposal=proposal_grid_from_nodes(board_nodes)
                if status is GridAuditImportStatus.PROPOSAL and board_nodes is not None
                else None,
            )
        )
    return items


def summary(items: Sequence[GridAuditProposalItem]) -> dict[str, Any]:
    statuses = Counter(item.import_status.value for item in items)
    with_symbols = [item for item in items if item.human_decided_cells > 0]
    return {
        "items": len(items),
        "byImportStatus": dict(sorted(statuses.items())),
        "withSymbolDecisions": len(with_symbols),
        "symbolDecisionCells": sum(item.human_decided_cells for item in items),
        "withSymbolDecisionsByImportStatus": dict(
            sorted(Counter(item.import_status.value for item in with_symbols).items())
        ),
        "byVerdictSource": dict(sorted(Counter(item.verdict_source for item in items).items())),
        "byClass": dict(sorted(Counter(item.audit_class for item in items).items())),
    }


def document_bytes(
    *,
    audit_id: str,
    game_id: UUID,
    created_at: str,
    items: Sequence[GridAuditProposalItem],
    sources: Mapping[str, Any],
    verification: Mapping[str, Any],
) -> bytes:
    document = {
        "schema": GRID_AUDIT_PROPOSALS_SCHEMA,
        "auditId": audit_id,
        "gameId": str(game_id),
        "createdAt": created_at,
        "coordinateSpace": GRID_AUDIT_COORDINATE_SPACE,
        "sources": dict(sources),
        "verification": dict(verification),
        "summary": summary(items),
        "items": [grid_audit_proposal_item_document(item) for item in items],
    }
    content = (json.dumps(document, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    # The API parser must accept exactly what is written.
    parse_grid_audit_proposal_document(json.loads(content), sha256=_sha256(content))
    return content


def write_artifact(
    target: Path, content: bytes, *, audit_id: str, game_id: UUID, created_at: str, items: int
) -> dict[str, Any]:
    """``proposals.json`` then ``manifest.json``, each fsynced; never overwrites."""

    if target.exists():
        raise GridAuditImportError(f"{target} exists; the proposal list is immutable")
    target.mkdir(parents=True)
    manifest = {
        "schema": GRID_AUDIT_PROPOSALS_MANIFEST_SCHEMA,
        "auditId": audit_id,
        "gameId": str(game_id),
        "createdAt": created_at,
        "file": GRID_AUDIT_PROPOSALS_FILE,
        "sha256": _sha256(content),
        "bytes": len(content),
        "items": items,
    }
    _write_new(target / GRID_AUDIT_PROPOSALS_FILE, content)
    _write_new(
        target / GRID_AUDIT_MANIFEST_FILE,
        (json.dumps(manifest, indent=1) + "\n").encode("utf-8"),
    )
    return manifest


def _write_new(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _lines(paths: Sequence[Path]) -> Iterable[bytes]:
    for path in paths:
        with path.open("rb") as stream:
            yield from stream


def read_current_boards(
    game_id: UUID, board_ids: Sequence[UUID]
) -> tuple[dict[UUID, CurrentBoard], dict[str, Any]]:
    """One ``REPEATABLE READ READ ONLY`` transaction bound to the game (owner role)."""

    from game_predictor_api.config import ApiSettings
    from game_predictor_api.storage.game_storage_routing import (
        GameStorageIntent,
        GameStorageRouter,
    )
    from game_predictor_api.storage.grid_audit_board_reader import CURRENT_REVIEW_ITEM_STATUSES
    from game_predictor_api.storage.models import ImageReviewItemModel, RecognizedBoardModel
    from sqlalchemy import create_engine, exists, select, text
    from sqlalchemy.orm import Session

    settings = ApiSettings.from_environment()
    engine = create_engine(settings.owner_database_url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": str(_STATEMENT_TIMEOUT_MS)},
            )
            if connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
                raise GridAuditImportError("The verification transaction is not read-only")
            states: dict[UUID, CurrentBoard] = {}
            with Session(bind=connection) as session:
                location = GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
                if location.status.value != "active":
                    raise GridAuditImportError(f"Game {game_id} storage is not active")
                board = RecognizedBoardModel
                review = ImageReviewItemModel
                current_review = exists(
                    select(review.id).where(
                        review.recognized_board_id == board.id,
                        review.status.in_(CURRENT_REVIEW_ITEM_STATUSES),
                    )
                )
                for start in range(0, len(board_ids), 500):
                    chunk = list(board_ids[start : start + 500])
                    for board_id, revision, has_review in session.execute(
                        select(board.id, board.geometry_revision, current_review).where(
                            board.id.in_(chunk)
                        )
                    ).tuples():
                        states[board_id] = CurrentBoard(int(revision), bool(has_review))
                alembic = session.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                read_only = session.execute(text("SHOW transaction_read_only")).scalar_one()
            connection.rollback()
    finally:
        engine.dispose()
    return states, {
        "transactionReadOnly": read_only == "on",
        "isolation": "REPEATABLE READ READ ONLY",
        "alembicRevision": alembic,
        "storageGeneration": location.generation,
        "boardsFound": len(states),
        "verifiedAt": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def run(
    *,
    audit: Path,
    game_id: UUID,
    artifact_root: Path,
    audit_id: str,
    dry_run: bool,
) -> dict[str, Any]:
    worklist_path = audit / WORKLIST
    suspects_path = audit / SUSPECTS
    boards_path = audit / BOARDS
    network_paths = sorted(audit.glob(NETWORK_GLOB))
    if not network_paths:
        raise GridAuditImportError("No network-*-of-*.jsonl files in the audit directory")
    rows = read_worklist(worklist_path)
    suspects = suspects_by_item(json.loads(suspects_path.read_text(encoding="utf-8")))
    with boards_path.open("rb") as stream:
        revisions = audit_revisions(stream)
    boards = join_worklist(rows, suspects, revisions)
    wanted: dict[UUID, set[int]] = {}
    for board in boards:
        if board.network_index is not None:
            wanted.setdefault(board.source_image_id, set()).add(board.network_index)
    nodes = network_nodes(_lines(network_paths), wanted)
    current, verification = read_current_boards(
        game_id, [board.recognized_board_id for board in boards]
    )
    if not verification["transactionReadOnly"]:
        raise GridAuditImportError("The verification transaction was not read-only")
    items = build_items(boards, nodes, current)
    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    sources = {
        "auditDirectory": str(audit),
        "correctionWorklist": {"file": WORKLIST.as_posix(), "sha256": file_sha256(worklist_path)},
        "suspects": {"file": SUSPECTS, "sha256": file_sha256(suspects_path)},
        "boards": {"file": BOARDS, "sha256": file_sha256(boards_path)},
        "network": [{"file": path.name, "sha256": file_sha256(path)} for path in network_paths],
    }
    identity_path = audit / NETWORK_IDENTITY
    if identity_path.exists():
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        sources["networkIdentity"] = {
            "file": NETWORK_IDENTITY,
            "sha256": file_sha256(identity_path),
            "weightsSha256": (identity.get("files") or {}).get("weights.pt"),
        }
    content = document_bytes(
        audit_id=audit_id,
        game_id=game_id,
        created_at=created_at,
        items=items,
        sources=sources,
        verification=verification,
    )
    target = artifact_root.resolve() / GRID_AUDIT_PROPOSALS_DIRECTORY / str(game_id) / audit_id
    result: dict[str, Any] = {
        "auditId": audit_id,
        "target": str(target),
        "dryRun": dry_run,
        "verification": verification,
        "summary": summary(items),
        "sha256": _sha256(content),
        "bytes": len(content),
    }
    if not dry_run:
        result["manifest"] = write_artifact(
            target,
            content,
            audit_id=audit_id,
            game_id=game_id,
            created_at=created_at,
            items=len(items),
        )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--audit", type=Path, required=True, help="silent-grid audit directory")
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument(
        "--artifact-root", type=Path, required=True, help="the API's GAME_PREDICTOR_ARTIFACT_ROOT"
    )
    parser.add_argument("--audit-id", default=None, help="default: silent-grid-<audit dir name>")
    parser.add_argument("--dry-run", action="store_true", help="verify and report, write nothing")
    arguments = parser.parse_args(argv)
    audit = arguments.audit.resolve()
    audit_id = arguments.audit_id or f"silent-grid-{audit.name}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", audit_id):
        parser.error("--audit-id must be a plain directory name")
    try:
        result = run(
            audit=audit,
            game_id=arguments.game_id,
            artifact_root=arguments.artifact_root,
            audit_id=audit_id,
            dry_run=arguments.dry_run,
        )
    except GridAuditImportError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
