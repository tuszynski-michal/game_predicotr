"""Exact, streamed preservation proof for the existing compact chat archive."""

from __future__ import annotations

import hashlib
import struct
import time
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Connection, text

from game_predictor_api.storage.game_deletion_policy_v1 import LEGACY_ID, DeletionError, digest


def verify_database_archive(connection: Connection, proof: Mapping[str, Any]) -> None:
    """Run before the first deletion, again under the write fence at activation.

    Fetch 2000 compact rows at a time. Resume uses the immutable receipt proof
    because the live index may already have been partially removed.
    """
    deadline = time.monotonic() + 25
    symbols = connection.execute(
        text(
            "SELECT mobile_code,code,name FROM public.symbols "
            "WHERE game_id=:game ORDER BY mobile_code"
        ),
        {"game": LEGACY_ID},
    ).all()
    if digest([tuple(row) for row in symbols]) != proof.get("symbolsSha256"):
        raise DeletionError("GAME_DELETE_ARCHIVE_SYMBOLS_MISMATCH", "Symbol catalog differs")
    sha = hashlib.sha256()
    count = 0
    with connection.execute(
        text(
            "SELECT sequence_number,status,primary_symbol_mobile_codes "
            "FROM public.image_board_search_fast_documents "
            "WHERE game_id=:game ORDER BY sequence_number"
        ).execution_options(yield_per=2000),
        {"game": LEGACY_ID},
    ) as rows:
        for sequence, status, codes in rows:
            if time.monotonic() > deadline:
                raise DeletionError(
                    "GAME_DELETE_ARCHIVE_TIMEOUT", "Preservation comparison exceeded 25s"
                )
            normalized = tuple(0 if value is None else int(value) for value in codes)
            if len(normalized) != 15 or any(value < 0 or value > 32767 for value in normalized):
                raise DeletionError("GAME_DELETE_ARCHIVE_TOPOLOGY", "Expected canonical 3x5 layout")
            sha.update(f"{int(sequence)}:{status}:".encode())
            sha.update(struct.pack("<15h", *normalized))
            count += 1
    if count != proof.get("layoutCount") or sha.hexdigest() != proof.get("layoutFingerprint"):
        raise DeletionError(
            "GAME_DELETE_ARCHIVE_CONTENT_MISMATCH", "Layouts differ from saved archive"
        )
