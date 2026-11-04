"""Versioned contracts of the correction-learning path; legacy stays explicit."""

CORRECTION_POLICY = "application-grid-corrections-v2"
SCREEN_CORRECTION_POLICY = "application-grid-corrections-v3"
CORRECTION_POLICIES = (
    "application-grid-corrections-v1",
    CORRECTION_POLICY,
    SCREEN_CORRECTION_POLICY,
    "application-grid-corrections-v4",
)
CORRECTION_SNAPSHOT = "application-grid-snapshot-v2"
CORRECTION_PRESET = "grid-corrections-v1"
CORRECTION_EVALUATION = "grid-correction-evaluation-v1"
CHECKPOINT_RULE = "validation-board-correct-photo-macro-error-earliest-v1"
SCREEN_CORRECTION_SNAPSHOT = "application-grid-snapshot-v3"
SCREEN_CORRECTION_PRESET = "screen-grid-corrections-v1"
SCREEN_CHECKPOINT_RULE = "validation-photo-board-correct-photo-macro-error-earliest-v1"


def correction_policy_for_mode(mode: str) -> str:
    if mode == "grid-only":
        return CORRECTION_POLICY
    if mode == "screen+grid":
        return SCREEN_CORRECTION_POLICY
    raise ValueError("Unsupported correction training mode.")


def correction_mode_for_policy(policy: str, mode: str | None = None) -> str:
    if policy == "application-grid-corrections-v4" and mode in ("grid-only", "screen+grid"):
        return mode
    if policy == SCREEN_CORRECTION_POLICY:
        return "screen+grid"
    if policy in CORRECTION_POLICIES:
        return "grid-only"
    raise ValueError("Unsupported correction policy.")
