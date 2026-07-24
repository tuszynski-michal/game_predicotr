---
title: TASK-0004 Payout engine and golden tests
status: done
last_updated: 2026-07-24
completed_at: 2026-07-24
---

# TASK-0004 — Payout engine and golden tests

## Goal

Zaimplementować czysty build-time payout engine w Pythonie i udowodnić jego
zgodność z zaakceptowanymi regułami za pomocą niezależnie opisanych golden
fixtures dla planszy M1 3 × 5.

## Context

TASK-0003 dostarczył kontrakty, codec i walidację graniczną. TASK-0004 dodaje
wyłącznie ocenę wypłat wykonywaną podczas przygotowania wydania. Mobile będzie
otrzymywać gotowy `total_payout` i nie uruchomi tego algorytmu w runtime.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0003-contracts-signature-codec-validation.md`

## Scope

- czysta funkcja oceny pełnego layoutu bez I/O i frameworków,
- odczyt payline po jednej komórce z każdej kolumny,
- ciąg rozpoczynający się w dowolnej kolumnie i przerywany luką,
- długości wygrywające 3, 4 i 5,
- wyłącznie najdłuższa skonfigurowana długość dla jednego ciągu,
- joker na początku, w środku i na końcu,
- odrzucenie ciągu złożonego wyłącznie z jokerów,
- niezależna interpretacja jokera dla każdej pary payline/symbol,
- sumowanie wszystkich prawidłowych par oraz przecinających się paylines,
- strukturalny audit: komórki, jokery i ich interpretacje,
- walidacja kompletności i rosnących wartości macierzy payoutów przed
  precomputingiem,
- jawne odrzucenie planszy szerszej niż pięć kolumn,
- współdzielone, ręcznie opisane golden fixtures JSON,
- test deterministyczności i testy błędnej konfiguracji.

## Out of scope

- Target forecast i pełny cykl `N - 1`,
- zapis payoutów do PostgreSQL albo SQLite,
- generator 3 × 1000 layoutów,
- jobs, raportowanie postępu i wznawianie,
- UI oraz konfiguracja panelu admina,
- semantyka kilku rozłącznych wygrywających ciągów na planszy szerszej niż
  pięć kolumn.

## Acceptance criteria

- [x] Funkcja ma deterministyczne, niemutowalne wejścia i wyjście.
- [x] Długość 2 nie wygrywa, a luka przerywa ciąg.
- [x] Ciąg może zaczynać się w kolumnie 0, 1 albo 2.
- [x] Długości 3, 4 i 5 zwracają właściwe payouty.
- [x] Długość 5 nie sumuje reguł dla długości 3 i 4.
- [x] Joker działa na początku, w środku i na końcu.
- [x] Ciąg złożony wyłącznie z jokerów nie wygrywa.
- [x] Ten sam joker może mieć różne interpretacje na różnych paylines.
- [x] Wszystkie prawidłowe symbole i paylines są sumowane, także gdy dzielą
  komórki.
- [x] Audit używa indeksów komórek `row-major` i kolumn 0-based.
- [x] Duplikaty, brakujące reguły, payouty, które nie rosną wraz z długością,
  i szerokość ponad M1 kończą się stabilnym kodem błędu.
- [x] Golden fixtures zawierają oczekiwane sumy i pełny audit policzony poza
  implementacją.
- [x] Kod domenowy nie importuje SQLite, FastAPI, ORM, React ani Expo.
- [x] Format, lint, typecheck i wszystkie testy przechodzą.
- [x] `CURRENT_STATE.md` i Outcome są zaktualizowane.

## Technical notes

- `start_column`, `matched_cells` i `joker_cells` są 0-based.
- Indeks komórki to `row * columns + column`.
- Interpretacja jokera jest strukturą
  `(cell_index, as_symbol_mobile_code)`, a nie tekstem do parsowania.
- Kolejność audit matches zachowuje kolejność wejściowych paylines, następnie
  `display_order` symboli i `start_column`.
- Konfiguracja gotowa do precomputingu zawiera po jednej regule dla każdego
  zwykłego symbolu i każdej długości `3..columns`; payout rośnie wraz z
  długością.

## Expected files

- `services/worker/src/game_predictor_worker/domain/payout.py`
- `services/worker/src/game_predictor_worker/domain/contracts.py`
- `services/worker/src/game_predictor_worker/domain/errors.py`
- `packages/shared-ts/src/contracts.ts`
- `packages/shared-ts/src/errors.ts`
- `packages/domain-fixtures/payout-golden-cases.json`
- `services/worker/tests/test_payout.py`
- dokumentacja wymagań i procesu

## Verification

```powershell
npm run quality
```

## Risks / open questions

- Plansze szersze niż pięć kolumn są świadomie blokowane do czasu
  rozstrzygnięcia semantyki kilku rozłącznych ciągów.
- Fixture M1 używa wartości testowych; finalne wartości będą pochodzić z
  wersjonowanej konfiguracji admina.

## Outcome

Zadanie zakończone. Build-time worker ma czysty, deterministyczny payout engine
zgodny z regułami M1 oraz ręcznie opisany zestaw golden cases z pełnym audytem.

### Changed

- dodano `evaluate_payout` bez I/O i zależności frameworkowych,
- zaimplementowano ciągi zaczynające się w dowolnej kolumnie, longest match,
  przerwanie przez lukę, jokera oraz sumowanie wszystkich par
  payline/symbol,
- dodano strukturalny `JokerInterpretation` w kontraktach Python i TypeScript,
- dodano walidację pełnej macierzy payoutów, ścisłego wzrostu wartości i
  granicy pięciu kolumn dla algorytmu v1,
- dodano dziewięć golden cases z ręcznymi obliczeniami i pełnym audytem,
- dodano stabilne błędy dla brakujących reguł, wartości, które nie rosną
  ściśle, i nieobsługiwanej szerokości,
- zapisano D-016 oraz zsynchronizowano wymagania, model danych i strategię
  testów.

### Verification results

- `npm run quality` — passed:
  - Prettier, Expo ESLint i Ruff,
  - TypeScript strict dla mobile i `shared-ts`,
  - mypy strict dla 10 plików źródłowych Python,
  - testy payout: 15/15,
  - wszystkie testy Python: 27/27,
  - testy kontraktu TypeScript: 9/9,
  - testy mobile: 4/4,
  - walidacja diagnostycznego snapshotu.
- `git diff --check` — passed.

### Not completed

- nie implementowano Target engine ani pełnego cyklu; to TASK-0005,
- nie zapisywano payoutów w SQLite/PostgreSQL i nie tworzono jobs,
- nie rozstrzygano wielu rozłącznych ciągów dla plansz szerszych niż pięć
  kolumn; algorytm v1 jawnie je blokuje.

### Documentation updates

- `ALGORITHMS.md` opisuje indeksowanie audytu, pełną macierz reguł i guard v1,
- `DATA_MODEL.md` rozróżnia niekompletny draft od konfiguracji gotowej do
  precomputingu,
- `TEST_STRATEGY.md` zawiera przypadki błędnej macierzy i szerokości,
- `DECISION_LOG.md` zawiera D-016.

### Recommended next task

Po osobnym poleceniu właściciela:

```text
TASK-0005 — Target engine and golden tests
```
