---
title: TASK-0515 — Real-corpus acceptance and guarded release of v0.10.4
status: done
last_updated: 2026-09-08
---

# TASK-0515 — Real-corpus acceptance and guarded release of v0.10.4

## Status

`done`

## Goal

Qualify the opt-in lateral-partial v0.10.4 engine on a checksum-bound,
source-disjoint real-image corpus and open its existing test-only launch path
only if every accuracy, safety, replay and performance gate passes.

## Context

TASK-0510–TASK-0514 delivered the immutable variant contract, registration
candidate, local lattice fit, durable reprocessing and Admin surface. The
backend release constant intentionally remains false until a real-data
comparison against v3 proves that full boards do not regress and lateral
recovery cannot shift columns or invent pixels.

## Dependencies / entry conditions

- TASK-0510–TASK-0514 are committed through `v0.10.230` (`3da91c39`) and their
  focused gates passed.
- The existing user corpus under `C:\Users\user\Documents\777`, managed
  originals and manual geometry revisions may be inspected read-only.
- No import, migration, service restart, cleanup or mutation of operator data
  is authorized.
- Existing dirty `next-env.d.ts`, cleanup artefacts, migration 0102 and virtual
  geometry repository/model/test changes are unrelated and excluded.

## Recommended execution

Use `gpt-5.6-sol` with `high` reasoning, matching the accepted TASK-0510–0515
plan. An independent `gpt-6-astra high` review is mandatory before commit,
with special attention to corpus independence, column identity, source-support
proof, decision preservation and the release predicate.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DECISION_LOG.md` (D-374)
- `ai_docs/quality/PARTIAL_GEOMETRY_ACCEPTANCE.md`
- completed TASK-0510–TASK-0514

## Scope

- Freeze a bounded checksum-bound corpus of real full boards and in-memory
  lateral crops derived from reviewed real sources, disjoint by source checksum
  from any tuning material.
- Include left, right, vertical, ambiguous and missing-board scenarios with
  manual references and stable scenario identities.
- Compare v3 and v4 on the exact same full-board inputs; report coverage,
  manual/error reason indexes, median/p95 runtime and full-board overhead.
- Verify exact original column indices, unavailable-cell masks, no crop outside
  real source support, real left/right recovery, deterministic replay and no
  loss or duplication of logical decisions.
- Add a reproducible bounded evaluator, focused tests, quality report and
  operator instructions.
- Set `LATERAL_PARTIAL_RELEASED = True` only when the immutable report proves
  every gate. Otherwise keep it false and record the exact blocker.

## Out of scope

- Running imports, preflights or reprocessing against operator data.
- Database writes, migrations, cleanup, service restarts or training.
- Changing the v3 engine, page-registration thresholds, game rollout policy or
  historical snapshots.
- Broad tuning on the acceptance corpus or lowering a safety threshold to make
  the report pass.

## Acceptance criteria

- [x] Full-board v4 output is byte-equivalent to v3 for every corpus board and
      has zero coverage regression.
- [x] Every accepted lateral proposal preserves the manually attested logical
      columns; column-shift count is zero.
- [x] Every unavailable index corresponds to a proper cell footprint outside
      source pixels and no unavailable cell is rendered.
- [x] No vertical, ambiguous or missing-board negative is accepted as lateral.
- [x] At least one real left crop and one real right crop are recovered.
- [x] Replay is deterministic and the scenario decision index has neither loss
      nor duplicates.
- [x] Median and p95 runtime are reported; v4 overhead on full images is at
      most 10% relative to v3 under paired repeated measurement.
- [x] API/worker/web regression suites, Ruff, mypy, lint, typecheck, OpenAPI,
      formatting and Admin/Reviewer production builds pass or an unrelated
      pre-existing blocker is recorded precisely.
- [x] Requirements, architecture, Decision Log, CURRENT_STATE, quality report,
      operator guide and Outcome are current.
- [x] Independent `gpt-6-astra high` review has no unresolved P0–P2 finding
      before commit.

## Technical notes

The evaluator must never write beside user JPEGs or update SQL. It resolves
managed originals by content checksum, validates bytes and dimensions, then
performs derived crops only in memory. Manual source geometry is reference
evidence, not an engine input beyond the explicitly frozen analysis/search
quad required by the corpus scenario. Corpus construction and threshold tuning
must remain separate; `tuningSourcesUsed` is zero.

Full-board timing uses paired v3/v4 calls on identical boards after warm-up and
reports medians and p95 values. Since v4 returns before the partial pass when v3
succeeds, any regression is a release blocker. A failing negative or invariant
is not reclassified as manual success.

## Expected files

- New: bounded evaluator and focused tests under `scripts/` and
  `services/worker/tests/`.
- New: immutable corpus/report artefacts and quality summary under
  `ai_docs/quality/`.
- Existing: `services/worker/.../lateral_partial_contract.py` release constant,
  only after a passing report.
- Existing: ingestion requirements, schema ownership/import architecture,
  Decision Log, CURRENT_STATE and local operator guide.

## Test cases

- Full real source: v3 result equals v4 payload and v4 runs no lateral pass.
- Real left/right crop: exact logical missing column and supported visible crop
  indices; replay produces the same decision and proposal payload.
- Vertical crop, insufficient/ambiguous horizontal evidence and absent board:
  fail closed with stable reason and no proposal.
- Duplicate scenario id/checksum, missing source, changed bytes, changed manual
  reference or incomplete decision index: evaluator rejects the corpus/report.
- Paired timing: finite median/p95 and full-image overhead `<= 10%`.
- Release predicate: a single failed gate keeps the public capability disabled.

## Verification

```powershell
# Run the bounded real-corpus evaluator and its focused worker tests first.
# Then run scoped API/worker regressions, Ruff, mypy, OpenAPI, client tests,
# Admin/Reviewer lint + typecheck + production builds and formatting checks.
# Each subprocess has an explicit timeout no greater than 120 seconds unless a
# known production build is announced separately.
```

The task may be completed only from a newly generated passing immutable report
whose source checksums still match. Review precedes staging and commit.

## Risks / open questions

- Existing reviewed material may be insufficient for every negative/recovery
  class. In that case the release remains closed until bounded real-derived
  fixtures are reviewed; absence of evidence is not acceptance.
- Timing on Windows is noisy. Use paired repetitions and a minimum sample size;
  do not hide a failed overhead gate by selecting a favourable single run.

## Outcome

### Changed

- Zamrożono checksum-bound korpus 32 rzeczywistych JPEG-ów: 5 bieżących
  ręcznych page override'ów z managed originals oraz 27 zaakceptowanych
  ręcznie plansz M5. Powstało 252 stabilnych scenariuszy: 72 pełne, 84 boczne
  i 96 negatywów.
- Dodano ograniczony evaluator. Pełne obrazy porównuje przez niezależne
  wywołania v3/v4, a pięć źródeł stron prowadzi rzeczywiste cropy RGB przez
  source-disjoint rejestrację ORB. Dodatkowe realne fixtures badają jawnie
  ograniczony lokalny fit i negatywy.
- Każda propozycja przechodzi niezależny test oczekiwanej maski, offsetu
  kolumn oraz rzeczywisty `VirtualCellRenderer`. Negatywy akceptują wyłącznie
  fail-closed `needs_review`/`source_preparation_error`.
- Lokalny fitter odrzuca maskę niedostępnych kolumn niespójną między rzędami,
  mniej niż trzy kolejne dostępne kolumny i inlier oparty na niedostępnej
  komórce. Po zielonej bramce otwarto testowy opt-in
  `LATERAL_PARTIAL_RELEASED=True`; v3 pozostaje domyślny.

### Verification results

- Finalny raport `002466ef722bdd555207b1f5af42bb8485c4cfb221b4414bd313a4a05caeb54f`
  przeszedł wszystkie bramki: 70/70 zaakceptowanych full v3/v4, 34 propozycje
  boczne (15 lewych, 19 prawych), 50 manualnych, zero błędów i zero utraty lub
  duplikacji decyzji. Wszystkie 32 checksumy źródeł pozostały bez zmian.
- Parowany pomiar 5× na 72 pełnych planszach: mediana v3/v4
  62,05305/62,39175 ms, p95 101,401/97,412 ms i łączna różnica -0,3978%
  wobec limitu +10%.
- Finalny focused batch worker/API: 152 passed. Wcześniej pełny worker w
  siedmiu ograniczonych shardach: 1395 passed. Admin: 445 passed; Reviewer:
  183 passed; oba lint/typecheck/build oraz testy interakcji przeszły.
  OpenAPI artefakt i generowany klient przeszły. Scoped Ruff, format, mypy i
  Prettier przeszły; `git diff --check` nie wykrył błędów.
- Pełne API: 1078 passed, 3 skipped i 3 niezwiązane failures opisane poniżej.

### Not completed

- Globalny Ruff blokuje obcy untracked `0102_index_symbol_review_prediction_revision.py`.
  Root mypy zatrzymuje się przed analizą przez obcy
  `scripts/legacy_777_v01_chat_search.py` widziany jako duplikat modułu.
  Globalny format wskazuje 31 wcześniejszych plików spoza zakresu.
- Trzy niezwiązane failures pełnego API: dirty migracja 0102 łamie oczekiwany
  pojedynczy head 0101; istniejący test OpenAPI oczekuje nieobecnego
  `minItems`; stary fixture backfillu nie ma atrybutu `asset_mode`. Nie
  zmieniano tych plików ani nie rozszerzano zakresu.
- Nie wykonano importu, migracji, restartu, reprocessingu ani mutacji danych
  operatora. Niezależny końcowy `gpt-6-astra high` re-review zaakceptował
  wynik bez findings P0–P2; commit nie został utworzony.

### Documentation updates

- Zaktualizowano wymagania image ingestion, trzy dokumenty architektury,
  Decision Log (D-375), CURRENT_STATE i instrukcję operatorską. Dodano
  checksum-bound JSON korpusu/raportu i raport jakości z procedurą powtórzenia.

### Recommended next task

- None. This is the final task in the accepted series.
