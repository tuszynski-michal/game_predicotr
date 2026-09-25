---
title: game_data_v2 qualification constraints
status: done
last_updated: 2026-09-25
---

# TASK-0664 — wyrównanie ograniczeń kwalifikacji `game_data_v2`

## Status

`done`

## Goal

Usunąć globalną rozbieżność ograniczeń PostgreSQL, która odrzuca poprawne
kwalifikacje geometrii v2/v3 w partycjach `game_data_v2`.

## Context

Reprocess joba `f786fed3-9814-42ce-941f-9cb04cbe2c17` przeszedł naprawioną
bramkę geometrii, ale projekcja symboli została zatrzymana przez
`ck_recognized_boards_qualification` w partycji gry. Diagnoza wykazała, że
migracje 0111 i 0120 aktualizowały wyłącznie `public`, pozostawiając rodziców
i partycje `game_data_v2` z kontraktem v1.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`

## Scope

- Migracja Alembic aktualizująca oba rodzice `game_data_v2` do kontraktu v1/v2/v3.
- Migracja Alembic aktualizująca v2 kontrakt `partial_visibility` dla komórek
  i zdarzeń review.
- Test izolowanego PostgreSQL potwierdzający obecność pełnego kontraktu.
- Ponowienie wyłącznie nieudanych etapów joba po zastosowaniu migracji.

## Out of scope

- Usuwanie obrazów, zmiana historycznych jobów i osłabianie geometry gate.

## Acceptance criteria

- [x] Rodzice i istniejące partycje `game_data_v2` akceptują kwalifikacje v1/v2/v3.
- [x] Komórki i zdarzenia review `game_data_v2` akceptują `partial_visibility`.
- [x] Świeży reprocess nie ma błędów `ck_recognized_boards_qualification`.
- [x] Zdjęcia źródłowe pozostają niezmienione.

## Technical notes

Migracja zastępuje CHECK wyłącznie na partycjonowanych rodzicach. PostgreSQL
propaguje kontrakt do istniejących i przyszłych partycji; nie wykonujemy
nieśledzonego DDL per gra. Nowe CHECK są `NOT VALID`, by nie blokować migracji
przez historyczne rekordy, lecz walidują wszystkie nowe zapisy.

## Expected files

- Nowy: `services/api/alembic/versions/0123_game_data_v2_qualification_constraints.py`
- Nowy: `services/api/tests/integration/test_game_data_v2_qualification_migration.py`
- `ai_docs/process/CURRENT_STATE.md`

## Test cases

- Świeża baza po `alembic upgrade head` ma oba CHECK `game_data_v2` z v1/v2/v3.
- Ponowienie błędnych plików joba po migracji kończy etap symboli bez naruszenia CHECK.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_game_data_v2_qualification_migration.py
```

## Risks / open questions

- Downgrade jest celowo blokowany: po migracji mogą już istnieć wiersze v2/v3.

## Outcome

### Changed

- Dodano migrację 0123 aktualizującą oba CHECK na partycjonowanych rodzicach
  `game_data_v2` do wspólnego kontraktu kwalifikacji v1/v2/v3.
- Dodano migrację 0124 aktualizującą v2-only kontrakt komórek i zdarzeń
  review o `geometry_partial` i `partial_visibility`.
- Dodano izolowany test PostgreSQL rodziców i nowych partycji dla obu kontraktów.
- Lokalna baza jest na 0124; sprawdzenie projekcji w transakcji wycofywanej
  potwierdziło zapis bez naruszenia CHECK.
- Wznowiono wyłącznie 61 etapów `symbol_inference` joba
  `f786fed3-9814-42ce-941f-9cb04cbe2c17`.

### Verification results

- Test izolowanej migracji PostgreSQL: 4/4 przeszły.
- Ruff dla migracji i testu: czysty.
- Końcowy job: 70/70 `waiting_for_review`, 0 `failed`; geometry gate nie
  zwrócił `IMAGE_GEOMETRY_SYSTEMIC_REGRESSION`.

### Not completed

- Ręczne zatwierdzenie 70 pozycji review nie należy do automatycznego importu.

### Documentation updates

- `CURRENT_STATE.md` opisuje obie trwałe migracje oraz końcowy wynik joba.

### Recommended next task

- Wykonać ręczny review symboli w Adminie, jeżeli użytkownik zleci odbiór.
