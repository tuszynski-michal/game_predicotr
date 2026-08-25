---
title: TASK-0291 — Jedna oczekująca plansza dla numeru sekwencji
status: todo
last_updated: 2026-08-25
---

# TASK-0291 — Jedna oczekująca plansza dla numeru sekwencji

## Goal

Zapewnić, że ponowne importy tego samego zakresu nie tworzą drugiej aktywnej
planszy `pending` dla tej samej pary `game_id + sequence_number`.

## Context

Aktualny rejestr kanoniczny chroni wyłącznie zaakceptowane i poprawione
plansze. Równoległe lub ponowione importy mogą więc pozostawić wiele oczekujących
źródeł tego samego numeru. Nowy widok wyszukiwania musi pokazywać jedną logiczną
planszę na numer, ale trwałe usunięcie przyczyny jest osobnym pionem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- zdefiniować deterministycznego właściciela oczekującej pozycji sekwencji,
- zablokować tworzenie drugiej aktywnej pozycji review dla tej samej gry i
  jednoznacznego numeru,
- przy ponownym imporcie pominąć lub oznaczyć alternatywne źródło bez
  materializowania drugiej kolejki,
- dodać migrację, testy współbieżności oraz raport naprawczy istniejących
  duplikatów.

## Out of scope

- wyszukiwanie plansz i ranking częściowego wzoru (TASK-0292),
- automatyczna zamiana zaakceptowanego kanonicznego źródła,
- usuwanie historycznych importów lub obrazów bez jawnej akcji właściciela.

## Acceptance criteria

- [ ] Dla `game_id + sequence_number` istnieje co najwyżej jedna aktywna
  logiczna pozycja oczekująca.
- [ ] Równoległe retry nie tworzy dwóch pozycji oczekujących.
- [ ] Akceptacja lub korekta nadal korzysta z istniejącego kanonicznego rejestru.
- [ ] Historyczne alternatywy pozostają audytowalne i nie są usuwane automatycznie.

## Outcome

### Changed

- Nie rozpoczęto.

### Verification results

- Nie dotyczy.

### Not completed

- Całość zadania oczekuje na osobny pion implementacyjny.

### Documentation updates

- Utworzono jako niezależny blocker dla TASK-0292.

### Recommended next task

- TASK-0292.
