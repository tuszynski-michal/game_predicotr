---
title: TASK-0014 Release APK and device acceptance
status: done
last_updated: 2026-07-26
---

# TASK-0014 — Release APK and device acceptance

## Goal

Zbudować prywatne, samodzielne APK M1 podpisane trwałym lokalnym kluczem,
udowodnić statycznie brak zależności sieciowej i przeprowadzić odbiór
instalacji, aktualizacji oraz pełnego przepływu na Pixel 10 Pro XL i Samsung
Galaxy S21 Ultra.

## Context

M1.1–M1.5 oraz korekta payout-v2 są ukończone. Prywatnie podpisany release
`0.1.2 (3)` z `m1-fixture.2` przeszedł lokalną bramkę jakości i statyczny audyt
APK bez uprawnienia `INTERNET`. Na Samsungu naprawiono wykryty podczas odbioru
zatrzymany loader oraz potwierdzono aktualizację in-place z `0.1.1 (2)`.
Scenariusze manualne na obu urządzeniach zostały wykonane offline. Właściciel
zaakceptował wynik M1 i zgodnie z D-020 przeniósł próbę aktywacji celowo
zmienionego snapshotu oraz dokładne pomiary urządzeniowe do M3.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_MOCKED_MOBILE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/quality/M1_DEVICE_ACCEPTANCE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0090-payout-v2-left-prefix-and-snapshot.md`
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
- [x] Instrukcja instalacji i aktualizacji działa w Windows PowerShell.
- [x] Pixel 10 Pro XL instaluje APK i uruchamia je bez Metro.
- [x] Pixel przechodzi unique, duplicate, not found i Target w trybie offline.
- [x] Galaxy S21 Ultra instaluje to samo APK i przechodzi scenariusz offline.
- [x] Aktualizacja do wyższego `versionCode` zachowuje podpis i instaluje się
  bez odinstalowania.
- [ ] APK aktualizacyjne zawiera inny snapshot i aplikacja pokazuje nową wersję
  — odroczone do M3.4 zgodnie z D-020.
- [ ] Dokładne pomiary matching, Target i przewijania są zapisane — odroczone
  do M3.5 zgodnie z D-020; czasy instalacji i startu M1 są zapisane.
- [x] Bramka G6 i końcowy protokół M1 zostały zaakceptowane przez właściciela z
  jawnymi odroczeniami D-020.

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
$env:GAME_PREDICTOR_GRADLE_USER_HOME = 'C:\gp-gradle'
npm run android:build:offline -- --VersionName 0.1.2 --VersionCode 3
npm run android:verify:offline
adb devices -l
```

## Risks / open questions

- Na początku zadania `adb devices -l` nie zwraca żadnego urządzenia.
- Historyczny APK `0.1.0 (1)` zawiera payout-v1 i nie może być użyty do
  końcowego odbioru. Aktualnym kandydatem jest `0.1.2 (3)` z payout-v2 oraz
  snapshotem `m1-fixture.2`.
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
- skrypt builda pozwala wskazać fizycznie krótki cache Gradle przez
  `GAME_PREDICTOR_GRADLE_USER_HOME`; na Windows użyto `C:\gp-gradle`, aby
  ominąć limit `MAX_PATH` narzędzi C++,
- verifier kontroluje standalone bundle, checksumę snapshotu, `applicationId`,
  wersję, `arm64-v8a`, brak debuggable/`INTERNET` oraz certyfikat release,
- dodano skrypt instalacji i pomiaru urządzenia oraz manualny protokół unique,
  duplicate, not found, Target, przewijania i aktualizacji.
- test na Samsungu wykrył, że memoizowany `SQLiteProvider` zachowywał pierwszy
  element `children` z loaderem mimo ukończonej weryfikacji; inicjalizację
  przeniesiono do stabilnego komponentu potomnego i dodano test regresji,
- Samsung `SM-G998B` z Androidem 15 zaktualizował aplikację in-place z
  `0.1.1 (2)` do `0.1.2 (3)` bez odinstalowania.
- Pixel 10 Pro XL z Androidem 16 zainstalował `0.1.2 (3)` w wymaganym trybie
  samolotowym; instalacja trwała `15,78 s`, a start procesu `1,1 s`.
- właściciel wykonał offline na obu urządzeniach pełny protokół manualny:
  unique 99 z golden Target, duplicate 101/995, not found z Undo, Reset,
  zmianę gry oraz sprawdzenie przewijania tabeli; wszystkie scenariusze
  zakończyły się poprawnie.

Aktualny zweryfikowany artefakt `0.1.2 (3)`:

- ścieżka:
  `.tooling/releases/sequence-target-analyzer-0.1.2-m1-fixture.2.apk`,
- rozmiar: `42 143 594` bajty,
- SHA-256:
  `906d2969fccbc629d849d5368673ca7ed897949d52b9b60bcb712a08457af0f0`,
- snapshot: `m1-fixture.2`, algorytm `payout-v2`, SHA-256 SQLite
  `4365a33d066a354d212693cd9169dac102b7cb1c164df6693f655e8690e9224a`,
- ABI: wyłącznie `arm64-v8a`,
- certyfikat:
  `CN=Game Predictor Private Release, OU=Private Testing, O=Local, C=PL`,
- `android.permission.INTERNET`: nieobecne,
- release nie jest debuggable.

Weryfikacja 2026-07-25:

- pełna bramka jakości: zaliczona; 63 testy mobile, 23 shared i 53 Python,
- walidacja `m1-fixture.2` i snapshotu: zaliczona,
- `npm run android:verify:offline`: zaliczone,
- aktualizacja Samsung: `28,39 s`, start procesu: `0,74 s`,
- Wi-Fi było wyłączone, a właściciel potwierdził brak karty SIM; ścisłe
  potwierdzenie z `Airplane mode` pozostaje otwarte.

Historyczny artefakt `0.1.0 (1)` z payout-v1 pozostaje wyłącznie punktem
odniesienia do testu aktualizacji i nie jest kandydatem do odbioru produktu.

### Odbiór końcowy

Właściciel potwierdził, że aktualny APK działa zgodnie z planem i nie ujawnił
błędów podczas scenariuszy manualnych offline na Samsungu i Pixelu. Aktualizacja
in-place została zainstalowana bez odinstalowania aplikacji. Dla Samsunga
wyłączone Wi-Fi i brak karty SIM zostały zaakceptowane jako wystarczający dowód
offline M1 mimo braku osobnego odczytu ustawienia `Airplane mode`.

G6 i M1 zostały zaakceptowane 2026-07-26. Próba aktualizacji z celowo zmienionym
snapshotem oraz dokładne pomiary matching, Target i przewijania nie są
oznaczone jako wykonane; zgodnie z D-020 należą do odbioru rzeczywistego
pipeline’u wydań w M3.4–M3.5.
