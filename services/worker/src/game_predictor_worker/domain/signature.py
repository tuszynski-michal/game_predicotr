"""Fixed-width decimal signature codec."""

from __future__ import annotations

from collections.abc import Sequence

from game_predictor_worker.domain.errors import DomainErrorCode, DomainValidationError

MAX_SIGNATURE_CELL_WIDTH = 5
MAX_SYMBOL_MOBILE_CODE = 32_767


def _validate_cell_width(cell_width: int) -> None:
    if isinstance(cell_width, bool) or cell_width < 1 or cell_width > MAX_SIGNATURE_CELL_WIDTH:
        raise DomainValidationError(
            DomainErrorCode.INVALID_CELL_WIDTH,
            f"Signature cell width must be between 1 and {MAX_SIGNATURE_CELL_WIDTH}.",
        )


def _encode_cell(symbol_code: int, cell_width: int) -> str:
    if isinstance(symbol_code, bool) or symbol_code < 1 or symbol_code > MAX_SYMBOL_MOBILE_CODE:
        raise DomainValidationError(
            DomainErrorCode.INVALID_SYMBOL_CODE,
            f"Symbol code must be between 1 and {MAX_SYMBOL_MOBILE_CODE}.",
        )

    encoded = str(symbol_code)
    if len(encoded) > cell_width:
        raise DomainValidationError(
            DomainErrorCode.SYMBOL_CODE_OUT_OF_RANGE,
            f"Symbol code {symbol_code} does not fit width {cell_width}.",
        )

    return encoded.zfill(cell_width)


def encode_signature(cells: Sequence[int], cell_width: int) -> str:
    """Encode row-major cells into an unambiguous opaque signature."""

    _validate_cell_width(cell_width)
    return "".join(_encode_cell(cell, cell_width) for cell in cells)


def encode_signature_prefix(cells: Sequence[int | None], cell_width: int) -> str:
    """Encode the contiguous populated prefix of a row-major board."""

    _validate_cell_width(cell_width)
    prefix: list[int] = []
    reached_empty_cell = False

    for cell in cells:
        if cell is None:
            reached_empty_cell = True
            continue
        if reached_empty_cell:
            raise DomainValidationError(
                DomainErrorCode.NON_PREFIX_BOARD,
                "A populated cell cannot occur after an empty prefix cell.",
            )
        prefix.append(cell)

    return "".join(_encode_cell(cell, cell_width) for cell in prefix)


def decode_signature(
    signature: str,
    cell_width: int,
    expected_cell_count: int | None = None,
) -> tuple[int, ...]:
    """Decode and validate a fixed-width decimal signature."""

    _validate_cell_width(cell_width)
    if len(signature) % cell_width != 0 or not signature.isascii() or not signature.isdigit():
        if signature == "":
            cells: tuple[int, ...] = ()
        else:
            raise DomainValidationError(
                DomainErrorCode.INVALID_SIGNATURE,
                "Signature must contain complete fixed-width decimal cells.",
            )
    else:
        cells = tuple(
            int(signature[offset : offset + cell_width])
            for offset in range(0, len(signature), cell_width)
        )

    if expected_cell_count is not None and (
        isinstance(expected_cell_count, bool)
        or expected_cell_count < 0
        or len(cells) != expected_cell_count
    ):
        raise DomainValidationError(
            DomainErrorCode.INVALID_SIGNATURE,
            f"Signature contains {len(cells)} cells; expected {expected_cell_count}.",
        )

    if any(symbol_code < 1 for symbol_code in cells):
        raise DomainValidationError(
            DomainErrorCode.INVALID_SIGNATURE,
            "Signature contains an invalid symbol code.",
        )

    return cells
