---
title: Plan usunięcia wyszukiwania wielu układów
status: done
last_updated: 2026-10-30
---

# TASK-1112 — Plan usunięcia wyszukiwania wielu układów

## Status

`done`

## Goal

Przygotować konkretny plan powrotu do jednej planszy, zachowujący sąsiednie
zdjęcia i dane, bez implementacji po zmianie polecenia przez użytkownika.

## Context

Po ograniczonej diagnozie i ocenie kosztu użytkownik potwierdził kierunek
usunięcia, następnie polecił wyłącznie napisać plan. Do tego momentu nie
powstały zmiany aplikacji. Plan zastępuje zamiar bieżącej implementacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- [D-573](../../process/decisions/DECISION_LOG_2026.md#d-573--wyszukiwanie-po-kolejnych-układach)
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/CODE_MAP.md`, `ai_docs/architecture/CODE_MAP_SYMBOLS.md`
- `ai_docs/DOC_INDEX.md`
- `.agents/skills/task-close/SKILL.md`

## Scope

Ograniczony odczyt kodu, plan `proposed`, karta TASK-1114, indeks dokumentów,
CURRENT_STATE, kontrola dokumentacji i zamknięcie taska planistycznego.

## Out of scope

Implementacja, audyty i delegacja, szerokie testy, benchmarki, operacje na
danych i usługach, migracje, merge i push.

## Acceptance criteria

- [x] Wskazano konkretną ścieżkę pojedynczego GET i wielowzorowego POST/SQL.
- [x] Usunięcie obejmuje przycisk, stan, backend, klienta i automatyczne replay.
- [x] Zachowano nawigację ±15, dane, historię i migrację 0169.
- [x] Plan ma jeden task, macierz testów, koszt i końcowe przypisanie modelu.
- [x] Dokumentacja przechodzi kontrole; zamknięcie skryptem i zapis wersji obejmuje commit tego taska.

## Outcome

Commit: v1.7.506 / `6ec12eab34254c2b5613fa889b40c07fa916927d`.

### Changed

- Plan `BOARD_SEARCH_SINGLE_BOARD_REMOVAL_PLAN_20261030.md`, status `proposed`.
- TASK-1114 czeka na akceptację zakresu i szacunku 1–2 godzin. Nie rozpoczęto
  implementacji. Brak osobnego audytu: plan go nie wymaga.
- Bez zmian kodu, danych, usług lub aktywnych kontraktów. D-573 pozostaje
  obowiązującym opisem wdrożonej funkcji do zatwierdzenia i wykonania zmiany.

### Verification results

- Sprawdzono ścieżki/symbole, istniejące testy i skrypty repozytorium.
- Początkowy worktree był czysty. Numery 1112/1113 wolne w lokalnych gałęziach.
- PASS: `check_decision_links.py`, `check_current_state_window.py`,
  `check_startup_read_budget.py`, `check_skill_mirrors.py` — wszystkie cztery
  kontrole z `npm run docs:check` uruchomione bezpośrednio systemowym Pythonem
  z timeoutem 120 s na skrypt, ponieważ worktree nie ma lokalnej `.venv`.
- Pierwsza kontrola budżetu wskazała przekroczenie o 223 B po dodaniu opisu.
  Skrócono wyłącznie nowy wpis; ponowna kontrola PASS, 11/11 budżetów.
- `git diff --check`: PASS. Kontrola planu względem PLAN_STANDARD: wszystkie
  wymagania pokryte przez TASK-1114 i macierz odbioru, brak delegacji.

### Not completed

- TASK-1114, testy aplikacji, odbiór urządzenia i wdrożenie nie należą do
  bieżącego polecenia przygotowania planu.

### Documentation updates

- Plan, karta wykonawcza, DOC_INDEX i CURRENT_STATE; bez zmiany zaakceptowanych
  wymagań, architektury i decyzji opisujących obecną aplikację.

### Recommended next task

Po akceptacji planu i kosztu wykonać TASK-1114. Merge/push i restarty pozostają
osobnymi decyzjami użytkownika.
