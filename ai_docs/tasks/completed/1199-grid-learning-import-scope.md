---
title: TASK-1199 — Domyślny zakres importów uczenia korekt
status: done
last_updated: 2026-11-12
---

# TASK-1199 — Domyślny zakres importów uczenia korekt

## Status

`done`

## Goal

Przycisk „Ulepsz siatki z korekt” dla Mumie A2 jest aktywny: domyślny odczyt
gotowości obejmuje tylko importy z ludzkimi korektami lub członkami kohort i
mieści się w limicie 5000 źródeł podziału.

## Context

Operator (2026-11-12): przycisk jest wyłączony, choć dodał ponad 100 siatek.
Panel nie wybiera importów, więc `GridCorrectionLearningService._split` brał
wszystkie importy gry. Po dwóch importach z 2026-11-12 Mumie A2
(`246a1f54-eee8-49d5-b11a-0fde70e5eecd`) ma 7039 źródeł w 6 importach, a
`population()` odrzuca więcej niż 5000 źródeł (`GRID_CORRECTION_POPULATION_LIMIT`).
Pomiar na danych operatora (tylko odczyt): 4 importy z etykietami (4538 źródeł)
dają `GRID_CORRECTION_PROTECTION_CONFLICT`, bo 49 i 75 źródeł bez plansz w
`ce7b2f19`/`6ac20272` dziedziczy atest po kopiach z `d7747436` (D-603); bez tego
importu kolejność staje się `indivisible-import-v1`. Pięć importów (etykiety lub
członkowie kohort, 4847 źródeł) daje `canStart=true`.

## Dependencies / entry conditions

`main` v1.7.624 (`3231f7b6`), baza operatora na `0186`. Bez migracji i bez zmiany
kontraktu API. Szkic `labelled_import_scope` i test PostgreSQL zastane
niezacommitowane w tym worktree (`claude/grid-learning-import-scope`); przejęte
przez ten task.

## Recommended execution

Claude Opus 5.5, reasoning standard — jedna funkcja zakresu i test; operator
zlecił naprawę bezpośrednio. Bez audytu krzyżowego (brak planu z kolumną
`Dodatkowy review`).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- [D-606](../../process/decisions/DECISION_LOG_2026.md#d-606--domyślny-zakres-uczenia-korekt-importy-z-etykietami-i-kohortami)
- [D-603](../../process/decisions/DECISION_LOG_2026.md#d-603--pozycja-kopii-bez-plansz-i-dłuższy-odczyt-podziału)
- `ai_docs/architecture/VISION_LAB.md`, „Photo-only correction split”

## Scope

- `labelled_import_scope(session, game)` w
  `services/api/src/game_predictor_api/application/grid_correction_learning.py`
  i jej użycie w `_split`, gdy polecenie nie podaje `importJobIds`.
- Test PostgreSQL zakresu, wpis D-606, zdanie w `VISION_LAB.md`.

## Out of scope

- Limity podziału (5000 źródeł, 100 importów, 120 s), wybór importów w UI.
- Jawne `importJobIds` (bez zmian), kontrakt API i OpenAPI.

## Acceptance criteria

- [x] Bez `importJobIds` zakres = importy z bieżącą ludzką akceptacją geometrii
  albo członkiem wcześniejszej kohorty; importy automatyczne, nieaktualne i puste
  są pomijane.
- [x] Mumie A2: zakres 5 importów, podgląd `canStart=true`.
- [x] Testy jednostkowe uczenia i test PostgreSQL przechodzą na kodzie worktree.

## Technical notes

Warunek akceptacji jest identyczny z kolumną `approved` w `population()`
(`approved_geometry_revision = geometry_revision`, aktor ≠ `system:%`/`worker:%`).
Członkowie kohort zachowują import z kopiami, po których źródła bez plansz
dziedziczą atest. Limit 101 zachowuje błąd `GRID_LEARNING_IMPORT_SCOPE_INVALID`
dla > 100 importów.

## Expected files

- `services/api/src/game_predictor_api/application/grid_correction_learning.py`
  — `labelled_import_scope`, `GridCorrectionLearningService._split`.
- Nowy: `services/api/tests/integration/test_grid_learning_import_scope_postgres.py`.
- `ai_docs/process/DECISION_LOG.md`, `decisions/DECISION_LOG_2026.md`,
  `decisions/DECISION_INDEX_ARCHIVE.md`, `ai_docs/architecture/VISION_LAB.md`.

## Test cases

- Import z ludzką akceptacją, import z członkiem kohorty, import z akceptacją
  `system:`/nieaktualną `worker:` i import bez akceptacji → zakres = dwa pierwsze.
- Regresja: istniejące testy API/przepływu/rekomendacji uczenia.

## Verification

```powershell
# z worktree; edytowalna instalacja .venv wskazuje na główny checkout, więc
# runner usuwa jej finder i wstawia ścieżki worktree przed importem
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe <runner> -q services/api/tests/integration/test_grid_learning_import_scope_postgres.py
```

## Outcome

Commit: v1.7.625 / `7203e1db78b75f140caa7745616d35053b2f46cc`.

- Wynik: zakres domyślny jak w D-606. Na danych operatora (odczyt)
  `labelled_import_scope` zwraca `6ac20272`, `bf601495`, `ce7b2f19`, `d7747436`,
  `fbca1ab5` (4847 źródeł; pomija `df5c22e1`, 2192 źródła bez etykiet i kohort).
  Podgląd API z tym zakresem: `canStart=true`, TRAIN 337/472, VALIDATION 16/57,
  REGRESSION 13/21 (zdjęcia/plansze), 165 nowych zdjęć TRAIN, ~2580 s.
- Weryfikacja: 78 testów jednostkowych uczenia (`test_grid_correction_learning_api`,
  `_workflow`, `_recommendation`, `test_screen_grid_correction_policy`,
  `test_grid_learning_candidate_status`, `test_grid_content_experiment_inputs`)
  PASS na kodzie worktree; test PostgreSQL PASS; ruff check/format PASS; mypy
  `--strict` zmienionego modułu PASS.
- Odstępstwa: podgląd trwa ~100 s przy budżecie 120 s (ryzyko przy wzroście
  danych, D-606, Konsekwencje). Żywe API działa z głównego checkoutu, więc
  przycisk zadziała po scaleniu do `main` (API z `--reload`). Uczenie
  `170f610d` dla Mumie A2 uruchomiono przez API z identycznym jawnym zakresem;
  worker `general` uruchomiony na polecenie operatora. Wersja v1.7.625
  koliduje numerem z gałęzią `claude/enter-saves-geometry`.
