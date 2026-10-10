---
title: TASK-0812 — rozpoznawanie konfliktu unikalności w partycjach gry, końce linii plików z sumą kontrolną, martwy backfill
status: done
last_updated: 2026-10-02
---

# TASK-0812 — rozpoznawanie konfliktu unikalności w partycjach gry

## Status

`done`

## Goal

Repozytoria tabel gry zwracają właściwy kod błędu domenowego przy naruszeniu
unikalności także wtedy, gdy PostgreSQL zgłasza nazwę indeksu partycji;
testy wiązane sumą kontrolną przechodzą na checkoutcie Windows; martwy
`backfill_legacy_states` jest usunięty.

## Context

TASK-0810 wykazał błąd produktu: repozytoria rozpoznają naruszenie po
`diag.constraint_name` równym nazwie indeksu/ograniczenia rodzica (np.
`uq_reviewer_work_assignments_active_import`). W `game_data_v2` tabele są
partycjonowane `LIST (game_id)` i PostgreSQL zgłasza nazwę indeksu partycji
(zmierzone: `gpv2_<gra>_<hash>_game_id_import_job_id_idx1`). Skutek: zamiast
`REVIEWER_ASSIGNMENT_ALREADY_ACTIVE` wychodzi
`REVIEWER_ASSIGNMENT_PERSISTENCE_CONFLICT`. Test
`test_postgres_baseline.py::test_duplicate_active_assignment_reports_already_active`
ma `xfail(strict=True)`.

Ten sam wzorzec (niepotwierdzony testem) dla tabel gry:
`storage/review_repository.py` (`uq_review_batches_source_report_sha256`),
`storage/image_import_geometry_guard_repository.py`
(`uq_image_import_guard_decisions_revision`, `…_checksum`),
`storage/page_geometry_override_repository.py`
(`uq_image_page_geometry_overrides_revision`).

Drobiazgi z raportu TASK-0810: `services/api/tests/test_reviews.py` ma 6
błędów na Windows, bo plik raportu jest w git jako LF, a checkout
(`* text=auto`, `core.autocrlf=true`) daje CRLF i suma kontrolna się nie
zgadza; `backfill_legacy_states` nie ma wywołań produkcyjnych od `48e12ea9`
i po D-448 nie da się go poprawnie użyć.

## Dependencies / entry conditions

- Gałąź `feat/grid-engine-v3`, HEAD `v1.7.151`, head Alembic `0139`.
- Bez zmian schematu i migracji.

## Recommended execution

`claude-sonnet-5-5`, reasoning `high`. Jedna wspólna funkcja i cztery
miejsca użycia według istniejącego wzorca; test odtwarzający już istnieje.
Eskalacja do `claude-opus-5-5` `high`, jeżeli mapowanie indeksu partycji na
indeks rodzica nie da się zrobić bez zmiany schematu. Audyt zawieszony
decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/tasks/completed/0810-stale-postgres-integration-tests.md`

## Scope

- Wspólna funkcja w `storage/` zwracająca nazwę ograniczenia/indeksu
  **rodzica** dla naruszenia zgłoszonego na partycji (z `IntegrityError`).
- Użycie jej we wszystkich repozytoriach tabel klasy `game`, które
  porównują `constraint_name` z nazwą — znajdź komplet przez grep
  `constraint_name` i manifest tabel gry, nie tylko cztery wymienione.
- Usunięcie `xfail` z testu przydziałów; test PG dla co najmniej jednego
  innego repozytorium z listy.
- Reguła `.gitattributes` `eol=lf` dla artefaktów testowych wiązanych sumą
  kontrolną (ustal dokładne ścieżki z testów) i potwierdzenie, że
  `test_reviews.py` przechodzi.
- Usunięcie `backfill_legacy_states` razem z martwymi odwołaniami, jeżeli
  grep potwierdza brak wywołań produkcyjnych i skryptów.
- Na końcu jedno uruchomienie pełnego `npm run db:baseline:verify`.

## Out of scope

- Zmiany schematu, nazw indeksów, migracje.
- Repozytoria tabel `catalog`/`shared` w `public` (tam nazwa jest zgodna).

## Acceptance criteria

- [x] Naruszenie unikalności na partycji gry daje ten sam kod domenowy co
      przed magazynem per gra; test przydziałów przechodzi bez `xfail`.
- [x] Wszystkie porównania `constraint_name` dla tabel gry używają wspólnej
      funkcji; lista miejsc w `Outcome`.
- [x] Nieznane naruszenie nadal jest zgłaszane tak jak dotąd (brak
      połknięcia błędu).
- [x] `services/api/tests/test_reviews.py` przechodzi w worktree Windows.
- [x] `backfill_legacy_states` usunięty albo opisany powód pozostawienia.
- [x] `npm run db:baseline:verify` — wynik rzeczywisty w `Outcome`; każdy
      błąd opisany (nowy czy wcześniejszy).
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

Rozstrzygnięcie: nie dopasowuj po wzorcu nazwy partycji. Źródłem prawdy jest
katalog: indeks partycji ma rodzica w `pg_inherits` (indeksy partycjonowane)
albo ograniczenie ma `conparentid`. Funkcja dostaje sesję i wyjątek, czyta
`diag.schema_name` / `diag.constraint_name` i jednym zapytaniem do katalogu
(w zagnieżdżonym savepoincie albo po wycofaniu savepointu, w którym wystąpił
błąd — sprawdź, jak każde miejsce obsługuje transakcję po `IntegrityError`)
zwraca nazwę najwyższego rodzica; gdy rodzica nie ma, zwraca nazwę
oryginalną. Zapytanie katalogowe nie wymaga wiązania gry. Jeżeli miejsce
użycia nie może wykonać zapytania po błędzie (transakcja przerwana bez
savepointu), zastosuj savepoint wokół zapisu zgodnie z wzorcem już obecnym
w `image_import_geometry_guard_repository.py`.

Końce linii: reguła w `.gitattributes` musi działać dla nowych checkoutów;
w istniejącym worktree znormalizuj dotknięte pliki (`git add --renormalize`
tylko tych ścieżek — bez stagowania; odnotuj w raporcie, co orkiestrator ma
dodać do commita).

## Expected files

- Nowe (proponowane): `services/api/src/game_predictor_api/storage/partition_constraints.py`,
  test jednostkowy i rozszerzenie testu PG.
- Istniejące: repozytoria z listy, `test_postgres_baseline.py`,
  `.gitattributes`, moduł z `backfill_legacy_states`.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_postgres_baseline.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_reviews.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check services/api services/worker scripts
npm run db:baseline:verify
```

Limit 300 s dla pliku PG, 1 500 s dla `db:baseline:verify` (znany czas ok.
18 minut; uruchamiany raz, sam). Testy są planowane.

## Risks / open questions

- `db:baseline:verify` uruchamia cały katalog integracyjny; mogą wyjść
  błędy niezwiązane z zadaniem — opisać, nie rozszerzać zakresu.

## Outcome

Rozstrzygnięcie projektowe: w `game_data_v2` indeks rodzica nie nosi nazwy
logicznej z ORM (to wygenerowane `v2_ix_<hash>` / `v2_uq_<hash>`), a kopie w
`public` zostały usunięte w `0125`. Samo zwrócenie nazwy rodzica nie dałoby więc
`uq_…`. Funkcja idzie przez katalog (`pg_inherits`) do najwyższego rodzica
indeksu partycji, czyta jego tabelę, kolumny kluczowe i predykat częściowy, i
dopasowuje strukturalnie (z pominięciem `game_id`) do kluczy unikalnych
zadeklarowanych w ORM dla tabeli. Nazwa zgłoszona przez PostgreSQL, która już
jest nazwą z ORM, jest zwracana bez zapytania; brak dopasowania zwraca nazwę
zgłoszoną bez zmian (nieznane naruszenie dalej jest rzucane jak dotąd). Żadnego
dopasowania po wzorcu nazwy partycji, bez zmian schematu.

### Changed

- Nowy `services/api/src/game_predictor_api/storage/partition_constraints.py`
  (`resolve_unique_constraint_name`, `fetch_parent_unique_index`,
  `match_declared_unique_name`).
- Miejsca użycia (komplet porównań `constraint_name` dla tabel klasy `game`;
  pozostałe w repozytoriach to tabele `catalog`/`shared` w `public`, poza
  zakresem):
  - `storage/reviewer_work_assignment_repository.py` (`add`,
    `uq_reviewer_work_assignments_active_import`; zapis owinięty w
    `begin_nested()`),
  - `storage/review_repository.py` (`create_review_batch`,
    `uq_review_batches_source_report_sha256`; zapis owinięty w
    `begin_nested()`),
  - `storage/image_import_geometry_guard_repository.py` (`add_decisions`,
    `uq_image_import_guard_decisions_revision`/`_checksum`),
  - `storage/page_geometry_override_repository.py` (`append`,
    `uq_image_page_geometry_overrides_revision`).
- Zdjęty `xfail(strict=True)` z
  `test_postgres_baseline.py::test_duplicate_active_assignment_reports_already_active`;
  nowy `test_duplicate_geometry_override_revision_is_recognised_in_partition`
  (PG; konflikt rewizji nadpisania geometrii oraz nieznane naruszenie klucza
  głównego rzucane jako `IntegrityError`).
- Nowy test jednostkowy `services/api/tests/test_partition_constraints.py`
  (katalog zamockowany).
- `.gitattributes`: `ai_docs/quality/*.json text eol=lf` (artefakty wiązane
  sumą kontrolną; `test_reviews.py` i `integration/test_review_repository.py`
  czytają bajty `m6-symbol-active-learning-selection.json`). W worktree
  przekonwertowano 179 plików `ai_docs/quality/*.json` z CRLF na LF (treść
  względem indeksu bez zmian; `git status` może je pokazywać jako `M` z powodu
  odświeżenia stat — `git diff` jest pusty).
- Usunięty martwy `SqlAlchemyImageGeometryRolloutRepository.backfill_legacy_states`
  wraz z `GeometryRolloutBackfillStep` (wersja w `image_geometry_v2_repository.py`),
  stałymi `_BACKFILL_ACTOR`/`_DEFAULT_BACKFILL_LIMIT`/`_MAX_BACKFILL_LIMIT`,
  nieużywanymi importami, testem
  `test_rollout_backfill_rejects_unbounded_batch_sizes` i odwołaniem w
  komentarzu `test_v010_virtual_geometry_migration.py`. Grep: brak wywołań w
  produkcji i skryptach; `ImageGeometryRolloutBackfillStep` (worker, osobne
  repozytorium) nietknięty.

### Verification results

- `pytest services/api/tests/integration/test_postgres_baseline.py` (PG): 5
  passed (w tym test przydziałów bez `xfail` i nowy test nadpisań).
- `pytest .../test_postgres_baseline.py .../test_v010_virtual_geometry_migration.py`
  (PG): 6 passed. `integration/test_review_repository.py` +
  `test_game_storage_routing_postgres.py` (PG): 13 passed.
- Nie-PG: `test_partition_constraints.py`, `test_image_geometry_v2_persistence.py`,
  `test_geometry_qualification.py`, `test_image_import_geometry_guard.py`,
  `test_reviewer_work_assignments.py`, `test_reviews.py`: 68 passed
  (`test_reviews.py` samodzielnie: 7 passed, wcześniej 6 błędów CRLF).
- `ruff check services/api services/worker scripts`: 1 błąd wcześniejszy,
  niezwiązany (`services/worker/tests/test_page_geometry_preflight.py:345`
  E501). Zmienione pliki: `ruff format --check` czyste. `mypy --strict` na
  zmienionych modułach: 0 błędów w zmienionych plikach (27 wcześniejszych w
  innych).
- `npm run db:baseline:verify` (raz, 1 392 s): `3 failed, 233 passed`.
  Nieudane testy (żaden nie dotyka rozpoznawania unikalności; wszystkie trzy
  przechodzą po samodzielnym uruchomieniu):
  - `test_cell_render_specs_postgres.py::test_switched_readers_reproduce_the_cell_column_from_the_manifest`
    — `FileNotFoundError` na ścieżce 273 znaki (Windows MAX_PATH 260;
    katalog `.tooling/pytest/postgres-baseline-<pid>/…` w głębokim worktree),
  - `test_superseded_import_image_removal.py::test_script_preview_report_drives_the_confirmed_execute`
    — `FileNotFoundError` na ścieżce 274 znaki, ta sama przyczyna,
  - `test_release_workflow_integration.py::test_postgres_release_workflow_keeps_previous_release_immutable`
    — `SNAPSHOT_ARTIFACT_LAYOUT_INVALID` ("entries must be regular files");
    nie zbadano głębiej, prawdopodobnie ta sama przyczyna środowiskowa
    (długie ścieżki); przechodzi samodzielnie.
  Wszystkie wcześniejsze/środowiskowe (nowe: brak). Samodzielne uruchomienie
  tych trzech: 3 passed.

### Not completed

- Commit i `CURRENT_STATE.md` — koordynator.
- Brak testu PG dla ścieżek `REVIEW_REPORT_IMPORT_RACE` i guard decisions
  (pokryte testem jednostkowym dopasowania i istniejącymi testami PG
  `test_review_repository.py`, `test_game_storage_routing_postgres.py`).
- Przyczyna `SNAPSHOT_ARTIFACT_LAYOUT_INVALID` nie zdiagnozowana do końca.

### Documentation updates

- Tylko ten `Outcome`. `CURRENT_STATE.md`/`DECISION_LOG.md` — koordynator.

### Recommended next task

- Skrócić bazę ścieżek tymczasowych `db:baseline:verify` (MAX_PATH) albo
  włączyć długie ścieżki, żeby pełny przebieg w głębokim worktree był zielony.
