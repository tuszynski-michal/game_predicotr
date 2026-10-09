from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "m8_gold_frame_pilot_test_module", REPOSITORY_ROOT / "scripts" / "m8_gold_frame_pilot.py"
)
assert _SPEC is not None and _SPEC.loader is not None
pilot: Any = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = pilot
_SPEC.loader.exec_module(pilot)

GOLD = (212, 175, 55)
SIZE = 96


def _square(*, border: bool) -> np.ndarray:
    image = np.full((SIZE, SIZE, 3), (40, 60, 160), dtype=np.uint8)  # blue cell
    image[30:66, 30:66] = (200, 30, 30)  # red symbol
    if border:
        width = 8
        image[:width] = GOLD
        image[-width:] = GOLD
        image[:, :width] = GOLD
        image[:, -width:] = GOLD
    return image


def test_perimeter_share_separates_gold_border() -> None:
    framed = pilot.perimeter_gold_share(_square(border=True))
    plain = pilot.perimeter_gold_share(_square(border=False))
    assert framed > 0.6
    assert plain == 0.0


def test_gold_symbol_inside_does_not_raise_perimeter_share() -> None:
    image = _square(border=False)
    image[30:66, 30:66] = GOLD
    assert pilot.perimeter_gold_share(image) == 0.0
    assert pilot.interior_gold_share(image) > 0.2


def test_threshold_sweep_perfect_on_synthetic_set() -> None:
    images = [_square(border=index % 2 == 0) for index in range(10)]
    truth = [index % 2 == 0 for index in range(10)]
    scores = [pilot.perimeter_gold_share(image) for image in images]
    best = pilot.best_threshold(pilot.sweep_thresholds(scores, truth, [0.0, 0.1, 0.3, 0.5, 0.9]))
    assert best is not None
    assert best[1].precision == 1.0 and best[1].recall == 1.0 and best[1].f1 == 1.0


def test_expand_quad_grows_around_centre() -> None:
    quad = ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0))
    grown = pilot.expand_quad(quad, 0.08)
    assert np.allclose(grown[0], (-8.0, -8.0)) and np.allclose(grown[2], (108.0, 108.0))


def test_label_normalisation() -> None:
    assert pilot.normalize_label(" Tak ") == "tak"
    assert pilot.normalize_label("czesciowo") == "częściowo"
    assert pilot.normalize_label("maybe") is None


def test_evaluate_report_from_synthetic_run(tmp_path: Path) -> None:
    (tmp_path / "cells").mkdir()
    rows = []
    for index in range(12):
        framed = index % 2 == 0
        cell_id = f"cell-{index}"
        for variant in pilot.VARIANTS:
            Image.fromarray(_square(border=framed)).save(
                tmp_path / "cells" / f"{cell_id}_{variant}.png"
            )
        rows.append(
            {
                "cell_id": cell_id,
                "board_sequence_number": index,
                "cell_index": 0,
                "symbol_code": "X",
                "in_series": "true",
                "is_super_symbol": str(framed).lower(),
                "frame_label_tight": "tak" if framed else "nie",
                "frame_label_margin": "tak" if framed else "nie",
            }
        )
    labels = tmp_path / "labels.csv"
    with labels.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=pilot.LABEL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    report = tmp_path / "report.md"
    code = pilot.main(
        ["--evaluate", "--labels", str(labels), "--report", str(report), "--min-labels", "10"]
    )
    assert code == 0
    text = report.read_text(encoding="utf-8")
    assert "Najlepszy próg wg F1" in text
    assert "| 1.000 | 1.000 | 1.000 |" in text


def _write_run(root: Path, *, margin_only: bool) -> Path:
    (root / "cells").mkdir()
    rows = []
    for index in range(12):
        framed = index % 2 == 0
        cell_id = f"cell-{index}"
        Image.fromarray(_square(border=framed and not margin_only)).save(
            root / "cells" / f"{cell_id}_tight.png"
        )
        Image.fromarray(_square(border=framed)).save(root / "cells" / f"{cell_id}_margin.png")
        rows.append(
            {
                "cell_id": cell_id,
                "board_sequence_number": index,
                "cell_index": 0,
                "symbol_code": "X",
                "in_series": "true" if index < 8 else "false",
                "is_super_symbol": str(framed and index < 8).lower(),
                "frame_label_tight": "tak" if framed and not margin_only else "nie",
                "frame_label_margin": "tak" if framed else "nie",
            }
        )
    labels = root / "labels.csv"
    with labels.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=pilot.LABEL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return labels


def test_frame_visible_only_in_margin_crop_uses_independent_labels(tmp_path: Path) -> None:
    labels = _write_run(tmp_path, margin_only=True)
    report = tmp_path / "report.md"
    assert (
        pilot.main(
            ["--evaluate", "--labels", str(labels), "--report", str(report), "--min-labels", "10"]
        )
        == 0
    )
    text = report.read_text(encoding="utf-8")
    assert "| ramka widoczna na wycinku V3 (`tak` lub `częściowo`) | 0 |" in text
    assert "| ramka widoczna na wycinku z marginesem | 6 |" in text
    assert "| ramka widoczna tylko z marginesem (V3: `nie`) | 6 |" in text
    assert "super symbol w serii | 4 | 0/4 | 4/4 |" in text
    assert "poza seriami | 4 |" in text
    scores = (tmp_path / "scores.csv").read_text(encoding="utf-8-sig")
    assert "frame_label_tight,frame_label_margin" in scores


def test_prepare_refuses_existing_run_and_keeps_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = tmp_path / "run-a"
    run.mkdir()
    labels = run / "labels.csv"
    labels.write_text("manual,labels\n", encoding="utf-8")
    image = run / "keep.png"
    image.write_bytes(b"png")
    code = pilot.main(["--prepare", "--out", str(tmp_path), "--run", "run-a"])
    assert code == 1
    assert "--run <new name>" in capsys.readouterr().err
    assert labels.read_text(encoding="utf-8") == "manual,labels\n"
    assert image.read_bytes() == b"png"
    assert sorted(path.name for path in run.iterdir()) == ["keep.png", "labels.csv"]
