---
title: TASK-0760 — T1 — plan, decyzje i wymagania rozszerzenia „Przybliżonej wygranej” i udostępniania online
status: done
last_updated: 2026-09-30
---

# TASK-0760 — T1 — plan, decyzje i wymagania

## Status

`done`

## Goal

Plan `BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`, decyzje D-470 i D-471,
wymagania Admina i pliki zadań TASK-0761–0770 są zapisane w `ai_docs/`.

## Context

Operator zgłosił 2026-09-30 pięć zmian w „Wyszukaj plansze” →
„Przybliżona wygrana”: modal planszy z liniami wypłat, siatkę wykresu,
przypinane punkty, przeliczanie na złote i stawki oraz udostępnianie sekcji
online. Plan przygotowano bez pytań do operatora; operator go zaakceptował,
potwierdził liniowość wypłat względem stawki i regułę liczenia linii od
lewej krawędzi, a następnie polecił zapis planu i wykonanie etapu A.

## Dependencies / entry conditions

- Gałąź bazowa `v1.1-vision-lab-hybrid-geometry` na `v1.7.81` / `f3340b3b`.
- Równoległy tor biblioteki symboli używa TASK-0740–0750 i D-466.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz T1 w tabeli planu). Audyt:
niezależny agent `claude-opus-5-5`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`

## Scope

- Zapis planu w `ai_docs/delivery/`.
- D-470 (stawka i złote, linie od lewej krawędzi) i D-471 (udostępnianie
  online) w `DECISION_LOG.md`.
- `ADMIN_APP.md`: kolumna akcji, siatka i przypinanie punktów, stawka i
  jednostka, modal linii, nowa sekcja „Udostępnianie wyszukiwania online”.
- Pliki zadań TASK-0761–0770, indeks `ai_docs/README.md`, `CURRENT_STATE.md`.

## Out of scope

- Kod.

## Acceptance criteria

- [x] Dokumenty opisują R1–R4 planu bez sprzeczności z D-446 i D-462.
- [x] Numery decyzji i zadań potwierdzone z repozytorium i worktree.
- [x] Każdy task etapu A ma pełny plik według `TASK_TEMPLATE.md`.

## Outcome

### Changed

- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md` (nowy).
- `ai_docs/process/DECISION_LOG.md`: D-470, D-471.
- `ai_docs/requirements/ADMIN_APP.md`: sekcja „Przybliżona wygrana” i nowa
  sekcja „Udostępnianie wyszukiwania online”.
- `ai_docs/tasks/0761–0770-*.md` (nowe), `ai_docs/README.md`,
  `ai_docs/process/CURRENT_STATE.md`.

### Verification results

- Przegląd dokumentów; `git diff --cached --check` PASS.
- Audyt niezależnego agenta `claude-opus-5-5` (poziom rozumowania agenta
  nieustawialny z sesji), trzy cykle przeglądu:
  1. FAIL — 6 × P2: kolizja dziedziny osi Y z podziałkami, niewykonalny brak
     nakładania etykiet, ryzyko obrazu w cache `immutable` z inną geometrią,
     brak stanów błędów modala, cache wyniku online sprzeczny z D-446,
     pusty odnośnik w Outcome; kilkanaście P3.
  2. FAIL — 1 × P2: odbiór planszy przyciętej z lewej przez modal jest
     niewykonalny (brak wiersza przy wypłacie 0); P3: uzasadnienie układu
     etykiet, lista błędów §4.1, testy T2, sformułowanie zaokrąglenia.
  3. PASS — brak uwag P0–P2 (drugi i ostatni dozwolony cykl poprawek).

### Not completed

- Nic w zakresie taska.

### Documentation updates

- Patrz „Changed”.

### Recommended next task

- TASK-0761 (siatka wykresu i przypinane punkty).
