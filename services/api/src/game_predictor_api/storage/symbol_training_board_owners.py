"""Evaluate the existing current-source fence once per distinct board binding.

All fifteen cells share these inputs. Materialization prevents PostgreSQL from
inlining the guard back into a per-cell filter. The guard, its arguments, and
the fast-document owner join retain their existing meaning.
"""


def current_symbol_board_owners_sql(*, approved_only: bool) -> str:
    approval = "AND c.review_state = 'approved'" if approved_only else ""
    return f"""
    WITH symbol_board_keys AS MATERIALIZED (
      SELECT DISTINCT c.game_id, c.recognized_board_id, c.review_item_id, c.sequence_number
      FROM image_symbol_review_cells c
      WHERE c.game_id = :game_id {approval}
    ), current_symbol_board_owners AS MATERIALIZED (
      SELECT k.*
      FROM symbol_board_keys k
      JOIN recognized_boards rb ON rb.game_id = :game_id AND rb.id = k.recognized_board_id
      JOIN source_images src ON src.game_id = :game_id AND src.id = rb.source_image_id
      JOIN image_board_search_fast_documents d ON d.game_id = :game_id
        AND d.game_id = k.game_id
        AND d.sequence_number = k.sequence_number AND d.review_item_id = k.review_item_id
      WHERE k.game_id = :game_id AND public.source_replacement_current_v1(
        k.game_id, src.id, src.checksum_sha256, k.sequence_number, k.review_item_id)
    )
    """


CURRENT_SYMBOL_BOARD_OWNER_JOIN = """
JOIN current_symbol_board_owners owner ON owner.game_id = c.game_id
  AND owner.recognized_board_id = c.recognized_board_id
  AND owner.review_item_id = c.review_item_id AND owner.sequence_number = c.sequence_number
"""
