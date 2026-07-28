---
title: CSV and JSON import contracts
status: done
last_updated: 2026-07-27
---

# TASK-0043 — CSV and JSON import contracts

## Status

`done`

## Goal

Zdefiniować i zaimplementować wersjonowany, strumieniowy kontrakt plików CSV
oraz JSON Lines dla ręcznego importu layoutów wraz ze stabilnymi kodami błędów
i przykładami.

## Context

M4 przyjmuje pliki dochodzące do około 500 000 layoutów na grę. Kontrakt musi
jednoznacznie zachować domenowy `sequence_number` i komórki w kolejności
row-major, a jednocześnie umożliwić późniejszy parser bounded-memory. Właściciel
zdecydował rozpocząć M4 przed formalnym zamknięciem benchmarkowej bramki G3;
brakujące pomiary urządzeń pozostają jawnie odroczone do odbioru po M4.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_04_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- kontrakt `layout-import-v1`,
- CSV z dokładnym nagłówkiem `schema_version,sequence_number,cells`,
- JSON Lines z jednym obiektem layoutu na linię,
- ścisłe UTF-8 bez BOM,
- `cells` jako tablica JSON dodatnich kodów `smallint` w kolejności row-major,
- stabilne kody błędów dla formatu, kodowania, nagłówka, wersji, sekwencji i
  komórek,
- czyste funkcje walidujące nagłówek i pojedynczy rekord bez zależności od
  systemu plików, API, ORM lub UI,
- poprawne i błędne przykłady kontraktu.

## Out of scope

- wybór dowolnej ścieżki z panelu, checksum pliku i limit rozmiaru,
- utworzenie joba importu lub jego klucza idempotencji,
- streaming całego pliku, checkpoint i wznowienie,
- walidacja wymiarów gry, przynależności symboli, luk i duplikatów,
- zapis stagingu, publikacja datasetu i UI.

## Acceptance criteria

- [x] Kontrakt ma jawną wersję `1` i opisane przykłady CSV/JSONL.
- [x] CSV wymaga dokładnego nagłówka i jednego niepustego rekordu logicznego na
  wiersz.
- [x] JSONL wymaga dokładnego zestawu pól każdego obiektu.
- [x] Nieznana wersja, UTF-8 BOM, błędne UTF-8 i zły nagłówek zwracają stabilne
  kody błędów.
- [x] `sequence_number` jest dodatnią liczbą całkowitą, a `cells` niepustą
  tablicą dodatnich kodów `smallint`.
- [x] Parser pojedynczego rekordu nie zna wymiarów gry ani symboli i nie
  podejmuje decyzji należących do TASK-0046.
- [x] Testy, Ruff i mypy zmienionych części przechodzą.

## Technical notes

- JSON oznacza w M4 format JSON Lines (`.jsonl`), nie monolityczny dokument z
  tablicą 500 000 rekordów. Każda linia jest samodzielnym poprawnym JSON.
- CSV zapisuje `cells` jako JSON array w cytowanym polu, np.
  `1,1,"[1,2,3]"`.
- Wersja jest powtarzana w każdym rekordzie. Ułatwia to walidację i bezpieczne
  wznowienie od granicy linii bez osobnego sidecaru.
- Puste linie nie są rekordami i będą pomijane dopiero przez parser strumieniowy
  TASK-0045; walidator pojedynczego rekordu odrzuca pustą linię.

## Expected files

- `services/worker/src/game_predictor_worker/imports/`
- `services/worker/tests/test_import_contracts.py`
- `examples/imports/layout-import-v1.csv`
- `examples/imports/layout-import-v1.jsonl`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_import_contracts.py -q
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/imports services/worker/tests/test_import_contracts.py
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/imports
```

## Risks / open questions

- Arkusze kalkulacyjne mogą zapisywać CSV jako UTF-8 z BOM. V1 świadomie go
  odrzuca, aby kontrakt kodowania był jednoznaczny; panel powinien pokazać
  instrukcję ponownego zapisu jako UTF-8 bez BOM.
- Limit rozmiaru i rozszerzenia pliku zostaną ustalone i wymuszone przez
  bezpieczną granicę wejścia w TASK-0044.

## Outcome

### Changed

- dodano niezależny od frameworków pakiet `game_predictor_worker.imports`,
- zdefiniowano wersję, formaty, niezmienny rekord i granice liczbowe v1,
- dodano ścisłe dekodowanie UTF-8 bez BOM, walidację nagłówka CSV oraz parsery
  pojedynczego rekordu CSV i JSONL,
- odrzucane są dodatkowe, brakujące i zduplikowane pola, błędne typy, nieznana
  wersja, niedodatni numer oraz puste lub niepoprawne komórki,
- dodano poprawne przykłady 3 × 5 i 33 testy kontraktu.

### Verification results

- `33 passed` — `test_import_contracts.py`,
- `162 passed` — cały zestaw testów workera,
- Ruff lint całego `services/worker/src` i `services/worker/tests` przeszedł,
- Ruff format zmienionych plików przeszedł,
- mypy przeszedł dla `86 source files` API i workera.

### Not completed

- checksum, limit rozmiaru, katalog wejściowy, idempotencja i utworzenie joba
  pozostają zakresem TASK-0044,
- streaming pliku, checkpoint, staging i walidacja względem gry pozostają
  zakresem TASK-0045–0046,
- fizyczna bramka G3 pozostaje zablokowana zgodnie z D-041.

### Documentation updates

- dodano `MANUAL_DATA_IMPORT.md`,
- zaakceptowano D-041 i D-042,
- zaktualizowano plan M4 oraz `CURRENT_STATE.md`.

### Recommended next task

- `TASK-0044 — Import job creation, checksums and path safety`.
