---
title: Frozen Mumie cross-recording blind AI audit
status: active
last_updated: 2026-10-06
---

# Result

Two independent blind visual reviews inspected the exact 60 PNGs and 20
human training anchors. High-confidence readable agreement accepted 53 cases;
seven remain unresolved. AI agreement is not human accuracy.

| Group | Accepted / selected | V3 RGB | V3 gray | V3 fusion | V4 RGB | V4 gray | V4 fusion |
|---|---|---|---|---|---|---|---|
| Preselected control | 47 / 50 | 46 / 47 | 45 / 47 | 45 / 47 | 47 / 47 | 47 / 47 | 47 / 47 |
| Directed cases | 6 / 10 | 5 / 6 | 0 / 6 | 0 / 6 | 6 / 6 | 5 / 6 | 6 / 6 |

Per-class denominators and disagreements are retained in the immutable proof,
not inferred for the whole folder. Eight exact crops need operator truth:
the seven unresolved cases and one gray-branch disagreement. The original
60-case queue and previous 26 approvals remain intact. No AI assessment was
written to a human store.

Gold-frame observations are separate: three agreed present, 51 agreed absent,
six uncertain/disputed. No Super training targets or gameplay rules were inferred.
The entire first film remains outside symbol development. Geometry was previously
trained on part of that film; this is not an independent geometry benchmark.

# Evidence and reproducibility

Absolute artifact root:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-autonomous-ai-audit-20261006`.
The authoritative pointer is `qualified-evaluation.json`, proof ID
`5fd1d19ca6927a0da1903bec08af191c4ef954354153e0459e367cae7488590a`.
The earlier preliminary report is retained; it lacked pins for the new anchor copies.

Fresh-process replay verified 8,748 source/model/review/output/anchor SHA pins,
all 60 consensus bindings and eight priority source/board/field/quad/byte/pixel
bindings. Detached regressions reject operator state appearing, changing or
disappearing, and stale review pixels. State fingerprint is checked before and
after preview, before publication and around runtime selection.

Thirty focused consensus/batch-label tests passed. Ruff, format and scoped strict
mypy passed for six helpers. Controlled editor restart preserved saved runtime
backup and prior histories. Read-only API/proxy returned eight exact PNGs at
revision zero in 0.297/0.266 seconds. Portal, editor and original gallery returned 200.
Owned API PID 2740, UI PID 26388; production API 8000 was untouched.

Independent artifact audit PASS. Both P2 findings (operator-write race and missing
new-anchor pins) were fixed and replayed. No open P0–P2 findings remain.

# Acceptance and next step

All six task criteria and plan steps 1–3 were checked against actual evidence.
No training, database changes, production activation, deployment, merge or push.
Continue TASK-0868 automatically; the eight optional corrections do not block it.
