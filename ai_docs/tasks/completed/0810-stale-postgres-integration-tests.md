---
title: TASK-0810 — porządek w 19 nieprzechodzących testach integracyjnych PostgreSQL
status: done
last_updated: 2026-10-02
---

# TASK-0810 — porządek w 19 nieprzechodzących testach integracyjnych PostgreSQL

## Status

`done`

## Goal

Każdy z 19 testów integracyjnych PostgreSQL, które nie przechodzą na
`v1.7.149`, ma ustaloną przyczynę i jest albo dostosowany do obowiązującego
kontraktu, albo usunięty jako test nieistniejącego już zachowania, albo
zgłoszony jako rzeczywisty błąd produktu — tak, aby siedem plików testów
przechodziło w całości.

## Context

Polecenie operatora z 2026-10-02 („najpierw porządek”). Pełny
`npm run db:baseline:verify` był czerwony już przed etapem V3-0. Stan na
`v1.7.149` (uruchomienie plik po pliku, 2026-10-02):

| Plik (`services/api/tests/integration/`) | Błędy | Objaw |
|---|---|---|
| `test_board_import_coverage_migration.py` | 4 | porównanie definicji indeksów; `downgrade` zatrzymuje `0136` (`CELL_RENDER_SPEC_DROP_IRREVERSIBLE`) |
| `test_board_import_coverage_repository.py` | 8 | `relation "image_import_job_files" does not exist`; `The game storage registry row is invalid` |
| `test_postgres_baseline.py` | 3 | sztywny head `0065_remove_symbol_bootstrap`; `relation "reviewer_access_sessions" does not exist` |
| `test_layout_import_report_repository.py` | 1 | kod `LAYOUT_IMPOR…OUNT_MISMATCH` zamiast `…R_PUBLICATION` |
| `test_m2_admin_acceptance.py` | 1 | `mobileCode`: `Extra inputs are not permitted` |
| `test_review_repository.py` | 1 | `The selection report checksum does not match its canonical payload` |
| `test_v010_virtual_geometry_migration.py` | 1 | `ck_image_geometry_rollout_states_geometry_mode` |

Hipoteza (nie diagnoza): testy powstały przed magazynem `game_data_v2`
(tabele gry poza `public`, wymagane wiązanie gry), przed nieodwracalnymi
migracjami `0134`–`0136` i przed zmianami kontraktów; nie były aktualizowane.

## Dependencies / entry conditions

- Gałąź `feat/grid-engine-v3`, HEAD `v1.7.149`, head Alembic `0139`.
- Zadanie nie zmienia schematu ani danych; baza deweloperska nie jest
  dotykana.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Każdy test wymaga rozstrzygnięcia, czy
nieaktualny jest test, czy kod; pomyłka oznacza ukrycie prawdziwego błędu.
Audyt zawieszony decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md` (sekcja „Testy, benchmarki i regresje”)
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/process/DECISION_LOG.md` — tylko wpisy, które zmieniły dany
  kontrakt (szukaj po nazwie pola, kodu błędu albo migracji; m.in. D-437,
  D-467)
- `ai_docs/quality/TEST_STRATEGY.md`

## Scope

- Diagnoza każdego z 19 testów: commit albo decyzja, która zmieniła
  zachowanie (`git log -S`, `git blame`, DECISION_LOG).
- Dostosowanie testu do obowiązującego kontraktu z zachowaniem jego
  intencji; usunięcie tylko wtedy, gdy testowane zachowanie zostało
  świadomie usunięte z produktu i inny test pokrywa następcę (wskaż który).
- Zgłoszenie (bez naprawy), gdy przyczyną jest błąd kodu produkcyjnego
  niewynikający z udokumentowanej zmiany — chyba że poprawka jest mała,
  oczywista i lokalna; wtedy napraw i opisz.

## Out of scope

- Zmiany schematu, migracje, przywracanie odwracalności `0134`–`0136`.
- Refaktor infrastruktury testów poza potrzebą tych plików.
- Pozostałe pliki testów.

## Acceptance criteria

- [x] Tabela w `Outcome`: test → przyczyna (commit/decyzja) → rozstrzygnięcie
      (dostosowany / usunięty z uzasadnieniem i wskazaniem testu-następcy /
      błąd produktu).
- [x] Siedem plików przechodzi w całości (każdy uruchomiony osobno).
- [x] Żadna asercja nie została osłabiona bez wskazania zmiany kontraktu,
      która to uzasadnia.
- [x] `ruff check` czysty dla zmienionych plików.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

- Testy tabel gry muszą tworzyć grę i jej partycje istniejącym lifecycle
  oraz wiązać sesję (`GameStorageRouter.bind` / `game_storage_scope`);
  wzorce: `test_image_geometry_completeness_repository.py`,
  `test_per_game_isolation_new_game.py`.
- Testy cyklu `upgrade → downgrade → upgrade` historycznych migracji nie
  mogą już zejść poniżej `0136`/`0134` (świadomie nieodwracalne). Jeżeli
  test sprawdzał własność samej migracji (np. dokładne definicje indeksów
  `board_import_coverage`), zachowaj tę asercję na stanie `head`, a cykl
  ogranicz do odwracalnego zakresu albo usuń z uzasadnieniem.
- `test_postgres_baseline.py` to test cyklu życia migracji uruchamiany przez
  `npm run db:baseline:verify` — sprawdź `scripts/verify_postgres_baseline.ps1`,
  co dokładnie wrapper uruchamia, i dopasuj oczekiwany head do źródła prawdy
  w kodzie (`storage/schema_readiness.py`) zamiast kolejnej sztywnej nazwy.

## Expected files

- Istniejące: siedem plików testów z tabeli; ewentualnie wspólne fixture w
  `services/api/tests/integration/`.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/<plik> -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check services/api
```

Każdy plik osobno, limit 300 s; jedna instancja pytest naraz (VM WSL 8 GB).

## Risks / open questions

- Część testów może dotyczyć funkcji usuniętych razem z legacy V1 (D-467);
  wtedy właściwe jest usunięcie testu, nie jego przepisywanie.

## Outcome

Wykonane 2026-10-02 (implementer `claude-opus-5-5`). Wszystkie 19 testów
zdiagnozowane; 18 dostosowanych do obowiązującego kontraktu, w jednym
(`test_reviewer_work_assignments_enforce_one_active_row_and_keep_history`)
asercja kodu błędu przeniesiona do osobnego testu `xfail(strict=True)`, bo
ujawnia błąd produktu (niżej). Żaden test nie został usunięty. Kod
produkcyjny bez zmian. Commit, `CURRENT_STATE.md` i przeniesienie pliku
zadania należą do koordynatora.

#### Tabela test → przyczyna → rozstrzygnięcie

| Test | Przyczyna (commit / decyzja) | Rozstrzygnięcie |
|---|---|---|
| `test_board_import_coverage_migration.py::test_upgrade_builds_exact_canonical_indexes` | `0125_remove_legacy_public_game_store` (`ef326389`, D-448) usuwa `public.image_review_items` i `public.recognized_boards` razem z indeksami; test sprawdzał 4 indeksy na `head` | Dostosowany: fixture migruje do `0122`, test sprawdza dokładne definicje 4 indeksów na stanie migracji `0122`; nowy test `test_head_keeps_only_the_game_data_v2_indexes` sprawdza na `head` dokładnie 2 indeksy `game_data_v2` |
| `…::test_downgrade_removes_indexes_and_upgrade_restores_them` | `head → 0121` niemożliwe: downgrade `0123`/`0124` (`e4c49020`), `0125` (D-448), `0133`–`0136` (D-467) odmawia (`CELL_RENDER_SPEC_DROP_IRREVERSIBLE` z `0136`, `d641a1e2`) | Dostosowany: cykl `0122 → 0121 → 0122` (odwracalny zakres), asercje bez zmian |
| `…::test_retry_after_partial_run_reuses_committed_public_indexes` | jw. | Dostosowany: retry `0121 → 0122`, asercje bez zmian |
| `…::test_foreign_index_with_same_name_is_a_conflict` | jw. | Dostosowany: konflikt nazwy przy `0121 → 0122`, asercje bez zmian |
| `test_board_import_coverage_repository.py` — 8 testów (`test_pending_complete_board_without_canonical_is_added`, `test_partial_only_board_is_missing_with_reason`, `test_number_without_any_trace_is_no_source`, `test_gaps_at_start_middle_and_end`, `test_active_import_file_marks_in_progress_not_no_source`, `test_geometry_pending_resolution_creates_item_and_stays_added`, `test_duplicate_supersession_counts_distinct_and_totals_match_expected`, `test_numbers_above_expected_are_out_of_range_not_added`) | Fixture rejestrowały grę w `public` (generacja 1): router odrzuca generację < 2 od `dbd61085` (v0.10.442, „enforce v2-only game storage routing”, D-448), a tabele gry w `public` usunęła `0125` (`ef326389`) | Dostosowane: usunięty helper `_provision_public_storage_location`; każdy scenariusz używa istniejącego już w pliku `_provision_v2_storage_location` (wiersz rejestru v2 + partycje + `GameStorageRouter.bind`), dodana partycja `image_board_geometry_pending`; asercje bez zmian |
| `test_postgres_baseline.py::test_upgrade_downgrade_upgrade_cycle_on_postgres` | Sztywny head `0065` i lista tabel sprzed `0066`; tabele gry przeniesione do `game_data_v2` (D-448, `0125`); pełny `downgrade base` z `head` niemożliwy (`0123` `e4c49020`, `0136` D-467) | Dostosowany: head z `schema_readiness.EXPECTED_ALEMBIC_HEAD`; tabele `public` = tabele ORM spoza manifestu gry + jawna lista 8 tabel control-plane bez modelu ORM; tabele `game_data_v2` = `GAME_TABLES` manifestu v4; cykl `0122 → base → head` oraz `head → 0136 → head`; nowa asercja, że zejście poniżej `0136` odmawia z `CELL_RENDER_SPEC_DROP_IRREVERSIBLE` i zostawia rewizję `0136` |
| `…::test_reviewer_work_assignments_enforce_one_active_row_and_keep_history` | `reviewer_access_sessions` / `reviewer_work_assignments` są tabelami gry (D-448, `0125`); fixture wstawiały do `public` | Dostosowany: gra przez lifecycle partycji (`GamePartitionLifecycleRepository`), każda transakcja w `game_storage_scope` + `GameStorageSession`. Asercja `code == REVIEWER_ASSIGNMENT_ALREADY_ACTIVE` ujawniła **błąd produktu** (niżej) — przeniesiona bez zmian do nowego testu `test_duplicate_active_assignment_reports_already_active` z `xfail(strict=True)`; w teście głównym zostało sprawdzenie, że baza odrzuca drugi aktywny wiersz (`ReviewerWorkAssignmentConflictError`) oraz cała historia |
| `…::test_online_assignment_capacity_is_serialized_across_postgres_transactions` | jw. (D-448); limit online liczony przez wszystkie gry od TASK-0797 (`OtherGamesOnlineAssignments`) | Dostosowany: 4 gry przez lifecycle, repozytorium okablowane jak w `create_app` (`GameEntityLocator`, `OtherGamesOnlineAssignments`); asercje bez zmian (3 × `opened`, 1 × `REVIEWER_ASSIGNMENT_ONLINE_LIMIT_REACHED`, 3 aktywne wiersze) |
| `test_layout_import_report_repository.py::test_postgres_report_has_exact_counts_bounded_groups_and_filtered_rows` | `bc1e47a9` (V0.2.2, migracja `0022_dataset_completeness_sources`): publikacja najpierw porównuje liczbę poprawnych wierszy z `games.expected_layout_count` (`LAYOUT_IMPORT_EXPECTED_COUNT_MISMATCH`), a `dataset_versions.expected_layout_count` jest `NOT NULL` | Dostosowany: gra tworzona z `expected_layout_count=4` (oba importy mają 4 poprawne wiersze, więc pierwsza publikacja nadal trafia na blokery raportu `LAYOUT_IMPORT_NOT_READY_FOR_PUBLICATION`); fixture `DatasetVersionModel` z `expected_layout_count=4`; asercje bez zmian |
| `test_m2_admin_acceptance.py::test_complete_m2_admin_flow_uses_only_public_http_contracts` | `67a6187a` (v0.8.13, „simplify manual symbol catalog management”): `SymbolCreate` przyjmuje tylko `name` i `isWildcard`; API nadaje `mobileCode`, `code`, `displayOrder`, status `active` | Dostosowany: żądanie wg nowego kontraktu; dodane asercje nadanych pól (`mobileCode` 1…12, `displayOrder` 0…11, `active`, `imagePath` null); reszta przepływu bez zmian |
| `test_review_repository.py::test_review_repository_persists_idempotent_immutable_batch` | (1) Środowisko: raport `ai_docs/quality/m6-symbol-active-learning-selection.json` jest w git jako LF (`i/lf`), ale `* text=auto` + systemowe `core.autocrlf=true` daje CRLF w checkout Windows, a test hashował bajty checkoutu; (2) `review_batches` jest tabelą gry (D-448, `0125`) | Dostosowany: hash z bajtów po normalizacji CRLF → LF (= blob w git; kontrola kanoniczności w produkcie bez zmian); gra przez `CatalogService.create_game` (lifecycle) i sesja w `game_storage_scope`; asercje bez zmian |
| `test_v010_virtual_geometry_migration.py::test_v010_virtual_geometry_upgrade_backfill_and_downgrade` (teraz `…_upgrade_defaults_and_downgrade`) | `102a6c8f` (TASK-0790, D-467): `backfill_legacy_states` zapisuje `structured_lattice_v3`/`virtual_default`, czego CHECK z `0082` nie dopuszcza (tryb dodaje `0095`); od `0125` (D-448) tabela istnieje tylko per gra w `game_data_v2`, a backfill wielu gier w jednej transakcji jest sprzeczny z wiązaniem jednej gry | Dostosowany: asercje schematu `0081 → 0082 → 0081` bez zmian; uruchamianie bieżącego backfillu na schemacie `0082` zastąpione asercją domyślnych wartości tabeli z `0082` (`legacy`/`legacy_files`/`0`/`not_started`). Następca zachowania „nowa gra dostaje stan rolloutu”: `test_game_partition_lifecycle_postgres.py::test_greenfield_catalog_create_provisions_v2_before_return` (polityka `structured_lattice_v3`: `test_game_storage_routing_postgres.py::test_import_policy_reads_v2_rollout_in_a_new_unscoped_session`) |

#### Błąd produktu (zgłoszony, nienaprawiony)

`SqlAlchemyReviewerWorkAssignmentRepository.add` rozpoznaje naruszenie
unikalności po nazwie `uq_reviewer_work_assignments_active_import`. W
`game_data_v2` PostgreSQL zgłasza nazwę indeksu partycji
(zmierzone: `gpv2_<gra>_<hash>_game_id_import_job_id_idx1`; indeks rodzica to
`v2_ix_fa8cf5eef7574f8e7690`), więc zamiast
`REVIEWER_ASSIGNMENT_ALREADY_ACTIVE` zwracany jest
`REVIEWER_ASSIGNMENT_PERSISTENCE_CONFLICT`. Skutek praktyczny ograniczony:
`ReviewerWorkAssignmentService.open` sprawdza aktywny przydział wcześniej pod
globalnym advisory lockiem. Ten sam wzorzec (mapowanie po nazwie z `public`
na tabeli gry) występuje w `review_repository.py`
(`uq_review_batches_source_report_sha256`),
`image_import_geometry_guard_repository.py`
(`uq_image_import_guard_decisions_*` — przy niedopasowaniu ponownie rzuca
`IntegrityError`) i `page_geometry_override_repository.py`
(`uq_image_page_geometry_overrides_revision`) — niezweryfikowane testem.
Poprawka nie jest lokalna (kilka repozytoriów, potrzebne mapowanie indeksu
partycji na rodzica albo inny mechanizm), dlatego tylko zgłoszona;
`test_duplicate_active_assignment_reports_already_active` (`xfail(strict=True)`)
zacznie failować po naprawie i wtedy trzeba zdjąć marker.

### Changed

- `services/api/tests/integration/test_board_import_coverage_migration.py`
- `services/api/tests/integration/test_board_import_coverage_repository.py`
- `services/api/tests/integration/test_postgres_baseline.py`
- `services/api/tests/integration/test_layout_import_report_repository.py`
- `services/api/tests/integration/test_m2_admin_acceptance.py`
- `services/api/tests/integration/test_review_repository.py`
- `services/api/tests/integration/test_v010_virtual_geometry_migration.py`

### Verification results

Każdy plik osobno, `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`,
`pytest … -q -p no:cacheprovider`:

- `test_board_import_coverage_migration.py`: 5 passed (8,3 s).
- `test_board_import_coverage_repository.py`: 9 passed (9,6 s).
- `test_layout_import_report_repository.py`: 1 passed (9,4 s).
- `test_m2_admin_acceptance.py`: 1 passed (21,7 s).
- `test_postgres_baseline.py`: 3 passed, 1 xfailed (54,9 s).
- `test_review_repository.py`: 1 passed (11,1 s).
- `test_v010_virtual_geometry_migration.py`: 1 passed (3,7 s).
- Dodatkowo z `GAME_PREDICTOR_PG_TEST_ROLE=application` (sesje aplikacyjne
  bez SUPERUSER/BYPASSRLS): `test_postgres_baseline.py` 3 passed, 1 xfailed;
  `test_review_repository.py`, `test_layout_import_report_repository.py`,
  `test_m2_admin_acceptance.py` — 1 passed każdy.
- `python -m ruff check services/api`: All checks passed.
  `python -m ruff format --check` (7 plików): already formatted.
  `git diff --check`: czysto.

### Orchestrator closure (2026-10-02)

- Błąd produktu z testu `xfail(strict=True)` (rozpoznawanie naruszenia
  unikalności po nazwie indeksu rodzica, podczas gdy PostgreSQL zgłasza nazwę
  indeksu partycji gry) przyjęty jako zgłoszenie; naprawa obejmuje kilka
  repozytoriów tabel gry i dostaje osobne zadanie (TASK-0812). Skutek
  ograniczony do mniej czytelnego kodu błędu przy wyścigu.
- Do tego samego zadania: reguła `eol=lf` dla artefaktów wiązanych sumą
  kontrolną (6 błędów `services/api/tests/test_reviews.py` na Windows) i
  martwe `backfill_legacy_states`.

### Not completed

- Nie uruchomiono `npm run db:baseline:verify` ani całego katalogu
  integracyjnego (poza zakresem, 18 min). Nie uruchamiano pozostałych plików
  testów.
- Commit, `CURRENT_STATE.md` i przeniesienie zadania — koordynator.
- Błąd produktu (wyżej) tylko zgłoszony.

### Documentation updates

- Brak poza tym `Outcome` (zmieniły się tylko testy).

### Recommended next task

- Naprawa mapowania naruszeń unikalności na tabelach `game_data_v2` (np.
  rozpoznanie indeksu partycji przez `pg_inherits` po savepoincie albo przez
  kolumny klucza) we wszystkich repozytoriach z wzorcem
  `diag.constraint_name == "uq_…"` na tabelach gry; zdjęcie `xfail` z
  `test_duplicate_active_assignment_reports_already_active`.
- `services/api/tests/test_reviews.py` (nie-PG, poza zakresem) ma 6
  błędów z tej samej przyczyny CRLF co `test_review_repository.py`
  (sprawdzone uruchomieniem). Trwała poprawka: reguła `.gitattributes`
  `eol=lf` dla artefaktów wiązanych sumą kontrolną (np.
  `ai_docs/quality/*.json`) albo normalizacja w teście jak tutaj.
- `SqlAlchemyImageGeometryRolloutRepository.backfill_legacy_states` nie ma
  wywołań produkcyjnych od wprowadzenia (`48e12ea9`) i po D-448 nie da się go
  poprawnie użyć (wiele gier w jednej transakcji) — kandydat do usunięcia.
