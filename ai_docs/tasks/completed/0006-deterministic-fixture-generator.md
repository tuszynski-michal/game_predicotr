---
title: TASK-0006 Deterministic fixture generator and sequence validator
status: done
last_updated: 2026-07-24
completed_at: 2026-07-24
---

# TASK-0006 — Deterministic fixture generator and sequence validator

## Goal

Zbudować czysty, deterministyczny generator fixture M1 dla 3 gier po 1000
layoutów oraz walidator, który odrzuca nieciągłą albo niespójną sekwencję przed
utworzeniem snapshotu SQLite.

## Context

TASK-0003 dostarczył kontrakty i codec sygnatury, a TASK-0004 gotowy payout
build-time. Ten task rozpoczyna M1.3 i przygotowuje zweryfikowane wejście dla
generatora SQLite z TASK-0007. Nie zapisuje jeszcze finalnego snapshotu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/delivery/MILESTONE_01_MOCKED_MOBILE.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0005-target-engine-golden-tests.md`

## Scope

- stałe konfiguracje `game-1`, `game-2` i `game-3`,
- zapisane, niezależne seedy generatora,
- dokładnie 1000 layoutów `row-major` na grę,
- ciągłe `sequence_number` od 1 do 1000,
- stałoszerokie sygnatury zgodne z komórkami,
- precomputed payout każdego layoutu przez engine z TASK-0004,
- dokładnie 6 kontrolowanych par duplikatów na grę,
- referencja unikalnego layoutu z unikalnym, niepełnym prefiksem,
- ręcznie policzone referencje pełnego Target dla braku plusa, pojedynczego
  szczytu, kilku szczytów, późniejszego niższego szczytu i plateau,
- deterministyczny fingerprint logicznej zawartości fixture,
- walidator konfiguracji, sekwencji, sygnatur, payoutów, duplikatów i prefiksu,
- komenda lokalna generująca i walidująca fixture bez zapisu bazy.

## Out of scope

- schemat i zapis SQLite,
- manifest oraz checksum pliku SQLite,
- exact/prefix queries i indeksy,
- cykliczny odczyt `N - 1`,
- benchmark repozytorium,
- React Native i UI.

## Acceptance criteria

- [x] Generator zwraca dokładnie 3 gry i 3000 layoutów.
- [x] Gry mają odpowiednio 10, 12 i 11 symboli; `game-3` ma jednego jokera.
- [x] Każda gra ma planszę 3 × 5 i `spin_cost = 10`.
- [x] Każda sekwencja jest dokładnie ciągiem `1..1000`.
- [x] Każdy layout ma 15 poprawnych komórek, zgodną sygnaturę i nieujemny,
  ponownie wyliczalny payout.
- [x] Każda gra zawiera dokładnie 6 jawnie opisanych par duplikatów, bez
  przypadkowych dodatkowych duplikatów.
- [x] Każda gra wskazuje co najmniej jeden unikalny layout rozpoznawalny po
  niepełnym prefiksie.
- [x] Kontrolowany rozkład payoutów daje ręcznie policzone golden Target:
  `game-1` od 99 oraz `game-2` od 199 i 200.
- [x] Dwa uruchomienia z tymi samymi seedami dają identyczne dane i fingerprint.
- [x] Zmiana numeru sekwencji, komórek, sygnatury, payoutu albo deklaracji
  duplikatu jest wykrywana przez stabilny błąd walidacji.
- [x] Generator i walidator nie importują SQLite, FastAPI, ORM ani UI.
- [x] Format, lint, typecheck i wszystkie testy przechodzą.
- [x] `CURRENT_STATE.md` i Outcome są zaktualizowane.

## Technical notes

- „Przypadek duplikatu” w M1 oznacza jedną sygnaturę występującą dokładnie w
  dwóch pozycjach; generator tworzy 6 takich grup na grę.
- Fingerprint opisuje logiczne wejście do przyszłego generatora snapshotu. Nie
  jest checksumą pliku SQLite z TASK-0007.
- Generator używa osobnego `random.Random(seed)` dla każdej gry i nie zależy od
  globalnego stanu generatora liczb losowych.

## Expected files

- `services/worker/src/game_predictor_worker/fixtures/`
- `services/worker/tests/test_m1_fixture.py`
- `scripts/validate_m1_fixture.py`
- `package.json`
- dokumentacja procesu

## Verification

```powershell
npm run fixture:validate
npm run quality
```

## Risks / open questions

Brak pytania blokującego. Golden report pełnego Target oraz checksum finalnego
SQLite należą do kolejnych zadań M1.3.

## Outcome

Zadanie zakończone. Powstało deterministyczne, niezależne od persystencji
wejście dla generatora snapshotu M1 oraz rygorystyczny walidator uruchamiany w
głównej bramce jakości.

### Changed

- dodano fixture `m1-fixture-v1` z seedami `71401`, `71402`, `71403`,
- dodano konfiguracje 3 gier, 5 paylines i pełne jawne macierze payoutów,
- generowane jest dokładnie 3 × 1000 layoutów z ciągłą numeracją,
- payout każdego layoutu jest precomputed przez engine z TASK-0004,
- każda gra zawiera dokładnie 6 kontrolowanych par duplikatów,
- generator odrzuca przypadkowe dodatkowe duplikaty i niekontrolowane payouty,
- zapisano unikalne, niepełne prefiksy do przyszłych testów matching,
- dodano ręcznie policzone golden pełnego Target dla kilku szczytów, późniejszego
  niższego szczytu, plateau, pojedynczego szczytu i braku plusa,
- walidator sprawdza metadata, konfiguracje, kolejność, komórki, sygnatury,
  payouty, duplikaty, prefiksy, golden totals i fingerprint,
- dodano `npm run fixture:validate` do głównej komendy `quality`,
- Pytest używa ignorowanego katalogu tymczasowego wewnątrz `.venv`, co usuwa
  zależność od niedostępnego systemowego `%TEMP%`.

### Verification results

- `npm run quality` — passed:
  - Prettier, Expo ESLint, Ruff i kontrola składni PowerShell,
  - TypeScript strict dla mobile i `shared-ts`,
  - mypy strict dla 16 plików Python,
  - testy `shared-ts`: 22/22,
  - testy Python: 39/39, w tym 12 testów fixture,
  - testy mobile: 4/4,
  - walidacja diagnostycznego snapshotu,
  - walidacja fixture 3 × 1000 i fingerprintu
    `f349dcbeec49f4627d330ad4a63d1f1f09480ec1d60443b462debd6a1df69f88`.
- `git diff --check` — passed.

### Not completed

- nie zapisano finalnego SQLite ani jego manifestu i checksumy,
- nie zaimplementowano indeksów, exact/prefix matching ani cyklicznego odczytu,
- nie wykonano benchmarku repozytorium.

### Recommended next task

Po osobnym poleceniu właściciela:

```text
TASK-0007 — SQLite snapshot generator and integrity tests
```
