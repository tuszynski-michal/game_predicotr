---
title: TASK-0284 - Deselect, undo, tombstone i kwarantanna
status: done
owner: Codex
version: 0.7
---

## Cel

Zaimplementować TASK 12 planu zdalnej ręcznej selekcji: zachować semantykę
`deselect`/`undo`, anulować starsze transfery oraz bezpiecznie przenosić wyłącznie
własny, checksumowo zgodny plik `seq_*` do odwracalnej kwarantanny, bez możliwości
wskrzeszenia go przez spóźnioną generację.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md` (TASK 12, sekcje 11.5, 14, 15 i 18)
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/tasks/completed/0283-remote-selection-host-materialization.md`

## Zakres

- state transitions oraz trwały tombstone dla `deselect`/`undo`;
- priorytet operacji sterującej i anulowanie queued/in-flight starszego transferu;
- trwała host action `remove`, fencing, retry i checksum-guarded quarantine;
- aktualizacja projekcji pliku po kwarantannie i zachowanie artefaktu bez finalnego GC;
- odporność na sekwencję select/deselect/reselect oraz spóźnione akcje;
- konflikt obcego lub zmienionego celu bez jego usunięcia;
- testy domenowe, repozytorium, filesystem, PostgreSQL i Reviewera.

## Poza zakresem

- arbitralne lub masowe usuwanie plików;
- usuwanie obcych plików;
- finalny GC kwarantanny przed decyzją o retencji;
- ponowne otwieranie ukończonej partii;
- finalizacja całej partii i pełny workspace zdalny z TASK 13.

## Invarianty

- tylko finalny plik należący do akcji i nadal zgodny checksumowo może zniknąć;
- generacja N nie może zostać materializowana po zastosowaniu N+1;
- dokładny retry `undo`/`deselect` nie zwiększa ponownie rewizji ani generacji;
- kwarantanna pozostaje odwracalna i nie podlega GC w tym zadaniu;
- obcy lub zmieniony cel pozostaje nietknięty i daje kontrolowany konflikt;
- spóźniona akcja nie może usunąć wyniku nowszej generacji;
- lokalny fallback pozostaje bez zmian.

## Kryteria odbioru

- deselect przed, w trakcie i po uploadzie kończy się zgodnym desired state;
- queued/active transfer starszej generacji jest anulowany, a jego retry nie wznawia uploadu;
- zsynchronizowany własny plik trafia do wewnętrznej kwarantanny i projekcja kończy się `removed`;
- rapid select/deselect/select materializuje wyłącznie ostatnią generację;
- foreign/changed target i unsafe path są fail-closed;
- crash windows akcji remove są idempotentnie odzyskiwalne;
- testy API/Reviewer/PostgreSQL, Ruff/mypy/OpenAPI oraz build są zielone w zakresie zmiany.

## Outcome

Zaimplementowano generacyjny tombstone dla `deselect`/`undo`, anulowanie
starszych transferów i materializacji oraz priorytetową, trwałą akcję `remove`.
Własny finalny plik jest przenoszony przypiętym uchwytem do checksumowanej,
odwracalnej kwarantanny; foreign/changed/reparse target pozostaje nietknięty.
Crash windows, exact retry i rapid select/deselect/select są idempotentne, a
Reviewer nie wznawia anulowanego checkpointu starszej generacji. Finalny GC
pozostaje świadomie poza zakresem do decyzji o retencji.

Weryfikacja: 144 celowane testy API i 1 pominięty symlink, 16 testów workera,
16 testów PostgreSQL, 93 testy Reviewera, Ruff, izolowany mypy, Reviewer
lint/typecheck/build oraz OpenAPI.
