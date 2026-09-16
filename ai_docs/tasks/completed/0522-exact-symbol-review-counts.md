---
title: Exact symbol review counts
status: in_progress
last_updated: 2026-09-09
---

# TASK-0522 — Dokładne liczniki Weryfikacji symboli

## Status

`done`

## Goal

Zapewnić dokładne, transakcyjne i szybko odczytywalne liczniki podstawowych filtrów Weryfikacji symboli dla magazynu V2.

## Dependencies / entry conditions

TASK-0520 i TASK-0521 są ukończone; V2 posiada bieżącą projekcję komórek i indeksowane odczyty listy.

## Recommended execution

`gpt-6-astra high`; dodatkowy audyt `gpt-6-astra high` obejmuje idempotencję, retry i kolejność blokad.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- zaakceptowany plan partycjonowania danych gier

## Scope

- Transakcyjna projekcja liczników podstawowych filtrów.
- Delta wyliczana ze stanu komórki przed i po mutacji.
- Wznawialna rekonstrukcja per gra z checkpointem.
- Dokładne zapytania SQL dla confidence i aktywnej kohorty.

## Out of scope

- Zmiana semantyki filtrów.
- Migracja istniejącej gry użytkownika albo uruchamianie jobów.
- Lifecycle partycji, realizowany w TASK-0523.

## Acceptance criteria

- [x] Podstawowe liczniki V2 nie skanują tabeli komórek.
- [x] Mutacja pojedyncza, zbiorcza i recrop stosują zagregowaną deltę dokładnie raz.
- [x] Rekonstrukcja jest wznawialna i w czasie jej trwania licznik jest jawnie niedostępny.
- [x] Filtry confidence i kohorty pozostają dokładnym, ograniczonym czasowo SQL.

## Technical notes

Licznik obejmuje wyłącznie `source_available`. Zakres `?` oznacza brak przypisanego symbolu albo `grid_issue`/`unreadable`; zakres konkretnego symbolu wymaga zgodnego `assigned_symbol_id` oraz braku `quality_issue`. Stan `all` jest sumą `approved` i `pending`. Projekcja i checkpoint są utrwalane przy stanie gry w tej samej partycji i transakcji co komórki.

## Expected files

- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
- `services/api/alembic/versions/0109_exact_symbol_review_counts.py`
- testy storage i migracji
- dokumentacja procesu i architektury

## Test cases

- No-op retry nie zmienia licznika.
- Zbiorcza zmiana wielu komórek stosuje jedną zagregowaną deltę.
- Recrop usuwa poprzedni zakres i dodaje nowy.
- Restart rekonstrukcji kontynuuje po UUID checkpointu.
- API nie zwraca zera, gdy licznik jest `rebuilding`.

## Verification

Skoncentrowane testy API/storage, Ruff i scoped mypy; następnie audyt staged diff.

## Risks / open questions

- Historyczny magazyn publiczny zachowuje dotychczasowy licznik SQL; projekcja liczników jest używana wyłącznie przez V2.

## Outcome

### Changed

- Dodano migrację 0109, transakcyjną projekcję liczników i keysetową rekonstrukcję.
- Podstawowe liczniki V2 czytają wyłącznie stan gry; confidence i kohorta zachowują SQL.
- Writer, bulk mutation, backfill oraz recrop aktualizują licznik ze stanu przed/po.

### Verification results

- 48 skoncentrowanych testów projekcji, backfillu, query i geometrii passed.
- 7 testów toru migracji/schema passed; Ruff i scoped mypy passed.

### Not completed

- Migracji nie zastosowano na bazie użytkownika; nie uruchomiono rekonstrukcji danych.

### Documentation updates

- Zaktualizowano ADMIN_APP, API_CONTRACT i CURRENT_STATE.

### Recommended next task

- TASK-0523 — lifecycle partycji gry.
