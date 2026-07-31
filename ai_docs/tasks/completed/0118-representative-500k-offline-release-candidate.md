---
title: TASK-0118 Representative 500k offline release candidate
status: done
last_updated: 2026-07-31
---

# TASK-0118 — Representative 500k offline release candidate

## Status

`done`

## Goal

Przygotować lokalną, statycznie zweryfikowaną paczkę APK wersji 0.1 z jedną
grą, grafikami ośmiu symboli, 10 paylines i dokładnie 500 000 layoutów.

## Context

Lokalny import gry `blazing-hot-7-deluxe` zawiera 169 ręcznie zatwierdzonych,
ponumerowanych plansz i katalog ośmiu symboli. Telefon jest odłączony, dlatego
zadanie kończy się na trwałej lokalnej paczce; instalacja i odbiór Pixela należą
do TASK-0119.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VERSION_0_1_RELEASE_PLAN.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- eksport wyłącznie accepted/corrected plansz z aktywnego importu,
- zachowanie ich numerów sekwencji i pełnych symboli jako chronionego podzbioru,
- deterministyczny wybór reprezentatywnego cropu dla każdego symbolu,
- jedna gra 3 × 5, spin cost 10, osiem symboli bez jokera,
- 10 unikalnych PAYLINE, w tym trzy poziome, V i warianty zygzak/krzyż,
- deterministyczne testowe minima i payouty,
- dopełnienie do 500 000 layoutów za pomocą wersjonowanego generatora z seedem,
- kilka jawnych grup duplikatów do scenariusza mobile,
- precomputed payout dla każdego layoutu,
- snapshot SQLite, manifest proweniencji, APK i raport checksum,
- statyczna weryfikacja offline bez telefonu.

## Out of scope

- instalacja lub uruchomienie APK na telefonie,
- zaliczenie TASK-0076 albo przedstawianie syntetycznego dopełnienia jako
  rzeczywistego datasetu zdjęciowego,
- zmiana zatwierdzonych decyzji człowieka,
- Admin 0.2, OCR, retraining i masowy auto-import,
- stabilny produkcyjny klucz podpisujący, backup/restore i formalny rollback.

## Acceptance criteria

- [x] eksport zawiera co najmniej 100 zatwierdzonych plansz, bez null i bez
  powtórzonego `sequence_number`,
- [x] osiem symboli ma poprawne nazwy oraz zweryfikowaną grafikę z zatwierdzonego
  cropu,
- [x] dokładnie 10 row paths jest kompletnych, unikalnych i zgodnych z planszą,
- [x] seed, generator, reguły, payouty, zatwierdzone źródła i checksumy są w
  kanonicznym manifeście,
- [x] snapshot ma dokładnie jedną grę i 500 000 ciągłych layoutów,
- [x] zatwierdzone sekwencje w snapshotcie są bajtowo zgodne z eksportem,
- [x] payout każdego layoutu jest przeliczony według zamrożonych reguł,
- [x] duplicate fixtures są rzeczywistymi duplikatami i pozostają niejednoznaczne,
- [x] mobile pokazuje grafiki i nazwy symboli, zachowując fallback tekstowy,
- [x] APK zawiera standalone bundle, właściwy snapshot i nie deklaruje
  `INTERNET`,
- [x] paczka APK, manifest i raport pozostają lokalnie pod `artifacts/`.

## Technical notes

- Przyjmujemy D-100: „randomowe” dane i wartości są pseudolosowe, ale w pełni
  deterministyczne oraz odtwarzalne.
- Źródłem prawdy decyzji jest lokalny PostgreSQL; źródłem bajtów cropów jest
  kontrolowany `artifacts/data/m65-real-workbench-v1`.
- Wydanie używa następnego `versionCode = 6`; TASK-0119 ma wykonać aktualizację
  istniejącej instalacji.
- Generator pracuje batchami i nie materializuje 500 000 plansz w pamięci.

## Expected files

- `services/worker/src/game_predictor_worker/releases/representative_v01.py`
- `services/worker/tests/test_representative_v01_release.py`
- `scripts/build_v01_representative_release.py`
- `scripts/validate_v01_representative_release.py`
- `apps/mobile/assets/symbols/v01/*.png`
- `apps/mobile/src/features/board/symbol-assets.ts`
- `apps/mobile/src/features/board/symbol-selection.tsx`
- `apps/mobile/src/features/board/board-grid.tsx`
- `apps/mobile/src/data/local-layout-repository.ts`
- `packages/shared-ts/src/contracts.ts`
- `package.json`
- `artifacts/v01-representative-release/`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_representative_v01_release.py
.venv\Scripts\python.exe scripts/build_v01_representative_release.py --prepare-only
.venv\Scripts\python.exe scripts/validate_v01_representative_release.py
npm test --workspace @game-predictor/mobile -- --runInBand
npm run typecheck --workspace @game-predictor/mobile
npm run lint --workspace @game-predictor/mobile
.venv\Scripts\python.exe scripts/build_v01_representative_release.py --build-apk
```

## Risks / open questions

- Brak pytania blokującego. Jeżeli build Android przekroczy znany limit,
  proces zostanie przerwany wraz z drzewem procesów, a snapshot i raport
  pozostaną do ponowienia builda.

## Outcome

Zadanie ukończono 2026-07-31. Powstała lokalna, statycznie zweryfikowana
paczka `0.1.5`; instalacja i pomiar na Pixelu są świadomie odłożone do
TASK-0119.

### Changed

- dodano deterministyczny generator i pełny walidator reprezentatywnego
  snapshotu 500k,
- zachowano 169 zatwierdzonych plansz oraz wybrano reprezentatywne grafiki dla
  `cherries`, `grapes`, `lemon`, `orange`, `plum`, `seven`, `star` i
  `watermelon`,
- dodano 10 paylines, 26 reguł payout, minima długości 2/3, spin cost `10` i 6
  kontrolowanych grup duplikatów,
- mobile odczytuje `image_asset_key`, pokazuje grafikę i nazwę symbolu oraz
  zachowuje tekstowy fallback,
- dodano komendy prepare/validate/build i raport wydania,
- zapisano APK pod
  `artifacts/v01-representative-release/android-releases/0.1.5/`.

### Verification results

- testy generatora: `3 passed`,
- Ruff zmienionych plików Python: pass,
- mypy zmienionych plików Python z pominięciem analizy niezmienionych importów:
  pass,
- TypeScript shared/mobile: pass,
- ESLint czterech zmienionych plików mobile: pass,
- testy mobile: `67 passed`,
- pełna walidacja snapshotu: `500 000/500 000`, 169 approved, 8 symboli, 6
  grup duplikatów, maksymalny batch `1000`,
- build Android Release: `BUILD SUCCESSFUL in 9m 23s`, `495` zadań Gradle,
- niezależny audyt APK: standalone bundle, wersja `0.1.5 (6)`, snapshot SHA-256
  `ddbfa90e673811efe2acad8e8049acc2435389bbbcaf256715573a744ef66de8`,
  brak `INTERNET`, signer `Game Predictor Private Release`,
- APK: `53 228 630` bajtów, SHA-256
  `d94061734d1e141ee9e68bf0e532eeb0ac1d485b68796f853c0dc3589326c522`.

### Not completed

- instalacja i test urządzeniowy należą do TASK-0119.
- pełne `expo lint` przekroczyło limit 120 sekund; zmienione pliki przeszły
  bezpośredni ESLint, a release przeszedł Android `lintVitalRelease`.

### Documentation updates

- zaktualizowano `CURRENT_STATE.md` i `VERSION_0_1_RELEASE_PLAN.md`.

### Recommended next task

- `TASK-0119 — Pixel 10 Pro XL release acceptance`
