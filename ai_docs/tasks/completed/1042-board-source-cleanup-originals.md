# TASK-1042 — Czyszczenie zakresów źródeł usuwa oryginały naprawdę i bezpiecznie

## Status

`done`

## Goal

`deleteBoardSourceRanges` usuwa (przez kwarantannę) pliki, które faktycznie
istnieją, raportuje prawdziwe liczby i nigdy nie usuwa oryginału, do którego
odwołuje się zachowany rekord albo niezakończony job.

## Context

2026-10-17 operator usunął 214 zdjęć importu `c2b7d87a` (gra 777a2) przez
`DELETE /api/v1/admin/games/{gameId}/board-sources`. Wynik zgłosił 214
usuniętych plików (`managed_artifacts`, `deletedArtifactCount`), ale wszystkie
214 oryginałów nadal leżą w `artifacts/data/originals/...`.

Przyczyna: `SqlAlchemyCleanupRepository._board_source_artifact_paths` bierze
`source_images.relative_path` (`originals/ab/<sha>.jpg`, względem
`artifacts/data`; worker zapisuje je przez `_data_relative_path`), a
`ManagedCleanupArtifactStore` rozwiązuje ścieżki względem `artifact_root`
(`artifacts`). `quarantine()` pomija nieistniejące ścieżki bez błędu.
Na bazie operatora ścieżki są mieszane: `originals/...`, `training/...`,
`models/<gra>/...` leżą pod `artifacts/data`, a `data/symbol-references/...`,
`data/models/...` i `models/lab-symbol-candidates/...` są względne do
`artifacts`.

## Dependencies / entry conditions

- Fakt: `main` bebc3851 (v1.7.398).
- Zlecenie operatora w sesji (2026-10-17), task poza planem.
- Brak migracji i zmiany schematu API (liczniki to lista nazw).

## Recommended execution

Claude Opus 5.5, reasoning high. Bez audytu krzyżowego (task poza planem,
audyty zawieszone przez operatora).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- [D-543](../../process/decisions/DECISION_LOG_2026.md#d-543--odrzucanie-przyciętych-plansz-po-imporcie-i-przejęcie-sekwencji-przez-zdjęcie-zastępcze)

## Scope

- `ManagedCleanupArtifactStore.resolve`: każda zapisana ścieżka jest
  rozwiązywana do postaci względnej wobec `artifacts`. Ścieżka z prefiksem
  `data/` zostaje bez zmian; pozostałe mają kandydatów `<p>` i `data/<p>`.
  Istnieje dokładnie jeden → ten; żaden → brakujący (nie liczony jako usunięty);
  oba → blokada `CLEANUP_ARTIFACT_PATH_AMBIGUOUS`.
- `CleanupService` dla `board_source_ranges` używa rozwiązanych ścieżek w
  podglądzie i wykonaniu: `managed_artifacts` = pliki istniejące, nowy licznik
  `missing_artifacts`, token podglądu obejmuje rozwiązany stan.
- Repozytorium zachowuje oryginał (`retained_shared_artifact_count`, ostrzeżenie
  `SOURCE_ORIGINALS_RETAINED`), gdy:
  - odwołuje się do niego zachowany `source_images` albo
    `image_board_geometry_revisions` dowolnej gry, albo
  - job importu źródła jest niezakończony (`created`, `processing`,
    `waiting_for_review`) albo jest `managed_source_job_id` niezakończonego joba
    (wznowienie weryfikuje cały manifest oryginałów).

## Out of scope

- `reset_game` i usuwanie wydań: nie zmieniam (`reset_game` ma osobny defekt:
  pliki przed bazą; poprawne ścieżki pogłębiłyby szkodę).
- Usuwanie osieroconych oryginałów bez wierszy w bazie (214 + 1962 zdjęć
  `60a7bc4d`): tylko opis dla operatora; wykonanie za osobną zgodą.

## Acceptance criteria

- [x] Test odtwarza defekt: oryginał `originals/..` pod `data/` trafia do
      kwarantanny i znika po finalizacji.
- [x] Brakujące pliki nie są raportowane jako usunięte; niejednoznaczne blokują.
- [x] Oryginał współdzielony albo używany przez niezakończony job zostaje.
- [x] Testy domenowe, integracyjne (izolowana baza `*_test`), ruff, mypy.

## Technical notes

- Rozwiązanie po istnieniu jest deterministyczne dla stanu dysku; zmiana
  dysku między podglądem a wykonaniem zmienia token (`CLEANUP_PREVIEW_STALE`).
- Kwarantanna i odtwarzanie dalej działają na ścieżkach względnych wobec
  `artifacts`, więc paragon i recovery się nie zmieniają.

## Expected files

- `services/api/src/game_predictor_api/application/cleanup.py`
- `services/api/src/game_predictor_api/storage/cleanup_repository.py`
- `services/api/tests/test_cleanup_domain.py`
- `services/api/tests/integration/test_cleanup_repository.py`
- `ai_docs/architecture/API_CONTRACT.md`

## Test cases

- `resolve`: `originals/..` pod `data/`, `models/lab..` w korzeniu, `data/..`,
  brak, oba → odpowiednio data, korzeń, bez zmian, brak, blokada.
- Serwis z prawdziwym magazynem: plik pod `data/originals` znika po
  finalizacji; brakujący nie jest liczony.
- Postgres: oryginał źródła z jobem `waiting_for_review` zostaje; po
  zakończeniu joba drugi cleanup go usuwa; ścieżka współdzielona z innym
  źródłem zostaje.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_cleanup_domain.py services/api/tests/test_cleanup_api.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_cleanup_repository.py -q
```

## Risks / open questions

- Job `c2b7d87a` (`waiting_for_review`) przy ponowieniu prawdopodobnie przetworzy
  ponownie usunięte 214 zdjęć, bo jego manifest nadal je wiąże. Zalecenie: anulować go
  za zgodą operatora zamiast ponawiać.

## Outcome

Commit: v1.7.399 / `6253c29635f0add53d91cd9a27183e40a0aa40f7`.

Wykonawca: Claude Opus 5.5 (sesja operatora). Bez audytu krzyżowego (task poza
planem; audyty zawieszone przez operatora).

### Changed

- `application/cleanup.py`: `ResolvedCleanupArtifacts`,
  `ManagedCleanupArtifactStore.resolve` (ścieżka `data/...` bez zmian; inna →
  `p` albo `data/p`, jedna istniejąca, brak = brakująca, dwie = niejednoznaczna),
  `CleanupService._board_source_snapshot` dla podglądu i wykonania
  `board_source_ranges`: `artifactPaths` tylko istniejące pliki,
  `managed_artifacts` = ich liczba, nowy licznik `missing_artifacts`, blokada
  `CLEANUP_ARTIFACT_PATH_AMBIGUOUS`. Reset gry i wydania bez zmian.
- `storage/cleanup_repository.py`: `_retained_source_paths` i `_cross_game_paths`
  zachowują oryginał współdzielony z innym `source_images` albo
  `image_board_geometry_revisions` dowolnej gry oraz oryginały źródeł
  niezakończonego joba importu (lub joba z `managed_source_job_id`);
  `retained_shared_artifact_count` i ostrzeżenie `SOURCE_ORIGINALS_RETAINED`.
- Testy: 4 nowe domenowe (rozwiązywanie, usunięcie oryginału pod `data/`,
  niejednoznaczność, nieaktualny podgląd), nowy test Postgres (zachowanie przy
  jobie `waiting_for_review` i współdzieleniu, usunięcie po ostatnim odwołaniu),
  fałszywe magazyny w `test_grid_reinference_postgres.py` i
  `test_super_game_series_postgres.py` dostały `resolve`.

### Verification results

- `test_cleanup_domain.py`, `test_cleanup_api.py`, `test_grid_shadow_retention.py`,
  `test_super_game_input_version.py` oraz `integration/test_cleanup_repository.py`
  (izolowana baza `game_predictor_cleanup_test`): 39 passed.
- Szerszy zestaw Postgres (`test_grid_cohort_retention_edges_postgres.py`,
  `test_grid_reinference_postgres.py`, `test_super_game_series_postgres.py`):
  na gałęzi i na `main` identycznie 3 failed, 1 error, 30 passed — wszystkie
  istniejące wcześniej (brak zmiennej `GAME_PREDICTOR_GC_RETENTION_EVIDENCE_ROOT`,
  znany defekt `reset_game` RestrictViolation `[cleanup_reset]`, brakujący
  fixture w `test_worker_queue_skips_locked_row_without_created_deadlock`).
- `ruff check`, `ruff format`, `mypy --strict` na zmienionych modułach: PASS.
- Testy Postgres biegły na serwerze operatora tylko w bazach `*_test`.

### Not completed

- Osierocone oryginały bez wierszy w bazie (214 po cleanupie z 2026-10-17 i
  1962 zdjęcia `60a7bc4d`, razem ~0,48 GB w `artifacts/data/originals`) nadal
  leżą na dysku: naprawiony cleanup ich nie widzi, bo nie mają już źródeł.
  Usunięcie wymaga osobnego narzędzia albo jednorazowej operacji z podglądem i
  zgodą operatora, po zamknięciu joba `c2b7d87a`.
- Nie sprawdzono w działającym API (usługi operatora; API z `--reload` wczyta
  zmianę po scaleniu).

### Documentation updates

- `ai_docs/architecture/API_CONTRACT.md` (sekcja usuwania źródeł plansz), mapa
  kodu.

### Recommended next task

- Anulowanie joba `c2b7d87a` za zgodą operatora, potem jednorazowe usunięcie
  osieroconych oryginałów stagingu `60a7bc4d` z podglądem.
