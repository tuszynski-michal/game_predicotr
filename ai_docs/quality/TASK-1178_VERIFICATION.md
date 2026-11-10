---
title: TASK-1178 — Current corrections, recommendation and acceptance
status: active
last_updated: 2026-11-10
---

# TASK-1178 — Verification

## Cause and repair

The live readiness endpoint returned GRID_LEARNING_HISTORY_STALE before
counting current corrections. verified_history required every label from the
base's previous publication cohorts to remain identical. A correction thus
prevented a new iteration. Evaluation creation had the same guard.

New preparation and evaluation creation read verified_publication_scope:
immutable model/report identity, producer, declared games and explicit
invalidation remain checked. Changed old labels do not erase the historical
game scope. Reusing a historical cohort still requires its exact pin, live
eligibility/current proof and ancestor base. The strict legacy reader,
publication, activation, default and report currentness are retained. Roles,
aliases, ancestor uses and buffers are never reassigned.

Opt-in recommendTrainingMode=true on existing GET ready selects a prepared
mode. Default GET/POST and pinned jobs retain their modes. Partial TRAIN
photos keep points training so individual corrections are not omitted.
Detector mode requires full TRAIN/VALIDATION, compatible historical scope
and successful mode-specific preflight. trainingRecommendation is explanatory
metadata, not a training command. OpenAPI, SDK, wrapper and request test
updated together. Admin adopts that exact mode/preview and explains why.
Manual choice is advanced; refresh keeps it. Restoring automatic choice
explicitly refreshes. Every start guard explains its reason.

## Actual read-only Mumie A2 acceptance

Cold interpreter, actual modified service, no monkeypatches, SQL READ ONLY,
no restart: **canStart=true, blockers=[]**. Artifact:
artifacts/task1178-ready-after.json (56.938s, including existing metadata scan).

| Population | Photos | Boards |
|---|---:|---:|
| Current qualified human approvals | 195 | 362 |
| Available TRAIN | 160 | 276 |
| Previously used TRAIN | 98 | 201 |
| New TRAIN | 62 | 75 |
| VALIDATION | 13 | 53 |
| REGRESSION | 13 | 21 |
| Labelled exclusions (buffers) | 9 | 12 |

Used/new TRAIN photos can overlap. Protected buffers total63 photos including
unlabelled ones. No reserve was invented. There are15 full approved photos
overall but150 partial TRAIN photos: recommended points, with explicit
GRID_LEARNING_PARTIAL_TRAIN_PRESENT. Corrections need not be saved again.
This proves data readiness, not completed training or model improvement.
Calculation can still take about a minute; instant metadata scan is not claimed.

## Tests performed

- **64 PASS Python** workflow, history/scope, recommendations, HTTP contract,
  incremental split counters/protections and screen report tests.
- **2 PASS PostgreSQL**: durable parent replay/CAS/same-budget resume30.39s;
  real v4 preview→freeze→training→evaluation binding112.34s with exact
  validation purposes. GPU computation is substituted, not actually run.
- **56 PASS Admin interactions** including recommended mode/exact start,
  manual refresh and return to automatic selection, counters/loading,
  stale evaluations and historical v1–v4 reports.
- **164 PASS SDK tests**, including optional GET query and legacy request;
  SDK build/typecheck and generated drift check PASS.
- Ruff, Prettier, scoped Admin ESLint, full Admin typecheck/build PASS.
  Strict scoped mypy5 modules PASS with project settings plus third-party
  torch imports skipped/follow-imports=silent. Not a full-project mypy or
  quality PASS. Backend OpenAPI, docs and code-map checks PASS.

Logs: worktree artifacts/grid-unit-local-temp.log, grid-ui-local-temp.log,
pg-grid-parent-local-temp.log, pg-grid-v4-local-temp.log and grid-sdk-local-temp.log;
task1177-{ruff,mypy,ui-lint,ui-type,build,sdk-all,sdk-type,sdk-generated,
prettier-check,openapi,docs,map-check}.log use the shared bounded helper.
Admin resolves this worktree's client through ignored local junction
apps/admin/node_modules/@game-predictor/admin-api-client; root node_modules
points to main. Detach this junction, root node_modules and root .venv during
authorized cleanup. Existing build warning
about multiple lockfiles remains.

## Baseline failures and time limits

Six existing test_grid_correction_split_adapter fixtures omit required nodes
and raise KeyError before their intended assertions. Adapter/tests unchanged.
Executed with adapter from HEAD0e1a02ec in a new interpreter: **6 FAIL/5 PASS**.
Exact file hashes and failures: artifacts/task1178-adapter-baseline.json.
No production fallback or weakened test was added; these are not called PASS.

A combined PG command exceeded120s after the first test passed. Separate
reruns passed within individual deadlines. Abandoned own fixture DB
game_predictor_t1159v4_10f56647c2d8_test,OID108469851, had0 connections and
was cleaned by its exact receipt/role markers. No backend terminated and
no operator DB changed.

## Audit and boundaries

Terminal Opus R1 REVISE,0 P0/1 P1. Correction round:

- P1-1: real _preview metadata test now parameterizes partial versus full
  TRAIN, includes partial VALIDATION/REGRESSION/buffer and a nonrepresentative
  TRAIN alias; asserts actual partial count and detector eligibility.
- P2-1: grid-only historical reuse now checks selected proof/ancestry during
  preview too; the same test covers eligible data with a stale selected proof.
- P2-2: accepted latency risk of two full previews for a full-photo automatic
  recommendation (roughly two minutes at this population's measured cost).
  Panel explains the potentially long check while history loads separately.
  The current Mumie A2 mixed data requires one preview only.
- P2-3/P2-4: missing labels added; old automatic explanations hidden after
  manual/options changes, with an interaction test.
- P2-5: docs clarify the strict legacy helper has no production consumer;
  actual publication barriers remain independent. P2-6: stale record-hash
  placeholder removed from this task's own T1 metadata entry.

Focused terminal Opus R2 **PASS**,0 P0/0 P1; actual model observed
claude-opus-5-5, High requested (CLI does not independently expose effort).
Payload SHA109a10e2bdc3144e58c7ad821a2727e8af4c382d5658259a602ae9c3c3918e90.
P2-2 remains accepted:56.938s is close to the per-preview60s deadline and
larger populations can time out. P2-7 remains a display limitation: the
explanation is visible but its partial TRAIN count150 is not printed there;
the detector's partial-photo count180 covers all roles. Both are documented,
not hidden as zero or presented as the same population.

No merge/push, operator
migration, restart, training, model application or import. No schema migration
required. T1 separate commit v1.7.594/0e1a02ec916629508570ee6570ded38d4df92817;
its record-hash metadata is included here. Final report must ask about merge.
