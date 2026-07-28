---
title: TASK-0050 Manual import scale and release acceptance
status: done
last_updated: 2026-07-28
completed_at: 2026-07-28
---

# TASK-0050 — Manual import scale and release acceptance

## Status

`done`

## Goal

Potwierdzić na reprezentatywnych 500 000 layoutów, że ręczny import można
bezpiecznie przerwać i wznowić, zwalidować, opublikować oraz przeprowadzić przez
istniejący pipeline payout → snapshot → zweryfikowany APK.

## Context

TASK-0043–0049 dostarczyły kontrakt pliku, bezpieczne utworzenie joba,
strumieniowy staging, normalizację, raport, panel i transakcyjną publikację.
Ostatnia bramka M4 wymaga jednego odtwarzalnego przebiegu na docelowej skali
oraz utrwalonych pomiarów. M4 nadal działa warunkowo na podstawie D-041 i nie
zalicza brakujących benchmarków urządzeniowych G3.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_04_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- D-039–D-041 oraz D-044–D-048 w `ai_docs/process/DECISION_LOG.md`

## Scope

- deterministyczny generator dużego pliku `layout-import-v1`,
- odizolowany harness akceptacyjny używający publicznych granic aplikacji i
  prawdziwego PostgreSQL, bez ręcznej modyfikacji tabel domenowych,
- kontrolowana przerwa i wznowienie tego samego joba importu,
- walidacja błędnego wariantu i dowód blokady publikacji,
- walidacja, publikacja i retry publikacji poprawnego wariantu,
- sprawdzenie ciągłości, dozwolonych duplikatów sygnatur i niezmienności
  opublikowanej wersji,
- przeprowadzenie opublikowanego datasetu przez payout, snapshot i kontrolowany
  build/weryfikację APK,
- raport JSON z czasami etapów, pamięcią, licznikami błędów i checksumami.

## Out of scope

- benchmarki czasu matching/Target na Pixelu i Samsungu należące do
  TASK-0041/TASK-0042,
- OCR, zdjęcia i klasyfikator,
- automatyczna instalacja APK na telefonie,
- publiczna dystrybucja lub deployment,
- zmiana architektury na Redis/Celery, mikroserwisy albo chmurę.

## Acceptance criteria

- [x] Generator tworzy poprawny, deterministyczny JSONL v1 z dokładnie
      500 000 rekordów i bounded użyciem pamięci.
- [x] Ten sam import po kontrolowanej przerwie i wznowieniu kończy staging bez
      utraty ani zduplikowania fizycznych wierszy.
- [x] Błędny wariant ma stabilny blocker raportu i nie tworzy datasetu.
- [x] Poprawny wariant publikuje dokładnie jeden dataset; retry zwraca tę samą
      wersję i ciąg `sequence_number` wynosi `1..500000`.
- [x] Duplikaty sygnatur są policzone jako ostrzeżenie, nie blokada.
- [x] Payouty są kompletne przed snapshotem, a niezależna walidacja snapshotu i
      APK potwierdza dokładne checksumy oraz brak uprawnienia `INTERNET`.
- [x] Raport zapisuje czasy etapów, peak memory, liczbę wierszy/błędów,
      checkpoint wznowienia, wersje i checksumy artefaktów.
- [x] Standardowa bramka jakości zmienionych części przechodzi.

## Technical notes

- Test używa osobnej bazy PostgreSQL oraz osobnych katalogów importu i
  artefaktów. Nie modyfikuje bazy deweloperskiej.
- Dane wejściowe są generowane strumieniowo; raport nie przechowuje pełnych
  layoutów.
- Kontrolowana przerwa występuje po trwałym checkpointcie, a wznowienie używa
  tego samego joba i istniejącego mechanizmu lease.
- Rzeczywisty build Android może wymagać lokalnego SDK, JDK i prywatnego klucza
  testowego. Brak narzędzia środowiskowego nie może być przedstawiony jako
  przejście kryterium.

## Expected files

- `scripts/generate_m4_import_fixture.py`
- `scripts/run_m4_import_acceptance.py`
- `scripts/complete_m4_acceptance_apk.py`
- `services/worker/src/game_predictor_worker/imports/fixtures.py`
- `services/worker/tests/test_m4_import_acceptance.py`
- `imports/README.md`
- `package.json`
- `ai_docs/quality/m4-import-acceptance-report.json`
- `ai_docs/delivery/MILESTONE_04_EXECUTION_PLAN.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run m4:import:fixture -- --layout-count 1000
npm run m4:import:acceptance -- --layout-count 1000 --skip-android-build
npm run m4:import:acceptance
npm run python:lint
npm run python:typecheck
npm run python:test
npm run openapi:check
```

## Risks / open questions

- Pełny przebieg 500 000 rekordów i Gradle może trwać kilkanaście minut.
- Dostępność lokalnego PostgreSQL oraz Android toolchainu musi zostać
  potwierdzona przed pomiarem.
- M4 może zostać zaliczone warunkowo, ale M3/G3 pozostaje zablokowane do
  fizycznych raportów obu telefonów zgodnie z D-041.

## Outcome

### Changed

- Dodano strumieniowy generator poprawnego i blokowanego fixture
  `layout-import-v1`, komendy `m4:import:fixture` i `m4:import:acceptance` oraz
  testy deterministyczności, bounded bufora, duplikatów i błędnych granic.
- Dodano odizolowany harness akceptacyjny tworzący osobną bazę PostgreSQL,
  konfigurację przez publiczne Admin API, kontrolowaną awarię po trwałym
  checkpointcie, retry, walidację, raport, publikację, payouty, snapshot i APK.
- Raport `ai_docs/quality/m4-import-acceptance-report.json` zachowuje wszystkie
  czasy, pamięć, liczniki, checksumy oraz pierwszy błąd Android i recovery.
- Android build nie czyści już destrukcyjnie projektu i cache bez jawnego
  `-CleanNativeProject`; finalny verifier może przyjąć jawny manifest
  niezmiennego snapshotu.
- Dodano recovery builder dla już opublikowanego i zweryfikowanego snapshotu;
  po błędzie pełny harness zachowuje izolowaną bazę do retry zamiast ją usuwać.

### Verification results

- Pełny fixture: 500 000 rekordów, 42 340 054 bajty, SHA-256
  `214ff8b99c74b24e1781a6b70b0add738588c15c9e85d3df745e14a73ec49d8d`,
  maksymalnie jeden rekord buforowany.
- Import przerwano po linii 1000 i wznowiono jako ten sam job; finalnie
  `attemptCount = 2`, 500 000 poprawnych i 0 błędnych rekordów.
- Walidacja: 500 000 poprawnych, ciąg `1..500000`, 499 994 unikalne sygnatury,
  sześć grup/12 rekordów duplikatów; wariant blokowany wykazał lukę 10 i
  zduplikowany numer 9 oraz `LAYOUT_IMPORT_NOT_READY_FOR_PUBLICATION`.
- Publikacja i retry zwróciły ten sam dataset; powstało dokładnie 500 000
  payoutów.
- Snapshot: 41 246 720 bajtów, SHA-256
  `103eeb52c9e0e5ef2212073bbff645b67d92285645bdea35425b96307b1b6ade`,
  logiczny SHA-256
  `31f2c4869033ca5520265c8e450742b979ad7c8d611c48ea6691b0660ea437bf`.
- APK: 47 409 574 bajty, SHA-256
  `63945624cc3c19686e02f7ce2d83d435bc7f41a157473c4381d88920fb79a972`;
  niezależny verifier potwierdził `arm64-v8a`, brak debug/`INTERNET`, prywatny
  podpis, standalone bundle i dokładny SQLite.
- Czasy: generator `27.8317 s`, resume importu `576.8007 s`, walidacja
  `772.5213 s`, raport `2.0221 s`, publikacja `17.1700 s`, pierwsze podejście
  payout/snapshot/build `1167.5416 s`, recovery APK `1359.5864 s`, łącznie
  `3931.5769 s`.
- Najwyższy zmierzony peak RSS: `482 725 888` bajtów; najwyższy przyrost etapu:
  `210 575 360` bajtów.
- `npm run quality`: 65 admin, 66 mobile, 12 admin client, 23 shared,
  `346 passed, 12 skipped` Python; Ruff, mypy 113 modułów, PowerShell,
  OpenAPI, wszystkie typechecki i walidacje snapshotu/fixture przeszły.
- Fizyczna macierz integracji PostgreSQL: `11 passed`.

### Not completed

- Nie instalowano nowego APK na telefonach i nie wykonywano benchmarków
  matching/Target na Pixelu ani Samsungu; pozostaje to zakresem
  TASK-0041/TASK-0042 oraz blokadą G3 przed M5.
- Pierwszy `android_build` w izolowanej bazie zakończył się `EPERM` podczas
  czyszczenia wygenerowanego Androida. Baza została w tej wersji harnessu
  usunięta, dlatego recovery wznowiło ten sam dokładny, opublikowany snapshot w
  kontrolowanym builderze, ale nie przepisało historycznego rekordu joba.
  Raport jawnie zachowuje `workflowJobStatusBeforeRecovery = failed`.

### Documentation updates

- Zaktualizowano plan M4, `CURRENT_STATE.md`, indeks ukończonych zadań i raport
  jakości. G4 jest zaliczone warunkowo bez fałszywego zaliczenia G3.

### Recommended next task

- Wznowić TASK-0041 na obu telefonach, a następnie TASK-0042 z
  `--require-pass`; nie rozpoczynać M5 przed G3.
