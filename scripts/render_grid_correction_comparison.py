"""Assemble a static report from checksum-bound inference, without any DB writes."""

import argparse
import html
import json
from pathlib import Path

import numpy as np


def render(root: Path) -> Path:
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
        paired = (
            base["status"] == candidate["status"] == "ok"
            and len(base["detections"]) == len(candidate["detections"]) == 9
            and 0 <= position < 9
        )
        left = base["detections"][position]["nodes"] if paired else None
        right = candidate["detections"][position]["nodes"] if paired else None
        delta = None
        if left is not None and right is not None:
            delta = float(np.linalg.norm(np.asarray(left) - np.asarray(right), axis=1).mean())
        record = membership.get(source["id"], {})
        cards.append(
            {
                "sequence": board["sequence_number"],
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
    old_error = regression["base"]["normalized_error"]
    new_error = regression["candidate"]["normalized_error"]
    reduction = (old_error - new_error) / old_error * 100 if old_error else 0
    summary = (
        f"Kontrola końcowa: {regression['base']['boards_correct']} → "
        f"{regression['candidate']['boards_correct']} poprawnych plansz z "
        f"{regression['base']['boards_expected']}. Spadek błędu punktów: {reduction:.1f}%."
    )
    metric_rows = []
    for game in report["games"]:
        for role, label in [("VALIDATION", "Dobór modelu"), ("REGRESSION", "Kontrola końcowa")]:
            data = game["roles"][role]
            old, new = data["base"], data["candidate"]
            metric_rows.append(
                "<tr>"
                f"<td>{html.escape(game['gameId'])}</td>"
                f"<td>{label}</td><td>{data['photos']}</td>"
                f"<td>{old['boards_correct']} / {old['boards_expected']}</td>"
                f"<td>{new['boards_correct']} / {new['boards_expected']}</td>"
                f"<td>{old['normalized_error']:.5f}</td><td>{new['normalized_error']:.5f}</td></tr>"
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
    parser.add_argument(
        "--directory",
        type=Path,
        required=True,
        help="Saved comparison inputs, inference JSON and photos",
    )
    args = parser.parse_args()
    print(render(args.directory.resolve()))


if __name__ == "__main__":
    main()
