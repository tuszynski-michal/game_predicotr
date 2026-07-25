---
title: TASK-0090 Payout v2 left prefix and snapshot
status: done
last_updated: 2026-07-24
---

# TASK-0090 — Payout v2 left prefix and snapshot

## Goal

Zastąpić payout-v1 przez deterministyczny payout-v2 zgodny z D-019, a następnie
wygenerować spójne fixture, golden Target i mobilny snapshot gotowy do nowego
builda APK.

## Context

D-019 zmieniła zaakceptowaną semantykę po ukończeniu pierwotnych bramek
M1.2–M1.6. Obecny kod wyszukuje ciągi od dowolnej kolumny, zakłada stałe
minimum 3 i odrzuca plansze szersze niż 5 kolumn. Generator, snapshot i APK
zawierają wynik payout-v1, dlatego M2 i odbiór urządzeń są zablokowane.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DECISION_LOG.md` — D-019
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/tasks/completed/0003-contracts-signature-codec-validation.md`
- `ai_docs/tasks/completed/0004-payout-engine-golden-tests.md`
- `ai_docs/tasks/completed/0006-deterministic-fixture-generator.md`
- `ai_docs/tasks/completed/0007-sqlite-snapshot-generator.md`

## Scope

- zgodne kontrakty TypeScript/Python konfiguracji minimum per symbol,
- walidacja progu `2..columns`, jokera, kompletności i rosnących payoutów,
- payout wyłącznie dla ciągłego prefiksu od pierwszej kolumny,
- `start_column = 0` dla każdego audytowanego dopasowania,
- brak dawnej granicy pięciu kolumn,
- golden tests dla minimum 2/3, luk, późnego startu, jokera i longest match,
- wersje `payout-v2`, fixture/dataset/rules v2,
- regeneracja deterministycznego fixture, golden Target, SQLite i manifestu,
- aktualizacja testów mobilnych zależnych od metadanych lub golden values.

## Out of scope

- PostgreSQL, Alembic, FastAPI i panel administracyjny M2,
- zmiana algorytmu Target,
- zmiana schematu mobilnego SQLite,
- build i podpisanie nowego APK,
- testy Pixel/Samsung.

## Acceptance criteria

- [x] Zwycięski ciąg może rozpocząć się wyłącznie w pierwszej kolumnie.
- [x] Symbol z minimum 2 wygrywa za dwie pierwsze zgodne kolumny.
- [x] Symbol z minimum 3 nie wygrywa za długość 2.
- [x] Pierwsza luka kończy dopasowanie i późniejsze symbole nie są liczone.
- [x] Joker zachowuje ślad interpretacji, a ciąg samych jokerów nie wygrywa.
- [x] Dla jednej pary payline/symbol liczona jest najdłuższa długość.
- [x] Konfiguracja wymaga wszystkich długości od minimum do `columns`.
- [x] Plansza szersza niż 5 kolumn ma jednoznaczny wynik prefiksowy.
- [x] TypeScript i Python odrzucają te same błędne kontrakty.
- [x] Fixture, fingerprint, snapshot, manifest i golden Target są spójne z v2.
- [x] Wszystkie składowe `npm run quality` przechodzą.

## Technical notes

- Build-time kontrakt powinien modelować wersjonowaną konfigurację symbolu
  oddzielnie od globalnego `SymbolDefinition`.
- Mobile nie otrzymuje pełnych reguł; nadal czyta wyłącznie precomputed payout.
- Snapshot schema pozostaje w wersji 2, ponieważ zmienia się treść i metadata,
  nie struktura tabel.
- Nie utrzymujemy równolegle aktywnego engine’u payout-v1.

## Expected files

- `packages/shared-ts/src/contracts.ts`
- `packages/shared-ts/src/validation.ts`
- `packages/domain-fixtures/domain-contract-cases.json`
- `packages/domain-fixtures/payout-golden-cases.json`
- `services/worker/src/game_predictor_worker/domain/`
- `services/worker/src/game_predictor_worker/fixtures/`
- `services/worker/tests/`
- `apps/mobile/assets/snapshot/`
- zależne testy i dokumentacja procesu

## Verification

```powershell
npm run quality
```

## Risks / open questions

- Kontrolowane layouty payout mogą zmienić sygnatury, więc wszystkie checksumy
  i golden Target muszą pochodzić z jednego przebiegu generatora.
- Snapshot v2 treści nie oznacza zmiany `snapshot_schema_version`; nazwy wersji
  datasetu, reguł, fixture i algorytmu muszą rozróżniać nowe dane.

## Outcome

- Dodano `PayoutSymbolDefinition` i zgodną walidację TypeScript/Python dla
  minimum `2..columns`, jokera, duplikatu konfiguracji oraz kompletności reguł.
- Engine analizuje wyłącznie zgodny prefiks od kolumny `0`, zatrzymuje się na
  pierwszej luce, wybiera najdłuższą regułę i nie przyznaje wygranej samym
  jokerom. Usunięto sztuczną granicę pięciu kolumn.
- Zastąpiono golden payout zestawem `payout-v2`, obejmującym minima 2/3,
  późniejszy start, lukę, longest match, jokery, współdzielone komórki i
  szerokość 6.
- Generator tworzy `m1-fixture-v2`, dataset/rules version `2` i algorytm
  `payout-v2`. Nowy fingerprint to
  `2b8345577ec949f102ae21992cef197e5c5756e184d43815a5dd527d25eb2b79`.
- Wygenerowano oraz zweryfikowano snapshot `m1-fixture.2`; SHA-256 SQLite:
  `4365a33d066a354d212693cd9169dac102b7cb1c164df6693f655e8690e9224a`.
- Golden Target zachowały kontrolowane sumy i szczyty. Zaktualizowano mobilne
  metadane testowe oraz protokół odbioru o nowe layouty.
- Weryfikacja: Prettier, ESLint, Ruff, PowerShell syntax, TypeScript/Python
  typecheck, `62` testy mobile, `23` shared-ts, `53` Python, walidacja fixture
  i snapshotu. Jedno zbiorcze uruchomienie `npm run quality` przekroczyło limit
  narzędzia; każda jego składowa przeszła osobno, a wcześniejszy pojedynczy
  timeout testu mobilnego nie powtórzył się.
- Nie wykonano builda APK ani testów fizycznych; pozostają w TASK-0014.
