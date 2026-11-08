"""Server-owned experiment inputs: positive ancestry proof and immutable role rosters."""

from collections.abc import Mapping, Sequence
from typing import Any

from .grid_training_cohorts import GridCohortError, digest
from .source_recording_groups import resolve_ancestor_references

INPUT_VERSION = "full-symbol-content-inputs-v1"
EXPERIMENT_VERSION = "full-symbol-content-experiment-v1"
ROLE_KEYS = {"selectionRoster": "A", "calibrationRoster": "B", "regressionRoster": "REG"}
SOURCE_KEYS = ("sourceId", "sourceSha256", "pixelSha256", "qualifiedLabelsSha256", "eligibleBoards")


def sealed(body: Mapping[str, Any]) -> dict[str, Any]:
    return {**body, "sha256": digest(body)}


def _fail(code: str) -> None:
    raise GridCohortError(code, "The content experiment input proof is incomplete or changed.")


def checked(value: Mapping[str, Any], keys: set[str]) -> None:
    if set(value) != keys | {"sha256"} or value.get("sha256") != digest(
        {key: item for key, item in value.items() if key != "sha256"}
    ):
        _fail("CONTENT_EXPERIMENT_INPUT_CHANGED")


def training_eligibility(
    *,
    game: str,
    base: Mapping[str, Any],
    base_sha256: str,
    lineage: dict[str, Any],
    providers: dict[str, dict[str, Any]],
    split: Mapping[str, Any],
    contexts: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    resolution = resolve_ancestor_references(lineage, providers)
    if not resolution.complete:
        _fail("CONTENT_BANK_ANCESTRY_UNRESOLVED")
    if (
        lineage["ancestors"][0]["versionId"] != base["versionId"]
        or lineage["ancestors"][0]["manifestSha256"] != base_sha256
    ):
        _fail("CONTENT_EXPERIMENT_BASE_CHANGED")
    protected = {
        entry["groupId"]
        for provider in resolution.references
        for entry in provider["recordingGroups"]
    }
    sources, excluded = [], []
    for source in split["sources"]:
        if source.get("role") != "TRAIN" or not source.get("representative"):
            continue
        context = contexts[source["sourceId"]]
        reason = None
        if source["eligibleBoards"] < 1 or source.get("buffer") or source.get("detectorExcluded"):
            reason = "CONTENT_BANK_SOURCE_UNAVAILABLE"
        elif not context.get("proofSha256") or context.get("sourceId") != source["sourceId"]:
            reason = "CONTENT_BANK_SOURCE_PROOF_CHANGED"
        elif "TRAIN" not in context["allowedRoles"] or set(context["priorRoles"]) - {"TRAIN"}:
            reason = "CONTENT_BANK_ROLE_PROTECTED"
        elif context.get("diagnosticExposed") or context.get("selectionExposed"):
            reason = "CONTENT_BANK_SOURCE_EXPOSED"
        elif protected.intersection(context["componentIds"]):
            reason = "CONTENT_BANK_ANCESTOR_EXPOSED"
        elif protected and not context["componentIds"]:
            reason = "CONTENT_BANK_ANCESTRY_UNRESOLVED"
        if reason:
            excluded.append({"sourceId": source["sourceId"], "reasonCode": reason})
        else:
            closure = {
                key: context[key]
                for key in (
                    "sourceId",
                    "componentIds",
                    "aliasComponentIds",
                    "allowedRoles",
                    "priorRoles",
                    "proofSha256",
                    "diagnosticExposed",
                    "selectionExposed",
                    "validationPurposes",
                )
            }
            sources.append(
                {
                    **{key: source[key] for key in SOURCE_KEYS},
                    "role": "TRAIN",
                    "splitRegistryProofSha256": source["registryProofSha256"],
                    "closure": closure,
                    "closureSha256": digest(closure),
                }
            )
    return sealed(
        {
            "gameId": game,
            "baseVersionId": base["versionId"],
            "baseManifestSha256": base_sha256,
            "lineage": lineage,
            "lineageSha256": resolution.lineage_sha256,
            "ancestorReferences": list(resolution.references),
            "trainingSourceIds": sorted(
                source["sourceId"]
                for source in split["sources"]
                if source.get("role") == "TRAIN"
                and source.get("representative")
                and source["eligibleBoards"] > 0
                and not source.get("buffer")
                and not source.get("detectorExcluded")
            ),
            "sources": sorted(sources, key=lambda s: s["sourceId"]),
            "excluded": sorted(excluded, key=lambda s: s["sourceId"]),
        }
    )


def build_inputs(
    proofs: Sequence[dict[str, Any]],
    splits: Sequence[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    train = sealed(
        {
            "schemaVersion": "content-train-eligibility-v1",
            "games": sorted(proofs, key=lambda p: p["gameId"]),
        }
    )
    body: dict[str, Any] = {"schemaVersion": INPUT_VERSION, "trainEligibility": train}
    for key, role in ROLE_KEYS.items():
        games = []
        for game, split in sorted(splits):
            if split.get("contentSampling", {}).get("policy") != "full-symbol-content-sampling-v1":
                _fail("CONTENT_EXPERIMENT_CONTENT_COHORT_REQUIRED")
            sources = [
                {name: source[name] for name in SOURCE_KEYS}
                for source in split["sources"]
                if source.get("representative")
                and source["eligibleBoards"] > 0
                and not source.get("detectorExcluded")
                and not source.get("contentExcluded")
                and (
                    source.get("role") == "REGRESSION"
                    if role == "REG"
                    else source.get("role") == "VALIDATION"
                    and source.get("validationPurpose") == role
                )
            ]
            games.append(
                {
                    "gameId": game,
                    "splitSha256": split["sha256"],
                    "sources": sorted(sources, key=lambda s: s["sourceId"]),
                }
            )
        body[key] = sealed(
            {"schemaVersion": "content-role-roster-v1", "role": role, "games": games}
        )
    result = sealed(body)
    require_inputs(result)
    return result


def require_inputs(value: Mapping[str, Any], plan: Mapping[str, Any] | None = None) -> None:
    checked(value, {"schemaVersion", "trainEligibility", *ROLE_KEYS})
    if value["schemaVersion"] != INPUT_VERSION:
        _fail("CONTENT_EXPERIMENT_INPUT_VERSION_INVALID")
    train = value["trainEligibility"]
    checked(train, {"schemaVersion", "games"})
    if train["schemaVersion"] != "content-train-eligibility-v1":
        _fail("CONTENT_EXPERIMENT_INPUT_VERSION_INVALID")
    games = [item["gameId"] for item in train["games"]]
    if not 1 <= len(games) <= 8 or games != sorted(set(games)):
        _fail("CONTENT_EXPERIMENT_SCOPE_CHANGED")
    if not any(item["sources"] for item in train["games"]):
        _fail("CONTENT_BANK_ANCESTOR_UNSEEN_TRAIN_REQUIRED")
    train_identities: set[str] = set()
    for item in train["games"]:
        checked(
            item,
            {
                "gameId",
                "baseVersionId",
                "baseManifestSha256",
                "lineage",
                "lineageSha256",
                "ancestorReferences",
                "trainingSourceIds",
                "sources",
                "excluded",
            },
        )
        providers = {
            ref["ancestor"]["versionId"]: {k: v for k, v in ref.items() if k != "providerSha256"}
            for ref in item["ancestorReferences"]
        }
        resolution = resolve_ancestor_references(item["lineage"], providers)
        if (
            not resolution.complete
            or list(resolution.references) != item["ancestorReferences"]
            or resolution.lineage_sha256 != item["lineageSha256"]
        ):
            _fail("CONTENT_BANK_ANCESTRY_UNRESOLVED")
        if (
            item["lineage"]["ancestors"][0]["versionId"] != item["baseVersionId"]
            or item["lineage"]["ancestors"][0]["manifestSha256"] != item["baseManifestSha256"]
        ):
            _fail("CONTENT_EXPERIMENT_BASE_CHANGED")
        protected = {g["groupId"] for ref in resolution.references for g in ref["recordingGroups"]}
        if item["trainingSourceIds"] != sorted(set(item["trainingSourceIds"])) or not {
            source["sourceId"] for source in item["sources"]
        } <= set(item["trainingSourceIds"]):
            _fail("CONTENT_EXPERIMENT_TRAIN_ROSTER_CHANGED")
        for source in item["sources"]:
            closure = source["closure"]
            if (
                set(source)
                != {*SOURCE_KEYS, "role", "splitRegistryProofSha256", "closure", "closureSha256"}
                or source["role"] != "TRAIN"
                or source["sourceId"] != closure["sourceId"]
                or source["closureSha256"] != digest(closure)
                or not closure.get("proofSha256")
                or "TRAIN" not in closure["allowedRoles"]
                or set(closure["priorRoles"]) - {"TRAIN"}
                or closure["diagnosticExposed"]
                or closure["selectionExposed"]
                or protected.intersection(closure["componentIds"])
                or (protected and not closure["componentIds"])
            ):
                _fail("CONTENT_BANK_SOURCE_PROOF_CHANGED")
            train_identities.update((source["sourceSha256"], source["pixelSha256"]))
            train_identities.update(closure["componentIds"])
            train_identities.update(closure["aliasComponentIds"])
        if plan is not None and (
            item["baseVersionId"] != plan["baseVersionId"]
            or item["baseManifestSha256"] != plan["baseManifestSha256"]
        ):
            _fail("CONTENT_EXPERIMENT_BASE_CHANGED")
    for key, role in ROLE_KEYS.items():
        roster = value[key]
        checked(roster, {"schemaVersion", "role", "games"})
        if (
            roster["schemaVersion"] != "content-role-roster-v1"
            or roster["role"] != role
            or [item["gameId"] for item in roster["games"]] != games
        ):
            _fail("CONTENT_EXPERIMENT_SCOPE_CHANGED")
        for item in roster["games"]:
            for source in item["sources"]:
                if set(source) != set(SOURCE_KEYS):
                    _fail("CONTENT_EXPERIMENT_INPUT_CHANGED")
                if train_identities.intersection((source["sourceSha256"], source["pixelSha256"])):
                    _fail("CONTENT_BANK_CONTROL_ALIAS")
    if plan is not None:
        if [p["gameId"] for p in plan["cohorts"]] != games:
            _fail("CONTENT_EXPERIMENT_SCOPE_CHANGED")
        for key in ("trainEligibility", *ROLE_KEYS):
            if plan[key + "Sha256"] != value[key]["sha256"]:
                _fail("CONTENT_EXPERIMENT_INPUT_CHANGED")
