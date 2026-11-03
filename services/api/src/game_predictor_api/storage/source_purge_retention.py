"""Exact file consumers for both purge preview and post-commit finalization."""

from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.storage.sequence_ownership_lock import (
    SequenceOwnershipLockMode,
    acquire_sequence_ownership_lock,
)


def lock_purge_games(session: Session, *, shared: bool = False) -> None:
    """Same ordering for a purge and its fresh cross-game finalization check."""
    session.execute(text("SET LOCAL lock_timeout='5s'"))
    session.execute(text("SET LOCAL statement_timeout='30s'"))
    games = session.scalars(
        text("SELECT game_id FROM public.game_storage_locations ORDER BY game_id")
    )
    for game in games:
        acquire_sequence_ownership_lock(
            session,
            game_id=game,
            mode=SequenceOwnershipLockMode.SHARED
            if shared
            else SequenceOwnershipLockMode.EXCLUSIVE,
        )


class SourcePurgeRetention:
    def __init__(
        self,
        factory: Callable[[], Session],
        fallback: Callable[[tuple[str, ...]], AbstractContextManager[bool]] | None = None,
    ) -> None:
        self.factory = factory
        self.fallback = fallback

    @contextmanager
    def dispatch(self, operation_key: str, paths: tuple[str, ...]) -> Iterator[bool]:
        with self.factory() as session:
            known = session.scalar(
                text("""SELECT EXISTS(SELECT 1 FROM
              game_data_v2.source_replacement_commands
              WHERE response->'purge'->>'quarantineKey'=:key)"""),
                {"key": operation_key},
            )
        if known:
            with self.guard(operation_key, paths) as protected:
                yield protected
        elif self.fallback is not None:
            with self.fallback(paths) as protected:
                if not isinstance(protected, bool):
                    raise ValueError("SOURCE_REPLACEMENT_PURGE_RETENTION_UNAVAILABLE")
                yield protected
        else:
            raise ValueError("SOURCE_REPLACEMENT_PURGE_RETENTION_UNAVAILABLE")

    @staticmethod
    def retained(
        session: Session, paths: Sequence[str], excluded: Sequence[UUID], game: UUID
    ) -> set[str]:
        """Only actual paths/roots; never infer ownership from a UUID substring."""
        if not paths:
            return set()
        # Normalize the small candidate set once. Exact consumers are filtered
        # in their own branches, never joined N_candidates x N_domain_rows.
        normalized = {path: path.removeprefix("data/") for path in paths}
        variants = sorted(
            {variant for path in normalized.values() for variant in (path, "data/" + path)}
        )
        rows = session.execute(
            text("""
        WITH consumers(path,is_root) AS (
          SELECT relative_path,false FROM game_data_v2.source_images
           WHERE relative_path=ANY(CAST(:variants AS text[])) AND purged_at IS NULL
            AND NOT(game_id=:game AND id=ANY(CAST(:excluded AS uuid[])))
          UNION ALL SELECT b.board_relative_path,false FROM game_data_v2.recognized_boards b
           WHERE b.board_relative_path=ANY(CAST(:variants AS text[]))
            AND NOT(b.game_id=:game AND b.source_image_id=ANY(CAST(:excluded AS uuid[])))
          UNION ALL SELECT c.crop_relative_path,false FROM game_data_v2.image_symbol_review_cells c
           JOIN game_data_v2.recognized_boards b ON b.game_id=c.game_id AND
           b.id=c.recognized_board_id
           WHERE c.crop_relative_path=ANY(CAST(:variants AS text[]))
            AND NOT(b.game_id=:game AND b.source_image_id=ANY(CAST(:excluded AS uuid[])))
          UNION ALL SELECT g.board_relative_path,false FROM
          game_data_v2.image_board_geometry_revisions g
           JOIN game_data_v2.recognized_boards b ON b.game_id=g.game_id AND
           b.id=g.recognized_board_id
           WHERE g.board_relative_path=ANY(CAST(:variants AS text[]))
            AND NOT(b.game_id=:game AND b.source_image_id=ANY(CAST(:excluded AS uuid[])))
          UNION ALL SELECT crop->>'cropRelativePath',false
           FROM game_data_v2.image_board_geometry_revisions g
           JOIN game_data_v2.recognized_boards b ON b.game_id=g.game_id AND
           b.id=g.recognized_board_id
           CROSS JOIN LATERAL jsonb_array_elements(g.crop_artifacts) crop
           WHERE crop->>'cropRelativePath'=ANY(CAST(:variants AS text[]))
            AND NOT(b.game_id=:game AND b.source_image_id=ANY(CAST(:excluded AS uuid[])))
          UNION ALL SELECT p,false FROM public.source_image_crops crop
           JOIN game_data_v2.source_images s ON s.checksum_sha256=crop.original_checksum_sha256
           CROSS JOIN LATERAL
           unnest(ARRAY[crop.crop_relative_path,crop.attestation_relative_path]) p
           WHERE p=ANY(CAST(:variants AS text[])) AND s.purged_at IS NULL
            AND NOT(s.game_id=:game AND s.id=ANY(CAST(:excluded AS uuid[])))
          UNION ALL SELECT image_relative_path,false FROM game_data_v2.symbol_reference_images
           WHERE image_relative_path=ANY(CAST(:variants AS text[]))
          UNION ALL SELECT artifact_relative_path,true FROM game_data_v2.verified_training_cohorts
          UNION ALL SELECT artifact_relative_path,true FROM
          game_data_v2.image_verified_cohort_exports
          UNION ALL SELECT p,true FROM game_data_v2.symbol_model_iterations m
           CROSS JOIN LATERAL
           unnest(ARRAY[m.dataset_manifest_relative_path,m.checkpoint_relative_path,
             m.candidate_manifest_relative_path,m.gate_report_relative_path,m.origin_manifest_relative_path])
             p
          UNION ALL SELECT manifest_json::jsonb->>'managedDirectory',true FROM
          public.grid_model_versions
        ) SELECT DISTINCT path,is_root FROM consumers WHERE path IS NOT NULL
        """),
            {"variants": variants, "excluded": list(excluded), "game": game},
        )
        exact, roots = set(), set()
        for path, is_root in rows:
            value = path.removeprefix("data/")
            exact.add(value)
            if is_root:
                roots.add(value.rstrip("/") + "/")
        # Prefix matching is limited to model/cohort/export roots, not the
        # board/cell population. Preserve the caller's exact path spelling.
        return {
            path
            for path, value in normalized.items()
            if value in exact or any(value.startswith(root) for root in roots)
        }

    @contextmanager
    def guard(self, operation_key: str, paths: tuple[str, ...]) -> Iterator[bool]:
        """None of the purged parents count as a live consumer after commit."""
        with self.factory() as session:
            try:
                lock_purge_games(session, shared=True)
                receipt = session.execute(
                    text("""SELECT response FROM
                  game_data_v2.source_replacement_commands
                  WHERE response->'purge'->>'quarantineKey'=:key"""),
                    {"key": operation_key},
                ).scalar_one_or_none()
                if receipt is None:
                    raise ValueError("SOURCE_REPLACEMENT_PURGE_RECEIPT_MISSING")
                expected = {p["path"] for p in receipt["purge"]["fileProof"]}
                if not set(paths).issubset(expected):
                    raise ValueError("SOURCE_REPLACEMENT_PURGE_RECEIPT_MISMATCH")
                excluded = [UUID(value) for value in receipt["purge"]["sourceIds"]]
                yield bool(self.retained(session, paths, excluded, UUID(receipt["game_id"])))
            finally:
                session.rollback()
