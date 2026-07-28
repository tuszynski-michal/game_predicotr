---
title: Import job creation, checksums and path safety
status: done
last_updated: 2026-07-27
---

# TASK-0044 — Import job creation, checksums and path safety

## Status

`done`

## Goal

Bezpiecznie utworzyć idempotentny job ręcznego importu wyłącznie dla
zweryfikowanego pliku CSV/JSONL znajdującego się w skonfigurowanym lokalnym
katalogu wejściowym.

## Context

TASK-0043 zdefiniował `layout-import-v1`, ale dotychczasowy generyczny payload
jobu importu przyjmował dowolny `sourcePath` i deklarowaną przez klienta wersję
pipeline. M4 wymaga, aby API nie ufało ścieżce, formatowi, rozmiarowi ani
checksumie klienta oraz nie tworzyło drugiego joba dla tej samej treści i
kontraktu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_04_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- konfigurowalny lokalny `import_root` i limit bajtów,
- wyłącznie względna ścieżka POSIX pod `import_root`,
- ochrona przed ścieżką absolutną, `..`, backslash, dwukropkiem i wyjściem
  przez symlink/junction,
- akceptacja wyłącznie zwykłego, niepustego pliku `.csv` albo `.jsonl`,
- bounded preview nagłówka/pierwszego rekordu zgodnie z TASK-0043,
- strumieniowy SHA-256 bez ładowania pliku do pamięci,
- wykrycie zmiany pliku podczas inspekcji,
- serwerowo utrwalone: kanoniczna ścieżka względna, format, wersja kontraktu,
  rozmiar i checksum,
- idempotencja po grze, checksumie, formacie i wersji kontraktu niezależnie od
  nazwy pliku,
- publiczny OpenAPI i wygenerowany klient TypeScript.

## Out of scope

- kopiowanie lub upload pliku przez HTTP,
- pełny streaming rekordów do PostgreSQL,
- checkpoint, wznowienie i staging datasetu,
- walidacja wszystkich wierszy, wymiarów i katalogu symboli,
- UI wyboru pliku i raporty importu,
- jawne utworzenie drugiego importu tej samej treści.

## Acceptance criteria

- [x] API przyjmuje wyłącznie względny `sourcePath` oraz
  `contractVersion = 1`.
- [x] Klient nie może podać checksumy, rozmiaru ani formatu.
- [x] Wyjście poza `import_root`, brak pliku, katalog, zły format, pusty plik i
  przekroczenie limitu zwracają stabilne kody błędów bez utworzenia joba.
- [x] Nieprawidłowy nagłówek/pierwszy rekord zwraca kod TASK-0043 i numer linii.
- [x] SHA-256 jest liczony bounded partiami, a zmiana pliku podczas inspekcji
  jest odrzucana.
- [x] Utrwalony job zawiera komplet serwerowo poświadczonych metadanych pliku.
- [x] Ta sama treść i kontrakt dla tej samej gry zwraca
  `JOB_INPUT_ALREADY_EXISTS`, także pod inną nazwą.
- [x] OpenAPI oraz wygenerowany klient odpowiadają implementacji.
- [x] Testy, lint, format i typecheck zmienionych części przechodzą.

## Technical notes

- domyślny katalog to repozytoryjne `imports/`,
- domyślny limit jednego pliku to 1 GiB i może zostać zmieniony przez dodatnią
  wartość `GAME_PREDICTOR_IMPORT_MAX_BYTES`,
- preview ma limit 1 MiB na fizyczną linię,
- API zapisuje `importKind = layout_file`; przyszły import zdjęć użyje osobnego
  kontraktu zamiast rozszerzać ten payload niejawnie,
- idempotencja ignoruje nazwę i rozmiar pliku, ponieważ SHA-256 identyfikuje
  bajty; gra, format i wersja kontraktu pozostają częścią klucza.

## Expected files

- `services/api/src/game_predictor_api/config.py`
- `services/api/src/game_predictor_api/application/layout_imports.py`
- `services/api/src/game_predictor_api/application/jobs.py`
- `services/api/src/game_predictor_api/schemas/jobs.py`
- `services/api/src/game_predictor_api/api/jobs.py`
- testy API/domain/config/import source
- `packages/admin-api-client/`
- `.env.example`, `.gitignore`, `imports/README.md`
- dokumentacja API, architektury i procesu

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_layout_imports.py services/api/tests/test_jobs_api.py services/api/tests/test_jobs_domain.py services/api/tests/test_config.py -q
npm run openapi:generate
npm run openapi:check
.venv\Scripts\python.exe -m ruff check services/api services/worker
.venv\Scripts\python.exe -m mypy services/api/src services/worker/src
npm run test --workspace @game-predictor/admin-api-client
```

## Risks / open questions

- plik pozostaje własnością użytkownika i może zostać zmieniony po utworzeniu
  joba; TASK-0045 musi ponownie sprawdzić checksumę przed i po przetwarzaniu,
- upload przez przeglądarkę nie należy do M4.1; operator umieszcza plik w
  kontrolowanym katalogu lokalnym,
- jawny drugi import identycznej treści wymaga osobnej intencji/operacji i nie
  jest potrzebny do bramki G4.1.

## Outcome

### Zmieniono

- dodano serwerowy inspektor lokalnego źródła importu z kanoniczną ścieżką
  względną, ochroną przed traversal i wyjściem przez symlink/junction, limitem
  rozmiaru oraz kontrolą zwykłego pliku,
- API rozpoznaje wyłącznie `.csv` i `.jsonl`, wykonuje ograniczony preview
  kontraktu TASK-0043 i liczy SHA-256 strumieniowo w partiach po 1 MiB,
- tożsamość pliku jest sprawdzana przed, w trakcie i po odczycie, dzięki czemu
  zmiana źródła podczas inspekcji nie może utworzyć joba,
- job importu przechowuje serwerowo poświadczone `sourcePath`,
  `sourceChecksum`, `sourceSizeBytes`, `fileFormat` i `contractVersion`,
- klucz idempotencji importu zależy od gry, checksumy, formatu i wersji
  kontraktu, a nie od nazwy pliku,
- zaktualizowano konfigurację, OpenAPI, generowany klient TypeScript, dokumenty
  wymagań i architektury oraz przyjęto D-043,
- zmiana korzysta z istniejącego pola JSONB `jobs.input_payload`; migracja bazy
  nie była potrzebna.

### Weryfikacja

- testy celowane API/kontraktu: `60 passed, 1 skipped`; skip dotyczy utworzenia
  symlinku bez uprawnienia dostępnego dla bieżącego konta Windows,
- pełny zestaw API i workera: `307 passed, 9 skipped`; osiem pozostałych skipów
  wymaga jawnie uruchomionej fizycznej instancji PostgreSQL,
- testy wygenerowanego klienta: `10 passed`,
- kontrola aktualności OpenAPI i wygenerowanego klienta przeszła,
- build i typecheck pakietu klienta przeszły,
- Ruff lint dla API i workera oraz mypy dla 87 plików źródłowych przeszły,
- Ruff/Prettier dla zmienionych plików autorskich oraz `git diff --check`
  przeszły.

### Świadomie niewykonane

- ponowne sprawdzenie checksumy przez worker, streaming wszystkich rekordów,
  staging i checkpoint należą do TASK-0045,
- walidacja wymiarów, symboli, sekwencji i raport końcowy należą do TASK-0046,
- jawne wymuszenie drugiego importu identycznych bajtów pozostaje poza zakresem,
- fizyczne dowody G3 na Pixelu i Samsungu pozostają odroczone zgodnie z D-041.

### Następny krok

Rozpocząć `TASK-0045 — Streaming parser and resumable staging`.
