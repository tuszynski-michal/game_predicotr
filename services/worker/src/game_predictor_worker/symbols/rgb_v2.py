"""RGB v2 symbol choice for pending review cells (plan SYMBOL_RGB_V2_REPROCESSING_PLAN).

The frozen ``SpatialSymbolCnn`` chooses the symbol from the original RGB crop. The
unchanged reference library only confirms it: a unanimous 7/7 consensus of both
library descriptors on the same class makes the proposal confirmed, anything else
leaves the CNN proposal tentative (the ``?`` of the audit UI). A cell is written
only when its symbol or its confirmed/tentative status changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MODEL_VERSION = "symbol-rgb-v2"
ENTRY_KEY = "rgbV2"
CONFIRMED_CONFIDENCE = 0.99
# Not a calibrated probability: a fixed marker that places the cell in the Admin
# band below 60%, where the operator reviews it.
TENTATIVE_CONFIDENCE = 0.50

Status = Literal["confirmed", "tentative"]
Source = Literal["model", "reference_library", "rgb_v2"]

# Half-open bands of the original model confidence, in processing order.
BANDS: tuple[tuple[str, float, float], ...] = (
    ("lt60", 0.0, 0.6),
    ("60-80", 0.6, 0.8),
    ("80-90", 0.8, 0.9),
    ("90-99", 0.9, 0.99),
    ("99-100", 0.99, 1.0001),
)


def band_of(original_confidence: float) -> str:
    """Band label of an original model confidence; raises outside [0, 1.0001)."""

    for label, low, high in BANDS:
        if low <= original_confidence < high:
            return label
    raise ValueError(f"Confidence {original_confidence!r} is outside every band.")


def band_bounds(label: str) -> tuple[float, float]:
    for name, low, high in BANDS:
        if name == label:
            return low, high
    raise ValueError(f"Unknown band {label!r}.")


def current_status(confidence: float) -> Status:
    """Status the Admin shows today: 0.99 and above is treated as confirmed."""

    return "confirmed" if confidence >= CONFIRMED_CONFIDENCE else "tentative"


def proposal_status(candidate_index: int, library_class_index: int | None) -> Status:
    """Confirmed only when the library consensus names the CNN candidate."""

    return "confirmed" if library_class_index == candidate_index else "tentative"


def confidence_for(status: Status) -> float:
    return CONFIRMED_CONFIDENCE if status == "confirmed" else TENTATIVE_CONFIDENCE


@dataclass(frozen=True, slots=True)
class CurrentPrediction:
    symbol_code: str
    confidence: float
    source: Source
    original_confidence: float


@dataclass(frozen=True, slots=True)
class RgbDecision:
    symbol_code: str
    status: Status
    cnn_symbol_code: str
    library_symbol_code: str | None

    @property
    def confidence(self) -> float:
        return confidence_for(self.status)


def decide_rgb(
    class_codes: tuple[str, ...], candidate_index: int, library_class_index: int | None
) -> RgbDecision:
    if not 0 <= candidate_index < len(class_codes):
        raise ValueError(f"CNN candidate {candidate_index} is outside the catalogue.")
    if library_class_index is not None and not 0 <= library_class_index < len(class_codes):
        raise ValueError(f"Library class {library_class_index} is outside the catalogue.")
    code = class_codes[candidate_index]
    return RgbDecision(
        symbol_code=code,
        status=proposal_status(candidate_index, library_class_index),
        cnn_symbol_code=code,
        library_symbol_code=None
        if library_class_index is None
        else class_codes[library_class_index],
    )


# Version of the write rules; part of the preview rows key, so a rule change recomputes rows.
WRITE_RULES_VERSION = 2


def library_keeps_current(current: CurrentPrediction, decision: RgbDecision) -> bool:
    """The unanimous library names the current symbol and only the CNN dissents.

    Added at the TASK-0874 gate (< 60% band): 3 227 of 3 563 planned writes were
    such cells, and their samples showed the CNN misled by colour casts (stars and
    watermelon slices proposed as lemon or orange). A lone CNN dissent is no reason
    to replace a symbol the library confirms.
    """

    return (
        decision.status == "tentative"
        and decision.symbol_code != current.symbol_code
        and decision.library_symbol_code == current.symbol_code
    )


# Bands written only where the symbol changes (operator decision 2026-10-06 at the
# TASK-0878 gate): in 99-100% the status rule alone would have demoted ~1 million
# cells with a correct symbol to review (lemons 68%), for ~2 800 real corrections.
SYMBOL_CHANGES_ONLY_BANDS = frozenset({"99-100"})


def needs_write(
    current: CurrentPrediction, decision: RgbDecision, *, symbol_changes_only: bool = False
) -> bool:
    """Write only when the symbol or the confirmed/tentative status changes."""

    if library_keeps_current(current, decision):
        return False
    if decision.symbol_code != current.symbol_code:
        return True
    return not symbol_changes_only and decision.status != current_status(current.confidence)
