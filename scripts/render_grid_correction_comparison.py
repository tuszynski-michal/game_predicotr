"""Assemble a static report from checksum-bound inference, without any DB writes."""

import argparse
import html
import json
import sys
from pathlib import Path

import numpy as np

# A shared editable virtualenv may point to main; the CLI belongs to this checkout.
ROOT = Path(__file__).resolve().parents[1]
for source_directory in ("services/api/src", "services/worker/src"):
    sys.path.insert(0, str(ROOT / source_directory))

from game_predictor_worker.images.comparison_content_changes import content_change  # noqa: E402
from game_predictor_worker.images.comparison_input_diagnostics import (  # noqa: E402
    diagnostic_inputs,
)
from game_predictor_worker.images.comparison_production_bundle import (  # noqa: E402
    build_production_package,
)
from game_predictor_worker.images.comparison_production_cells import (  # noqa: E402
    ComparisonProductionCells,
)


def render(root: Path, *, artifact_root: Path | None = None) -> Path:
    """Render saved checksum-bound results; never run inference or write domain data."""

    inputs = json.loads((root / "inputs.json").read_text(encoding="utf-8"))
    learning = json.loads((root / "learning-final.json").read_text(encoding="utf-8"))
    evaluation = json.loads((root / "evaluation-final.json").read_text(encoding="utf-8"))
    if (
        not learning["candidateVersionId"]
        or evaluation["status"] != "completed"
        or not evaluation["report"]
    ):
        raise ValueError("A completed evaluation and candidate identity are required")
    if (
        evaluation["versionId"] != learning["candidateVersionId"]
        or evaluation["trainingGameId"] != learning["gameId"]
    ):
        raise ValueError("Evaluation identity differs from the learning run")
    membership = {row["source_id"]: row for row in inputs["membership"]}
    photos = {row["id"]: row for row in inputs["photos"]}
    packaging_errors = (
        {}
        if artifact_root is None
        else build_production_package(root, artifact_root, evaluation, set(photos))
    )
    production = ComparisonProductionCells(root, evaluation)
    cards = []
    for board in inputs["boards"]:
        source = photos[board["source_image_id"]]
        base = json.loads((root / "base" / (source["id"] + ".json")).read_text(encoding="utf-8"))
        candidate = json.loads(
            (root / "candidate" / (source["id"] + ".json")).read_text(encoding="utf-8")
        )
        if (
            candidate["versionId"] != learning["candidateVersionId"]
            or base["versionId"] != evaluation["baseVersionId"]
        ):
            raise ValueError("Inference model identity differs from the evaluation")
        if not base["sourceChecksum"] == candidate["sourceChecksum"] == source["checksum_sha256"]:
            raise ValueError("Inference source checksum differs from the selected photo")
        position = board["position_index"]
        crops = production.for_board(source, board, {"base": base, "candidate": candidate})
        if source["id"] in packaging_errors:
            crops = {"state": "unavailable", "reason": packaging_errors[source["id"]]}
        paired = base["status"] == candidate["status"] == "ok" and crops["state"] == "available"
        paired = paired and all(
            crops["models"][name]["state"] == "available" for name in ("base", "candidate")
        )
        left = crops["models"]["base"]["nodes"] if paired else None
        right = crops["models"]["candidate"]["nodes"] if paired else None
        delta = None
        if left is not None and right is not None:
            delta = float(np.linalg.norm(np.asarray(left) - np.asarray(right), axis=1).mean())
        record = membership.get(source["id"], {})
        diagnostics = diagnostic_inputs(
            root,
            source,
            board,
            {"base": evaluation["baseVersionId"], "candidate": learning["candidateVersionId"]},
        )
        if crops["state"] == "available":
            for name in ("base", "candidate"):
                if diagnostics[name]["state"] != "available":
                    diagnostics[name] = crops["models"][name].get("neuralInput", diagnostics[name])
        cards.append(
            {
                "sequence": board["sequence_number"],
                "productionCells": crops,
                "contentChange": content_change(crops),
                "reference": crops.get("referenceNodes"),
                "humanReference": crops.get("humanReference"),
                "diagnostics": diagnostics,
                "boardId": board["id"],
                "position": position,
                "gridRows": board["grid_rows"],
                "gridColumns": board["grid_columns"],
                "sourceId": source["id"],
                "width": source["oriented_width"],
                "height": source["oriented_height"],
                "saved": (board.get("board_geometry") or {}).get("latticeNodes"),
                "base": left,
                "candidate": right,
                "baseAll": []
                if paired
                else [d["nodes"] for d in base["detections"] if d["nodes"] is not None],
                "candidateAll": []
                if paired
                else [d["nodes"] for d in candidate["detections"] if d["nodes"] is not None],
                "paired": paired,
                "delta": delta,
                "available": base["status"] == candidate["status"] == "ok",
                "trainingPhoto": record.get("used") == "true" and record.get("role") == "TRAIN",
            }
        )
    cards.sort(
        key=lambda row: (
            -(row["delta"] if row["delta"] is not None else -1),
            row["sequence"],
            row["boardId"],
        )
    )
    report = evaluation["report"]
    current = next(game for game in report["games"] if game["gameId"] == learning["gameId"])
    regression = current["roles"]["REGRESSION"]
    old_error = regression["base"].get("normalized_error", regression["base"].get("image_macro"))
    new_error = regression["candidate"].get(
        "normalized_error", regression["candidate"].get("image_macro")
    )
    change = (
        f"Spadek błędu punktów: {(old_error - new_error) / old_error * 100:.1f}%."
        if old_error and new_error is not None
        else "Brak porównywalnej metryki błędu punktów."
    )
    summary = (
        f"Kontrola końcowa: {regression['base']['boards_correct']} → "
        f"{regression['candidate']['boards_correct']} poprawnych plansz z "
        f"{regression['base']['boards_expected']}. {change}"
    )
    metric_rows = []
    for game in report["games"]:
        for role, label in [("VALIDATION", "Dobór modelu"), ("REGRESSION", "Kontrola końcowa")]:
            data = game["roles"][role]
            old, new = data["base"], data["candidate"]
            old_nme = old.get("normalized_error", old.get("image_macro"))
            new_nme = new.get("normalized_error", new.get("image_macro"))
            old_display = f"{old_nme:.5f}" if old_nme is not None else "—"
            new_display = f"{new_nme:.5f}" if new_nme is not None else "—"
            metric_rows.append(
                "<tr>"
                f"<td>{html.escape(game['gameId'])}</td>"
                f"<td>{label}</td><td>{data['photos']}</td>"
                f"<td>{old['boards_correct']} / {old['boards_expected']}</td>"
                f"<td>{new['boards_correct']} / {new['boards_expected']}</td>"
                f"<td>{old_display}</td><td>{new_display}</td></tr>"
            )
    payload = json.dumps(cards, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    template = (Path(__file__).parent / "templates" / "grid-correction-comparison.html").read_text(
        encoding="utf-8"
    )
    # Application status needs completed, matching receipts; absent proof stays unknown.
    application = "brak potwierdzenia w zapisanym zestawie"
    proof_path = root / "apply-final.json"
    if proof_path.exists():
        operation = json.loads(proof_path.read_text(encoding="utf-8"))["operation"]
        steps = operation.get("steps", [])
        required = {"publish", "set_default", "activate"}
        valid = (
            operation.get("status") == "completed"
            and operation.get("versionId") == learning["candidateVersionId"]
            and operation.get("gameId") == learning["gameId"]
        )
        valid = valid and required <= {
            step["kind"]
            for step in steps
            if step.get("status") == "completed"
            and step.get("receipt", {}).get("versionId") == learning["candidateVersionId"]
            and (step["kind"] != "activate" or step.get("gameId") == learning["gameId"])
        }
        if valid:
            application = (
                "zapisana operacja potwierdza publikację, wspólny default "
                "i przypisanie bieżącej gry (stan w chwili zapisu)"
            )
    replacements = {
        "__DATA__": payload,
        "__APPLICATION__": html.escape(application),
        "__GAME__": html.escape(learning["gameId"]),
        "__GAME_ID__": html.escape(learning["gameId"], quote=True),
        "__METRICS__": "".join(metric_rows),
        "__SUMMARY__": html.escape(summary),
        "__VERDICT__": html.escape(report["verdict"]),
        "__VERDICT_CLASS__": "good" if report["verdict"] == "PASS" else "bad",
        "__BOARDS__": str(len(cards)),
        "__PHOTOS__": str(len(photos)),
        "__PAIRED__": str(sum(row["paired"] for row in cards)),
        "__CHANGED__": str(sum(row["delta"] is not None and row["delta"] >= 1 for row in cards)),
        "__REASONS__": html.escape(
            "; ".join(reason for game in report["games"] for reason in game["reasons"])
        )
        or "Brak powodów blokujących w raporcie oceny.",
        "__MODEL__": html.escape(learning["candidateVersionId"]),
        "__DIAGNOSTIC_SCOPE__": html.escape(
            ", ".join(
                str(row["sequence"])
                for row in cards
                if any(value["state"] == "available" for value in row["diagnostics"].values())
            )
            or "brak wiarygodnych rekordów"
        ),
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    (root / "comparison.html").write_text(template, encoding="utf-8")
    (root / "comparison-data.json").write_text(
        json.dumps(cards, indent=2, allow_nan=False), encoding="utf-8"
    )
    return root / "comparison.html"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument(
        "--directory",
        type=Path,
        help="Saved comparison inputs, inference JSON and photos",
    )
    modes.add_argument(
        "--crop-report", type=Path, help="Sealed diagnostic production-crop-comparison-v1 report"
    )
    parser.add_argument(
        "--output-directory", type=Path, help="New standalone directory for crop diagnostic HTML"
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        help="Read-only artifact store: package exact read-v6 cohort/detail pins automatically",
    )
    args = parser.parse_args()
    if args.crop_report is not None:
        if args.output_directory is None or args.artifact_root is None:
            parser.error("--crop-report requires --output-directory and --artifact-root")
        from game_predictor_worker.images.comparison_production_crop_report import (
            render_crop_report,
        )

        print(
            render_crop_report(
                args.crop_report, output=args.output_directory, artifact_root=args.artifact_root
            )
        )
    else:
        if args.output_directory is not None:
            parser.error("--output-directory applies only to --crop-report")
        print(render(args.directory.resolve(), artifact_root=args.artifact_root))


if __name__ == "__main__":
    main()
