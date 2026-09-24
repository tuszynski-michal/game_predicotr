"""Proposed grid engine v3: template-free 3 x 3 screen layout and 5 x 3 grids."""

from .engine import (
    SCREEN_LAYOUT_V3_VERSION,
    BoardGrid,
    BoardStatus,
    ResultStatus,
    ScreenLayoutResult,
    detect_screen_layout_v3,
)

__all__ = [
    "SCREEN_LAYOUT_V3_VERSION",
    "BoardGrid",
    "BoardStatus",
    "ResultStatus",
    "ScreenLayoutResult",
    "detect_screen_layout_v3",
]
