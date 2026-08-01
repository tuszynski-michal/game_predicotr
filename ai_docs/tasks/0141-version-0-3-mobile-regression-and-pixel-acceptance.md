---
title: TASK-0141 — Version 0.3 mobile regression and Pixel acceptance
status: in_progress
last_updated: 2026-08-01
---

# TASK-0141 — Version 0.3 mobile regression and Pixel acceptance

## Status

`in_progress`

## Goal

Przejść automatyczną bramkę Mobile 0.3, przygotować statycznie zweryfikowane
APK i odebrać pełny przepływ offline na Google Pixel 10 Pro XL.

## Context

TASK-0135–0140 dostarczyły wszystkie zaplanowane zmiany Mobile 0.3. Ostatnie
zadanie nie rozszerza produktu; integruje te zmiany w jednym artefakcie i
potwierdza je automatycznie oraz na docelowym urządzeniu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/VERSION_0_3_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/quality/M1_DEVICE_ACCEPTANCE.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- uruchomić pełne testy Mobile i współdzielonej logiki używanej przez 0.3,
- przeprowadzić typecheck, lint i kontrolę formatowania zmienionych plików,
- zweryfikować środowisko Android i bieżący snapshot,
- zbudować podpisane Release APK z wyższym `VersionCode`,
- statycznie potwierdzić podpis, architekturę, bundle JS, snapshot i brak
  uprawnienia `INTERNET`,
- zachować nazwany artefakt APK i checksumę SHA-256,
- zainstalować aktualizację na jednym Google Pixel 10 Pro XL bez usuwania
  poprzedniej aplikacji,
- przejść manualny odbiór funkcji 0.3 w trybie offline.

## Out of scope

- pełne rzeczywiste testy i benchmarki 500 000 nowych layoutów,
- nowe gry i wielogrowe wydanie,
- test Samsung Galaxy S21 Ultra i rozszerzona macierz urządzeń,
- zmiany funkcjonalne inne niż naprawa regresji blokującej odbiór.

## Acceptance criteria

- [x] Pełna regresja Mobile i shared engine przechodzi.
- [x] Typecheck, lint i format zmienionych plików przechodzą.
- [x] Snapshot użyty przez build przechodzi walidację wymaganego schematu.
- [ ] Release APK ma wyższy `VersionCode` od wersji zainstalowanej na Pixelu.
- [x] Statyczny audyt APK potwierdza podpis, `arm64-v8a`, bundle JS, checksumę
  SQLite oraz brak uprawnienia `INTERNET`.
- [ ] Aktualizacja `adb install -r` zachowuje `firstInstallTime` i uruchamia
  właściwy pakiet.
- [ ] W trybie samolotowym właściciel potwierdza kompaktowy ekran, Selection,
  `Next`, `Undo`, `Reset`, zmianę limitu Targetu, statusy, długą tabelę i powrót
  na górę.
- [ ] Artefakt, checksumy i wynik odbioru są zapisane w dokumentacji.

## Technical notes

Build ma być pojedynczym kontrolowanym procesem z timeoutami istniejącego
skryptu. Nie uruchamiamy równolegle drugiego Gradle. Instalacja jest aktualizacją
in-place; odinstalowanie aplikacji nie jest dopuszczalne w tym odbiorze.

## Expected files

- `ai_docs/tasks/0141-version-0-3-mobile-regression-and-pixel-acceptance.md`
- `ai_docs/delivery/VERSION_0_3_EXECUTION_PLAN.md`
- `ai_docs/process/CURRENT_STATE.md`
- `artifacts/v03-ready-for-pixel/`

## Verification

```powershell
npm.cmd test --workspace @game-predictor/mobile -- --runInBand
npm.cmd test --workspace @game-predictor/shared-ts
npm.cmd run typecheck --workspace @game-predictor/mobile
npm.cmd run lint --workspace @game-predictor/mobile
npm.cmd run snapshot:validate
npm.cmd run windows:environment:check
npm.cmd run android:build:offline -- --VersionName 0.3.0 --VersionCode <next>
npm.cmd run android:verify:offline
npm.cmd run android:device:accept -- -ExpectedModelPattern '^Pixel 10 Pro XL$' -Stage Update -RequireAirplaneMode
```

## Risks / open questions

- Fizyczna instalacja i odbiór zależą od podłączenia jednego odblokowanego
  Pixela oraz decyzji właściciela po scenariuszach manualnych.
- Numer `VersionCode` zostanie wybrany po odczycie wersji z urządzenia; bez
  telefonu przygotujemy APK z pierwszym bezpiecznym numerem wyższym od
  zachowanego 0.1.5 (6).

## Outcome

### Changed

- Trwałe środowisko Windows zostało ponownie zapisane i potwierdzone w nowym
  procesie: Node 24.14.0, npm 11.18.0, JDK 17.0.20, Android SDK 36 i ADB 1.0.41.
- Zbudowano podpisane APK `0.3.0 (7)` i zachowano je wraz z manifestem w
  `artifacts/v03-ready-for-pixel/`.
- Lokalne wydanie uzupełniono o osobny plik SHA-256 i instrukcję późniejszej
  aktualizacji Pixela; artefakt nie zależy od działającego procesu Codex.
- Dodano osobny, ograniczony do Pixela protokół odbioru Mobile 0.3.

### Verification results

- Mobile: 82/82 testów passed.
- Shared engine: 24/24 testy passed.
- Mobile typecheck, ESLint i Prettier zmienionych plików: passed.
- Snapshot: schema 3, 3000 layoutów, SHA-256
  `bc583c2b36417a43de593a13848d64976b53cf408f6916a40a470f732185751c`.
- Build Release: passed w 485,2 s.
- APK: 42 267 190 bajtów, SHA-256
  `80dfb99fa85c466689d69901f0aea57d3fdf03d425c46fd71bb0f883569e1332`.
- Statyczny audyt: podpis, `arm64-v8a`, bundle JS, snapshot i brak `INTERNET`
  passed.

### Not completed

- Pixel nie był podłączony (`adb devices -l` zwróciło pustą listę), dlatego
  instalacja in-place i manualny odbiór offline pozostają pending.

### Documentation updates

- Dodano `ai_docs/quality/V0_3_MOBILE_ACCEPTANCE.md` oraz zaktualizowano indeks,
  plan 0.3 i `CURRENT_STATE.md`.

### Recommended next task

- Dokończyć TASK-0141 po podłączeniu Google Pixel 10 Pro XL; nie rozpoczynać
  zakresu 0.4 przed wynikiem odbioru.
