---
title: Jobs readability response verification
status: active
last_updated: 2026-11-10
---

# TASK-1181 — Verification

## Cause and change

GET /api/v1/admin/jobs?limit=10 returned500 in the running application.
Persisted SYMBOL_READABILITY fell through _payload_from_domain to
AndroidBuildJobPayload. Added the exact producer contract to response decoding
and JobPayloadResponse: schemaVersion1, workflow symbol_readability,
prepare/fit/scan and UUID identifier. Generic POST /jobs is unchanged.
No catch-all, dropped rows, schema migration or rewritten jobs.

Backend OpenAPI, generated client, wrapper type export and request tests
are updated together. Admin already has the quality-job label. No UI feature
or alternative endpoint is introduced. TASK-1180 files remain untouched.

## Performed checks

- RED: the three action-specific mixed-list tests failed with the original
  Android payload validation error before the code change.
- 9 new Python regressions PASS: mixed list and detail preserve status,
  progress and error; Android unchanged; five malformed payloads rejected;
  generic creation of readability remains422 and creates no job.
- Existing API suite:36 PASS and1 stale assertion in the five-type creation
  test. The same assertion fails on unchanged main a9af0032 because its
  complement list omitted existing readability/grid-learning enum members.
  Updated it to assert the exact five permitted types, matching JobCreateRequest;
  this one test then PASS. The remaining36 were not rerun unnecessarily.
- 165 SDK tests PASS, including GET list filters and detail payload forwarding.
- Ruff format/check PASS; scoped strict mypy of schemas/jobs.py PASS with
  project configuration and only third-party torch imports skipped. This is
  not a full-project mypy result. SDK build and Admin typecheck PASS.
- OpenAPI exported and client regenerated; generated drift, Admin production
  build, docs:check and code-map:check PASS. Existing multiple-lockfile build
  warning remains. A local encoding error while updating CURRENT_STATE was
  caught by docs:check and repaired from exact HEAD UTF-8 bytes plus task hunks
  before audit; no corrupted state was committed or deployed.

## Operator data, new interpreter

Actual owner connection with default_transaction_read_only and5s statement
timeout:50 newest jobs serialized without errors using the changed reader.
Population:4 readability,1 symbol training,2 validation,33 series derivation,
10 bulk symbol reviews. Failed readability status/errors are retained; no
job is retried, hidden, rewritten or deleted. Evidence artifacts/operator-readonly.json.
This is a new-interpreter read, not a restarted production API or new server.

## Boundaries

No service restart, operator mutation, merge/push, training or deployment.
Running API remains on main and may still return500 until explicitly deployed.
All finite commands bounded to120s; audit uses the
repository terminal runner,1800s with stream idle guard60s.

## Independent audit

Terminal Claude Code Opus5.5 R1 PASS,0 P0/0 P1. High requested; CLI receipt
independently exposes model, not effort. Exact approved payload SHA:
7fe9fa0798b118c99893cc8d52d776a3974c20f7e9e1c72a3c55960039bae50e.
Report and receipt: TASK-1181_AUDIT_claude-opus-5-5.md/.receipt.json.

P2-1 addressed by nonzero success/failure/review counts and exact assertions
in the Python API regression. This changes tests only, not production behavior.
P2-2 accepted: the SDK request fixture verifies transport; generated drift,
SDK compilation and Admin typecheck cover the generated union, but there is
no separate handwritten satisfies-JobResponse fixture.
P2-3 accepted: operator data remain in local ignored evidence; aggregate
population and READ ONLY method are committed here. Preserve artifacts on
future authorized worktree cleanup rather than publishing private operator rows.
