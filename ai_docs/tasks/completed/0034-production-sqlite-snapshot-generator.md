---
title: Production SQLite snapshot generator
status: done
last_updated: 2026-07-27
---

# TASK-0034 — Production SQLite snapshot generator

## Status

`done`

## Goal

Zastąpić fixture-only ścieżkę M1 produkcyjnym, bounded-memory generatorem
niezmiennego SQLite schema v2 z opublikowanych wersji PostgreSQL i dokładnych
precomputed payoutów.

## Context

M1 udowodnił schemat i semantykę mobilnego SQLite na deterministycznym fixture.
M3.2 dostarczył trwałe payouty oraz bramkę kompletności dla dokładnej kombinacji
dataset/rules/algorithm. Generator M3.3 ma połączyć te elementy bez zależności od
fixture, przyszłej tabeli `mobile_releases` ani transportu HTTP.

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

- typowany kontrakt snapshotu i wyboru wielu gier,
- produkcyjny adapter PostgreSQL dla gry, symboli, layoutów i payoutów,
- obowiązkowa bramka gotowości TASK-0033 dla każdej dokładnej kombinacji,
- deterministyczne przypisanie mobilnych identyfikatorów gier,
- SQLite schema version 2 zgodny z kontraktem M1,
- deterministyczna i strumieniowa serializacja layoutów partiami,
- logiczny SHA-256 treści zapisany w metadata,
- atomowa publikacja kompletnego pliku bez nadpisania istniejącego celu,
- testy jednostkowe i fizycznego PostgreSQL.

## Out of scope

- zewnętrzny manifest, jego schema i niezależny walidator artefaktu,
- niezmienny katalog release i polityka nazw artefaktów,
- `mobile_releases`, publiczne API, panel i snapshot job handler,
- kopiowanie obrazów symboli do assetów Android,
- Android build i podmiana assetu aplikacji,
- benchmark 500 000 layoutów i decyzja TEXT kontra BLOB,
- zmiana schema SQLite lub migracja PostgreSQL.

## Acceptance criteria

- [x] Generator przyjmuje jawne wybory dataset/rules/algorithm i release metadata.
- [x] Każdy wybór przechodzi dokładną bramkę gotowości przed utworzeniem pliku.
- [x] Gry są serializowane deterministycznie niezależnie od kolejności wejścia.
- [x] Layouty są pobierane keysetowo i zapisywane partiami bez pełnej
  materializacji.
- [x] SQLite zawiera wyłącznie metadata, games, symbols i layouts oraz wymagany
  indeks signature.
- [x] Metadata zawiera release, schema, algorithm, czas, liczniki i logiczny
  checksum.
- [x] Dataset/rules version są zapisane osobno dla każdej gry.
- [x] Staging, brak payoutu dokładnej wersji lub brak audytu blokuje generowanie.
- [x] Identyczne logiczne wejście i metadata tworzą identyczne bajty SQLite.
- [x] Istniejący plik docelowy nie jest nadpisywany.
- [x] Exact, duplicate, prefix i cykliczny odczyt zachowują semantykę M1.
- [x] Testy standardowe i fizyczny PostgreSQL przechodzą.

## Assumptions

- Wszystkie gry jednego snapshotu używają jednej wersji algorytmu, ponieważ
  `algorithm_version` jest globalnym metadata schema v2.
- Produkcyjny snapshot nie zapisuje pól fixture ani golden cases.
- `image_path` symbolu jest serializowane jako opcjonalny `image_asset_key`;
  materializacja samego obrazu pozostaje zakresem późniejszego build workflow.
- Jawny `release_version` i `created_at` są wejściami generatora, więc nie
  zależą od zegara ani UUID powstałych podczas wykonania.
- TASK-0035 zdefiniuje manifest, katalog artefaktu i pełną niezależną walidację;
  TASK-0034 waliduje wejście oraz constraints podczas zapisu.
- Rejestracja snapshot joba czeka na `mobile_releases`, które zgodnie z planem
  powstają w M3.4.

## Expected files

- `services/worker/src/game_predictor_worker/snapshots/contracts.py`
- `services/worker/src/game_predictor_worker/snapshots/generator.py`
- `services/worker/src/game_predictor_worker/snapshots/store.py`
- `services/worker/tests/test_production_snapshot.py`
- `services/api/tests/integration/test_production_snapshot_store.py`
- dokumentacja architektury, testów, decyzji i bieżącego stanu

## Verification

```powershell
pytest services/worker/tests/test_production_snapshot.py -q
pytest services/api/tests/integration/test_production_snapshot_store.py -q
npm run quality
```

## Risks / open questions

- Brak pytania blokującego. Wydajność i rozmiar przy 500 000 layoutów oraz
  przydatność indeksu TEXT pozostają jawną bramką M3.5.

## Outcome

- Dodano typowany produkcyjny generator SQLite schema v2 i adapter PostgreSQL
  dla dokładnych wyborów dataset/rules/algorithm.
- Generator wymaga gotowości payoutów, porządkuje gry po stabilnym kodzie,
  symbole po `mobile_code` i zapisuje layouty keysetowo w bounded partiach.
- Logiczny SHA-256 powstaje strumieniowo razem z zapisem, a plik docelowy jest
  publikowany dopiero po pełnym sukcesie i nigdy nie jest nadpisywany.
- Testy pokrywają identyczne bajty niezależnie od kolejności wejścia, schema i
  metadata bez fixture, exact/duplicate/prefix/cycle, blokady gotowości, lukę w
  strumieniu, istniejący cel i dokładny payout-v2 obok historycznego payout-v1.
- Pełna bramka przeszła: 179 standardowych testów Python, 63 mobile, 51 panelu,
  23 wspólnej domeny i 8 klienta API; dodatkowo przeszło 6 fizycznych testów
  PostgreSQL.
