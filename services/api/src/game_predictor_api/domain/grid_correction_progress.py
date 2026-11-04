"""One deduplicated population, explicit overlapping photo counters."""

from typing import Any


def correction_progress_counts(split: dict[str, Any]) -> dict[str, Any]:
    names = (
        "approved",
        "availableTrain",
        "usedTrain",
        "newTrain",
        "validation",
        "regression",
        "validationReserve",
        "regressionReserve",
        "buffers",
        "excluded",
    )
    result: dict[str, Any] = {name: {"photos": 0, "boards": 0} for name in names}
    reasons: dict[str, dict[str, Any]] = {}

    def add(name: str, boards: int, *, unlabelled: bool = False) -> None:
        result[name]["photos"] += int(boards > 0 or unlabelled)
        result[name]["boards"] += boards

    for item in split["sources"]:
        if not item["representative"]:
            continue
        boards, role = item["eligibleBoards"], item["role"]
        qualified = (
            item["qualifiedBoards"]
            if split.get("schemaVersion") == "grid-correction-split-v3"
            else item.get("qualifiedBoards", boards)
            if split.get("schemaVersion") == "grid-correction-split-v4"
            else boards
        )
        add("approved", qualified)
        if (
            qualified
            and not boards
            and split.get("schemaVersion")
            in ("grid-correction-split-v3", "grid-correction-split-v4")
        ):
            add("excluded", qualified)
            if item["buffer"]:
                add("buffers", qualified)
            reason = (
                "SCREEN_PARTIAL_PHOTO_EXCLUDED"
                if item.get("detectorExcluded")
                else "GRID_CORRECTION_BUFFER"
                if item["buffer"]
                else "GRID_CORRECTION_PROTECTED_NEIGHBORHOOD"
            )
            entry = reasons.setdefault(reason, {"reason": reason, "photos": 0, "boards": 0})
            entry["photos"] += 1
            entry["boards"] += qualified
            continue
        if item["buffer"]:
            add("buffers", boards, unlabelled=True)
        if role == "TRAIN":
            used = min(boards, item.get("usedTrainBoards", 0))
            add("availableTrain", boards)
            add("usedTrain", used)
            add("newTrain", boards - used)
        elif role in ("VALIDATION", "REGRESSION"):
            name = role.lower()
            if boards:
                add(name, boards)
            elif item.get("pendingCorrection"):
                add(name + "Reserve", 0, unlabelled=True)
            else:
                add("excluded", 0, unlabelled=True)
                reason = "GRID_CORRECTION_CONTROL_NOT_PENDING"
                entry = reasons.setdefault(reason, {"reason": reason, "photos": 0, "boards": 0})
                entry["photos"] += 1
        elif boards:
            add("excluded", boards)
            reason = (
                "GRID_CORRECTION_BUFFER"
                if item["buffer"]
                else "GRID_CORRECTION_PROTECTED_NEIGHBORHOOD"
            )
            entry = reasons.setdefault(reason, {"reason": reason, "photos": 0, "boards": 0})
            entry["photos"] += 1
            entry["boards"] += boards
    result["exclusionReasons"] = [reasons[key] for key in sorted(reasons)]
    return result
