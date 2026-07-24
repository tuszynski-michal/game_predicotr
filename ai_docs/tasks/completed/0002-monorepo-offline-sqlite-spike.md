---
title: TASK-0002 Monorepo and offline SQLite spike
status: done
last_updated: 2026-07-24
completed_at: 2026-07-24
---

# TASK-0002 — Monorepo and offline SQLite spike

## Goal

Utworzyć odtwarzalny fundament monorepo oraz minimalną aplikację Android, która
bez sieci otwiera wersjonowany snapshot SQLite dołączony do builda i pokazuje
jego zweryfikowane metadata.

## Context

To jedyny zakres M1.1. Zadanie ma wcześnie potwierdzić integrację Expo,
`expo-sqlite`, assetu SQLite i lokalnego Android build, zanim powstaną algorytmy
oraz właściwy UI.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- utworzenie struktury monorepo dla `apps/`, `services/`, `packages/` i
  `scripts/`,
- wybór oraz zapisanie narzędzi JavaScript i Python,
- root commands dla formatowania, lint, typecheck i testów,
- minimalna aplikacja Expo/React Native z TypeScript strict,
- stabilny Android `applicationId`,
- minimalny generator SQLite z tabelą `metadata` i rekordami diagnostycznymi,
- build-time manifest z wersją, checksumą i wersją schematu,
- wersjonowana nazwa lokalnej kopii bazy,
- walidacja metadata oraz kontrolowany `local_data_error`,
- prosty ekran diagnostyczny,
- lokalny Android development/debug build na Windows,
- dokumentacja uruchomienia i weryfikacji.

## Out of scope

- plansza, symbole, Undo i Reset,
- prefix/exact matching,
- payout engine,
- Target forecast,
- 3 × 1000 właściwych mock layoutów,
- PostgreSQL, FastAPI i panel admina,
- import zdjęć,
- finalny release signing i odbiór na dwóch urządzeniach,
- finalna kontrola braku uprawnienia `INTERNET` z M1.6.

## Acceptance criteria

- [x] Monorepo ma jeden lockfile JavaScript i jawne komendy root.
- [x] TypeScript działa w trybie strict.
- [x] Python tooling ma odtwarzalne środowisko i jawne komendy jakości.
- [x] Jedna komenda generuje oraz waliduje minimalny snapshot SQLite.
- [x] Manifest zawiera release version, schema version i checksum.
- [x] Nazwa lokalnej bazy zmienia się po zmianie checksum snapshotu.
- [x] Aplikacja odczytuje dołączony SQLite bez API i pokazuje metadata.
- [x] Niezgodny schema version daje kontrolowany `local_data_error`.
- [x] Format, lint, typecheck i testy przechodzą.
- [x] Lokalny Android debug/development APK buduje się na Windows.
- [x] Decyzje toolchainu i builda są zapisane w Decision Log.
- [x] `CURRENT_STATE.md` i Outcome są zaktualizowane.

## Technical notes

- Dokładne wersje i komendy są opisane w D-013 i `TECH_STACK.md`.
- Snapshot jest identyfikowany przez checksumę pliku; metadata bazy służą do
  walidacji release i schematu.
- Komponenty UI nie powinny znać szczegółów kopiowania assetu ani zapytań
  inicjalizacyjnych.

## Expected files

- `package.json`
- lockfile JavaScript
- `apps/mobile/`
- `services/worker/`
- `scripts/`
- `.gitignore`
- `.gitattributes`
- `.editorconfig`
- root `README.md`
- dokumentacja i Decision Log

## Verification

Obowiązują komendy:

```powershell
npm run quality
npm run snapshot:generate
npm run snapshot:validate
npm run android:build:debug
npm run android:build:offline
npm run android:verify:offline
```

## Risks / open questions

- brak globalnego JDK/Android SDK obsługuje lokalny, weryfikowany skrypt setup,
- Metro ma jawnie dodane rozszerzenie `.db`,
- fizyczne uruchomienie wymaga podłączenia urządzenia i pozostaje w M1.6.

## Outcome

Zadanie zakończone. Fundament M1.1 jest odtwarzalny na Windows, a bramka
pakietowa G1 przeszła. Uruchomienie na fizycznym urządzeniu pozostaje elementem
odbioru M1.6.

### Changed

- utworzono monorepo npm z jednym `package-lock.json` i komendami root,
- utworzono minimalną aplikację Expo SDK 57 / React Native 0.86 z TypeScript
  strict i stabilnym `applicationId` `com.gamepredictor.mobile`,
- dodano deterministyczny generator i walidator diagnostycznego snapshotu
  SQLite wraz z manifestem, checksumami i wersją schematu,
- dodano adapter inicjalizacji `expo-sqlite`, nazwę lokalnej kopii zależną od
  checksumy, walidację metadata oraz kontrolowany `local_data_error`,
- dodano ekran loading/success/error pokazujący zweryfikowane metadata,
- dodano odtwarzalny lokalny toolchain JDK 17 / Android SDK 36 i skrypty build,
- dodano osobny build testowy offline oraz kontrolę zawartości APK,
- usunięto nieużywane tekstowe artefakty startowego szablonu Expo.

### Verification results

- `npm run quality` — passed:
  - Prettier,
  - Expo ESLint,
  - Ruff,
  - TypeScript `tsc --noEmit`,
  - mypy strict dla 4 plików Python,
  - Jest: 4/4 testy,
  - pytest: 3/3 testy,
  - walidacja snapshotu.
- `npm run powershell:check` — 4/4 skrypty mają poprawną składnię.
- `expo install --check` — zależności są zgodne z Expo SDK 57.
- lokalny Android debug build — passed na Windows.
- `npm run android:build:offline` — passed:
  - czas ostatniego builda: 16 min 23 s,
  - ABI: `arm64-v8a`,
  - rozmiar: 41 990 846 B,
  - SHA-256 APK:
    `3201d92f29d21731a9fd5b99cc88c299a321a1847939ac5384e190838bfe0ee2`.
- `npm run android:verify:offline` — passed:
  - pakiet: `com.gamepredictor.mobile`,
  - min SDK 24, target/compile SDK 36,
  - standalone bundle JavaScript jest w APK,
  - snapshot SQLite jest w APK,
  - SHA-256 SQLite w APK i w źródle jest identyczny:
    `5d198fea586954abe005864c7a8c5a9a71af5bd8c0a30167c544981a62d9cb77`,
  - bundle zawiera release version, checksum i kod `local_data_error`.
- `adb devices -l` — brak podłączonego urządzenia.
- `npm audit` — brak high/critical; 11 moderate w przechodnich zależnościach
  narzędziowych Expo CLI. Automatyczna poprawka wymagałaby niekompatybilnego,
  breaking downgrade Expo i nie została zastosowana.

### Not completed

- nie instalowano APK na Pixel 10 Pro XL ani Galaxy S21 Ultra, ponieważ żadne
  urządzenie nie było podłączone; odbiór na urządzeniach pozostaje w M1.6,
- użyto testowego podpisu release; trwały klucz wydania pozostaje w M1.6,
- testowe APK nadal deklaruje domyślne uprawnienie Expo `INTERNET`; kod M1.1
  nie wykonuje requestów ani nie pobiera danych, a usunięcie uprawnienia i
  automatyczna kontrola jego braku są bramką M1.6,
- nie rozpoczęto kontraktów ani algorytmów M1.2.

### Documentation updates

- dodano D-013 w `DECISION_LOG.md`,
- uszczegółowiono wersje i komendy w `TECH_STACK.md`,
- zaktualizowano `CURRENT_STATE.md` i plan wykonania M1,
- dodano instrukcje bootstrapu, builda i weryfikacji APK w root `README.md`
  oraz `apps/mobile/README.md`.

### Recommended next task

- po poleceniu rozpoczęcia M1.2:
  `TASK-0003 — Contracts, signature codec and validation`
