"""Preview and remove the dead source images of a superseded duplicate import.

TASK-0811. An image of the selected import qualifies only when it is wholly
replaced by another import of the same game and carries no human work and no
live data (rules in :func:`build_removal_plan`); every other image of the
import is kept whole and reported with its reasons. Nothing is ever deleted
partially: a qualifying image goes with all of its boards, review items and
their dependent rows, a kept image keeps every row.

The set of rows to delete is owned by the image (see ``_OWNED_TABLES``). The
complete set of tables that *reference* those rows is read from the PostgreSQL
catalog (``pg_constraint``), never from a hand-written list alone: a row of a
table outside the delete set, or of another image, that points to a row of a
qualifying image keeps that image (``REFERENCED_BY``). The delete order is the
children-before-parents order of the same foreign keys. No statement uses
``CASCADE``; the review queue projection is maintained by its existing
trigger (``project_image_review_queue_delete_v1``).

Shared ``public`` executions (``image_file_executions`` with their stage
results and terminal manifests) are deleted only when, after the removal, no
row of any game references their ``file_execution_key``.

Role: the cross-game execution check and the ``public`` deletes must happen in
the same transaction as the game deletes, which a game-bound application-role
transaction cannot do (RLS, one game per transaction). The tool therefore runs
on the schema-owner connection (maintenance engine, the role
``CrossGameOwnerSession`` and game deletion use) and refuses a role that is
subject to row-level security. The game is still bound through
``GameStorageRouter`` (registry check, write fence, ``search_path``) and every
game query keeps its explicit ``game_id`` predicate.

Preview runs in one ``REPEATABLE READ READ ONLY`` transaction and writes
nothing. Execute takes the game's exclusive lifecycle advisory fence
(``hashtextextended(game_id, 519)``, session level, before the snapshot) and
then, in one ``REPEATABLE READ`` transaction: recomputes the plan and requires
the preview digest, writes a JSON Lines backup of every row it will delete,
deletes, checks the invariants and commits only when all hold.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.image_geometry_completeness import (
    MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE,
    GeometryImageState,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.image_geometry_completeness_repository import (
    GeometryCompletenessReport,
    SqlAlchemyImageGeometryCompletenessRepository,
)

REMOVAL_SCHEMA: Final = "superseded-import-image-removal-v1"
GAME_SCHEMA: Final = "game_data_v2"
LIVE_REVIEW_STATUSES: Final = ("pending", "accepted", "corrected")
SETTLED_IMPORT_FILE_STATUSES: Final = ("waiting_for_review", "completed")
ACTIVE_JOB_STATUSES: Final = ("created", "processing")
SYSTEM_ACTOR_PREFIX: Final = "system:"
STATEMENT_TIMEOUT: Final = "300s"
LOCK_TIMEOUT: Final = "10s"
MAX_PLAN_ITERATIONS: Final = 20
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_ARRAY_TYPES: Final = {"uuid": "uuid[]", "character varying": "varchar[]", "text": "text[]"}

# Keep reasons (an image is kept whole when it has at least one).
NO_BOARDS: Final = "NO_BOARDS"
BOARD_NOT_REJECTED: Final = "BOARD_NOT_REJECTED"
BOARD_WITHOUT_REVIEW_ITEM: Final = "BOARD_WITHOUT_REVIEW_ITEM"
REVIEW_ITEM_NOT_SUPERSEDED: Final = "REVIEW_ITEM_NOT_SUPERSEDED"
SEQUENCE_NUMBER_MISSING: Final = "SEQUENCE_NUMBER_MISSING"
SEQUENCE_WITHOUT_LIVE_SUCCESSOR: Final = "SEQUENCE_WITHOUT_LIVE_SUCCESSOR_IN_OTHER_IMPORT"
NO_SOURCE_GEOMETRY_REVISION: Final = "NO_SOURCE_GEOMETRY_REVISION"
COMPLETENESS_NOT_SUPERSEDED: Final = "COMPLETENESS_STATE_NOT_SUPERSEDED"
HUMAN_REVIEW_RESOLUTION: Final = "NON_SYSTEM_REVIEW_RESOLUTION"
GEOMETRY_APPROVED: Final = "BOARD_GEOMETRY_APPROVED"
BOARD_GEOMETRY_REVIEW_EVENT: Final = "BOARD_GEOMETRY_REVIEW_EVENT"
HUMAN_BOARD_GEOMETRY_REVISION: Final = "NON_SYSTEM_BOARD_GEOMETRY_REVISION"
HUMAN_SOURCE_GEOMETRY_REVISION: Final = "NON_SYSTEM_SOURCE_GEOMETRY_REVISION"
OPEN_DEFERRED_GEOMETRY: Final = "OPEN_DEFERRED_GEOMETRY"
GEOMETRY_EXCEPTION: Final = "GEOMETRY_EXCEPTION"
IMPORT_FILE_MISSING: Final = "IMPORT_FILE_MISSING"
IMPORT_FILE_NOT_SETTLED: Final = "IMPORT_FILE_NOT_SETTLED"
IMPORT_FILE_SHARED: Final = "IMPORT_FILE_SHARED_WITH_ANOTHER_IMAGE"
PROTECTED_ROWS: Final = "PROTECTED_ROWS"
REFERENCED_BY: Final = "REFERENCED_BY"
OWNER_REFERENCE: Final = "OWNER_REVIEW_ITEM_REFERENCE"
SOFT_REFERENCE: Final = "SOFT_REFERENCE"

# Blockers of the whole operation (no image is deleted while one is present).
ACTIVE_GAME_JOB: Final = "ACTIVE_GAME_JOB"
QUEUE_PROJECTION_MISMATCH: Final = "QUEUE_PROJECTION_MISMATCH"


class RemovalError(RuntimeError):
    """Stable refusal of the removal tool."""

    def __init__(self, code: str, message: str, *, details: Mapping[str, object] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = dict(details or {})


class RemovalInvariantError(RemovalError):
    """An invariant failed before ``COMMIT``; the transaction was rolled back."""

    def __init__(self, violations: Sequence[str]):
        super().__init__(
            "REMOVAL_INVARIANT_VIOLATED",
            "An invariant failed before COMMIT; the transaction was rolled back.",
            details={"violations": list(violations)},
        )
        self.violations = tuple(violations)


@dataclass(frozen=True, slots=True)
class _OwnedTable:
    """A table whose rows go with a qualifying image.

    ``scope`` names the id array the rows are selected by; ``key_column`` is
    matched against it. ``owner_sql`` is the owning source image of a row
    (alias ``t``); ``trigger_maintained`` rows are removed by the existing
    queue projection trigger of ``image_review_items``, never by a statement.
    """

    schema: str
    name: str
    scope: str
    key_column: str
    owner_sql: str | None
    trigger_maintained: bool = False

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"


_BOARD_OWNER = (
    "(SELECT b.source_image_id FROM game_data_v2.recognized_boards b "
    "WHERE b.game_id = t.game_id AND b.id = t.recognized_board_id)"
)
_ITEM_OWNER = (
    "(SELECT b.source_image_id FROM game_data_v2.image_review_items i "
    "JOIN game_data_v2.recognized_boards b ON b.game_id = i.game_id "
    "AND b.id = i.recognized_board_id "
    "WHERE i.game_id = t.game_id AND i.id = t.review_item_id)"
)
_JOB_FILE_OWNER = (
    "(SELECT s.id FROM game_data_v2.source_images s WHERE s.game_id = t.game_id "
    "AND s.import_job_id = t.job_id AND s.file_execution_key = t.file_execution_key "
    "ORDER BY s.id LIMIT 1)"
)

_OWNED_TABLES: Final[tuple[_OwnedTable, ...]] = (
    _OwnedTable(GAME_SCHEMA, "source_images", "image", "id", "t.id"),
    _OwnedTable(
        GAME_SCHEMA,
        "image_source_geometry_revisions",
        "image",
        "source_image_id",
        "t.source_image_id",
    ),
    _OwnedTable(GAME_SCHEMA, "recognized_boards", "image", "source_image_id", "t.source_image_id"),
    _OwnedTable(
        GAME_SCHEMA,
        "image_board_geometry_pending",
        "image",
        "source_image_id",
        "t.source_image_id",
    ),
    _OwnedTable(GAME_SCHEMA, "image_review_items", "board", "recognized_board_id", _BOARD_OWNER),
    _OwnedTable(
        GAME_SCHEMA, "board_render_manifests", "board", "recognized_board_id", _BOARD_OWNER
    ),
    _OwnedTable(
        GAME_SCHEMA,
        "image_board_geometry_revisions",
        "board",
        "recognized_board_id",
        _BOARD_OWNER,
    ),
    _OwnedTable(
        GAME_SCHEMA,
        "image_symbol_prediction_revisions",
        "board",
        "recognized_board_id",
        _BOARD_OWNER,
    ),
    _OwnedTable(
        GAME_SCHEMA,
        "image_review_resolution_events",
        "item",
        "review_item_id",
        _ITEM_OWNER,
    ),
    _OwnedTable(
        GAME_SCHEMA,
        "image_review_queue_items",
        "item",
        "review_item_id",
        _ITEM_OWNER,
        trigger_maintained=True,
    ),
    _OwnedTable(
        GAME_SCHEMA,
        "image_import_job_files",
        "job_file",
        "file_execution_key",
        _JOB_FILE_OWNER,
    ),
    _OwnedTable("public", "image_pipeline_stage_results", "execution", "file_execution_key", None),
    _OwnedTable(
        "public", "image_pipeline_terminal_manifests", "execution", "file_execution_key", None
    ),
    _OwnedTable("public", "image_file_executions", "execution", "file_execution_key", None),
)
_OWNED_BY_NAME: Final = {table.qualified: table for table in _OWNED_TABLES}
_QUEUE_STATE_TABLE: Final = "game_data_v2.image_review_queue_states"

# Condition 4: rows of these tables keep the image (human work or live data).
# Each entry names the column and the kind of id it holds.
_PROTECTED_REFERENCES: Final[tuple[tuple[str, tuple[tuple[str, str], ...]], ...]] = (
    (
        "image_symbol_review_cells",
        (
            ("review_item_id", "item"),
            ("recognized_board_id", "board"),
            ("source_geometry_revision_id", "revision"),
            ("approved_source_geometry_revision_id", "revision"),
        ),
    ),
    (
        "image_symbol_review_events",
        (
            ("review_item_id", "item"),
            ("source_geometry_revision_id", "revision"),
            ("previous_source_geometry_revision_id", "revision"),
            ("approved_source_geometry_revision_id", "revision"),
            ("previous_approved_source_geometry_revision_id", "revision"),
        ),
    ),
    (
        "image_symbol_review_bulk_targets",
        (("review_item_id", "item"), ("recognized_board_id", "board")),
    ),
    (
        "symbol_reference_images",
        (("source_review_item_id", "item"), ("source_recognized_board_id", "board")),
    ),
    (
        "verified_training_cohort_items",
        (
            ("review_item_id", "item"),
            ("recognized_board_id", "board"),
            ("source_image_id", "image"),
        ),
    ),
    (
        "verified_training_cohort_cells",
        (
            ("review_item_id", "item"),
            ("recognized_board_id", "board"),
            ("source_image_id", "image"),
            ("source_geometry_revision_id", "revision"),
        ),
    ),
    (
        "image_sequence_canonical",
        (
            ("review_item_id", "item"),
            ("recognized_board_id", "board"),
            ("source_image_id", "image"),
        ),
    ),
    ("image_sequence_source_override_events", (("selected_review_item_id", "item"),)),
    (
        "image_board_search_candidates",
        (("review_item_id", "item"), ("recognized_board_id", "board")),
    ),
    (
        "image_board_search_fast_documents",
        (("review_item_id", "item"), ("recognized_board_id", "board")),
    ),
    (
        "image_layout_staging_rows",
        (("review_item_id", "item"), ("recognized_board_id", "board")),
    ),
)

# Non-FK uuid columns that may name a review item or board (conservative).
_SOFT_REFERENCES: Final[tuple[tuple[str, str, tuple[str, ...]], ...]] = (
    ("image_symbol_review_states", "last_review_item_id", ("item", "board")),
    ("image_symbol_review_states", "count_rebuild_cursor", ("item", "board")),
    ("layouts", "source_board_id", ("item", "board")),
)


@dataclass(frozen=True, slots=True)
class ForeignKey:
    name: str
    child_schema: str
    child_table: str
    child_root: str
    parent_root: str
    child_columns: tuple[str, ...]
    parent_columns: tuple[str, ...]
    child_types: tuple[str, ...]

    @property
    def label(self) -> str:
        return (
            f"{self.child_root}({','.join(self.child_columns)})"
            f"->{self.parent_root}({','.join(self.parent_columns)})"
        )


@dataclass(frozen=True, slots=True)
class ImageDecision:
    source_image_id: UUID
    relative_path: str
    board_count: int
    review_item_count: int
    qualifies: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Scope:
    image_ids: tuple[str, ...]
    board_ids: tuple[str, ...]
    item_ids: tuple[str, ...]
    revision_ids: tuple[str, ...]
    job_file_keys: tuple[str, ...]
    execution_keys: tuple[str, ...]

    def params(self, game_id: UUID, import_job_id: UUID) -> dict[str, object]:
        return {
            "game_id": game_id,
            "import_job_id": import_job_id,
            "image_ids": list(self.image_ids),
            "board_ids": list(self.board_ids),
            "item_ids": list(self.item_ids),
            "job_file_keys": list(self.job_file_keys),
            "execution_keys": list(self.execution_keys),
        }


@dataclass(frozen=True, slots=True)
class RemovalPlan:
    game_id: UUID
    import_job_id: UUID
    import_job_status: str
    images: tuple[ImageDecision, ...]
    image_ids: tuple[UUID, ...]
    row_counts: Mapping[str, int]
    delete_order: tuple[str, ...]
    execution_keys: tuple[str, ...]
    retained_execution_keys: tuple[str, ...]
    foreign_keys: tuple[str, ...]
    blockers: tuple[str, ...]
    queue_state: Mapping[str, int] | None
    plan_sha256: str
    completeness_images: Mapping[str, int]
    scope: _Scope = field(repr=False)

    @property
    def kept(self) -> tuple[ImageDecision, ...]:
        return tuple(image for image in self.images if not image.qualifies)


@dataclass(frozen=True, slots=True)
class RemovalExecution:
    plan: RemovalPlan
    committed: bool
    deleted_counts: Mapping[str, int]
    backup_directory: Path | None
    backup_manifest: Mapping[str, Any] | None
    metrics_before: Mapping[str, Any] | None
    metrics_after: Mapping[str, Any] | None


def _quote(identifier: str) -> str:
    if _IDENTIFIER.fullmatch(identifier) is None:
        raise RemovalError(
            "REMOVAL_IDENTIFIER_INVALID",
            "Unexpected catalog identifier.",
            details={"identifier": identifier},
        )
    return f'"{identifier}"'


def _relation(schema: str, name: str) -> str:
    return f"{_quote(schema)}.{_quote(name)}"


def _scope_predicate(table: _OwnedTable) -> str:
    column = f"t.{_quote(table.key_column)}"
    if table.scope == "image":
        return f"t.game_id = :game_id AND {column} = ANY(CAST(:image_ids AS uuid[]))"
    if table.scope == "board":
        return f"t.game_id = :game_id AND {column} = ANY(CAST(:board_ids AS uuid[]))"
    if table.scope == "item":
        return f"t.game_id = :game_id AND {column} = ANY(CAST(:item_ids AS uuid[]))"
    if table.scope == "job_file":
        return (
            "t.game_id = :game_id AND t.job_id = :import_job_id "
            f"AND {column} = ANY(CAST(:job_file_keys AS varchar[]))"
        )
    if table.scope == "execution":
        return f"{column} = ANY(CAST(:execution_keys AS varchar[]))"
    raise RemovalError("REMOVAL_SCOPE_INVALID", table.scope)


def _is_system_actor(actor: object) -> bool:
    return isinstance(actor, str) and actor.startswith(SYSTEM_ACTOR_PREFIX)


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _require_owner_role(connection: Connection) -> None:
    bypasses = connection.execute(
        text("SELECT r.rolsuper OR r.rolbypassrls FROM pg_roles r WHERE r.rolname = current_user")
    ).scalar_one()
    if not bypasses:
        raise RemovalError(
            "REMOVAL_OWNER_SESSION_REQUIRED",
            "The removal must run on the schema-owner (maintenance) connection: the "
            "cross-game execution check needs to see every game in the same transaction.",
        )


def _set_limits(connection: Connection) -> None:
    connection.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'"))
    connection.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))


def _require_transaction(connection: Connection, *, read_only: bool) -> None:
    isolation = str(connection.execute(text("SHOW transaction_isolation")).scalar_one())
    mode = str(connection.execute(text("SHOW transaction_read_only")).scalar_one())
    if isolation != "repeatable read" or (mode == "on") != read_only:
        raise RemovalError(
            "REMOVAL_TRANSACTION_MODE_INVALID",
            "The removal transaction did not start in the required mode.",
            details={"isolation": isolation, "readOnly": mode, "expectedReadOnly": read_only},
        )


def load_foreign_keys(session: Session) -> tuple[ForeignKey, ...]:
    """Every user-declared foreign key whose parent (or its root) is an owned table."""

    rows = session.execute(
        text(
            """
SELECT c.conname, cn.nspname, child.relname,
  COALESCE(cr.relname, child.relname),
  pn.nspname, COALESCE(pr.relname, parent.relname),
  ARRAY(SELECT a.attname::text FROM unnest(c.conkey) WITH ORDINALITY k(attnum, n)
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum ORDER BY k.n),
  ARRAY(SELECT a.attname::text FROM unnest(c.confkey) WITH ORDINALITY k(attnum, n)
        JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.attnum ORDER BY k.n),
  ARRAY(SELECT format_type(a.atttypid, NULL) FROM unnest(c.conkey) WITH ORDINALITY k(attnum, n)
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum ORDER BY k.n)
FROM pg_constraint c
JOIN pg_class child ON child.oid = c.conrelid
JOIN pg_namespace cn ON cn.oid = child.relnamespace
JOIN pg_class parent ON parent.oid = c.confrelid
JOIN pg_namespace pn ON pn.oid = parent.relnamespace
LEFT JOIN pg_inherits ci ON ci.inhrelid = child.oid
LEFT JOIN pg_class cr ON cr.oid = ci.inhparent
LEFT JOIN pg_inherits pi ON pi.inhrelid = parent.oid
LEFT JOIN pg_class pr ON pr.oid = pi.inhparent
WHERE c.contype = 'f' AND c.conparentid = 0
ORDER BY 2, 3, 1
"""
        )
    ).all()
    keys: list[ForeignKey] = []
    for name, child_schema, child, child_root, parent_schema, parent_root, cc, pc, types in rows:
        if f"{parent_schema}.{parent_root}" not in _OWNED_BY_NAME:
            continue
        keys.append(
            ForeignKey(
                name=str(name),
                child_schema=str(child_schema),
                child_table=str(child),
                child_root=f"{child_schema}.{child_root}",
                parent_root=f"{parent_schema}.{parent_root}",
                child_columns=tuple(str(value) for value in cc),
                parent_columns=tuple(str(value) for value in pc),
                child_types=tuple(str(value) for value in types),
            )
        )
    for key in keys:
        _referenced_column(key)
    return tuple(keys)


def _referenced_column(key: ForeignKey) -> tuple[str, str, str]:
    """``(parent column, child column, child type)`` of a supported FK shape."""

    parent = _OWNED_BY_NAME[key.parent_root]
    if parent.schema == GAME_SCHEMA:
        if (
            len(key.parent_columns) != 2
            or key.parent_columns[0] != "game_id"
            or key.child_columns[0] != "game_id"
        ):
            raise RemovalError(
                "REMOVAL_FOREIGN_KEY_SHAPE_UNSUPPORTED",
                "A foreign key to an owned game table is not (game_id, id)-shaped.",
                details={"foreignKey": key.label},
            )
        return key.parent_columns[1], key.child_columns[1], key.child_types[1]
    if len(key.parent_columns) != 1:
        raise RemovalError(
            "REMOVAL_FOREIGN_KEY_SHAPE_UNSUPPORTED",
            "A foreign key to an owned public table has more than one column.",
            details={"foreignKey": key.label},
        )
    return key.parent_columns[0], key.child_columns[0], key.child_types[0]


def delete_order(keys: Sequence[ForeignKey]) -> tuple[str, ...]:
    """Children before parents among the owned tables, from the catalog edges."""

    dependencies: dict[str, set[str]] = {table.qualified: set() for table in _OWNED_TABLES}
    for key in keys:
        if key.child_root in dependencies and key.child_root != key.parent_root:
            # The parent waits for the child: TopologicalSorter emits a node
            # after its predecessors, so parents name their children.
            dependencies[key.parent_root].add(key.child_root)
    try:
        return tuple(
            TopologicalSorter(
                {table: sorted(children) for table, children in sorted(dependencies.items())}
            ).static_order()
        )
    except CycleError as error:
        raise RemovalError(
            "REMOVAL_DEPENDENCY_CYCLE", "The owned tables form a foreign-key cycle."
        ) from error


@dataclass(slots=True)
class _ImageFacts:
    source_image_id: UUID
    relative_path: str
    checksum_sha256: str
    file_execution_key: str
    reasons: set[str] = field(default_factory=set)
    board_ids: list[str] = field(default_factory=list)
    item_ids: list[str] = field(default_factory=list)
    revision_ids: list[str] = field(default_factory=list)
    sequence_numbers: set[int] = field(default_factory=set)


def _rows(session: Session, sql: str, params: Mapping[str, object]) -> list[Any]:
    return list(session.execute(text(sql), dict(params)).all())


def _load_images(session: Session, game_id: UUID, import_job_id: UUID) -> dict[str, _ImageFacts]:
    params = {"game_id": game_id, "import_job_id": import_job_id}
    images: dict[str, _ImageFacts] = {}
    for row in _rows(
        session,
        """SELECT s.id, s.relative_path, s.checksum_sha256, s.file_execution_key,
                  s.geometry_completeness_status, s.geometry_exception_reason,
                  s.geometry_exception_by, s.geometry_exception_at
           FROM game_data_v2.source_images s
           WHERE s.game_id = :game_id AND s.import_job_id = :import_job_id
           ORDER BY s.relative_path, s.id""",
        params,
    ):
        facts = _ImageFacts(
            source_image_id=row[0],
            relative_path=str(row[1]),
            checksum_sha256=str(row[2]),
            file_execution_key=str(row[3]),
        )
        # Condition 7: an operator geometry exception keeps the image.
        if row[4] == "geometry_exception" or any(value is not None for value in row[5:8]):
            facts.reasons.add(GEOMETRY_EXCEPTION)
        images[str(row[0])] = facts
    if not images:
        return images

    image_join = (
        "JOIN game_data_v2.source_images s ON s.game_id = b.game_id AND s.id = b.source_image_id "
        "AND s.import_job_id = :import_job_id"
    )
    boards: dict[str, str] = {}
    for board_id, image_id, status, sequence, approved_revision, approved_by in _rows(
        session,
        f"""SELECT b.id, b.source_image_id, b.status, b.sequence_number,
                   b.approved_geometry_revision, b.geometry_approved_by
            FROM game_data_v2.recognized_boards b {image_join}
            WHERE b.game_id = :game_id""",
        params,
    ):
        facts = images[str(image_id)]
        facts.board_ids.append(str(board_id))
        boards[str(board_id)] = str(image_id)
        if status != "rejected":
            facts.reasons.add(BOARD_NOT_REJECTED)
        if sequence is not None:
            facts.sequence_numbers.add(int(sequence))
        if approved_revision is not None or approved_by is not None:
            facts.reasons.add(GEOMETRY_APPROVED)

    boards_with_items: set[str] = set()
    for item_id, board_id, status, sequence, resolved_by in _rows(
        session,
        f"""SELECT ri.id, ri.recognized_board_id, ri.status, ri.sequence_number, ri.resolved_by
            FROM game_data_v2.image_review_items ri
            JOIN game_data_v2.recognized_boards b
              ON b.game_id = ri.game_id AND b.id = ri.recognized_board_id
            {image_join}
            WHERE ri.game_id = :game_id""",
        params,
    ):
        facts = images[boards[str(board_id)]]
        facts.item_ids.append(str(item_id))
        boards_with_items.add(str(board_id))
        if status != "superseded":
            facts.reasons.add(REVIEW_ITEM_NOT_SUPERSEDED)
        if sequence is None:
            facts.reasons.add(SEQUENCE_NUMBER_MISSING)
        else:
            facts.sequence_numbers.add(int(sequence))
        # A resolution by anyone but a ``system:`` actor is human work; a
        # superseded item without an actor is not provably automatic.
        if (resolved_by is not None or status == "superseded") and not _is_system_actor(
            resolved_by
        ):
            facts.reasons.add(HUMAN_REVIEW_RESOLUTION)
    for board_id, image_id in boards.items():
        if board_id not in boards_with_items:
            images[image_id].reasons.add(BOARD_WITHOUT_REVIEW_ITEM)

    for image_id, resolved_by in _rows(
        session,
        f"""SELECT b.source_image_id, e.resolved_by
            FROM game_data_v2.image_review_resolution_events e
            JOIN game_data_v2.image_review_items ri
              ON ri.game_id = e.game_id AND ri.id = e.review_item_id
            JOIN game_data_v2.recognized_boards b
              ON b.game_id = ri.game_id AND b.id = ri.recognized_board_id
            {image_join}
            WHERE e.game_id = :game_id""",
        params,
    ):
        if not _is_system_actor(resolved_by):
            images[str(image_id)].reasons.add(HUMAN_REVIEW_RESOLUTION)

    for image_id, corrected_by in _rows(
        session,
        f"""SELECT b.source_image_id, r.corrected_by
            FROM game_data_v2.image_board_geometry_revisions r
            JOIN game_data_v2.recognized_boards b
              ON b.game_id = r.game_id AND b.id = r.recognized_board_id
            {image_join}
            WHERE r.game_id = :game_id""",
        params,
    ):
        if not _is_system_actor(corrected_by):
            images[str(image_id)].reasons.add(HUMAN_BOARD_GEOMETRY_REVISION)

    for (image_id,) in _rows(
        session,
        f"""SELECT DISTINCT b.source_image_id
            FROM game_data_v2.image_board_geometry_review_events e
            JOIN game_data_v2.recognized_boards b
              ON b.game_id = e.game_id AND b.id = e.recognized_board_id
            {image_join}
            WHERE e.game_id = :game_id""",
        params,
    ):
        images[str(image_id)].reasons.add(BOARD_GEOMETRY_REVIEW_EVENT)

    for revision_id, image_id, created_by in _rows(
        session,
        """SELECT r.id, r.source_image_id, r.created_by
           FROM game_data_v2.image_source_geometry_revisions r
           JOIN game_data_v2.source_images s ON s.game_id = r.game_id AND s.id = r.source_image_id
             AND s.import_job_id = :import_job_id
           WHERE r.game_id = :game_id""",
        params,
    ):
        facts = images[str(image_id)]
        facts.revision_ids.append(str(revision_id))
        if not _is_system_actor(created_by):
            facts.reasons.add(HUMAN_SOURCE_GEOMETRY_REVISION)

    for image_id, start, slots in _rows(
        session,
        """SELECT DISTINCT ON (r.source_image_id) r.source_image_id, r.sequence_range_start,
                  r.active_board_slots
           FROM game_data_v2.image_source_geometry_revisions r
           JOIN game_data_v2.source_images s ON s.game_id = r.game_id AND s.id = r.source_image_id
             AND s.import_job_id = :import_job_id
           WHERE r.game_id = :game_id AND r.status <> 'reverted'
           ORDER BY r.source_image_id, r.revision DESC""",
        params,
    ):
        # The expected positions of the newest revision must be covered too.
        images[str(image_id)].sequence_numbers.update(int(start) + int(slot) for slot in slots)

    for image_id, status in _rows(
        session,
        """SELECT p.source_image_id, p.status
           FROM game_data_v2.image_board_geometry_pending p
           JOIN game_data_v2.source_images s ON s.game_id = p.game_id AND s.id = p.source_image_id
             AND s.import_job_id = :import_job_id
           WHERE p.game_id = :game_id""",
        params,
    ):
        if status == "pending":
            images[str(image_id)].reasons.add(OPEN_DEFERRED_GEOMETRY)

    files = {
        str(key): str(status)
        for key, status in _rows(
            session,
            """SELECT f.file_execution_key, f.workflow_status
               FROM game_data_v2.image_import_job_files f
               WHERE f.game_id = :game_id AND f.job_id = :import_job_id""",
            params,
        )
    }
    key_usage = Counter(facts.file_execution_key for facts in images.values())
    for facts in images.values():
        status = files.get(facts.file_execution_key)
        if status is None:
            facts.reasons.add(IMPORT_FILE_MISSING)
        elif status not in SETTLED_IMPORT_FILE_STATUSES:
            facts.reasons.add(IMPORT_FILE_NOT_SETTLED)
        if key_usage[facts.file_execution_key] > 1:
            facts.reasons.add(IMPORT_FILE_SHARED)
        if not facts.board_ids:
            facts.reasons.add(NO_BOARDS)
        if not facts.revision_ids:
            facts.reasons.add(NO_SOURCE_GEOMETRY_REVISION)
    return images


def _apply_live_successors(
    session: Session, game_id: UUID, import_job_id: UUID, images: Mapping[str, _ImageFacts]
) -> None:
    """Condition 3: each sequence number has a live item on an image of another import."""

    numbers = sorted({number for facts in images.values() for number in facts.sequence_numbers})
    if not numbers:
        return
    live = {
        int(value)
        for (value,) in _rows(
            session,
            """SELECT DISTINCT ri.sequence_number
               FROM game_data_v2.image_review_items ri
               JOIN game_data_v2.recognized_boards b
                 ON b.game_id = ri.game_id AND b.id = ri.recognized_board_id
                AND b.status <> 'rejected'
               JOIN game_data_v2.source_images s
                 ON s.game_id = b.game_id AND s.id = b.source_image_id
               WHERE ri.game_id = :game_id
                 AND ri.sequence_number = ANY(CAST(:numbers AS bigint[]))
                 AND ri.status IN ('pending', 'accepted', 'corrected')
                 AND s.import_job_id <> :import_job_id""",
            {"game_id": game_id, "import_job_id": import_job_id, "numbers": numbers},
        )
    }
    for facts in images.values():
        if facts.sequence_numbers - live:
            facts.reasons.add(SEQUENCE_WITHOUT_LIVE_SUCCESSOR)


def _superseded_by_completeness(session: Session, game_id: UUID, import_job_id: UUID) -> set[str]:
    """Images of the import the D-484 report classifies ``superseded``."""

    repository = SqlAlchemyImageGeometryCompletenessRepository(session)
    found: set[str] = set()
    cursor = None
    while True:
        page = repository.incomplete_images(
            game_id,
            import_job_id=import_job_id,
            image_state=GeometryImageState.SUPERSEDED,
            after=cursor,
            limit=MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE,
        )
        if page is None:
            raise RemovalError("REMOVAL_GAME_NOT_FOUND", "The game does not exist.")
        found.update(str(image.source_image_id) for image in page.images)
        if page.next_cursor is None:
            return found
        cursor = page.next_cursor


def _apply_protected_rows(
    session: Session, game_id: UUID, import_job_id: UUID, images: Mapping[str, _ImageFacts]
) -> None:
    """Condition 4: rows of the protected tables keep their image."""

    owners: dict[str, dict[str, str]] = {"image": {}, "board": {}, "item": {}, "revision": {}}
    for image_id, facts in images.items():
        owners["image"][image_id] = image_id
        owners["board"].update(dict.fromkeys(facts.board_ids, image_id))
        owners["item"].update(dict.fromkeys(facts.item_ids, image_id))
        owners["revision"].update(dict.fromkeys(facts.revision_ids, image_id))
    for table, columns in _PROTECTED_REFERENCES:
        for column, kind in columns:
            ids = sorted(owners[kind])
            if not ids:
                continue
            for (value,) in _rows(
                session,
                f"""SELECT DISTINCT t.{_quote(column)}::text
                    FROM {_relation(GAME_SCHEMA, table)} t
                    WHERE t.game_id = :game_id
                      AND t.{_quote(column)} = ANY(CAST(:ids AS uuid[]))""",
                {"game_id": game_id, "ids": ids},
            ):
                images[owners[kind][str(value)]].reasons.add(f"{PROTECTED_ROWS}:{table}")
    # Sequence-keyed rows of the import or of the image's sequence numbers.
    by_sequence: dict[int, set[str]] = defaultdict(set)
    by_checksum: dict[str, set[str]] = defaultdict(set)
    for image_id, facts in images.items():
        by_checksum[facts.checksum_sha256].add(image_id)
        for number in facts.sequence_numbers:
            by_sequence[number].add(image_id)
    numbers = sorted(by_sequence)
    for number, checksum, job_id in _rows(
        session,
        """SELECT a.sequence_number, a.source_checksum_sha256, a.import_job_id
           FROM game_data_v2.image_sequence_alternatives a
           WHERE a.game_id = :game_id
             AND (a.import_job_id = :import_job_id
                  OR a.sequence_number = ANY(CAST(:numbers AS bigint[])))""",
        {"game_id": game_id, "import_job_id": import_job_id, "numbers": numbers},
    ):
        hit = set(by_sequence.get(int(number), set()))
        if job_id == import_job_id:
            hit |= by_checksum.get(str(checksum), set())
        for image_id in hit:
            images[image_id].reasons.add(f"{PROTECTED_ROWS}:image_sequence_alternatives")
    for (number,) in _rows(
        session,
        """SELECT DISTINCT o.sequence_number
           FROM game_data_v2.image_sequence_source_override_events o
           WHERE o.game_id = :game_id AND o.sequence_number = ANY(CAST(:numbers AS bigint[]))""",
        {"game_id": game_id, "numbers": numbers},
    ):
        for image_id in by_sequence.get(int(number), set()):
            images[image_id].reasons.add(f"{PROTECTED_ROWS}:image_sequence_source_override_events")


def _scope_for(images: Mapping[str, _ImageFacts], candidates: Iterable[str]) -> _Scope:
    chosen = sorted(candidates)
    keys = sorted({images[image_id].file_execution_key for image_id in chosen})
    return _Scope(
        image_ids=tuple(chosen),
        board_ids=tuple(sorted(b for i in chosen for b in images[i].board_ids)),
        item_ids=tuple(sorted(x for i in chosen for x in images[i].item_ids)),
        revision_ids=tuple(sorted(r for i in chosen for r in images[i].revision_ids)),
        job_file_keys=tuple(keys),
        execution_keys=tuple(keys),
    )


def _parent_values(
    session: Session,
    parent: _OwnedTable,
    column: str,
    params: Mapping[str, object],
) -> dict[str, set[str]]:
    """Referenced column values of the delete-set rows of ``parent`` with their owners."""

    owner = "NULL" if parent.owner_sql is None else parent.owner_sql
    values: dict[str, set[str]] = defaultdict(set)
    for value, image_id in _rows(
        session,
        f"""SELECT t.{_quote(column)}::text, ({owner})::text
            FROM {_relation(parent.schema, parent.name)} t
            WHERE {_scope_predicate(parent)}""",
        params,
    ):
        if value is not None:
            values[str(value)].add("" if image_id is None else str(image_id))
    return values


def _outside_references(
    session: Session,
    key: ForeignKey,
    child_column: str,
    child_type: str,
    values: Sequence[str],
    params: Mapping[str, object],
) -> set[str]:
    """Referenced values that a row outside the delete set points to."""

    if not values:
        return set()
    array_type = _ARRAY_TYPES.get(child_type)
    if array_type is None:
        raise RemovalError(
            "REMOVAL_FOREIGN_KEY_TYPE_UNSUPPORTED",
            "Unsupported referencing column type.",
            details={"foreignKey": key.label, "type": child_type},
        )
    child = _OWNED_BY_NAME.get(key.child_root)
    member = "false" if child is None else f"({_scope_predicate(child)})"
    game_scoped = key.parent_root.startswith(f"{GAME_SCHEMA}.")
    game_filter = "t.game_id = :game_id AND " if game_scoped else ""
    found: set[str] = set()
    for value, is_member in _rows(
        session,
        f"""SELECT t.{_quote(child_column)}::text, {member}
            FROM {_relation(key.child_schema, key.child_table)} t
            WHERE {game_filter}t.{_quote(child_column)} = ANY(CAST(:fk_values AS {array_type}))""",
        {**params, "fk_values": list(values)},
    ):
        if not is_member:
            found.add(str(value))
    return found


def _reference_blocks(
    session: Session,
    game_id: UUID,
    import_job_id: UUID,
    images: Mapping[str, _ImageFacts],
    candidates: set[str],
    keys: Sequence[ForeignKey],
) -> dict[str, set[str]]:
    """Condition 6 for the current candidates: image id -> reasons."""

    scope = _scope_for(images, candidates)
    params = scope.params(game_id, import_job_id)
    blocks: dict[str, set[str]] = defaultdict(set)
    parent_cache: dict[tuple[str, str], dict[str, set[str]]] = {}
    for key in keys:
        parent = _OWNED_BY_NAME[key.parent_root]
        if parent.scope == "execution":
            continue  # shared executions are kept, not the image (see _deletable_keys)
        parent_column, child_column, child_type = _referenced_column(key)
        cache_key = (key.parent_root, parent_column)
        if cache_key not in parent_cache:
            parent_cache[cache_key] = _parent_values(session, parent, parent_column, params)
        values = parent_cache[cache_key]
        for value in _outside_references(
            session, key, child_column, child_type, sorted(values), params
        ):
            for image_id in values[value]:
                if image_id in candidates:
                    blocks[image_id].add(f"{REFERENCED_BY}:{key.label}")
    # ``ownerReviewItemId`` in resolution JSON of rows outside the delete set.
    item_owner = {item: image_id for image_id in candidates for item in images[image_id].item_ids}
    if item_owner:
        for table, membership in (
            (
                "image_review_items",
                "t.recognized_board_id = ANY(CAST(:board_ids AS uuid[]))",
            ),
            (
                "image_review_resolution_events",
                "t.review_item_id = ANY(CAST(:item_ids AS uuid[]))",
            ),
        ):
            for (value,) in _rows(
                session,
                f"""SELECT DISTINCT t.resolved_value->>'ownerReviewItemId'
                    FROM {_relation(GAME_SCHEMA, table)} t
                    WHERE t.game_id = :game_id
                      AND t.resolved_value->>'ownerReviewItemId' = ANY(CAST(:item_ids AS text[]))
                      AND NOT ({membership})""",
                params,
            ):
                blocks[item_owner[str(value)]].add(f"{OWNER_REFERENCE}:{table}")
    owners_by_kind = {
        "item": item_owner,
        "board": {b: i for i in candidates for b in images[i].board_ids},
    }
    for table, column, kinds in _SOFT_REFERENCES:
        for kind in kinds:
            ids = sorted(owners_by_kind[kind])
            if not ids:
                continue
            for (value,) in _rows(
                session,
                f"""SELECT DISTINCT t.{_quote(column)}::text
                    FROM {_relation(GAME_SCHEMA, table)} t
                    WHERE t.game_id = :game_id
                      AND t.{_quote(column)} = ANY(CAST(:ids AS uuid[]))""",
                {"game_id": game_id, "ids": ids},
            ):
                blocks[owners_by_kind[kind][str(value)]].add(f"{SOFT_REFERENCE}:{table}.{column}")
    return blocks


def _deletable_keys(
    session: Session,
    keys: Sequence[ForeignKey],
    scope: _Scope,
    params: Mapping[str, object],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Executions no row of any game references after the removal."""

    candidates = set(scope.execution_keys)
    retained: set[str] = set()
    for key in keys:
        if key.parent_root != "public.image_file_executions":
            continue
        child = _OWNED_BY_NAME.get(key.child_root)
        if child is not None and child.scope == "execution":
            continue  # stage results and manifests go with their execution
        _, child_column, child_type = _referenced_column(key)
        retained |= _outside_references(
            session, key, child_column, child_type, sorted(candidates), params
        )
    existing = {
        str(value)
        for (value,) in _rows(
            session,
            """SELECT e.file_execution_key FROM public.image_file_executions e
               WHERE e.file_execution_key = ANY(CAST(:keys AS varchar[]))""",
            {"keys": sorted(candidates)},
        )
    }
    deletable = tuple(sorted((candidates & existing) - retained))
    return deletable, tuple(sorted(candidates & retained))


def _count_rows(session: Session, table: _OwnedTable, params: Mapping[str, object]) -> int:
    return int(
        session.execute(
            text(
                f"SELECT count(*) FROM {_relation(table.schema, table.name)} t "
                f"WHERE {_scope_predicate(table)}"
            ),
            dict(params),
        ).scalar_one()
    )


def _queue_state(session: Session, game_id: UUID, import_job_id: UUID) -> dict[str, int] | None:
    row = (
        session.execute(
            text(
                """SELECT total_count, pending_count, accepted_count, corrected_count,
                          rejected_count, superseded_count
                   FROM game_data_v2.image_review_queue_states
                   WHERE game_id = :game_id AND import_job_id = :import_job_id"""
            ),
            {"game_id": game_id, "import_job_id": import_job_id},
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else {str(name): int(value) for name, value in row.items()}


def _completeness_images(report: GeometryCompletenessReport | None) -> dict[str, int]:
    if report is None:
        raise RemovalError("REMOVAL_GAME_NOT_FOUND", "The game does not exist.")
    images = report.images
    return {
        "total": images.total,
        "complete": images.complete,
        "incomplete_missing": images.incomplete_missing,
        "incomplete_partial": images.incomplete_partial,
        "incomplete_uncertain": images.incomplete_uncertain,
        "no_source_geometry": images.no_source_geometry,
        "import_failed": images.import_failed,
        "superseded": images.superseded,
    }


def build_removal_plan(session: Session, game_id: UUID, import_job_id: UUID) -> RemovalPlan:
    """Qualify every image of the import; the session must be bound to ``game_id``.

    An image qualifies only when all of these hold (TASK-0811):

    1. it belongs to the game and the import;
    2. it has boards, every board is ``rejected`` and has a review item, and
       every review item of those boards is ``superseded`` with a sequence number;
    3. every sequence number of its review items, boards and the expected
       positions of its newest source revision has a live review item
       (``pending``/``accepted``/``corrected``, on a non-rejected board) on an
       image of *another* import of the game, and the D-484 report classifies
       the image ``superseded``;
    4. no row of the protected tables (``_PROTECTED_REFERENCES``, plus sequence
       alternatives and source overrides of its sequence numbers) belongs to it;
    5. no board has an approved geometry or a geometry review event; every board
       and source geometry revision, review item resolution and resolution event
       was written by a ``system:`` actor; no deferred geometry row is open;
    6. no row outside the delete set references its rows: every foreign key of
       the catalog into an owned table, ``ownerReviewItemId`` in resolution JSON
       and the known non-FK id columns (``_SOFT_REFERENCES``);
    7. it has no geometry exception;

    and its import file is settled and not shared with another image of the
    import. Anything else keeps the whole image.
    """

    job = (
        session.execute(
            text("SELECT game_id, job_type, status FROM public.jobs WHERE id = :import_job_id"),
            {"import_job_id": import_job_id},
        )
        .mappings()
        .one_or_none()
    )
    if job is None or job["game_id"] != game_id:
        raise RemovalError(
            "REMOVAL_IMPORT_NOT_FOUND",
            "The import does not exist in this game.",
            details={"gameId": str(game_id), "importJobId": str(import_job_id)},
        )
    if job["job_type"] != "import":
        raise RemovalError(
            "REMOVAL_JOB_NOT_IMPORT",
            "The selected job is not an import.",
            details={"jobType": str(job["job_type"])},
        )
    blockers: list[str] = []
    active_jobs = int(
        session.execute(
            text(
                "SELECT count(*) FROM public.jobs WHERE game_id = :game_id "
                "AND status IN ('created', 'processing')"
            ),
            {"game_id": game_id},
        ).scalar_one()
    )
    if active_jobs:
        blockers.append(ACTIVE_GAME_JOB)

    keys = load_foreign_keys(session)
    order = delete_order(keys)
    images = _load_images(session, game_id, import_job_id)
    _apply_live_successors(session, game_id, import_job_id, images)
    _apply_protected_rows(session, game_id, import_job_id, images)
    superseded = _superseded_by_completeness(session, game_id, import_job_id)
    for image_id, facts in images.items():
        if image_id not in superseded:
            facts.reasons.add(COMPLETENESS_NOT_SUPERSEDED)

    candidates = {image_id for image_id, facts in images.items() if not facts.reasons}
    for _ in range(MAX_PLAN_ITERATIONS):
        blocks = _reference_blocks(session, game_id, import_job_id, images, candidates, keys)
        if not blocks:
            break
        for image_id, reasons in blocks.items():
            images[image_id].reasons.update(reasons)
            candidates.discard(image_id)
    else:
        raise RemovalError(
            "REMOVAL_PLAN_NOT_STABLE", "The reference check did not reach a fixed point."
        )

    scope = _scope_for(images, candidates)
    params = scope.params(game_id, import_job_id)
    deletable, retained = _deletable_keys(session, keys, scope, params)
    scope = _Scope(
        image_ids=scope.image_ids,
        board_ids=scope.board_ids,
        item_ids=scope.item_ids,
        revision_ids=scope.revision_ids,
        job_file_keys=scope.job_file_keys,
        execution_keys=deletable,
    )
    params = scope.params(game_id, import_job_id)
    row_counts = {table.qualified: _count_rows(session, table, params) for table in _OWNED_TABLES}
    queue_state = _queue_state(session, game_id, import_job_id)
    queue_items = row_counts["game_data_v2.image_review_queue_items"]
    if queue_items != row_counts["game_data_v2.image_review_items"] or (
        queue_items and (queue_state is None or queue_state["superseded_count"] < queue_items)
    ):
        blockers.append(QUEUE_PROJECTION_MISMATCH)

    decisions = tuple(
        ImageDecision(
            source_image_id=facts.source_image_id,
            relative_path=facts.relative_path,
            board_count=len(facts.board_ids),
            review_item_count=len(facts.item_ids),
            qualifies=image_id in candidates,
            reasons=tuple(sorted(facts.reasons)),
        )
        for image_id, facts in images.items()
    )
    completeness = _completeness_images(
        SqlAlchemyImageGeometryCompletenessRepository(session).completeness_report(game_id)
    )
    digest_payload = {
        "schema": REMOVAL_SCHEMA,
        "gameId": str(game_id),
        "importJobId": str(import_job_id),
        "imageIds": list(scope.image_ids),
        "rowCounts": row_counts,
        "executionKeys": list(deletable),
        "retainedExecutionKeys": list(retained),
        "deleteOrder": list(order),
        "blockers": sorted(blockers),
    }
    return RemovalPlan(
        game_id=game_id,
        import_job_id=import_job_id,
        import_job_status=str(job["status"]),
        images=decisions,
        image_ids=tuple(UUID(value) for value in scope.image_ids),
        row_counts=row_counts,
        delete_order=order,
        execution_keys=deletable,
        retained_execution_keys=retained,
        foreign_keys=tuple(key.label for key in keys),
        blockers=tuple(sorted(blockers)),
        queue_state=queue_state,
        plan_sha256=hashlib.sha256(canonical_json(digest_payload)).hexdigest(),
        completeness_images=completeness,
        scope=scope,
    )


def plan_report(plan: RemovalPlan) -> dict[str, Any]:
    kept = plan.kept
    reasons: Counter[str] = Counter(reason for image in kept for reason in image.reasons)
    deleted_boards = sum(image.board_count for image in plan.images if image.qualifies)
    return {
        "schema": REMOVAL_SCHEMA,
        "gameId": str(plan.game_id),
        "importJobId": str(plan.import_job_id),
        "importJobStatus": plan.import_job_status,
        "planSha256": plan.plan_sha256,
        "blockers": list(plan.blockers),
        "images": {
            "inImport": len(plan.images),
            "qualifying": len(plan.image_ids),
            "kept": len(kept),
            "keptByReason": dict(sorted(reasons.items())),
            "qualifyingBoards": deleted_boards,
        },
        "rowCounts": dict(plan.row_counts),
        "deleteOrder": list(plan.delete_order),
        "triggerMaintained": [t.qualified for t in _OWNED_TABLES if t.trigger_maintained],
        "executions": {
            "deleted": len(plan.execution_keys),
            "retainedShared": list(plan.retained_execution_keys),
        },
        "queueStateBefore": plan.queue_state,
        "completenessImagesBefore": dict(plan.completeness_images),
        "completenessImagesExpectedAfter": {
            **plan.completeness_images,
            "total": plan.completeness_images["total"] - len(plan.image_ids),
            "superseded": plan.completeness_images["superseded"] - len(plan.image_ids),
        },
        "foreignKeysChecked": list(plan.foreign_keys),
        "qualifyingImageIds": [str(value) for value in plan.image_ids],
        "keptImages": [
            {
                "sourceImageId": str(image.source_image_id),
                "relativePath": image.relative_path,
                "boards": image.board_count,
                "reviewItems": image.review_item_count,
                "reasons": list(image.reasons),
            }
            for image in kept
        ],
    }


# --- metrics and invariants -------------------------------------------------

_GAME_METRICS_SQL = """
SELECT
  (SELECT count(*) FROM game_data_v2.recognized_boards
    WHERE game_id = :game_id AND status <> 'rejected') AS live_boards,
  (SELECT count(*) FROM game_data_v2.image_review_items
    WHERE game_id = :game_id AND status IN ('pending', 'accepted', 'corrected')) AS live_items,
  (SELECT count(*) FROM game_data_v2.image_symbol_review_cells
    WHERE game_id = :game_id) AS symbol_cells,
  (SELECT count(*) FROM game_data_v2.image_symbol_review_events
    WHERE game_id = :game_id) AS symbol_events,
  (SELECT count(*) FROM game_data_v2.image_board_search_fast_documents
    WHERE game_id = :game_id) AS search_documents,
  (SELECT count(*) FROM game_data_v2.image_board_search_candidates
    WHERE game_id = :game_id) AS search_candidates,
  (SELECT count(*) FROM game_data_v2.image_sequence_canonical
    WHERE game_id = :game_id) AS canonical
"""

_LIVE_SEQUENCES_SQL = """
SELECT count(*), COALESCE(md5(string_agg(n::text, ',' ORDER BY n)), '')
FROM (
  SELECT DISTINCT sequence_number AS n FROM game_data_v2.image_review_items
  WHERE game_id = :game_id AND status IN ('pending', 'accepted', 'corrected')
    AND sequence_number IS NOT NULL
) x
"""


def _per_import(session: Session, sql: str, game_id: UUID) -> dict[str, int]:
    return {
        str(job): int(count)
        for job, count in session.execute(text(sql), {"game_id": game_id}).all()
    }


def collect_metrics(session: Session, plan: RemovalPlan) -> dict[str, Any]:
    game_id = plan.game_id
    row = session.execute(text(_GAME_METRICS_SQL), {"game_id": game_id}).mappings().one()
    sequences = session.execute(text(_LIVE_SEQUENCES_SQL), {"game_id": game_id}).one()
    params = plan.scope.params(game_id, plan.import_job_id)
    table_rows: dict[str, int] = {}
    for table in _OWNED_TABLES:
        if table.schema == GAME_SCHEMA:
            table_rows[table.qualified] = int(
                session.execute(
                    text(
                        f"SELECT count(*) FROM {_relation(table.schema, table.name)} "
                        "WHERE game_id = :game_id"
                    ),
                    {"game_id": game_id},
                ).scalar_one()
            )
        else:
            table_rows[table.qualified] = _count_rows(session, table, params)
    retained_rows = {
        table.qualified: int(
            session.execute(
                text(
                    f"SELECT count(*) FROM {_relation(table.schema, table.name)} t "
                    "WHERE t.file_execution_key = ANY(CAST(:keys AS varchar[]))"
                ),
                {"keys": list(plan.retained_execution_keys)},
            ).scalar_one()
        )
        for table in _OWNED_TABLES
        if table.scope == "execution"
    }
    return {
        **{str(name): int(value) for name, value in row.items()},
        "live_sequence_count": int(sequences[0]),
        "live_sequence_md5": str(sequences[1]),
        "images_by_import": _per_import(
            session,
            "SELECT import_job_id, count(*) FROM game_data_v2.source_images "
            "WHERE game_id = :game_id GROUP BY 1",
            game_id,
        ),
        "boards_by_import": _per_import(
            session,
            "SELECT s.import_job_id, count(*) FROM game_data_v2.recognized_boards b "
            "JOIN game_data_v2.source_images s ON s.game_id = b.game_id "
            "AND s.id = b.source_image_id WHERE b.game_id = :game_id GROUP BY 1",
            game_id,
        ),
        "items_by_import": _per_import(
            session,
            "SELECT s.import_job_id, count(*) FROM game_data_v2.image_review_items ri "
            "JOIN game_data_v2.recognized_boards b ON b.game_id = ri.game_id "
            "AND b.id = ri.recognized_board_id "
            "JOIN game_data_v2.source_images s ON s.game_id = b.game_id "
            "AND s.id = b.source_image_id WHERE ri.game_id = :game_id GROUP BY 1",
            game_id,
        ),
        "table_rows": table_rows,
        "retained_execution_rows": retained_rows,
        "job_statuses": {
            str(job): str(status)
            for job, status in session.execute(
                text("SELECT id, status FROM public.jobs WHERE game_id = :game_id"),
                {"game_id": game_id},
            ).all()
        },
        "queue_state": _queue_state(session, game_id, plan.import_job_id),
        "completeness": _completeness_images(
            SqlAlchemyImageGeometryCompletenessRepository(session).completeness_report(game_id)
        ),
    }


_UNCHANGED_SCALARS: Final = (
    "live_boards",
    "live_items",
    "symbol_cells",
    "symbol_events",
    "search_documents",
    "search_candidates",
    "canonical",
    "live_sequence_count",
    "live_sequence_md5",
)


def invariant_violations(
    plan: RemovalPlan, before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[str]:
    """Every failed invariant of a removal (empty when the removal may commit)."""

    violations: list[str] = []
    for name in _UNCHANGED_SCALARS:
        if before[name] != after[name]:
            violations.append(f"{name}: {before[name]} -> {after[name]}")
    target = str(plan.import_job_id)
    removed = {
        "images_by_import": len(plan.image_ids),
        "boards_by_import": plan.row_counts["game_data_v2.recognized_boards"],
        "items_by_import": plan.row_counts["game_data_v2.image_review_items"],
    }
    for name, count in removed.items():
        jobs = set(before[name]) | set(after[name])
        for job in sorted(jobs):
            expected = before[name].get(job, 0) - (count if job == target else 0)
            if after[name].get(job, 0) != expected:
                violations.append(
                    f"{name}[{job}]: expected {expected}, found {after[name].get(job, 0)}"
                )
    for table, planned in plan.row_counts.items():
        difference = before["table_rows"][table] - after["table_rows"][table]
        if difference != planned:
            violations.append(f"rows {table}: planned {planned}, removed {difference}")
    if before["retained_execution_rows"] != after["retained_execution_rows"]:
        violations.append("retained shared execution rows changed")
    if before["job_statuses"] != after["job_statuses"]:
        violations.append("job statuses changed")
    items = plan.row_counts["game_data_v2.image_review_items"]
    queue_before, queue_after = before["queue_state"], after["queue_state"]
    if queue_before is not None and items:
        if queue_before["total_count"] == items:
            if queue_after is not None:
                violations.append("queue state should be gone with its last item")
        elif queue_after is None:
            violations.append("queue state disappeared")
        else:
            expected = dict(queue_before)
            expected["total_count"] -= items
            expected["superseded_count"] -= items
            if queue_after != expected:
                violations.append(f"queue state: expected {expected}, found {queue_after}")
    elif queue_before != queue_after:
        violations.append("queue state changed without removed items")
    deleted_images = len(plan.image_ids)
    completeness_before, completeness_after = before["completeness"], after["completeness"]
    for state, value in completeness_before.items():
        expected = value - deleted_images if state in ("total", "superseded") else value
        if completeness_after[state] != expected:
            violations.append(
                f"completeness {state}: expected {expected}, found {completeness_after[state]}"
            )
    return violations


# --- backup -------------------------------------------------------------------


def _primary_key(session: Session, table: _OwnedTable) -> tuple[str, ...]:
    columns = tuple(
        str(value)
        for (value,) in session.execute(
            text(
                """SELECT a.attname FROM pg_index i
                   JOIN pg_class c ON c.oid = i.indrelid
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   JOIN unnest(i.indkey) WITH ORDINALITY k(attnum, n) ON true
                   JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
                   WHERE i.indisprimary AND n.nspname = :schema AND c.relname = :name
                   ORDER BY k.n"""
            ),
            {"schema": table.schema, "name": table.name},
        ).all()
    )
    if not columns:
        raise RemovalError("REMOVAL_PRIMARY_KEY_MISSING", table.qualified)
    return columns


def _export(
    connection: Connection,
    sql: str,
    params: Mapping[str, object],
    path: Path,
) -> tuple[int, str, int]:
    digest = hashlib.sha256()
    rows = written = 0
    with path.open("xb") as target:
        result = connection.execute(
            text(sql), dict(params), execution_options={"stream_results": True}
        )
        for partition in result.partitions(500):
            for (line,) in partition:
                data = str(line).encode("utf-8") + b"\n"
                target.write(data)
                digest.update(data)
                rows += 1
                written += len(data)
        target.flush()
        os.fsync(target.fileno())
    return rows, digest.hexdigest(), written


def write_backup(session: Session, plan: RemovalPlan, directory: Path) -> dict[str, Any]:
    """JSON Lines copy of every row the removal deletes or the trigger touches."""

    directory.mkdir(parents=True, exist_ok=False)
    connection = session.connection()
    params = plan.scope.params(plan.game_id, plan.import_job_id)
    tables: list[dict[str, Any]] = []
    for table in _OWNED_TABLES:
        order = ", ".join(f"t.{_quote(column)}" for column in _primary_key(session, table))
        file_name = f"{table.qualified}.jsonl"
        rows, checksum, size = _export(
            connection,
            f"SELECT row_to_json(t)::text FROM {_relation(table.schema, table.name)} t "
            f"WHERE {_scope_predicate(table)} ORDER BY {order}",
            params,
            directory / file_name,
        )
        if rows != plan.row_counts[table.qualified]:
            raise RemovalError(
                "REMOVAL_BACKUP_COUNT_MISMATCH",
                "The backup does not hold every planned row.",
                details={"table": table.qualified, "planned": plan.row_counts[table.qualified]},
            )
        tables.append(
            {
                "table": table.qualified,
                "file": file_name,
                "rows": rows,
                "bytes": size,
                "sha256": checksum,
                "deletedBy": "trigger" if table.trigger_maintained else "statement",
            }
        )
    rows, checksum, size = _export(
        connection,
        "SELECT row_to_json(t)::text FROM game_data_v2.image_review_queue_states t "
        "WHERE t.game_id = :game_id AND t.import_job_id = :import_job_id",
        params,
        directory / f"{_QUEUE_STATE_TABLE}.jsonl",
    )
    tables.append(
        {
            "table": _QUEUE_STATE_TABLE,
            "file": f"{_QUEUE_STATE_TABLE}.jsonl",
            "rows": rows,
            "bytes": size,
            "sha256": checksum,
            "deletedBy": "trigger (counters updated, row removed with its last item)",
        }
    )
    manifest = {
        "schema": REMOVAL_SCHEMA,
        "kind": "backup-manifest",
        "gameId": str(plan.game_id),
        "importJobId": str(plan.import_job_id),
        "planSha256": plan.plan_sha256,
        "snapshot": "REPEATABLE READ (same transaction as the deletes)",
        "createdAt": datetime.now(UTC).isoformat(),
        "imageIds": [str(value) for value in plan.image_ids],
        "tables": tables,
    }
    path = directory / "manifest.json"
    with path.open("x", encoding="utf-8") as target:
        target.write(json.dumps(manifest, indent=2, sort_keys=True))
        target.flush()
        os.fsync(target.fileno())
    return manifest


# --- repository ---------------------------------------------------------------


class SupersededImportImageRemovalRepository:
    """Preview (read-only) and execute (one transaction) over the owner engine."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def preview(self, game_id: UUID, import_job_id: UUID) -> RemovalPlan:
        """Plan in one ``REPEATABLE READ READ ONLY`` transaction; always rolled back."""

        with self._engine.connect() as connection:
            _require_owner_role(connection)
            connection.rollback()
            with Session(bind=connection) as session:
                # The first statement of the session's transaction fixes its mode.
                session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                _require_transaction(session.connection(), read_only=True)
                _set_limits(session.connection())
                try:
                    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
                    return build_removal_plan(session, game_id, import_job_id)
                finally:
                    session.rollback()

    def execute(
        self,
        game_id: UUID,
        import_job_id: UUID,
        *,
        confirm_plan_sha256: str,
        backup_root: Path,
        before_invariants: Callable[[Session], None] | None = None,
    ) -> RemovalExecution:
        """Delete the qualifying images in one transaction or nothing at all.

        ``before_invariants`` is a test seam that runs after the deletes and
        before the invariant check (to prove that a violation rolls back).
        """

        lock_key = str(game_id)
        with self._engine.connect() as connection:
            _require_owner_role(connection)
            connection.rollback()
            # Session-level exclusive lifecycle fence, taken *before* the
            # REPEATABLE READ snapshot so the plan sees every write that
            # finished before the fence; released after COMMIT/ROLLBACK.
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(hashtextextended(:key, 519))"),
                {"key": lock_key},
            ).scalar_one()
            connection.commit()
            if not acquired:
                raise RemovalError(
                    "REMOVAL_GAME_LOCKED",
                    "Another lifecycle operation or writer holds the game fence.",
                )
            try:
                return self._execute_locked(
                    connection,
                    game_id,
                    import_job_id,
                    confirm_plan_sha256=confirm_plan_sha256,
                    backup_root=backup_root,
                    before_invariants=before_invariants,
                )
            finally:
                connection.rollback()
                connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:key, 519))"),
                    {"key": lock_key},
                )
                connection.commit()

    def _execute_locked(
        self,
        connection: Connection,
        game_id: UUID,
        import_job_id: UUID,
        *,
        confirm_plan_sha256: str,
        backup_root: Path,
        before_invariants: Callable[[Session], None] | None,
    ) -> RemovalExecution:
        with Session(bind=connection) as session:
            session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ WRITE"))
            _require_transaction(session.connection(), read_only=False)
            _set_limits(session.connection())
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
            plan = build_removal_plan(session, game_id, import_job_id)
            if plan.plan_sha256 != confirm_plan_sha256:
                raise RemovalError(
                    "REMOVAL_PLAN_CHANGED",
                    "The plan differs from the confirmed preview; run a fresh preview.",
                    details={"expected": confirm_plan_sha256, "current": plan.plan_sha256},
                )
            if plan.blockers:
                raise RemovalError(
                    "REMOVAL_BLOCKED",
                    "The removal is blocked.",
                    details={"blockers": list(plan.blockers)},
                )
            if not plan.image_ids:
                return RemovalExecution(
                    plan=plan,
                    committed=False,
                    deleted_counts={table: 0 for table in plan.row_counts},
                    backup_directory=None,
                    backup_manifest=None,
                    metrics_before=None,
                    metrics_after=None,
                )
            before = collect_metrics(session, plan)
            directory = backup_root / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            manifest = write_backup(session, plan, directory)
            params = plan.scope.params(game_id, import_job_id)
            deleted: dict[str, int] = {}
            for name in plan.delete_order:
                table = _OWNED_BY_NAME[name]
                if table.trigger_maintained:
                    continue
                result = session.execute(
                    text(
                        f"DELETE FROM {_relation(table.schema, table.name)} t "
                        f"WHERE {_scope_predicate(table)}"
                    ),
                    params,
                )
                count = int(getattr(result, "rowcount", -1))
                if count != plan.row_counts[name]:
                    raise RemovalInvariantError(
                        [f"deleted {name}: planned {plan.row_counts[name]}, deleted {count}"]
                    )
                deleted[name] = count
            for table in _OWNED_TABLES:
                if table.trigger_maintained:
                    deleted[table.qualified] = plan.row_counts[table.qualified] - _count_rows(
                        session, table, params
                    )
            if before_invariants is not None:
                before_invariants(session)
            after = collect_metrics(session, plan)
            violations = invariant_violations(plan, before, after)
            if violations:
                raise RemovalInvariantError(violations)
            session.commit()
            return RemovalExecution(
                plan=plan,
                committed=True,
                deleted_counts=deleted,
                backup_directory=directory,
                backup_manifest=manifest,
                metrics_before=before,
                metrics_after=after,
            )


__all__ = [
    "ForeignKey",
    "ImageDecision",
    "RemovalError",
    "RemovalExecution",
    "RemovalInvariantError",
    "RemovalPlan",
    "SupersededImportImageRemovalRepository",
    "build_removal_plan",
    "collect_metrics",
    "delete_order",
    "invariant_violations",
    "load_foreign_keys",
    "plan_report",
    "write_backup",
]
