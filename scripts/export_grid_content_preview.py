"""Export current TRAIN annotations and pinned overlays, using GET requests only.

Replaces the ad-hoc brightness/colour proposal preparation. Never generates,
imports or approves labels. Existing unapproved drafts remain unapproved.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


def _points(points: list[list[float]]) -> str:
    return " ".join(f"{x},{y}" for x, y in points)


def preview_html(records: list[dict[str, Any]]) -> str:
    """Draw current quads only: preview boxes and pre-rendered overlays are ignored."""
    cards = []
    for record in records:
        target, reference = record["target"], record["reference"]
        preview = reference.get("ordinaryPreview") or {}
        if (
            target["role"] != "TRAIN"
            or preview.get("state") == "protected"
            or preview.get("nodes") is None
        ):
            continue
        source = target["source"]
        annotation = reference.get("annotation")
        if annotation and not (
            annotation["sequenceNumber"] == target["sequenceNumber"]
            and annotation["reference"]["positionIndex"] == target["positionIndex"]
            and annotation["source"]["sourceRepresentativeSha256"]
            == source["sourceRepresentativeSha256"]
            and annotation["source"]["width"] == source["width"]
            and annotation["source"]["height"] == source["height"]
        ):
            annotation = None
        cells = annotation["reference"]["cells"] if annotation else []
        labels = {
            "visible": "Widoczny w całości",
            "occluded": "Zasłonięty — fragment",
            "out_of_frame": "Poza kadrem — fragment",
            "unknown": "Nieznany — fragment",
        }
        outlines = "".join(
            f'<polygon data-cell="{i}" data-state="{c["state"]}" points="{_points(c["quad"])}">'
            f"<title>Pole {i + 1}: {labels[c['state']]}</title></polygon>"
            for i, c in enumerate(cells)
            if c.get("quad") is not None
        )
        nodes = preview.get("nodes")
        lattice = (
            ""
            if nodes is None
            else "".join(
                f'<polyline points="{_points(points)}"/>'
                for points in [nodes[r * 6 : r * 6 + 6] for r in range(4)]
                + [[nodes[r * 6 + c] for r in range(4)] for c in range(6)]
            )
        )
        footprints = "".join(
            f'<polygon points="{_points(c["quad"])}"/>' for c in preview.get("productionCells", [])
        )
        name = html.escape(target.get("displayName") or "Zdjęcie bez nazwy")
        provenance = "Brak aktualnej adnotacji"
        if annotation:
            provenance = (
                f"Pochodzenie: {annotation['origin']}; autor: {annotation['actor']}; "
                f"zatwierdzenie: {'tak' if annotation['reference']['humanApproved'] else 'nie'}; "
                f"zatwierdzający: {annotation.get('approvedBy') or 'brak'}"
            )
        image = html.escape(record["asset"], quote=True)
        reason_labels = {
            "CONTENT_PRODUCTION_MANIFEST_UNAVAILABLE": "Brak zapisanego manifestu wycinków.",
            "CONTENT_PRODUCTION_MANIFEST_CONFLICT": (
                "Dane wycinków są niespójne; siatka i adnotacje pozostają dostępne."
            ),
            "CONTENT_PRODUCTION_CELL_UNAVAILABLE": (
                "Część wycinków jest niedostępna lub niezgodna z bieżącą siatką."
            ),
            "CONTENT_PRODUCTION_CELLS_PARTIAL": "Pokazujemy tylko dostępne wycinki.",
            "CONTENT_PRODUCTION_FOOTPRINT_OUTSIDE_SOURCE": (
                "Część wycinka znajduje się poza zdjęciem i nie zawiera pikseli źródła."
            ),
            "CONTENT_SAVED_NODES_UNAVAILABLE": "Brak kompletnej zapisanej siatki.",
        }
        codes = preview.get("reasonCodes", [])
        reasons = " ".join(
            reason_labels.get(code, "Część podglądu jest niedostępna.") for code in codes
        )
        details = (
            "<details><summary>Szczegóły podglądu</summary>"
            f"<code>{html.escape('; '.join(codes))}</code></details>"
            if codes
            else ""
        )
        cards.append(f'''<article><h2>{name} — plansza {target["sequenceNumber"]},
pozycja {target["positionIndex"] + 1}</h2>
<p>Rewizja zawartości: {reference["revision"]}. {html.escape(provenance)}.
Obrysy: {sum(c.get("quad") is not None for c in cells)}/15.</p>
<p>Rewizja geometrii: {preview.get("geometryRevision")}.
Produkcyjne wycinki: {len(preview.get("productionCells", []))}/15.
{html.escape(reasons)}</p>{details}
<svg viewBox="0 0 {source["width"]} {source["height"]}"
aria-label="Zapisana siatka, aktualne obrysy i produkcyjne zakresy">
<image href="{image}" width="{source["width"]}" height="{source["height"]}"/>
<g class="lattice">{lattice}</g><g class="outlines">{outlines}</g>
<g class="crops">{footprints}</g></svg></article>''')
    return (
        """<!doctype html><html lang="pl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aktualne adnotacje pól</title><style>
body{font:16px/1.5 system-ui;background:#11231d;color:#edf8f1;margin:24px}
main{max-width:1200px;margin:auto}
article{border:1px solid #557267;padding:20px;margin:24px 0}
svg{width:100%;max-height:85vh}
polygon,polyline{fill:none;stroke-width:2;vector-effect:non-scaling-stroke}
.lattice{stroke:#5cdaff}.outlines{stroke:#4ce2a4}
.outlines [data-state="unknown"]{stroke:#c4cbd1;stroke-dasharray:3 5}
.outlines [data-state="occluded"],.outlines [data-state="out_of_frame"]{
stroke:#ffbc69;stroke-dasharray:7 4}
.crops{stroke:#ffcf69;stroke-dasharray:8 4;display:none}
.crops polygon{fill:#ffcf691a}label{display:inline-block;padding:12px}</style>
<main><h1>Aktualne adnotacje pól — TRAIN</h1>
<p>Odczyt nie generuje szkiców ani nie zapisuje adnotacji.
Propozycja pozostaje szkicem do sprawdzenia.
Chronione zdjęcia i role kontrolne są pominięte. Brak quadu oznacza brak obrysu.</p>
<label><input type="checkbox" data-layer="lattice" checked> Siatka pól</label>
<label><input type="checkbox" data-layer="outlines" checked> Obrysy grafik</label>
<label><input type="checkbox" data-layer="crops"> Rzeczywiste wycinki</label>
<p>Siatka: dokładne zapisane24punkty. Obrysy: grafika z aktualnej adnotacji.
Przerywane obrysy to fragmenty lub stan nieznany, nie potwierdzenie pełnego symbolu.
Kreskowane zakresy: rzeczywisty footprint przypiętego renderu produkcji,
bez zmiany marginesu. Zdjęcie zawiera otoczenie; zakres wycinka jest osobny.</p>"""
        + (
            "".join(cards)
            if cards
            else '<p role="status">Brak gotowych, niechronionych plansz TRAIN do podglądu.</p>'
        )
        + """</main><script>
document.querySelectorAll('input[data-layer]').forEach(input=>input.onchange=()=>
document.querySelectorAll('.'+input.dataset.layer).forEach(group=>
group.style.display=input.checked?'block':'none'));</script></html>"""
    )


def export(
    api: str, game: str, cohort: str, manifest: str, output: Path, limit: int, offset: int
) -> Path:
    pins = {"cohortId": cohort, "manifestSha256": manifest}
    prefix = f"{api.rstrip('/')}/admin/games/{game}/grid-quality-measurements"
    deadline = monotonic() + 110

    def get(url: str) -> bytes:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("The bounded preview export exceeded 110 seconds")
        with urlopen(url, timeout=min(20, remaining)) as response:
            data = response.read(32 * 1024 * 1024 + 1)
        if monotonic() > deadline:
            raise TimeoutError("The bounded preview export exceeded 110 seconds")
        if not isinstance(data, bytes) or len(data) > 32 * 1024 * 1024:
            raise ValueError("The preview response exceeds its bounded byte size")
        return data

    page = json.loads(
        get(f"{prefix}/content-targets?{urlencode({**pins, 'limit': limit, 'offset': offset})}")
    )
    output.mkdir(parents=True, exist_ok=False)
    records, assets, skipped = [], set(), []
    for target in page["items"]:
        if target["role"] != "TRAIN" or target["state"] != "ready":
            skipped.append({"sourceId": target["source"]["sourceId"], "reason": "NOT_READY_TRAIN"})
            continue
        source = target["source"]
        reference = json.loads(
            get(
                f"{prefix}/content-references/{source['sourceId']}/{target['positionIndex']}?{urlencode(pins)}"
            )
        )
        preview = reference.get("ordinaryPreview") or {}
        if preview.get("state") == "protected" or preview.get("nodes") is None:
            skipped.append(
                {
                    "sourceId": source["sourceId"],
                    "reason": preview.get("reasonCodes", ["PREVIEW_UNAVAILABLE"]),
                }
            )
            continue
        asset = f"{source['sourceId']}.jpg"
        if asset not in assets:
            data = get(
                f"{prefix}/content-targets/sources/{source['sourceId']}/asset?{urlencode(pins)}"
            )
            if hashlib.sha256(data).hexdigest() != source["sourceSha256"]:
                raise ValueError("Source asset differs from the frozen pin")
            (output / asset).write_bytes(data)
            assets.add(asset)
        records.append({"target": target, "reference": reference, "asset": asset})
    (output / "preview.json").write_text(
        json.dumps(
            {"records": records, "skipped": skipped, "nextOffset": page["nextOffset"]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    path = output / "preview.html"
    path.write_text(preview_html(records), encoding="utf-8")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    for name in ("game", "cohort", "manifest", "output"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--limit", type=int, choices=range(1, 51), default=50)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    print(
        export(
            args.api,
            args.game,
            args.cohort,
            args.manifest,
            Path(args.output),
            args.limit,
            args.offset,
        )
    )
