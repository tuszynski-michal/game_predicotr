---
title: TASK-0275 - Kontrakty domenowe zdalnej ręcznej selekcji
status: done
owner: Codex
version: 0.7
---

# Cel

Zamrozić wersjonowane, niezależne od HTTP, ORM, filesystemu i UI kontrakty
zdalnej ręcznej selekcji oraz ich maszyny stanów przed dodaniem trwałości.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md` (TASK 3)
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`

## Zakres

- wersjonowane kontrakty sesji, kolekcji, partii, pliku, operacji, transferu i
  host action;
- jawne legalne przejścia stanów oraz stabilne błędy fail-closed;
- rewizja serwera, generacja wyboru, kolejność klienta i exact retry;
- kanoniczny `remote-source-manifest-v1`, host-internal manifest operacyjny v1
  oraz projekcje istniejących output/trace v1;
- testy legalnych i niedozwolonych przejść, scope IDs, generacji,
  idempotencji, snapshotów i projekcji 15 000 rekordów.

## Poza zakresem

- ORM, migracja Alembic, repozytorium i blokady bazy;
- HTTP, OpenAPI, route, autoryzacja transportowa i upload;
- filesystem hosta, worker, outbox IndexedDB i UI.

## Invarianty

- starsza generacja nie zmienia żądanego stanu ani rewizji;
- exact retry tego samego `operationId` zwraca identyczny wynik bez zmiany
  rewizji;
- luka lub regresja `clientSequence`, obcy scope i nieznany typ operacji są
  odrzucane fail-closed;
- finalne projekcje output/trace zachowują istniejące schema v1 i pola;
- moduł domeny nie zależy od FastAPI, SQLAlchemy, filesystemu ani Reacta.

## Outcome

- Dodano czysty moduł domenowy API z wersjonowanymi kontraktami wszystkich
  siedmiu agregatów, pełnymi macierzami przejść i stabilnymi kodami błędów.
- Operacje mają jawne reguły scope, kolejności, rewizji, generacji i exact
  retry. Stale generation jest neutralne dla desired state i rewizji.
- Dodano kanoniczne manifesty źródła/hosta oraz kompatybilne projekcje
  output/trace v1. Python i TypeScript używają tego samego snapshotu SHA-256.
- Testy: 36/36 domeny API, 8/8 wspólnego core, Ruff i celowany mypy bez błędów,
  typecheck wspólnego core bez błędów. Projekcja 15 000 rekordów przeszła.
- Nie dodano ORM, migracji, route, HTTP, filesystemu, workera ani UI. TASK 4
  pozostaje nierozpoczęty i wymaga checkpointu kontraktów.
