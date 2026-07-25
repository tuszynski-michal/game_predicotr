---
title: TASK-0008 Matching repository and cyclic payout stream
status: done
last_updated: 2026-07-24
---

# TASK-0008 — Matching repository and cyclic payout stream

## Goal

Zaimplementować mobilny adapter SQLite dla konfiguracji gier, prefix/exact
matching i pełnego cyklicznego strumienia `N - 1` payoutów, udowodnić semantykę
na finalnym snapshotcie oraz domknąć bramkę G3 podetapu M1.3.

## Context

TASK-0007 dostarczył zwalidowany `m1-snapshot.db` schema version `2` z indeksem
`(game_id, signature)`. TASK-0008 tworzy granicę między tym snapshotem a
przyszłym UI. Adapter otrzymuje już otwartą instancję `SQLiteDatabase` od
`SQLiteProvider`; nie zarządza kopiowaniem assetu ani nie otwiera bazy dla
każdego spinu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/delivery/MILESTONE_01_MOCKED_MOBILE.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0007-sqlite-snapshot-generator.md`

## Scope

- interfejs lokalnego repozytorium niezależny od komponentów React,
- odczyt konfiguracji gier i symboli z finalnego SQLite,
- exact match zwracający `not_found`, `unique` albo `duplicate`,
- brak arbitralnego wyboru pierwszego rekordu dla duplikatu,
- diagnostyczny limit numerów duplikatu bez utraty pełnego
  `occurrence_count`,
- prefix match z dokładnym `candidate_count`,
- pełny layout i numer tylko dla jednego kandydata prefiksu,
- zakresowe wyszukiwanie prefiksu zgodne ze stałoszeroką sygnaturą,
- jeden uporządkowany odczyt cykliczny od następcy spin 0 do poprzednika,
- walidacja wyników SQLite jako `local_data_error`,
- testy jednostkowe adaptera TypeScript,
- testy integracyjne na prawdziwym `m1-snapshot.db`,
- sprawdzenie planów zapytań i indeksów,
- benchmark exact/prefix/cyclic na skali M1 oraz zapis wyników,
- domknięcie bramki G3.

## Out of scope

- reducer planszy i komponenty UI,
- modal pojedynczego kandydata,
- Reset/Undo i przechowywanie odrzuconej propozycji,
- wywołanie Target engine i renderowanie tabeli,
- benchmark 500 000 layoutów na telefonie,
- zmiana reprezentacji sygnatury na BLOB.

## Acceptance criteria

- [x] Repozytorium otrzymuje jedną otwartą bazę i nie otwiera jej per spin.
- [x] Lista gier zawiera konfiguracje, symbole, wersje i `layout_count`.
- [x] Pusty, nieznaleziony, pojedynczy i wieloznaczny prefiks mają testy.
- [x] Unikalny prefiks zwraca pełne komórki i `sequence_number`.
- [x] Exact zwraca poprawne `not_found`, `unique` i `duplicate`.
- [x] Duplicate nie wybiera żadnego `sequence_number` jako wyniku unique.
- [x] Cykliczny odczyt zwraca dokładnie `layout_count - 1` par w kolejności.
- [x] Zawinięcie `1000 → 1` jest objęte testem.
- [x] Błędne wejście albo niespójny rekord daje `local_data_error`.
- [x] Zapytania exact/prefix używają indeksu sygnatury, a cykl klucza głównego.
- [x] Integracja na finalnym snapshotcie odtwarza golden unique, duplicate i
  Target stream.
- [x] Benchmark M1 zapisuje rozmiar bazy, plany i p95 operacji.
- [x] Format, lint, typecheck i wszystkie testy przechodzą.
- [x] Bramka G3 i dokumentacja są zaktualizowane.

## Technical notes

- Prefiks cyfr używa zakresu `[prefix, prefix + ":")`; znak `:` jest
  bezpośrednio po `9` w ASCII, więc zakres obejmuje wszystkie i tylko
  sygnatury zaczynające się od prefiksu.
- Exact i prefix korzystają z `idx_layouts_game_signature`.
- Pełny cykl jest jednym `UNION ALL` z segmentem po spin 0 i segmentem przed
  spin 0, uporządkowanym po segmencie oraz `sequence_number`.
- Adapter waliduje kolejność niezależnie przed przekazaniem danych do Target
  engine, który wykona drugą walidację domenową.
- Benchmark 500 000 layoutów na fizycznym urządzeniu pozostaje bramką M3.

## Expected files

- `apps/mobile/src/data/local-layout-repository.ts`
- `apps/mobile/__tests__/local-layout-repository-test.ts`
- `services/worker/tests/test_repository_integration.py`
- `scripts/benchmark_m1_repository.py`
- `package.json`
- dokumentacja procesu i architektury

## Verification

```powershell
npm run repository:benchmark
npm run quality
```

## Risks / open questions

Pomiar Windows/Python potwierdza plan i semantykę SQLite, ale nie zastępuje
benchmarku `expo-sqlite` na słabszym urządzeniu przy 500 000 rekordów.

## Outcome

Zadanie zakończone. Powstała niezależna od React warstwa repozytorium
`LocalLayoutRepository`, która otrzymuje jedną otwartą bazę od warstwy
aplikacyjnej i realizuje cały kontrakt M1.3.

### Changed

- dodano mapowanie katalogu gier i symboli wraz z `layout_count`,
  `dataset_version` i `rules_version`,
- prefix matching używa zakresu `[prefix, prefix + ":")`, zwraca dokładny
  `candidate_count`, a pełny layout wyłącznie dla jednego kandydata,
- exact matching rozróżnia `not_found`, `unique` i `duplicate`; duplikat
  zachowuje pełny licznik i nie jest zamieniany na arbitralny unique,
- diagnostyka duplikatu ma jawny limit 20 numerów sekwencji,
- cały strumień Target jest pobierany jednym `UNION ALL` w kolejności od
  następcy spin 0 do poprzednika i walidowany jako dokładnie `N - 1`,
- stabilny `LocalDataError` został wydzielony do wspólnego modułu danych mobile,
- mobile korzysta ze współdzielonych kontraktów i walidacji
  `@game-predictor/shared-ts`,
- testy integracyjne wykonują te same kształty zapytań na finalnym
  `m1-snapshot.db`,
- dodano powtarzalny benchmark `npm run repository:benchmark` zapisujący wynik
  do `ai_docs/quality/m1-repository-benchmark.json`.

### Benchmark M1

Środowisko: Windows 11, AMD64, Python 3.12.13, SQLite 3.50.4. Baza została
otwarta raz przez część repozytoryjną benchmarku.

- rozmiar snapshotu: `274432` bajty,
- exact unique, 1000 iteracji: p95 `0.1627 ms`,
- prefix unique, 1000 iteracji: p95 `0.1655 ms`,
- cykl `N - 1`, 100 iteracji: p95 `3.1932 ms`,
- exact i prefix użyły covering index
  `idx_layouts_game_signature`,
- obie części cyklu użyły primary key `(game_id, sequence_number)`.

To jest dowód dla fixture M1 z 1000 layoutów na komputerze developerskim, nie
benchmark docelowych 500 000 rekordów na Androidzie.

### Verification results

- `npm run repository:benchmark` — passed,
- `npm run quality` — passed:
  - Prettier, Expo ESLint, Ruff i składnia 5 skryptów PowerShell,
  - TypeScript strict dla mobile i `shared-ts`,
  - mypy strict dla 17 plików Python,
  - testy mobile: 18/18,
  - testy `shared-ts`: 22/22,
  - testy Python: 52/52, w tym 5 integracyjnych repozytorium,
  - walidacja finalnego snapshotu i logicznego fixture.
- `git diff --check` — passed.

### Not completed

- nie dodano reduktora planszy ani matching UI,
- nie wywołano Target engine z ekranu mobile,
- nie wykonano benchmarku 500 000 layoutów na urządzeniu,
- nie zbudowano w tym zadaniu nowego APK i nie wykonano testów urządzeń.

### Recommended next task

Po osobnym poleceniu właściciela:

```text
TASK-0009 — Board reducer and basic components
```
