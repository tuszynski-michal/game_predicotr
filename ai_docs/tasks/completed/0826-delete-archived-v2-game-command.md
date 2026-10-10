---
title: TASK-0826 — komenda trwałego usunięcia zarchiwizowanej gry V2
status: done
last_updated: 2026-10-02
---

# TASK-0826 — komenda trwałego usunięcia zarchiwizowanej gry V2

## Status

`done`

## Goal

Operator może jedną komendą z podglądem i jawnym potwierdzeniem trwale usunąć
z bazy zarchiwizowaną grę V2; dwie testowe gry „Mumie” są usunięte.

## Context

Zgłoszenie operatora z 2026-10-02: usunąć całkowicie dwie zarchiwizowane,
testowe gry „Mumie” (`mums` `cf300bc1-c0c1-4bf9-b607-4c4e1e4f031c`,
`mums-test-1` `2a46d3a6-bc56-4a13-8f98-dd51c88df0b2`). Admin i API potrafią
grę tylko zarchiwizować. `GamePartitionLifecycleRepository` ma wznawialną
operację `delete`, ale wywoływały ją wyłącznie testy.

## Dependencies / entry conditions

- Baza deweloperska na `0139`, manifest magazynu v4 (fakt, sprawdzone
  zapytaniem tylko do odczytu).
- Jawna zgoda operatora na usunięcie obu gier (treść zgłoszenia).

## Recommended execution

`claude-fable-5-1`, reasoning domyślny sesji. Cienka komenda nad istniejącym,
przetestowanym lifecycle; ryzyko leży w danych, nie w logice. Audyt zawieszony
decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`

## Scope

- Nowy `scripts/delete_archived_v2_game.py`: podgląd tylko do odczytu, blokady
  fail-closed, wykonanie przez istniejący lifecycle `delete`.
- Testy jednostkowe i test na izolowanej bazie PostgreSQL.
- Usunięcie gier `mums` i `mums-test-1` z bazy deweloperskiej.

## Out of scope

- Endpoint API i przycisk w Adminie.
- Usuwanie plików z dysku (katalogi `imports/browser-selections`, manifesty).
- Zmiany w `GamePartitionLifecycleRepository` i schemacie.

## Acceptance criteria

- [x] Podgląd nie zapisuje do bazy i wymienia blokady.
- [x] Gra `draft`/`active`, z aktywnymi zadaniami, w wydaniu mobilnym albo z
      rekordami w tabelach spoza zakresu lifecycle jest blokowana.
- [x] Wykonanie wymaga dokładnego potwierdzenia i SHA podglądu; jest wznawialne.
- [x] Po wykonaniu obie gry „Mumie” nie mają rekordu gry, partycji, symboli
      ani zadań; gra 777 ma nadal 63 partycje i komplet zadań.

## Technical notes

Finalizacja lifecycle czyści w `public` tylko `paylines`, `payout_rules`,
`rules_version_symbols`, `symbols`, `rules_versions`, `jobs`,
`game_storage_locations` i `games`. Nowsze tabele z kluczem obcym `RESTRICT`
do gry lub jej zadań (`board_search_share_sessions`,
`board_search_share_query_events`, `mobile_releases.build_job_id`,
`storage_gc_runs`, `semi_automatic_image_selection_runs`, receipty legacy)
nie są czyszczone. Komenda wykrywa je z katalogu `pg_constraint` i blokuje
start, zamiast zostawiać grę w stanie `deleting` z usuniętymi partycjami.

## Expected files

- Nowe: `scripts/delete_archived_v2_game.py`,
  `services/api/tests/test_delete_archived_v2_game_script.py`.
- Istniejące: `services/api/tests/integration/test_game_partition_lifecycle_postgres.py`
  (nowy test), `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`.

## Outcome

### Changed

- Dodano komendę `scripts/delete_archived_v2_game.py` i opis w przewodniku
  operatora.
- Usunięto z bazy deweloperskiej gry `mums-test-1` (operacja
  `c7c0b68a-6b4c-4691-a63c-81955be3fd4e`) i `mums` (operacja
  `2b452713-9566-4186-a3ca-70e0dd1e13d7`), po 63 partycje każda. Przy `mums`
  jeden krok trafił na limit blokady 2 s; ponowienie wznowiło operację.

### Verification results

- `pytest services/api/tests/test_delete_archived_v2_game_script.py`: 6/6.
- `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, test
  `test_archived_game_deletion_script_previews_and_deletes_only_that_game`
  oraz `test_restartable_provision_and_delete_keep_other_game_isolated`: 2/2.
  W pierwszym przebiegu teardown fixture zgłosił błąd (asercja braku aktywnych
  połączeń przed `DROP DATABASE`) i zostawił bazę testową, którą usunięto
  ręcznie; dwa kolejne przebiegi czyste. Przyczyny nie ustalono.
- Ruff check i format: czyste dla zmienionych plików. `mypy --strict` nie
  uruchomiony w konfiguracji repo (worktree bez własnego `.venv`).
- Baza po wykonaniu: jedna gra (`7` / 777, `draft`), 0 partycji i 0 rekordów
  katalogu obu „Mumii”, 63 partycje i 590 zadań gry 777.

### Not completed

- Pliki na dysku pozostały, bez żadnej referencji w bazie:
  `imports/browser-selections/fa6772db-70ba-4c1f-b34c-5769730d1231` (8 plików,
  1,2 MB), `imports/browser-selections/b8dc0d14-96e8-48a4-bd15-ebe9d2f97141`
  (28 plików, 6,9 MB),
  `artifacts/data/page-geometry-manifests/b5b8b0401ea0134a25b9bb5469f36f789d0031f9524f300fe098fcd3106a4bee.json`.
- Receipty operacji w `game_storage_lifecycle_operations` pozostają jako ślad.
- Pełne `npm run quality` nie było uruchamiane.

### Documentation updates

- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`, `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- Decyzja operatora, czy dodać usuwanie zarchiwizowanej gry do panelu Admin.
