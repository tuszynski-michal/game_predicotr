---
title: TASK-0745 — T4 — filtry źródła predykcji i zakresu dat zmiany w API weryfikacji symboli
status: done
last_updated: 2026-09-30
---

# TASK-0745 — T4 — filtry źródła predykcji i zakresu dat zmiany w API weryfikacji symboli

## Status

`done`

## Goal

Lista, pomijanie, liczniki i operacje masowe weryfikacji symboli przyjmują
opcjonalne filtry: źródło bieżącej predykcji komórki (nowy algorytm / stary
model) oraz zakres dat ostatniej zmiany komórki (od–do).

## Context

D-466: operator chce po zapisie biblioteki wzorców (B1) oddzielić komórki
zmienione przez nowy algorytm od pozostałych i zawęzić je do dnia zapisu.

## Dependencies / entry conditions

- TASK-0744 done (`MODEL_VERSION = symbol-reference-library-v1`).

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: `claude-fable-5-1`,
reasoning `medium` na polecenie operatora (poziomu nie da się ustawić z
sesji; rekomendacja warunkowa), osobny agent.

## Relevant docs

- `ai_docs/delivery/SYMBOL_REFERENCE_LIBRARY_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-466)

## Scope

- Domena: `SymbolCellReviewPredictionSource` (`reference_library`, `model`),
  pola `prediction_source`, `changed_from`, `changed_to` w filtrze listy i w
  wyborze filtra operacji masowej, walidacja zakresu, kursor związany z
  filtrami rozszerzonymi.
- Repozytorium: wspólne klauzule `extended_symbol_cell_review_filter_clauses`
  dla listy, liczników i operacji masowych.
- HTTP: parametry `predictionSource`, `changedFrom`, `changedTo`
  (`AwareDatetime`) dla listy, pomijania i liczników; pola w żądaniu
  operacji masowej.
- OpenAPI, wygenerowany klient, wrapper `packages/admin-api-client`, testy.

## Out of scope

- UI Admina (TASK-0746), migracje i nowe indeksy.

## Acceptance criteria

- [x] Bez nowych parametrów zapytania, kursory i odciski operacji masowych
  są identyczne jak wcześniej.
- [x] `reference_library` = bieżąca wersja predykcji komórki ma
  `model_version = symbol-reference-library-v1`, a wpis tej komórki w
  predykcjach tej wersji ma klucz `referenceLibrary`; `model` = dopełnienie
  (także brak wersji). Wersja biblioteki obejmuje całą planszę, więc sama
  wersja nie wystarcza: komórki bez pewnej propozycji zachowują predykcję
  modelu i są „starym modelem”.
- [x] Zakres dat obejmuje oba końce, wymaga strefy czasowej, `od ≤ do`;
  inaczej 422 / kod `SYMBOL_CELL_REVIEW_CHANGED_RANGE_INVALID`
  (`…_BULK_CHANGED_RANGE_INVALID` dla operacji masowej).
- [x] Kursor z filtrami rozszerzonymi nie działa bez nich (409
  `SYMBOL_CELL_REVIEW_CURSOR_SCOPE_INVALID`).
- [x] Backend, OpenAPI, klient, wrapper i test żądania razem; Ruff, mypy,
  testy; audyt bez P0–P2.

## Technical notes

- Filtr daty działa na `image_symbol_review_cells.updated_at`
  (`onupdate=now()`); zapis biblioteki i każda decyzja operatora go zmieniają.
  Zapis biblioteki zmienia `updated_at` wszystkich 15 komórek planszy (nowa
  wersja predykcji), więc komórki zmienione przez algorytm wybiera filtr
  źródła, a data tylko zawęża.
- Przy filtrach rozszerzonych liczniki nie korzystają z tabeli liczników
  (`_basic_count_scope` zwraca `None`) i liczą dokładnie.

## Test cases

- `services/api/tests/test_symbol_review_extended_filters.py` (klauzule SQL,
  walidacja, kursor, odcisk operacji masowej).
- `test_list_endpoint_passes_prediction_source_and_changed_range` (HTTP).
- `packages/admin-api-client/test/client.test.mjs`: parametry wysyłane tylko,
  gdy ustawione.

## Outcome

- Zmiany jak w zakresie. Wrapper: wspólny typ
  `SymbolCellReviewExtendedFilterOptions` dla listy, pomijania i liczników.
- Pierwsza wersja filtra (`prediction_revision_id IN` wersje biblioteki)
  została poprawiona po kanarku B1 (3 plansze): pokazywała też komórki
  planszy, których biblioteka nie przepisała. Obecnie skorelowany `EXISTS`
  (alias `library_revision`, jawne `correlate` do komórki, bo część
  instrukcji już łączy wersję predykcji) z zawieraniem JSONB wpisu komórki
  (`rowIndex` = `row_index`, `columnIndex` = `column_index`,
  `referenceLibrary`). Test kompiluje listę, liczniki i operację masową z
  filtrem pewności w obu ścieżkach projekcji.
- UTC w kursorze i odcisku operacji masowej (`utc_isoformat`): ten sam
  moment w innej strefie nie unieważnia kursora.
- Pomiar na grze 777 (7,5 mln komórek; Arbuz pending 901 145) przez
  tymczasowe API z worktree po pełnym zapisie B1: lista Arbuz
  `reference_library` 0,9 s, liczniki 0,76 s (2 621); liczniki
  `reference_library` dla wszystkich symboli 3,2 s (2 917); liczniki
  `model` + data 2,4 s; lista `model` + pewność < 60% dla Arbuz 4,8 s
  (skan bez indeksu na `updated_at` / źródło). Akceptowalne dla lokalnego
  Admina; indeks wymagałby migracji na 7,5 mln wierszy i nie jest potrzebny.
- Audyt `claude-fable-5-1`: runda 1 PASS dla pierwszej wersji (uwagi P2
  procesowe i P3 wdrożone), runda 2 FAIL (P2: auto-korelacja `EXISTS` w
  instrukcjach z joinem wersji — błąd kompilacji w ścieżce legacy) —
  poprawione aliasem i `correlate`, runda 3 — patrz CURRENT_STATE.
- Weryfikacja: testy filtrów (klauzule, walidacja, kursor, odcisk,
  kompilacja z joinem), testy HTTP listy i operacji masowej, 74 testy API /
  storage / filtrów, 83 testy repozytorium i domeny, 67 testów klienta;
  Ruff, mypy `--strict`, OpenAPI i klient wygenerowane.
  Istniejący wcześniej błąd `test_list_endpoint_uses_keyset_cursors_without_duplicates`
  (oczekuje limitu 5 000, jest 20 000) występuje także bez tych zmian — poza
  zakresem.
