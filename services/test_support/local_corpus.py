"""Skip helper for tests that read local, Git-ignored corpora.

TASK-0940: the M5/M6 real-corpus tests read photos and crops from
``artifacts/m5-*`` and ``examples/imgs`` that are ignored by Git and absent from
a clean checkout. Each such test calls ``require_local_corpus`` with the paths it
needs, so it is skipped with the missing path named and still runs, unchanged,
wherever the corpus exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def require_local_corpus(*paths: Path) -> None:
    """Skip the calling test when any of the given corpus paths is missing."""

    missing = [Path(path) for path in paths if not Path(path).exists()]
    if not missing:
        return
    names: list[str] = []
    for path in missing:
        try:
            names.append(path.resolve().relative_to(_REPOSITORY_ROOT).as_posix())
        except ValueError:
            names.append(str(path))
    pytest.skip("local corpus not available (ignored by Git): " + ", ".join(names))
