---
title: TASK-0276 - Trwały model zdalnej ręcznej selekcji
status: done
owner: Codex
version: 0.7
---

# Cel

Utrwalić kontrakty TASK-0275 w PostgreSQL przez addytywną migrację, modele ORM
i repozytoria zachowujące rewizje, generacje, idempotencję, scope oraz
append-only historię, bez dodawania transportu i obsługi plików.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md` (sekcje 12-14, TASK 4)
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/tasks/completed/0275-remote-manual-selection-domain-contracts.md`

## Zakres

- osiem tabel zdalnej selekcji: sesje, kolekcje, partie, pliki, operacje,
  transfery, akcje hosta i audyt;
- addytywna migracja Alembic z FK scope, checkami, indeksami i blokadą mutacji
  append-only operacji/audytu;
- modele ORM bez BLOB-ów obrazów;
- repozytorium SQLAlchemy z row/advisory lockami, mapowaniem constraint errors,
  atomowym zastosowaniem operacji i bounded delta;
- in-memory parity double dla operacji domenowych;
- testy mapperów, constraintów, konkurencji, baseline i skali 15 000 rekordów.

## Poza zakresem

- picker i bezpieczne mapowanie ścieżek Windows z TASK 5;
- kod, token, auth i writer lease service z TASK 6;
- API, OpenAPI, upload, materializacja, worker i UI.

## Invarianty

- dokładnie jedno mapowanie `base binding + collection + batch`;
- batch revision i client sequence są monotoniczne pod blokadą wiersza;
- `operationId` oraz `batch + clientInstance + clientSequence` są unikalne;
- operations i audit są append-only;
- composite FK odrzucają obcy session/batch/file scope;
- baza nie przechowuje JPEG/BLOB, a publiczna projekcja repozytorium nie
  ujawnia base/temp path, salt/hash ani lease tokenu;
- TASK-0275 pozostaje źródłem semantyki operacji.

## Outcome

- Dodano migrację `0056_remote_manual_selection_persistence` z ośmioma
  tabelami, composite FK scope, constraintami, indeksami delta/queue,
  unikalnym mapowaniem base oraz triggerami append-only.
- Dodano odpowiadające modele ORM i repozytorium SQLAlchemy. Zastosowanie
  operacji blokuje batch/file i atomowo aktualizuje rewizję, desired state oraz
  dziennik; exact retry pozostaje neutralny.
- Dodano parity double in-memory, publiczne mappery bez host-only sekretów oraz
  stabilne mapowanie błędów constraintów.
- Testy TASK 4: `53 passed` unit/migration, `10 passed` PostgreSQL integration,
  Ruff bez błędów i focused mypy bez błędów. Test skali sprawdził delta/indexy
  na 15 000 plików i operacji.
- Pełne `npm run db:baseline:verify`: `35 passed, 4 failed`. Cztery błędy są
  historyczne i niezwiązane z TASK 4: dwa fixture nie ustawiają obecnie
  obowiązkowego `expected_layout_count`, raport importu oczekuje poprzedniego
  kodu błędu, a generator mock datasetu tworzy nieoczekiwane duplikaty. Tabele
  dodane w 0056 nie są używane przez te testy.
- Nie wykonano migracji roboczej bazy użytkownika i nie rozpoczęto TASK 5.
