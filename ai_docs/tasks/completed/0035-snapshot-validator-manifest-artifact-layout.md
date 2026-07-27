---
title: Snapshot validator, manifest and artifact layout
status: done
last_updated: 2026-07-27
---

# TASK-0035 — Snapshot validator, manifest and artifact layout

## Status

`done`

## Goal

Domknąć M3.3 deterministycznym manifestem, niezależnym pełnym przebiegiem
walidacji SQLite i niezmiennym katalogiem artefaktu, który może być bezpiecznym
wejściem przyszłego Android build workflow.

## Context

TASK-0034 generuje produkcyjny SQLite schema v2 z dokładnych wersji PostgreSQL,
wyznacza logiczny oraz plikowy SHA-256 i nie nadpisuje pliku. Brakuje jeszcze
kanonicznego manifestu, pełnej kontroli zawartości po zapisie i atomowej
publikacji całego katalogu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- produkcyjny manifest schema version 1 bez pól fixture,
- wszystkie globalne wersje, checksumy i liczniki,
- per-game: kod, mobilny id, kanoniczne UUID oraz numery dataset/rules,
- niezmienna ścieżka
  `snapshots/<releaseVersion>/<logicalContentSha256>/`,
- atomowa publikacja katalogu zawierającego tylko `snapshot.db` i
  `manifest.json`,
- idempotentny retry wyłącznie przez ponowną walidację identycznego artefaktu,
- ścisły parser manifestu ze stabilnymi kodami błędów,
- niezależny read-only przebieg walidacji schema, metadata, wersji, checksum,
  liczników, sekwencji, symboli, sygnatur, payoutów, FK i indeksu,
- strumieniowa rekonstrukcja logicznego checksumu,
- testy deterministyczności i kontrolowanych uszkodzeń.

## Out of scope

- `mobile_releases`, API, panel i snapshot job handler,
- Android build, kopiowanie do `apps/mobile` i instalacja APK,
- aktywacja nowego snapshotu na urządzeniu,
- sprzątanie historycznych artefaktów,
- benchmark 500 000 layoutów,
- zmiana schema SQLite albo migracja PostgreSQL.

## Acceptance criteria

- [x] Manifest ma ścisły `manifestVersion = 1` i nie zawiera fixture/golden.
- [x] Manifest zawiera release, schema, algorithm, czas, oba checksumy i
  dokładne liczniki.
- [x] Każda gra ma dataset/rules UUID i numer wersji oraz parametry mobilne.
- [x] Identyczne wejście tworzy identyczny manifest i tę samą ścieżkę.
- [x] Katalog końcowy zawiera wyłącznie `snapshot.db` i `manifest.json`.
- [x] Poprzedni artefakt nigdy nie jest nadpisywany.
- [x] Identyczny retry zwraca istniejący artefakt dopiero po pełnej walidacji.
- [x] Walidator otwiera SQLite read-only i rekonstruuje logiczny checksum.
- [x] Walidator wykrywa brak/obce pole manifestu, zły layout katalogu, checksum,
  schema, metadata, licznik, lukę, obcy symbol, błędną sygnaturę, payout, FK i
  indeks.
- [x] Duplikaty sygnatur pozostają dozwolone.
- [x] Uszkodzenie lub niepełny staging nie publikuje katalogu końcowego.
- [x] Testy standardowe i fizyczny PostgreSQL przechodzą.

## Assumptions

- `releaseVersion` jest bezpiecznym segmentem ścieżki zgodnym z TASK-0034.
- Pełny logiczny SHA-256 jest segmentem katalogu i identyfikatorem treści;
  manifest dodatkowo zapisuje SHA-256 fizycznego pliku.
- Manifest jest deterministycznym JSON UTF-8 z sortowanymi kluczami i końcowym
  newline; nie zawiera ścieżek absolutnych ani czasu wykonania.
- Identyczny istniejący katalog jest wynikiem poprawnego retry tylko wtedy, gdy
  przejdzie pełną walidację i jego manifest jest równy oczekiwanemu.
- Walidator współdzieli kanoniczny codec logicznego checksumu z generatorem,
  ale wykonuje osobny odczyt gotowego SQLite i nie ufa metadata ani manifestowi.
- Integracja z typowanym snapshot jobem czeka na `mobile_releases` w M3.4.

## Expected files

- `services/worker/src/game_predictor_worker/snapshots/integrity.py`
- `services/worker/src/game_predictor_worker/snapshots/manifest.py`
- `services/worker/src/game_predictor_worker/snapshots/validator.py`
- `services/worker/src/game_predictor_worker/snapshots/artifacts.py`
- testy production snapshot i fizycznego PostgreSQL
- dokumentacja architektury, testów, decyzji i bieżącego stanu

## Verification

```powershell
pytest services/worker/tests/test_snapshot_artifact.py -q
pytest services/api/tests/integration/test_production_snapshot_store.py -q
npm run quality
```

## Risks / open questions

- Brak pytania blokującego. Koszt pełnego odtworzenia logicznego checksumu dla
  kilku milionów layoutów zostanie zmierzony w M3.5.

## Outcome

- Dodano ścisły manifest produkcyjny schema v1 z kanoniczną serializacją,
  globalnymi checksumami i licznikami oraz identyfikatorami i wersjami per gra.
- Artefakty są budowane w stagingu, w pełni walidowane i atomowo publikowane do
  `snapshots/<releaseVersion>/<logicalContentSha256>/` bez nadpisywania.
- Niezależny walidator otwiera SQLite read-only, sprawdza układ katalogu,
  manifest, schema, metadata, FK, indeks, sekwencje, symbole, sygnatury i
  payouty oraz strumieniowo odtwarza logiczny SHA-256.
- Idempotentny retry ponownie waliduje istniejący artefakt; kolizja albo
  uszkodzenie kończy się stabilnym błędem bez modyfikacji istniejących danych.
- Przeszła pełna bramka jakości: 195 standardowych testów Python, 63 mobile,
  51 panelu, 23 wspólnej domeny i 8 klienta API oraz 6 fizycznych testów
  PostgreSQL. Zaliczono G3.3 i zamknięto M3.3.
