---
title: TASK-0293 Approved symbol reference images
status: done
---

# TASK-0293 — Grafiki symboli wyłącznie z zatwierdzonych plansz

## Goal

Katalog symboli jest ręczny, a aktywna grafika każdego symbolu może pochodzić
wyłącznie ze świadomie wybranego cropa zatwierdzonego przez człowieka.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- niezależna domena i zapytanie kandydatów kanonicznych `accepted/corrected`,
- trwałe, checksum-bound referencje cropów,
- ręczny CRUD katalogu i blokowane fizyczne usuwanie,
- usunięcie bootstrapu,
- picker Admina wyłącznie zatwierdzonych cropów,
- odbiór dokumentacji, API, migracji i panelu.

## Acceptance criteria

- [x] Brak aktywnej ścieżki automatycznego bootstrapu symboli.
- [x] Referencja symbolu ma pełną proweniencję i trwały asset.
- [x] Picker wyklucza pending, rejected, superseded oraz predykcje modelu.
- [x] Katalog pozwala utworzyć symbol wyłącznie z nazwą i Jokerem.
- [x] Używany symbol nie jest usuwalny, a interfejs pokazuje powody.

## Outcome

### Changed

- `v0.8.10`–`v0.8.16` dostarczyły domenę kandydatów, kanoniczne źródło,
  trwałą referencję, ręczny CRUD, usunięcie bootstrapu oraz picker Admina.
- `v0.8.17` aktualizuje obowiązujące wymagania, kontrakt API, model danych,
  Decision Log i Current State.

### Verification results

- Celowane testy domeny, repozytorium, migracji i OpenAPI: 70 passed.
- Testy Admina: 263 passed; klient Admin API: 42 passed.
- OpenAPI/generowany klient, celowane Ruff i mypy, typecheck oraz produkcyjny
  build Admina przeszły.
- Lokalna baza jest na migracji `0065_remove_symbol_bootstrap (head)`.

### Not completed

- Lokalna baza użyta do odbioru nie zawiera obecnie gry z ośmioma symbolami,
  dlatego odbiór klikany wszystkich ośmiu pickerów wymaga później właściwych
  danych użytkownika. Kontrakty i testy izolowane pokrywają tę ścieżkę.
- Pełny baseline PostgreSQL zatrzymuje się na niezwiązanym teście generowania
  datasetu, który oczekuje 1 000 layoutów mimo bieżącego celu 500 000.
- Pełny lint Pythona ma 9 wcześniejszych błędów poza pionem referencji.

### Documentation updates

- Zaktualizowano `ADMIN_APP.md`, `API_CONTRACT.md`, `DATA_MODEL.md`,
  `CURRENT_STATE.md` i `DECISION_LOG.md`.

### Recommended next task

- Wczytać istniejącą grę z zatwierdzonymi planszami i wykonać ręczny odbiór
  propozycji oraz wyboru reprezentatywnego cropa dla każdego symbolu.
