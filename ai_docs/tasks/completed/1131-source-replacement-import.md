---
title: Import zamienników i zamknięcie rezerwacji
status: done
last_updated: 2026-11-03
---

# TASK-1131 — Import zamienników i zamknięcie rezerwacji

## Status

`done`

## Goal

Operator importuje wybrane nowe zdjęcie do otwartego entry, poprawia i weryfikuje je, a po pełnej weryfikacji zamyka rezerwacje bez utraty historii.

## Context

Plan 777A2 C2 łączy trwały request B2b, lokalny repair-v3 C1 i guardy/bootstrap B2a w operatorowy workflow.

## Dependencies / entry conditions

B2b i C1 zakończone. HEAD wejścia `6af10ac0149df93ce845326e1eadf0308c92993e`, v1.7.530; clean. Schemat 0175/v21. Cały plan, koszt i delegowanie zatwierdzone. Brak zgody na usługi, operacje danych operatora, aktywację, wdrożenie, merge/push.

## Recommended execution

`gpt-6-astra` / `high`; trwałe transakcje ownership i granice worker/API. Niezależny audyt `claude-opus-5-5` / `high`, jedna runda poprawek. Nierozstrzygnięta zmiana właściciela po częściowym accepted wymaga jawnej decyzji operatora.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md` — C2 i handoff B2a/B2b/C1.
- `ai_docs/requirements/IMAGE_INGESTION.md` — D543, browser staging, replacement.
- `ai_docs/architecture/API_CONTRACT.md` — browser import, replacement.
- `ai_docs/architecture/DATA_MODEL.md` — replacementAdmission, current, retention.
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-543--odrzucanie-przyciętych-plansz-po-imporcie-i-przejęcie-sekwencji-przez-zdjęcie-zastępcze`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-580--wycofanie-całego-źródła-i-autoryzacja-otwartej-luki`
- `ai_docs/quality/TASK-1128_AUDIT_claude-opus-5-5_R1.md` — P2 provisional/manual i orphan closure.

## Scope

- Optional binding w istniejącym browser staging/preflight/start, backend/OpenAPI/generated/wrapper/request-test/UI.
- Fresh DB scope/revision/SHA validation pod ownership lockiem; pin staging/job i materializacja sourceId przy discovery/rehydrate.
- Whole-photo binding, scoped working geometry/undo i normalne accepted/corrected bez transferu approvals.
- Idempotentne restored z canonical/readability proof, atomic orphan closure, fizyczne zwolnienie slots i zachowanie retention/tombstones.
- Fresh mobile publication provenance także po restored; historyczne wydane snapshoty bez zmian.

## Out of scope

Nowe zdjęcie po częściowym accepted bez decyzji; miks źródeł A+B; generic force; restore_retired/expiry; operatorowe importy/migracje/usługi; aktywacja modelu; APK collision group D1; merge/push.

## Acceptance criteria

- [x] A+B request i wybrane ukończone A importują wyłącznie A; realny SHA bez recropu.
- [x] Błędny/obcy SHA, zakres, entry, revision i job odmawiają przed mutacją.
- [x] Staging/start/discovery replay po restarcie i utracie odpowiedzi nie duplikuje źródła/review.
- [x] Provisional niewidoczne; ponowna ręczna korekta jednego slotu zachowuje tożsamość i finalizuje pełne zdjęcie.
- [x] Partial/rejected pozostaje w entry z reservations; verified working undo i ponowna ocena tego samego source.
- [x] Restored wymaga wszystkich canonical jednego nowego source i świeżej ludzkiej oceny pikseli; zamyka orphan i late worker przed usunięciem slots.
- [x] Old SHA/source pozostaje retired; nowe referencje i historia pozostają chronione.
- [x] Nowa publikacja mobile odmawia staremu datasetowi po restored, historyczne wydane pliki pozostają.
- [x] Testy, typy/lint, docs/map, audyt i task-close zakończone.

## Technical notes

Założenie zatwierdzone przez koordynatora: kontynuacja dotyczy jednego admission/source. Kolejne zdjęcie po częściowym accepted czeka na odpowiedź operatora; brak odpowiedzi nie upoważnia do nowego trybu. Wariant future fresh-preview wymaga osobnego wycofania całego nieudanego zamiennika z snapshotem canonical, markerami historii i ponownymi reservations; nie jest ukrytym retry. Wariant same-photo wymaga adaptera working undo dla reserved deferred slotów, gdzie zwykłe require_sequence_binding(review=None) dziś odmawia.

Klient GET służy prezentacji; backend i worker czytają DB w tej samej transakcji, bez self-HTTP i URL z pliku. ScopeDigest liczyć z immutable batch.document.entries, nie mutable admission entry.document. Staging pin zawiera verified upload/manifest/file SHA/range; job pin powstaje atomowo z add_source_bound_job. Worker po INSERT+flush source pod lease/ownership dopełnia proof i retention, przed canonical shortcut. Receipt sprawdzany przed świeżymi guardami; key/body conflict odmawia. Wcześniejsze skipy canonical muszą respektować opt-in pełnego pliku.

## Expected files

- Nowe: `storage/source_replacement_admission.py`, domenowy kontrakt admission i celowane testy.
- `api/image_imports.py`, `schemas/image_imports.py`, `application/image_imports.py`, `application/jobs.py`, `storage/job_repository.py`: staging i atomic job binding.
- `storage/source_replacement_binding.py`, `storage/source_replacement_retirement.py`, `storage/virtual_grid_geometry_repository.py`, `storage/geometry_rejection_revert.py`: proof, immutable scope, working geometry/undo i restore.
- Worker `images/pipeline_store.py`, `images/production_workflow.py`: materializacja pinu i skipy.
- Istniejący source replacement API/schema/UI, klient generated/wrapper; scoped mobile publication guard.

## Test cases

Małe fixture: foreign sameSHA seq1200/no mutation; selected A z request A+B; restart/lost response każdej granicy; rollback po pierwszym bindzie; repeated manual provisional; rejected/undo; partial accepted bez podmiany A; restored bez orphan; late old source/late worker; current/history/inne gry; stale pre-retirement mobile dataset po restored.

## Verification

Root Python `D:/game_predicotr/.venv/Scripts/python.exe`, cwd worktree. Każdy przebieg ma limit <=120 s; HTTP/PG require_escalated, izolowana baza name/OID/receipt, krótkie basetemp `D:/game_predicotr/artifacts/t1131-*`. Najpierw testy pionu, lint/typecheck, następnie uzasadniona regresja. Audyt timeout480/external600, modelUsage Opus5.5/high. Docs cztery checkery rootPython, code map regenerate/check. Bez zmian junction node_modules; scoped TS paths lokalne. Realny build całości D1.

## Risks / open questions

- Wybór kolejnego zdjęcia po częściowym accepted oczekuje decyzji; obecny zakres zachowuje jedno źródło.
- Working undo używa wdrożonego explicit verified adaptera; brak public force.
- Mutable admission jest oddzielony od immutable scopeDigest w batch snapshot.

## Outcome

Commit: v1.7.531 / `ad92ac35699b364e11a81b4cc0622f8ec281142a`.

Implementacja C2 obejmuje jeden admission/source na wpis: actual selected JPEG bez recropu, fresh DB validation i durable upload/job/source pin, verified working geometry/undo, normalne approvals i osobne restored z aktualną czytelnością cropów. Migracja0176 utrzymuje terminalny orphan fence po usunięciu slots. Mobile capture zapisuje istniejący source_board_id i waliduje current cells także po restored. Historia, tombstones i normalized retention pozostają. Immutable scopeDigest pochodzi z planned batch snapshot, nie mutable operational document.

Verification results (root Python, cwd worktree, timeout120; PG/HTTP require_escalated):

- `pytest services/api/tests/integration/test_source_replacement_admission_postgres.py services/api/tests/integration/test_source_replacement_manual_postgres.py services/api/tests/integration/test_source_replacement_working_undo_postgres.py --basetemp=D:/game_predicotr/artifacts/t1131-final-pg -q -x --tb=short --show-capture=no`: **5 PASS /75,62 s**. Atomic job rollback, fresh-session discovery/replay, tampered staged proof refusal, foreign SHA scope refusal, repeated provisional correction without duplicate, whole-photo bind, real normal approvals, restored rollback/restart/receipt, rejected/pending orphan closure, late commands, nullable current fence and legal winner geometry after restored.
- Domain admission + worker pipeline execution + storage resume: **48 PASS /12,68 s** (`t1131-unit02`). Working undo own PG **2 PASS /34,22 s**, ordinary undo/reverts **41 PASS /17,93 s**; no weakening of legacy behavior.
- Mobile delegated owned PG **1 PASS /24,42 s**, ordinary release/layout publication PG **2 PASS /35,16 s**, worker **3 PASS /1,54 s**. Real retirement/aliases, restored slot deletion, old/NULL lineage refusal, current capture/record/ready, receipt/history, another game, cell drift and real SHARED/EXCLUSIVE fence. Core restored separately proven above.
- API/UI: **81 node request/actions/storage/UI/legacy PASS**; **5 HTTP PASS**, then **2 HTTP PASS** after manifest-state-loss and staging-GC replay regression. Scoped Admin TS, ESLint (0 errors; one existing img warning), OpenAPI freshness and generated drift **PASS**. UI covers selected A from request A+B, persisted recovery, explicit real-crop readability and ordinary review.
- Scoped core mypy **10 source files PASS**, follow-imports=skip; disabled no-any-return plus misc/redundant-cast to accommodate existing skipped Protocol/base imports and pre-existing redundant cast. This is not full backend dependency typecheck. Mobile scoped mypy5 PASS, API scoped mypy6 PASS, undo scoped module PASS. Delegated Ruff PASS.

Audit: [Opus5.5/high R1](../../quality/TASK-1131_AUDIT_claude-opus-5-5.md) **PASS**, rzeczywisty modelUsage `claude-opus-5-5`, exit0, brak P0/P1; bez rundy2 i zmian kodu po audycie. P2-1 sprostowany istniejącym _require_candidate_lease ownership lock (pipeline_store.py:1422), wywołanym przed require_open_admission. P2-2 przyjęty fail-closed limit dostępności przy dodatkowych orphan na tej samej seq; P2-3 redundantny self-comparison, właściwy freshness check pozostaje. Zgodnie pilnym poleceniem operatora nie dodano nowych wariantów ani scenariuszy. Ruff31 changed Python files PASS; code-map regenerate/check PASS; cztery docs checkery PASS; git diff --check PASS.

Scope/limitations: no services, operator data changes, production migration, activation, merge/push, broad benchmark or full product build. Migration0176 applied only to owned disposable test DBs (name/OID/receipt guards). D1 owns final integration/build and the already documented APK collision regression. One source per entry remains the approved assumption; no next-photo/attempt-reset mode, no mixed owners and no generic force. Earlier test failures were fixture shape/assertion corrections; final runs above pass. No lingering test processes.

DoD comparison: API/backend/generated/wrapper/request tests present; durable restart and lost-response paths verified; current/history and retention preserved; normal consumer regressions passed. Audyt i kontrole dokumentacji zakończone; task zamknięty skryptem task-close. Wszystkie kryteria planu C2 spełnione w zakresie jednego admission/source; P2 rozliczone powyżej. D1 wykonuje wymagane changed checks/build i końcowy flow, bez przebudowy typów całego repo ani szerokiej eksploracji. Koordynator jawnie zaakceptował P2-2/P2-3 i potwierdził sprostowanie P2-1.
