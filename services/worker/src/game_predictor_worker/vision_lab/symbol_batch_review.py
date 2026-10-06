"""Static, bounded review evidence; predictions never become human labels."""

from __future__ import annotations

import html
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .annotations import digest, exclusive_bounded
from .symbol_batch import checked_publish, result_path, validate_batch, validate_result
from .symbol_store import publish_file

STYLE = """
body{font:16px system-ui;margin:20px;background:#101827;color:#e5edf9}
a{color:#8ed2ff}button,select{font:inherit;min-height:44px;padding:6px;cursor:pointer}
.layout{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap}
.photo{max-width:100%;max-height:90vh;object-fit:contain;position:sticky;top:8px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;max-width:790px}
.card{background:#223147;padding:8px;border-radius:5px}.warning{border:2px solid #f6b460}
.crop{width:96px;height:96px;background-repeat:no-repeat;background-size:480px auto}
small{display:block;color:#c4d0e0}li{margin:8px 0}.board{margin-bottom:24px}
.notice{background:#23324a;padding:12px;max-width:1000px}.muted{color:#c4d0e0}
@media(max-width:700px){body{margin:10px}.photo{position:static}.cards{grid-template-columns:repeat(2,1fr)}}
"""


def page(title: str, body: str) -> bytes:
    return (
        '<!doctype html><html lang="pl"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{STYLE}</style><body>{body}</body></html>"
    ).encode()


REASONS = {
    "SYMBOL_MODEL_DISAGREEMENT": "Modele wskazują różne symbole",
    "SYMBOL_LOW_CONFIDENCE": "Niska pewność rozpoznania",
    "CELL_OUTSIDE_IMAGE": "Pole wychodzi poza zdjęcie",
    "GRID_STRUCTURE_INVALID": "Nieprawidłowa siatka",
    "GRID_UNAVAILABLE": "Brak siatki",
    "BOARD_COUNT_EXCESS": "Sieć wykryła za dużo plansz; nadmiar pominięty",
    "BOARD_COUNT_MISSING": "Sieć nie wykryła wszystkich plansz",
    "FILENAME_FOLDER_RANGE_CLIPPED": "Nazwa pliku przekracza koniec folderu; zakres ograniczony",
}


def explain(reasons: list[str]) -> str:
    return "; ".join(REASONS.get(reason, reason) for reason in reasons)


def card(cell: dict[str, Any], atlas: str, link: str | None = None) -> str:
    x, y, _, _ = cell["atlas"]
    proposal = html.escape(cell["predicted"] or "brak obrazu")
    confidence = "" if cell["confidence"] is None else f" · {cell['confidence'] * 100:.1f}%"
    where = f"plansza {cell['board_index'] + 1}, pole {cell['cell_index'] + 1}"
    reasons = html.escape(explain(cell["reasons"]))
    crop = (
        f'<div class="crop" role="img" aria-label="{where}" '
        f'style="background-image:url({atlas});background-position:-{x}px -{y}px"></div>'
    )
    if link:
        crop = f'<a href="{link}">{crop}</a>'
    return (
        f'<article class="card {"warning" if cell["requires_review"] else ""}">{crop}'
        f"<strong>{proposal}{confidence}</strong><small>{where}</small>"
        f"<small>RGB: {html.escape(cell.get('rgb', '—'))} · "
        f"gray: {html.escape(cell.get('gray', '—'))}</small><small>{reasons}</small></article>"
    )


def representative_cells(
    results: list[dict[str, Any]], classes: list[str]
) -> list[tuple[int, int]]:
    """Three source-separated samples per predicted class, without an accuracy claim."""
    selected = []
    for name in classes:
        candidates = [
            (i, j)
            for i, result in enumerate(results)
            for j, cell in enumerate(result["cells"])
            if cell["predicted"] == name and not cell["requires_review"]
        ]
        by_photo: dict[int, int] = {}
        for i, j in candidates:
            by_photo.setdefault(i, j)
        rows = list(by_photo.items())
        if rows:
            for index in sorted({0, len(rows) // 2, len(rows) - 1}):
                selected.append(rows[index])
    return selected


def render_gallery(root: Path, payload: dict[str, Any], results: list[dict[str, Any]]) -> None:
    nav = '<p><a href="../../review.html">Lista zdjęć</a></p>'
    notice = (
        '<p class="notice">To propozycje modeli. Żadne pole ani siatka nie zostały '
        "zatwierdzone automatycznie. Pewność modelu nie jest pomiarem poprawności. "
        "Plansze i pola są numerowane od 1, rzędami od lewej. "
        "Części poza zdjęciem pozostają bez symbolu. "
        "Złota ramka Super wymaga osobnego oznaczenia.</p>"
    )
    for i, result in enumerate(results):
        name = html.escape(result["row"]["filename"])
        groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for cell in result["cells"]:
            groups[cell["board_index"]].append(cell)
        board_html = "".join(
            f'<section class="board"><h2>Plansza {bi + 1}</h2><div class="cards">'
            + "".join(card(cell, "atlas.jpg") for cell in cells)
            + "</div></section>"
            for bi, cells in groups.items()
        )
        previous = f'<a href="../{i - 1:04d}/review.html">Poprzednie</a> ' if i else ""
        following = (
            f'<a href="../{i + 1:04d}/review.html">Następne</a>' if i + 1 < len(results) else ""
        )
        body = (
            f"{nav}<h1>{name}</h1>{previous}{following}{notice}"
            f"<p>Wykryte: {result['detected']}; oczekiwane: {result['expected']}; "
            f"pokazane: {result['selected']}. "
            f"{html.escape(explain(result['photo_reasons']))}</p>"
            f'<div class="layout"><img class="photo" src="overlay.jpg" alt="Zdjęcie z siatkami">'
            f"<div>{board_html}</div></div>"
        )
        publish_file(result_path(root, i).parent / "review.html", page(name, body))
    uncertain = [
        (i, j)
        for i, result in enumerate(results)
        for j, cell in enumerate(result["cells"])
        if cell["requires_review"] and cell["predicted"] is not None
    ]
    uncertain.sort(key=lambda ij: (results[ij[0]]["cells"][ij[1]]["confidence"], ij))
    # Bound front-page DOM; all cases remain accessible in the photo index.
    focused = uncertain[:60]
    examples = representative_cells(results, payload["classes"])

    def preview(indices: list[tuple[int, int]]) -> str:
        return (
            '<div class="cards">'
            + "".join(
                card(
                    results[i]["cells"][j],
                    f"photos/{i:04d}/atlas.jpg",
                    f"photos/{i:04d}/review.html",
                )
                for i, j in indices
            )
            + "</div>"
        )

    listing = []
    for i, result in enumerate(results):
        reviews = sum(c["requires_review"] for c in result["cells"])
        listing.append(
            f'<li><a href="photos/{i:04d}/review.html">'
            f"{html.escape(result['row']['filename'])}</a> · {result['selected']} plansz · "
            f"{reviews} pól do sprawdzenia</li>"
        )
    body = (
        f"<h1>Mumie — {len(results)} nowych zdjęć</h1>{notice}"
        f"<p>Najpierw przejrzyj najniższą pewność. Każdy crop otwiera całe zdjęcie. "
        "Dalej znajdują się przykłady każdej klasy i pełny indeks.</p>"
        f"<h2>Niepewne rozpoznania ({len(uncertain)}, pokazane do 60)</h2>{preview(focused)}"
        f"<h2>Kontrola każdej klasy</h2>{preview(examples)}"
        f"<h2>Wszystkie zdjęcia</h2><ol>{''.join(listing)}</ol>"
    )
    publish_file(root / "review.html", page("Mumie — niezależna partia", body))
    checked_publish(
        root / "review-selection.json",
        {"batch_id": digest(payload), "uncertain": focused, "class_control": examples},
    )


def finish(root: Path, render: bool = True) -> dict[str, Any]:
    with exclusive_bounded(root):
        payload = validate_batch(root)
        results = [validate_result(root, payload, i) for i in range(len(payload["rows"]))]
        cells = [cell for result in results for cell in result["cells"]]
        summary = {
            "batch_id": digest(payload),
            "photos": len(results),
            "expected_boards": sum(r["expected"] for r in results),
            "detected_boards": sum(r["detected"] for r in results),
            "selected_boards": sum(r["selected"] for r in results),
            "count_anomalies": sum(bool(r["photo_reasons"]) for r in results),
            "cells": len(cells),
            "predicted_cells": sum(c["predicted"] is not None for c in cells),
            "requires_review": sum(c["requires_review"] for c in cells),
            "model_uncertain": sum(bool(c.get("symbol_reasons")) for c in cells),
            "disagreements": sum("SYMBOL_MODEL_DISAGREEMENT" in c["reasons"] for c in cells),
            "unavailable_cells": sum(c["predicted"] is None for c in cells),
            "classes": dict(Counter(c["predicted"] for c in cells if c["predicted"])),
            "review_reasons": dict(Counter(reason for c in cells for reason in c["reasons"])),
            "human_labels_written": 0,
            "accuracy": None,
            "limitation": "Unlabelled independent photos: coverage/agreement are not accuracy.",
        }
        checked_publish(root / "summary.json", summary)
        if render:
            render_gallery(root, payload, results)
        return summary
