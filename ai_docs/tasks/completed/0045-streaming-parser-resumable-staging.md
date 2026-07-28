---
title: Streaming parser and resumable staging
status: done
last_updated: 2026-07-27
---

# TASK-0045 — Streaming parser and resumable staging

## Status

`done`

## Goal

Strumieniowo odczytać poświadczony plik `layout-import-v1`, zapisać każdy
niepusty rekord albo jego bezpieczny błąd do izolowanego stagingu PostgreSQL i
wznowić ten sam job od trwałego checkpointu bez utraty lub duplikowania
wierszy.

## Context

TASK-0044 tworzy job związany z konkretną grą, checksumą, formatem, rozmiarem i
kanoniczną ścieżką względną. Worker nie ma jeszcze handlera `import`, a surowe
wiersze nie mogą trafić bezpośrednio do `layouts`, ponieważ TASK-0046 dopiero
zweryfikuje wymiary, alfabet symboli i wyliczy stałoszeroką sygnaturę.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_04_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- migracja Alembic tworząca izolowane `layout_import_rows`,
- jeden rekord stagingu na fizyczną niepustą linię danych i job,
- trwałe: numer linii, końcowy offset bajtowy, poprawny rekord albo stabilny
  błąd parsera,
- parser pliku czytający najwyżej jedną ograniczoną linię oraz bounded partię,
- dokładna obsługa nagłówka CSV i pustych linii,
- ponowna atestacja ścieżki, formatu, rozmiaru i SHA-256 przed stagingiem,
- ponowne sprawdzenie SHA-256 po pełnym przebiegu,
- checkpoint schema v1 po trwałym upsercie partii,
- retry po awarii przed checkpointem bez duplikatów,
- reset kursora do początku po końcowej rozbieżności źródła,
- rejestracja handlera `import` w lokalnym workerze,
- liczniki bajtów, poprawnych i błędnych rekordów w istniejącym lifecycle jobs.

## Out of scope

- walidacja liczby komórek względem wymiarów gry,
- sprawdzenie przynależności symboli do gry,
- wyliczenie finalnej stałoszerokiej sygnatury,
- utworzenie `dataset_version` i rekordów `layouts`,
- raport luk i duplikatów sekwencji lub sygnatur,
- UI importu, publikacja datasetu i odrzucanie stagingu,
- upload pliku przez HTTP.

## Acceptance criteria

- [x] Migracja ma jeden head, rollback i constraints izolujące rekordy per job.
- [x] Worker odrzuca job innego typu lub niepoświadczony payload.
- [x] Worker ponownie sprawdza bezpieczną ścieżkę i dokładną checksumę przed
  zapisaniem pierwszej partii.
- [x] CSV oraz JSONL są czytane liniowo bez załadowania pliku do pamięci.
- [x] Każdy poprawny rekord i każdy błąd parsera ma numer linii oraz offset.
- [x] Pojedynczy błędny rekord nie usuwa poprawnych rekordów z tej samej ani
  kolejnej partii.
- [x] Checkpoint powstaje dopiero po trwałym idempotentnym upsercie partii.
- [x] Awaria po upsercie przed checkpointem i późniejszy retry nie tworzą
  duplikatów stagingu.
- [x] Zmiana pliku po utworzeniu joba lub podczas przebiegu nie może zakończyć
  importu jako poprawnego.
- [x] Przerwanie i wznowienie daje ten sam uporządkowany staging co jeden
  przebieg.
- [x] Staging nie tworzy datasetu ani rekordów `layouts`.
- [x] Testy, migracje, lint, format i typecheck zmienionych części przechodzą.

## Technical notes

- domyślna partia zawiera 1000 niepustych rekordów,
- checkpoint przechowuje fizyczny `byte_offset` i `line_number`; numer sekwencji
  nie jest kursorem pliku,
- checkpoint przechowuje `prefix_chain`, czyli deterministyczny łańcuch
  checksum fizycznych linii do trwałego offsetu,
- `progress.current/total` opisuje bajty źródła, a liczniki
  `succeeded/failed` opisują rekordy,
- linia fizyczna ma limit 1 MiB; zbyt długa linia jest drenowana bounded
  fragmentami i zapisywana jako bezpieczny błąd rekordu,
- `(job_id, line_number)` jest kluczem idempotencji stagingu,
- staging przechowuje parserowo poprawne `sequence_number/cells` albo parę
  `error_code/error_message`; nigdy oba warianty jednocześnie,
- kompletna normalizacja do `layouts` pozostaje wyłączną odpowiedzialnością
  TASK-0046.

## Expected files

- `services/api/alembic/versions/0011_layout_import_staging.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/worker/src/game_predictor_worker/imports/streaming.py`
- `services/worker/src/game_predictor_worker/imports/contracts.py`
- `services/worker/src/game_predictor_worker/imports/handler.py`
- `services/worker/src/game_predictor_worker/imports/store.py`
- `services/worker/src/game_predictor_worker/cli.py`
- testy parsera, handlera, migracji i fizycznego PostgreSQL
- dokumentacja modelu, architektury, stosu i procesu

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_import_streaming.py services/worker/tests/test_import_handler.py services/api/tests/test_migration_baseline.py -q
.venv\Scripts\python.exe -m ruff check services/api services/worker
.venv\Scripts\python.exe -m mypy services/api/src services/worker/src
```

## Risks / open questions

- źródło pozostaje plikiem użytkownika; końcowa rewalidacja musi wyzerować
  checkpoint przed zgłoszeniem rozbieżności, aby retry odtworzył wszystkie
  wcześniej zapisane wiersze,
- checkpoint joba i upsert stagingu są osobnymi krótkimi transakcjami; kolejność
  `upsert → checkpoint` jest bezpieczna dzięki kluczowi
  `(job_id, line_number)` i deterministycznemu parserowi,
- fizyczne wiersze stagingu nie są jeszcze datasetem i nie mogą być źródłem
  release.

## Outcome

### Zmieniono

- migracja `0011_layout_import_staging` tworzy `layout_import_rows` z kluczem
  `(job_id, line_number)`, fizycznym offsetem i rozłącznym wariantem
  poprawnego rekordu albo bezpiecznego błędu,
- bounded reader obsługuje CSV/JSONL, puste linie, CRLF, limit 1 MiB oraz
  drenowanie zbyt długiej linii bez utraty kolejnego rekordu,
- `LayoutImportStagingHandler` ponownie atestuje źródło, zapisuje partie po
  1000 rekordów, checkpointuje bajty i liczniki oraz końcowo rewaliduje pełny
  SHA-256,
- checkpoint zawiera łańcuch checksumy prefiksu; wznowienie usuwa wyłącznie
  rekordy za trwałym numerem linii, a rozbieżność wymusza czysty replay,
- PostgreSQL store wykonuje idempotentny upsert oraz bounded usunięcie
  nietrwałego ogona,
- worker `worker-v3` rejestruje handler `import` obok payoutu i workflow
  Android build,
- D-044 i dokumenty wymagań, modelu danych, architektury, API, stosu oraz
  testów opisują nowy kontrakt,
- zaktualizowano nieaktualny testowy Android builder o istniejący callback
  heartbeat; produkcyjny release handler nie został zmieniony.

### Weryfikacja

- pełny zestaw API i workera: `324 passed, 10 skipped`; dziewięć skipów to
  jawnie wyłączone integracje PostgreSQL, a jeden dotyczy braku uprawnienia do
  utworzenia symlinku na bieżącym koncie Windows,
- wszystkie izolowane integracje na fizycznym PostgreSQL: `9 passed`,
- celowane testy parsera, handlera, CLI i migracji: `30 passed`,
- migracja ma jeden head, generuje constraints i przechodzi fizyczny cykl
  `upgrade → downgrade → upgrade`,
- Ruff lint dla całego API/workera przeszedł,
- mypy przeszedł dla 90 plików źródłowych,
- Ruff format dla nowych i bezpośrednio zmienionych modułów TASK-0045 przeszedł,
- OpenAPI i wygenerowany klient pozostają aktualne,
- `git diff --check` przeszedł.

### Świadomie niewykonane

- walidacja wymiarów, alfabetu symboli i finalnej sygnatury należy do TASK-0046,
- surowy staging nie tworzy jeszcze `dataset_version` ani `layouts`,
- raport luk i duplikatów oraz UI należą do TASK-0047–TASK-0048,
- fizyczne dowody G3 na Pixelu i Samsungu pozostają odroczone zgodnie z D-041.

### Następny krok

Rozpocząć `TASK-0046 — Layout normalization and row validation`.
