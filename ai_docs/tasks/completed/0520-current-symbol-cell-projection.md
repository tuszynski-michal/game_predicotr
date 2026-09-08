---
title: TASK-0520 — Lekka projekcja bieżących symboli
status: done
last_updated: 2026-09-09
---

# TASK-0520 — Lekka projekcja bieżących symboli

## Status

`done`

## Goal

Ustanowić partycjonowane `image_symbol_review_cells` jako jednoznaczny bieżący
stan dostępnej komórki dla gry, bez drugiej projekcji i bez kopiowania danych.

## Context

Legacy zachowuje w tabeli wiersze poprzednich właścicieli i filtruje je przez
fast documents. Pusty magazyn V2 może od początku utrzymywać jeden stabilny
wiersz `(game_id, sequence_number, cell_index)`, podczas gdy historię zachowują
append-only eventy.

## Dependencies / entry conditions

- TASK-0519 zakończony w `v0.10.239`.
- Schemat 0105 i routing 0106 istnieją w kodzie, ale nie są zastosowane na bazie
  użytkownika.
- Docelowy V2 jest pusty; task nie wykonuje backfillu `new-siedem`.

## Recommended execution

`gpt-6-astra high`. Dodatkowy review `gpt-6-astra high` sprawdza semantykę
właściciela, retry oraz zgodność z eventami i niedostępnymi komórkami.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/requirements/ADMIN_APP.md`

## Scope

- Unikalna tożsamość bieżącej komórki V2 po grze, numerze i indeksie.
- Atomowe przepięcie stabilnego wiersza na nowego właściciela planszy.
- Zachowanie decyzji, proweniencji cropa, unavailable i historii eventowej.
- Wznawialny istniejący backfill bez uruchamiania go dla danych użytkownika.

## Out of scope

Listowanie, nowe indeksy filtrów, liczniki, provisioning partycji i operacje na
rzeczywistej bazie.

## Acceptance criteria

- [x] V2 uniemożliwia dwie komórki dla jednej logicznej pozycji.
- [x] Reprocessing aktualizuje stabilny wiersz zamiast tworzyć drugi.
- [x] Legacy zachowuje dotychczasową semantykę current-owner join.
- [x] Niedostępna komórka nie jest zwracana ani używana treningowo.
- [x] Retry i restart nie tworzą duplikatu.

## Technical notes

Constraint dotyczy wyłącznie pustego `game_data_v2`. Repozytorium rozpoznaje
przypięty store przez istniejący router. Dla V2 pobiera wiersz po logicznej
pozycji i w tej samej transakcji aktualizuje właściciela, piksele i stan. Dla
legacy nadal pobiera po `review_item_id`, więc historyczne wyniki są niezmienne.

## Expected files

- `image_symbol_review_repository.py`
- nowa migracja po 0106
- test migracji i zachowania projekcji
- dokumentacja modelu danych i procesu

## Test cases

- Dwa review items tej samej pozycji w V2 nie tworzą dwóch wierszy.
- Ten sam retry nie zmienia liczby wierszy.
- Wymiana właściciela zachowuje ID komórki i zapisuje zmianę stanu.
- Brak źródła oznacza unavailable bez sztucznego cropa.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_current_symbol_cell_projection_v2.py -q
.venv\Scripts\python.exe -m pytest services/api/tests/test_qualified_cell_reconciliation.py -q
.venv\Scripts\python.exe -m ruff check <changed Python files>
.venv\Scripts\python.exe -m mypy <changed Python files>
```

## Risks / open questions

- Pełna izolowana próba PostgreSQL należy do bramki TASK-0523 po utworzeniu
  fizycznych partycji gry.

## Outcome

### Changed

- Migracja 0107 dodaje unikalną logiczną pozycję wyłącznie do pustego V2.
- Write-through rozwiązuje istniejący wiersz po logicznej pozycji w V2 i
  atomowo przepina właściciela; ścieżka legacy pozostała bez zmian.
- Właściciel jest częścią porównania projekcji, więc jego zmiana nie może zostać
  uznana za no-op nawet przy identycznym content-addressed cropie.

### Verification results

- 22 testy projekcji, reconciliacji, dostępności i zapytań — passed.
- Ruff zmienionych plików — passed.
- Offline upgrade/downgrade 0107 dowodzi braku data rewrite i CASCADE.
- Bezpośredni mypy modułu zatrzymały istniejące braki `py.typed` workera oraz
  wcześniejszy `no-any-return` w `application/jobs.py`; brak nowego błędu w
  zmienionym kodzie.

### Not completed

- Nie zastosowano migracji i nie utworzono partycji żadnej gry.
- Izolowany test fizycznej partycji należy do TASK-0523.

### Documentation updates

- Zaktualizowano DATA_MODEL i CURRENT_STATE.

### Recommended next task

- TASK-0521 — indeksowane listowanie Weryfikacji symboli.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0520 | `gpt-6-astra` | `high` | Atomowa projekcja i ochrona tożsamości cropów. | `gpt-6-astra high` — zgodność semantyki |
