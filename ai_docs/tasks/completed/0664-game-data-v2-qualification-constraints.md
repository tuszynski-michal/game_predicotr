---
title: game_data_v2 qualification constraints
status: in_progress
last_updated: 2026-09-25
---

# TASK-0664 — wyrównanie ograniczeń kwalifikacji `game_data_v2`

## Status

`in_progress`

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
- [ ] Komórki i zdarzenia review `game_data_v2` akceptują `partial_visibility`.
- [ ] Świeży reprocess nie ma błędów `ck_recognized_boards_qualification`.
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
- Dodano izolowany test PostgreSQL dla rodziców oraz nowych partycji.
- Diagnoza jednej transakcji zawsze wycofywanej wykazała dodatkowy v2-only
  kontrakt `image_symbol_review_cells`, odrzucający `partial_visibility`.

### Verification results

- Test izolowanej migracji PostgreSQL: 2/2 przeszły przed rozszerzeniem
  kontroli `partial_visibility`.
- Ruff dla migracji i testu: czysty.

### Not completed

- Zastosowanie migracji do lokalnej bazy i ponowienie joba są wykonywane
  następnie.

### Documentation updates

- Zadanie dokumentuje diagnozę oraz bezpieczny zakres naprawy.

### Recommended next task

- Nie dotyczy; po migracji kontynuować bieżący job.
