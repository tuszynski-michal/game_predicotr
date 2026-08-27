---
title: TASK-0291 — Jedna oczekująca plansza dla numeru sekwencji
status: done
last_updated: 2026-08-27
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

- [x] Dla `game_id + sequence_number` istnieje co najwyżej jedna aktywna
  logiczna pozycja oczekująca.
- [x] Równoległe retry nie tworzy dwóch pozycji oczekujących.
- [x] Akceptacja lub korekta nadal korzysta z istniejącego kanonicznego rejestru.
- [x] Historyczne alternatywy pozostają audytowalne i nie są usuwane automatycznie.

## Outcome

### Changed

- Dodano wspólną politykę właściciela pending używaną przez pipeline workera i
  ręczne materializowanie odroczonej geometrii.
- Najnowszy import zastępuje starsze unresolved, natomiast canonical
  `accepted/corrected` pozostaje chroniony.
- Migracja `0069` dodała trwałe kolumny zakresu, triggery synchronizacji,
  częściowy indeks unikalny oraz naprawę istniejących duplikatów.
- Dropdown zatwierdzania ukrywa zakończone importy. Search fast-document i
  Weryfikacja symboli wskazują tego samego właściciela.

### Verification results

- Migracja realnej bazy zakończyła się na head `0069`; naprawiła `114 676`
  grup duplikatów i `159 754` nadmiarowe pending.
- Test migracji, test polityki newest-import-wins oraz istniejące testy obu
  ścieżek materializacji przeszły na izolowanym PostgreSQL.
- Testy stanu launchera Admina oraz Ruff dla zmienionych modułów przeszły.

### Not completed

- Nie usuwano historycznych importów ani plików. Pozostają audytowalne zgodnie
  z zakresem zadania.
- Niezależny błąd joba walidacji `JOB_PROGRESS_REGRESSION` nie należy do tego
  pionu i nie został ukryty przez zmianę.

### Documentation updates

- Zaktualizowano wymagania Admina, model danych, kontrakt API, Current State i
  Decision Log (D-238).

### Recommended next task

- Odbiór operatorski kolejnych nakładających się importów i osobna diagnoza
  `JOB_PROGRESS_REGRESSION`, jeżeli błąd walidacji zostanie ponowiony.
