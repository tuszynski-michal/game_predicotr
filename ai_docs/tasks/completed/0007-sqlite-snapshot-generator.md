---
title: TASK-0007 SQLite snapshot generator and integrity tests
status: done
last_updated: 2026-07-24
completed_at: 2026-07-24
---

# TASK-0007 — SQLite snapshot generator and integrity tests

## Goal

Przekształcić zwalidowane fixture z TASK-0006 w deterministyczny, niezmienny
snapshot SQLite M1 z manifestem, checksumami i pełną walidacją integralności,
a następnie zastąpić nim diagnostyczny asset M1.1 w aplikacji mobilnej.

## Context

TASK-0006 dostarcza dokładnie 3 × 1000 layoutów, konfiguracje gier, symbole,
precomputed payouty, kontrolowane duplikaty, unikalne prefiksy i golden Target.
TASK-0007 odpowiada wyłącznie za kontrakt persystencji i artefakt wydania.
Repozytorium zapytań exact/prefix/cyclic powstanie dopiero w TASK-0008.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/delivery/MILESTONE_01_MOCKED_MOBILE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0006-deterministic-fixture-generator.md`

## Scope

- finalny schemat SQLite M1 dla `metadata`, `games`, `symbols` i `layouts`,
- klucze obce, constraints i indeks `(game_id, signature)`,
- `PRAGMA user_version` oraz stały identyfikator aplikacyjny bazy,
- zapis dokładnie 3 gier, 3000 layoutów i precomputed payoutów,
- manifest wersji wydania, datasetu, reguł, algorytmu i fixture,
- checksum logicznej zawartości i SHA-256 pliku SQLite,
- manifestowe referencje kontrolowanych duplikatów, prefiksów i golden Target,
- generowanie przez pliki tymczasowe i atomowe zastąpienie pojedynczych
  artefaktów,
- walidacja SQLite, schematu, metadata, checksum, liczników, sekwencji,
  sygnatur, symboli, payoutów i duplikatów,
- deterministyczność bajtowa dla identycznego wejścia,
- zastąpienie assetu `m1-spike.db` finalnym snapshotem M1,
- aktualizacja mobilnego kontraktu diagnostycznego do finalnego schematu.

## Out of scope

- implementacja repozytorium exact/prefix,
- cykliczny odczyt `N - 1`,
- benchmark indeksu i czasu zapytań,
- UI planszy i Target,
- migracje PostgreSQL,
- Android release build i test urządzeń.

## Acceptance criteria

- [x] Jedna komenda generuje bazę i manifest, druga je waliduje.
- [x] Snapshot ma schema version `2`, ponieważ nie jest zgodny ze spike schema
  version `1`.
- [x] Baza zawiera dokładnie tabele i indeks wymagane przez model mobilny.
- [x] Snapshot zawiera dokładnie 3 gry, 33 symbole i 3000 layoutów.
- [x] Każda gra ma sekwencję dokładnie `1..1000`.
- [x] Każdy layout ma poprawną stałoszeroką sygnaturę i nieujemny payout.
- [x] Każda gra zachowuje dokładnie 6 kontrolowanych par duplikatów.
- [x] Manifest i metadata bazy opisują te same wersje oraz liczniki.
- [x] SHA-256 pliku i logiczna checksum treści są weryfikowane niezależnie.
- [x] Dwa generowania z tego samego fixture dają identyczną bazę i manifest.
- [x] Zmiana pliku, manifestu, metadata, sekwencji albo treści jest odrzucana
  jako `local_data_error`.
- [x] Aplikacja mobilna materializuje nowy asset pod nazwą zależną od checksumy
  i waliduje schema version `2`.
- [x] Format, lint, typecheck i wszystkie testy przechodzą.
- [x] `CURRENT_STATE.md`, architektura, Decision Log i Outcome są aktualne.

## Technical notes

- `created_at` fixture M1 jest stałym wejściem wydania, a nie czasem wykonania
  komendy; dzięki temu artefakt pozostaje deterministyczny.
- `content_checksum` obejmuje logiczną treść zapisaną w SQLite.
  `fixture_fingerprint` dodatkowo identyfikuje pełne wejście build-time.
- SHA-256 pliku SQLite pozostaje wyłącznie w zewnętrznym manifeście, ponieważ
  plik nie może zawierać własnej checksumy bez zależności cyklicznej.
- Constraints tworzą granicę integralności, ale nie zastępują walidacji
  ciągłości i zgodności z manifestem.

## Expected files

- `services/worker/src/game_predictor_worker/snapshot.py`
- `services/worker/tests/test_snapshot.py`
- `scripts/generate_m1_snapshot.py`
- `scripts/validate_m1_snapshot.py`
- `apps/mobile/assets/snapshot/`
- `apps/mobile/src/data/bundled-snapshot.ts`
- `apps/mobile/__tests__/bundled-snapshot-test.ts`
- `package.json`
- dokumentacja architektury i procesu

## Verification

```powershell
npm run snapshot:generate
npm run snapshot:validate
npm run quality
```

## Risks / open questions

Benchmark indeksu i odczytu 500 000 layoutów nie należy do tego zadania.
Zostanie wykonany na granicy repozytorium w TASK-0008/M3.

## Outcome

Zadanie zakończone. Diagnostyczny snapshot M1.1 został zastąpiony finalnym,
deterministycznym artefaktem danych M1 gotowym dla repozytorium z TASK-0008.

### Changed

- dodano schema version `2` z tabelami `metadata`, `games`, `symbols`,
  `layouts`, constraints, kluczami obcymi i indeksem
  `idx_layouts_game_signature`,
- ustawiono `PRAGMA user_version = 2` i
  `PRAGMA application_id = 0x47505244`,
- generator zapisuje dokładnie 3 gry, 33 symbole i 3000 layoutów,
- manifest zawiera wersje, seedy, kontrolowane duplikaty, unikalne prefiksy,
  golden Target, fixture fingerprint i oba rodzaje checksum,
- walidator sprawdza integralność SQLite, schema, metadata, liczniki, ciągłość,
  sygnatury, symbole, payouty, duplikaty, prefiksy i golden totals,
- generowanie używa plików tymczasowych i waliduje je przed zastąpieniem
  artefaktów,
- dodano bezpieczny runner Pytest z osobnym katalogiem tymczasowym per proces
  dla Windows,
- zastąpiono `m1-spike.db` przez `m1-snapshot.db`,
- mobile akceptuje schema version `2`, liczy rekordy z `games` i `layouts` oraz
  pokazuje wersje fixture, datasetu i reguł,
- zaakceptowano D-018 opisującą finalny kontrakt snapshotu M1.

### Artifact

- plik: `apps/mobile/assets/snapshot/m1-snapshot.db`,
- rozmiar: `274432` bajty,
- SHA-256 pliku:
  `142e0ad84313adf553c9ca81c17e69867307be3a78c79db617aad80fc9511ddd`,
- logiczna checksum:
  `129d928383c89da0a1a65a57ebcd1eccbf5e2e94bd36036b6125119fd93517d2`,
- fixture fingerprint:
  `f349dcbeec49f4627d330ad4a63d1f1f09480ec1d60443b462debd6a1df69f88`.

### Verification results

- `npm run quality` — passed:
  - Prettier, Expo ESLint, Ruff i składnia 5 skryptów PowerShell,
  - TypeScript strict dla mobile i `shared-ts`,
  - mypy strict dla 16 plików Python,
  - testy `shared-ts`: 22/22,
  - testy Python: 47/47, w tym 11 testów snapshotu,
  - testy mobile: 5/5,
  - walidacja finalnego snapshotu i logicznego fixture.
- `npm run snapshot:generate` — passed.
- `npm run snapshot:validate` — passed.
- `git diff --check` — passed.

### Removed

Usunięto zastąpiony `apps/mobile/assets/snapshot/m1-spike.db` oraz stare skrypty
`generate_spike_snapshot.py` i `validate_spike_snapshot.py`. Pliki pozostają
odzyskiwalne z historii Git.

### Not completed

- nie zaimplementowano repozytorium exact/prefix/cyclic,
- nie wykonano benchmarku indeksu ani pomiarów zapytań,
- nie zbudowano nowego APK i nie wykonano testów urządzeń.

### Recommended next task

Po osobnym poleceniu właściciela:

```text
TASK-0008 — Matching repository and cyclic payout stream
```
