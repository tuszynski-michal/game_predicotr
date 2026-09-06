---
title: Optimize symbol review count query
status: done
last_updated: 2026-09-07
---

# TASK-0500 — Optymalizacja liczników Weryfikacji symboli

## Status

`done`

## Goal

Zwracać dokładne liczniki bieżącej projekcji dla największej lokalnej gry przed
limitem 15 sekund, bez skanowania geometrii osobno dla każdej komórki.

## Context

Lokalna tabela ma 7 518 540 komórek, z czego największa gra ma 6 304 230.
Obecne zapytanie wykonuje do 6,2 mln lookupów `recognized_boards` i sortuje
wszystkie pasujące komórki przed `GROUP BY`. Pomiar `EXPLAIN (ANALYZE,
BUFFERS)` wyniósł około 28,7 s dla największej gry i przekracza produkcyjny
`statement_timeout=15s`.

Projekcja `ready` już gwarantuje przy finalizacji brak nieaktualnej geometrii,
a write-through atomowo aktualizuje komórki lub oznacza projekcję jako failed.
Aktualnego właściciela nadal należy ustalać przez
`image_board_search_fast_documents`; ponowny lookup bieżącej rewizji planszy
dla każdej z 15 komórek nie wnosi nowej informacji do licznika.

## Dependencies / entry conditions

- TASK-0498 ustawia limit 15 sekund.
- TASK-0499 po audycie fizycznie anuluje porzucone zapytanie.
- Pomiar wykonano tylko odczytowo na rzeczywistych danych.

## Recommended execution

`gpt-5.6-sol high`: zakres jest wąski, ale wymaga kontroli równoważności SQL na
milionach rekordów i zachowania invariantów projekcji. Review
`gpt-6-astra high` jest wymagany, jeśli rozwiązanie będzie wymagało nowej
projekcji liczników, triggerów albo migracji dużej tabeli.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/quality/SYMBOL_CELL_REVIEW_SCALABILITY_ANALYSIS.md`

## Scope

- Dodać dedykowane, wąskie zapytanie liczników zamiast hydratacyjnego zapytania
  listy.
- Zachować current-owner join i wszystkie filtry symbolu, stanu, quality,
  confidence oraz aktywnej kohorty.
- Pominąć per-cell join `recognized_boards` wyłącznie w szerokim liczniku całej
  gotowej projekcji bez filtra confidence. Wąskie filtry zachowują join, jeśli
  pomiar pokazuje lepszy plan.
- Zastąpić `GROUP BY review_state` dwoma agregatami `COUNT(*) FILTER`, bez
  sortowania milionów rekordów.
- Porównać wartości starego i nowego zapytania na rzeczywistych grach i
  filtrach oraz zapisać plany `EXPLAIN`.

## Out of scope

- Osobna tabela/cache liczników, Redis, trigger lub zmiana schematu bazy.
- Zmiana zapytania listy, filtrów, API, timeoutów albo UI.
- Sztuczny wielomilionowy fixture i operacje zapisu na danych użytkownika.

## Acceptance criteria

- [x] Liczniki największej gry kończą się przed 15 s na obecnej bazie.
- [x] Nowe i historyczne zapytanie zwracają identyczne wyniki dla reprezentacji
      filtrów bez timeoutu.
- [x] Szerokie zapytanie nie sortuje wszystkich komórek i nie wykonuje per-cell lookupu
      `recognized_boards`.
- [x] Lista nadal zachowuje pełną bramkę bieżącej geometrii.
- [x] Timeout, cancellation i revision-bound kontrakt pozostają bez zmian.

## Technical notes

Nowa prywatna ścieżka query używa tego samego current-owner join oraz tych
samych predykatów filtra co lista. Wyłącznie szeroki wariant bez confidence
opiera aktualność geometrii na zweryfikowanym stanie projekcji; wąskie warianty
zachowują jawny join planszy. `require_ready_game` pozostaje wykonane w tej
samej ograniczonej transakcji przed countem. Warunek geometrii nie zostaje
usunięty z listy, assetów ani mutacji.

Wynik jednej instrukcji zawiera `approved_count` i `pending_count` przez
warunkowe agregaty. `all_count` pozostaje ich sumą, również gdy filtr stanu
zeruje jeden z liczników.

## Expected files

- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
- `services/api/tests/test_image_symbol_review_query_storage.py`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/quality/SYMBOL_CELL_REVIEW_SCALABILITY_ANALYSIS.md`
- `ai_docs/process/CURRENT_STATE.md`

## Test cases

- Szeroki SQL count zawiera current-owner join i dwa `FILTER`, bez joinu
  `recognized_boards` i bez `GROUP BY`; wąskie warianty zachowują join
  geometrii.
- Stan `all`, `pending`, `approved`, symbol, `?`, confidence i aktywna kohorta
  zachowują dotychczasowe wyniki.
- Query nadal podlega sygnałowi cancel oraz `statement_timeout`.
- Rzeczywiste gry 6,3 mln i 624 tys. komórek mieszczą się w limicie; wynik jest
  równy kontrolnemu zapytaniu historycznemu tam, gdzie ono kończy się w limicie.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_image_symbol_review_query_storage.py services/api/tests/test_image_symbol_reviews_api.py
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/storage/image_symbol_review_repository.py services/api/tests/test_image_symbol_review_query_storage.py
.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/storage/image_symbol_review_repository.py
npm run openapi:check
```

## Risks / open questions

- Pierwszy odczyt po całkowicie zimnym cache może być wolniejszy; bramka 15 s
  jest weryfikowana na obecnym komputerze, nie deklarowana dla dowolnego hosta.
- Jeśli current-owner invariant okaże się naruszony, task zatrzymuje się zamiast
  ukrywać drift szybszym licznikiem.

## Outcome

### Changed

- Zastąpiono `GROUP BY review_state` dwoma agregatami `COUNT(*) FILTER`.
- Szeroki filtr całej gry bez confidence korzysta z current-owner projection bez
  redundantnego lookupu geometrii dla każdej komórki.
- Filtry symbolu, `?`, confidence i aktywnej kohorty zachowują pełny join
  geometrii, podobnie jak lista.

### Verification results

- 13 skoncentrowanych testów storage przeszło.
- Pełny pion API/storage, Ruff, mypy i kontrola OpenAPI przeszły.
- Rzeczywisty produkcyjny odczyt największej gry: 4,669 s przy limicie 15 s;
  6 220 575 wszystkich, 38 542 zatwierdzone i 6 182 033 oczekujące komórki.
- Kontrolne stare zapytanie zwróciło te same wartości; pomiary wąskich filtrów
  potwierdziły zasadność zachowania ich dotychczasowego planu.

### Not completed

- Nie dodano tabeli/cache liczników, migracji ani zmian UI, zgodnie z zakresem.
- Globalny `npm run format:check` nadal zgłasza 35 wcześniejszych, niezwiązanych
  plików. Żaden plik zmieniony przez TASK-0500 nie znajduje się na tej liście.

### Documentation updates

- Zaktualizowano wymagania Admina, kontrakt API, analizę skalowalności,
  `CURRENT_STATE.md` oraz Decision Log D-370.

### Recommended next task

- Brak; plan ograniczonych i anulowalnych odczytów Weryfikacji symboli jest
  zakończony.
