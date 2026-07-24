---
title: TASK-0014 Release APK and device acceptance
status: blocked
last_updated: 2026-07-24
---

# TASK-0014 — Release APK and device acceptance

## Goal

Zbudować prywatne, samodzielne APK M1 podpisane trwałym lokalnym kluczem,
udowodnić statycznie brak zależności sieciowej i przeprowadzić odbiór
instalacji, aktualizacji oraz pełnego przepływu na Pixel 10 Pro XL i Samsung
Galaxy S21 Ultra.

## Context

M1.1–M1.5 są ukończone. Istniejący build offline używa testowego debug key i
tylko raportuje uprawnienie `INTERNET`. M1.6 musi usunąć to uprawnienie,
utrwalić prywatny klucz poza repozytorium, zapisać pomiary artefaktu i wykonać
manualny odbiór na dwóch urządzeniach.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_MOCKED_MOBILE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0002-monorepo-offline-sqlite-spike.md`
- `ai_docs/tasks/completed/0013-virtualized-result-table-calculation-state.md`

## Scope

- trwały lokalny signing key i hasła w ignorowanym `.tooling`,
- release podpisany innym certyfikatem niż Android Debug,
- parametry `versionName` i `versionCode` dla kolejnych prywatnych APK,
- blokada `android.permission.INTERNET` w konfiguracji Expo,
- verifier, który kończy się błędem przy obecności `INTERNET`,
- kontrola applicationId, ABI, wersji, standalone bundle i snapshot checksum,
- zapis rozmiaru, SHA-256 i kluczowych czasów lokalnego artefaktu,
- instrukcja budowy, instalacji, aktualizacji i scenariusza offline,
- instalacja i odbiór na Pixel 10 Pro XL,
- instalacja i odbiór na Galaxy S21 Ultra,
- aktualizacja do wyższego `versionCode` z innym snapshotem i potwierdzenie
  aktywacji nowej wersji danych,
- końcowy protokół demo i bramka G6.

## Out of scope

- Google Play, EAS Build i publiczna dystrybucja,
- chmurowe przechowywanie klucza,
- finalny komercyjny branding,
- dane inne niż kontrolowane fixture M1,
- benchmark 500 000 layoutów,
- panel administracyjny i automatyczny kreator APK.

## Acceptance criteria

- [x] `applicationId` pozostaje `com.gamepredictor.mobile`.
- [x] Release używa trwałego lokalnego klucza poza Git.
- [x] Hasła i keystore nie trafiają do logów ani repozytorium.
- [x] Build przyjmuje jawny `versionName` i rosnący `versionCode`.
- [x] Samodzielne APK zawiera bundle JS oraz finalny snapshot SQLite.
- [x] APK zawiera wyłącznie wymagane ABI `arm64-v8a`.
- [x] Manifest finalnego APK nie deklaruje `android.permission.INTERNET`.
- [x] Verifier kończy się błędem, jeśli `INTERNET` powróci.
- [x] Certyfikat APK nie jest certyfikatem Android Debug.
- [x] SHA-256 i rozmiar APK są zapisane.
- [x] `npm run quality`, snapshot i release verifier przechodzą.
- [ ] Instrukcja instalacji i aktualizacji działa w Windows PowerShell.
- [ ] Pixel 10 Pro XL instaluje APK i uruchamia je bez Metro.
- [ ] Pixel przechodzi unique, duplicate, not found i Target w trybie offline.
- [ ] Galaxy S21 Ultra instaluje to samo APK i przechodzi scenariusz offline.
- [ ] Aktualizacja do wyższego `versionCode` zachowuje podpis i instaluje się
  bez odinstalowania.
- [ ] APK aktualizacyjne zawiera inny snapshot i aplikacja pokazuje nową wersję.
- [ ] Pomiary uruchomienia, matching, Target i przewijania są zapisane.
- [ ] Bramka G6 i końcowy protokół M1 są kompletne.

## Technical notes

- Klucz i properties powstają w `.tooling/android-signing/`; cały `.tooling`
  jest ignorowany.
- Custom Expo config plugin wprowadza release signing do generowanego
  `build.gradle`, dlatego `expo prebuild --clean` pozostaje odtwarzalny.
- `android.blockedPermissions` usuwa `INTERNET` również wtedy, gdy dodaje je
  manifest biblioteki.
- Brak urządzenia nie może zostać zastąpiony deklaracją sukcesu. Część
  urządzeniowa pozostaje otwarta do rzeczywistego podłączenia telefonu.

## Expected files

- `apps/mobile/app.json`
- `apps/mobile/app.config.js`
- `apps/mobile/plugins/with-release-signing.js`
- `scripts/ensure_android_release_signing.ps1`
- `scripts/build_android_debug.ps1`
- `scripts/verify_android_apk.ps1`
- skrypt/protokół odbioru urządzenia
- README i dokumentacja jakości/procesu

## Verification

```powershell
npm run quality
npm run android:build:offline
npm run android:verify:offline
adb devices -l
```

## Risks / open questions

- Na początku zadania `adb devices -l` nie zwraca żadnego urządzenia.
- D-019 zastąpiła semantykę payout po zbudowaniu artefaktu `0.1.0 (1)`.
  Snapshot w tym APK zawiera payout-v1 i nie może być użyty do końcowego
  odbioru; wymagane są korekta engine’u, regeneracja fixture/snapshotu i nowy
  build.
- Do testu aktualizacji potrzebny jest drugi APK z wyższym `versionCode` i
  celowo zmienioną wersją snapshotu. Nie należy modyfikować kanonicznego
  snapshotu bez kontrolowanego backupu i walidacji.
- Utrata lokalnego keystore uniemożliwi aktualizację już zainstalowanego APK;
  właściciel musi wykonać jego bezpieczną kopię poza repozytorium.

## Outcome

### Zrealizowane lokalnie

- dodano wersjonowaną konfigurację Expo i blokadę uprawnienia `INTERNET`,
- release jest podpisywany trwałym prywatnym kluczem generowanym w ignorowanym
  `.tooling/android-signing`,
- build używa krótkiego `.g` jako `GRADLE_USER_HOME`, aby nie przekraczać
  historycznego limitu ścieżek narzędzi C++ na Windows,
- verifier kontroluje standalone bundle, checksumę snapshotu, `applicationId`,
  wersję, `arm64-v8a`, brak debuggable/`INTERNET` oraz certyfikat release,
- dodano skrypt instalacji i pomiaru urządzenia oraz manualny protokół unique,
  duplicate, not found, Target, przewijania i aktualizacji.

Zweryfikowany artefakt `0.1.0 (1)`:

- rozmiar: `42 140 070` bajtów,
- SHA-256:
  `1eb8da0ba87a19f42975e46a192af190cf5e51905b97126204c8495ffe2bc0a3`,
- snapshot: `m1-fixture.1`, SHA-256
  `142e0ad84313adf553c9ca81c17e69867307be3a78c79db617aad80fc9511ddd`,
- certyfikat:
  `CN=Game Predictor Private Release, OU=Private Testing, O=Local, C=PL`,
- `android.permission.INTERNET`: nieobecne.

Weryfikacja:

- `npm run quality`: zaliczone; 62 testy mobile, 22 shared i 52 Python,
- `npm run android:verify:offline`: zaliczone,
- `adb devices -l`: zero podłączonych urządzeń.

### Blokada

Artefakt potwierdza poprawność techniczną pipeline’u release, lecz został
zbudowany z superseded payout-v1. Nie można wykonać wiążącego odbioru przed
wdrożeniem D-019 i przygotowaniem nowego snapshotu/APK. Po tej korekcie nadal
pozostają instalacja, testy offline, pomiary urządzeniowe i aktualizacja na
Pixel 10 Pro XL oraz Galaxy S21 Ultra. TASK-0014, M1.6 i G6 pozostają otwarte.
