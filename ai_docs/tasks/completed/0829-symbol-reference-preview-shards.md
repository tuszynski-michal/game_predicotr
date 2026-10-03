---
title: TASK-0829 — podział zakresu podglądu biblioteki wzorców na części (`--shard`)
status: done
last_updated: 2026-10-03
---

# TASK-0829 — podział zakresu podglądu biblioteki wzorców na części (`--shard`)

## Status

`done`

## Goal

`preview` i `apply-preview` w `scripts/evaluate_symbol_reference_library.py`
obsługują zakres zbyt duży na jeden cache wycinków, którego nie da się podzielić
pewnością (np. 341 766 oczekujących komórek Śliwka z pewnością dokładnie 100%).

## Context

Polecenie operatora 2026-10-03: po Winogronie (TASK-0828) przepuścić Śliwkę
≥ 99%. Narzędzie przy każdym wznowieniu wczytuje i zapisuje cały cache wycinków
(~12 KB na komórkę), więc zakres 342 tys. komórek oznaczałby ~4,2 GB cache i
~9 GB szczytowej pamięci procesu na rundę. Wszystkie te komórki mają tę samą
pewność, więc podział `--min/--max-confidence` nie działa.

## Dependencies / entry conditions

- Brak; zmiana tylko w narzędziu offline, bez API i bez migracji.

## Recommended execution

`claude-opus-5-5`, reasoning `high`; audyt wstrzymany decyzją operatora
z 2026-10-01 (bez agentów audytowych, chyba że operator poprosi).

## Relevant docs

- `ai_docs/tasks/0828-symbol-reference-library-winogron-99-100.md`

## Scope

- Argument `--shard INDEX/COUNT` (domyślnie `0/1`) w `preview`, dziedziczony
  przez `apply-preview`.
- Warunek SQL w `_PREVIEW_SQL` i `_PREVIEW_SCOPE_SQL`:
  `mod(('x' || left(md5(id), 7))::bit(28)::int, COUNT) = INDEX` — stały,
  rozłączny podział po identyfikatorze komórki.
- `parameters.shard` w `preview.json` (i przez to w sumie kontrolnej rewizji
  zapisu) tylko dla `COUNT > 1`, więc przebiegi bez podziału liczą te same sumy
  co wcześniej.

## Out of scope

- Przyspieszenie `_with_render_specs` (osobna propozycja zadania), zmiany zapisu
  (`apply`, `apply-verify`), API i UI.

## Acceptance criteria

- [x] Części są rozłączne i razem dają cały zakres.
- [x] Błędny argument jest odrzucany przez `argparse`.
- [x] Testy, Ruff, format i mypy dla zmienionych plików bez nowych błędów.

## Test cases

- `test_shard_is_parsed_and_inherited_by_apply_preview`,
  `test_invalid_shard_is_rejected`, `test_shard_clause_is_part_of_both_preview_queries`.
- Odczyt bazy operatora (tylko do odczytu): Śliwka 100%, `--shard i/6` daje
  56 919 / 56 762 / 57 049 / 57 152 / 57 076 / 56 808 = 341 766 komórek, tyle
  samo co zapytanie bez podziału.

## Outcome

- Dodano `_shard`, `_SHARD_CLAUSE`, argument `--shard` i klucz `shard` w
  parametrach podglądu. 32 testy pliku PASS, Ruff i format PASS, mypy bez błędów
  w skrypcie (błędy mypy w `api/v7_label_geometry_calibration.py` i innych
  plikach są wcześniejsze i niezwiązane).
- Audyt nie był uruchamiany (wstrzymany przez operatora 2026-10-01).
