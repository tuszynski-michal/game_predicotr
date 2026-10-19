---
title: Kolejka operacji masowej weryfikacji symboli
status: done
last_updated: 2026-10-19
---

# TASK-1071 — Kolejka operacji masowej weryfikacji symboli

## Status

`done`

## Goal

Przywrócić kolejkowanie kilku operacji weryfikacji symboli przy pojedynczym wykonaniu.

## Context

Operator zgłosił `GAME_JOB_ADMISSION_CONFLICT` przy drugiej operacji. Przyczyna:
TASK-0999, commit `62e9f719`, wprowadził wspólny guard odrzucający nowe joby,
gdy ta sama gra ma CREATED lub PROCESSING import/geometry/symbol job.
D-551 wymagał tej blokady także między operacjami masowymi. Po diagnozie operator
2026-10-19 jawnie zatwierdził wyjątek: „Przywróć kolejkę operacji symboli”.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md` — Weryfikacja symboli.
- `ai_docs/architecture/API_CONTRACT.md` — trwałe operacje masowe i admission.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-551--propozycje-dla-błędnej-siatki-v3`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Wyjątek wyłącznie bulk → bulk przy publikacji joba, także retry/resume.
- Worker nadal blokuje wykonanie przy innym PROCESSING jobie.
- Zachowanie symetrycznej blokady wobec importu, geometrii, treningu,
  reinferencji i rekonstrukcji projekcji.
- Testy regresji, D-566, wymagania i dokumentacja kontraktu.

## Out of scope

Zmiany endpointów i schematu, równoległe wykonanie jobów, usługi operatora i operacje na jego danych.

## Acceptance criteria

- [x] Można dodać kolejny bulk przy CREATED albo PROCESSING bulk tej samej gry.
- [x] Drugi bulk nie rozpoczyna wykonania przed zakończeniem pierwszego.
- [x] Inne kolidujące typy nadal blokują nowe bulk i odwrotnie.
- [x] Rewizje cropów, rollback, idempotencja i izolacja gry pozostają chronione.
- [x] Zakres jest gotowy do scalenia wraz z wcześniejszymi TASK-1068–1070 zgodnie z poleceniem operatora; brak nowych migracji.

## Expected files

- `services/api/src/game_predictor_api/storage/job_admission.py` — acquire_job_admission, admit_job.
- `services/api/tests/integration/test_symbol_review_bulk_start_locking_postgres.py` — kolejka i blokady.
- Nowy: `services/api/tests/test_job_admission.py` — macierz konfliktów i gate wykonania.
- Wymagania, kontrakt API, indeks i pełny wpis decyzji, mapa kodu oraz dokumentacja zamknięcia.

## Verification

Celowane testy API i PostgreSQL (izolowane bazy testowe), istniejąca regresja
UI kolejnych operacji, Ruff, mypy zmienionego modułu, docs:check i code-map:check.
Timeout każdej komendy 120 s. Bez benchmarków i szerokiej eksploracji.

## Risks / open questions

Brak otwartych decyzji po zgodzie operatora. Zadanie poza planem wymagającym
audytu. Dane operatora i zastane zmiany artefaktów nie należą do zakresu.

## Outcome

Commit: v1.7.447 / `a88af5c2f2289cca6c498c4b2faa7833e5faf715`.

### Changed

- Potwierdzono przyczynę: `job_admission.py` z TASK-0999, commit `62e9f719`,
  blokował publikację nowego bulk przy innym CREATED/PROCESSING bulk.
- Po jawnej zgodzie operatora D-566 dodaje wyjątek wyłącznie dla kolejkowania
  bulk za bulk. Wspólny mutex, worker claim/recovery i globalny slot nie zmieniają się.
- Pozostałe konflikty są symetryczne; rewizje, rollback i idempotentny replay są zachowane.
- Naprawa jest zapisana w kodzie; sprawdzona w nowych procesach oraz sesjach PostgreSQL.

### Verification results

- `pytest services/api/tests/test_job_admission.py services/api/tests/test_symbol_review_bulk_start_locking.py -q -p no:cacheprovider`: 39 PASS.
- PostgreSQL: test kolejki 1 PASS (26 s), pozostałe testy blokad, stale i utraconej odpowiedzi 4 PASS (74 s), izolowane bazy z pełnymi migracjami.
- Pierwsza próba PostgreSQL w sandboxie: połączenie zabronione. Próba poza sandboxem z przechwyconym wyjściem przerwana po braku widocznego wyniku; po potwierdzeniu braku procesów własną bazę i role usunięto helperem ownership receipt. Testy ponowiono z widocznym postępem i wynikiem PASS.
- UI: `tsx --tsconfig tsconfig.json --test --test-name-pattern="independent bulk jobs" test-interactions/symbol-review-partial.test.mjs`: 2 PASS (processing i completed).
- Ruff check i format trzech plików Pythona: PASS.
- `mypy services/api/src/game_predictor_api/storage/job_admission.py --follow-imports=silent`: PASS.
- Regeneracja mapy: wykonana, zmiana wyłącznie liczby testów API.
- `npm run docs:check`, kontrola zamknięcia oraz `npm run code-map:check`: PASS.
- Wszystkie kryteria implementacji i właściwe punkty Definition of Done spełnione. Audyt krzyżowy niewymagany poza planem.

### Not completed

- Nie uruchamiano szerokich testów, benchmarków, usług ani operacji na danych operatora.
- Brak nowego endpointu, typu HTTP i migracji; nie wymaga regeneracji klienta OpenAPI.

### Documentation updates

- D-566 i indeksy decyzji; wymagania Admina i istniejący kontrakt admission.
- Zamknięcie i hash skryptem task-close. Zgoda na scalenie/push całego zakresu pochodzi z bieżącego polecenia operatora; usługi pozostają pod jego kontrolą.

### Recommended next task

- Scalenie TASK-1068–1071 do main i push zgodnie z poleceniem operatora, potem odbiór w Adminie.
