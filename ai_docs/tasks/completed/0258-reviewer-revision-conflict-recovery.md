---
title: TASK-0258 Reviewer revision conflict recovery
status: done
release: "0.7"
last_updated: 2026-08-21
---

# TASK-0258 — Automatyczne odzyskiwanie konfliktu rewizji Reviewera

## Goal

Reviewer nie może pozostawić operatora na nieaktualnej planszy po
`IMAGE_REVIEW_REVISION_CONFLICT`. Musi automatycznie pobrać autorytatywną
rewizję, zachowując ochronę przed cichym nadpisaniem decyzji drugiej sesji.

## Context

- Plansza `253` importu `b2d9b299-a851-4e17-9ba3-dacaa7966978` została
  poprawnie zaakceptowana 21 sierpnia 2026 o 19:20:27 czasu lokalnego.
- Następna komenda korzystała ze starego snapshotu rewizji `0`, podczas gdy
  rekord miał już rewizję `1`, dlatego API prawidłowo zwróciło konflikt.
- Bounded prefetch Reviewera albo drugie otwarte okno może zgodnie z projektem
  posiadać taki starszy snapshot.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- automatycznie przeładować bieżącą planszę po konflikcie rewizji pełnej
  decyzji,
- wyczyścić klucz idempotencji nieaktualnej komendy,
- pozostawić backendową kontrolę `expectedRevision` bez zmian,
- dodać regresję kontraktu Reviewera i zaktualizować wymagania.

## Out of scope

- automatyczne nadpisanie decyzji innej sesji,
- osłabienie kontroli rewizji lub geometrii,
- zmiana API, OpenAPI, bazy albo mechanizmu bounded prefetch,
- automatyczne rozstrzyganie konfliktu ręcznej korekty geometrii.

## Acceptance criteria

- [x] Konflikt rewizji pełnej decyzji automatycznie uruchamia odczyt aktualnej
      planszy.
- [x] Klucz idempotencji starej komendy nie przechodzi na nową rewizję.
- [x] Aktualna decyzja drugiego reviewera pozostaje źródłem prawdy.
- [x] Pozostałe błędy zapisu nadal pozostają widoczne bez automatycznego reloadu.
- [x] Testy, typecheck, lint i build Reviewera przechodzą.

## Outcome

- Konflikt rewizji pełnej decyzji czyści klucz idempotencji starej komendy i
  automatycznie wywołuje ograniczony odczyt bieżącej planszy. Ponowny zapis nie
  jest wykonywany bez udziału operatora.
- Plansza `253` nie wymaga naprawy danych: read-only kontrola PostgreSQL
  potwierdziła status `accepted`, rewizję `1`, geometrię `1` oraz pojedynczy
  append-only event z 21 sierpnia 2026, 19:20:27 czasu lokalnego.
- Backendowa kontrola `expectedRevision`, first-save-wins, API, OpenAPI i baza
  pozostały bez zmian.
- Przeszło `35/35` testów Reviewera, typecheck, ESLint oraz produkcyjny build.
