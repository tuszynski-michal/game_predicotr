---
title: Release failure and immutability integration tests
status: done
last_updated: 2026-07-31
closed_at: 2026-07-31
---

# TASK-0039 — Release failure and immutability integration tests

## Status

`done`

## Goal

Zamknąć bramkę G3.4 przez kontrolowane testy awarii i retry kompletnego
workflow release, dowód niezmienności historycznych artefaktów oraz fizyczną
aktualizację istniejącej instalacji do APK z celowo zmienionym
`releaseVersion` i snapshotem.

## Context

TASK-0036–0038 dostarczyły niezmienny model release, jeden resumowalny job,
kontrolowany Android builder oraz panel. Istnieją testy przebiegu poprawnego i
pojedynczej awarii buildera, ale nie ma jeszcze kompletnej macierzy checkpointów,
fizycznego przebiegu PostgreSQL → snapshot → APK ani dowodu aktywacji nowego
snapshotu po aktualizacji urządzenia.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/quality/M1_DEVICE_ACCEPTANCE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- kontrolowane awarie rewalidacji źródeł, payoutu, publikacji/walidacji
  snapshotu, Android builda, audytu APK i końcowego zapisu `ready`,
- anulowanie i utrata lease w bezpiecznych checkpointach,
- błędny, obcy lub niezgodny checkpoint release,
- retry tego samego joba od zagnieżdżonego checkpointu bez child-jobów,
- ponowne użycie wyłącznie w pełni zweryfikowanego snapshotu,
- brak `ready` i brak częściowego APK po dowolnej awarii,
- niezmienność poprzedniego gotowego release, jego bajtów, ścieżek i checksum,
- integracja na fizycznym PostgreSQL dla dwóch wersji release,
- rzeczywisty kontrolowany Release APK `arm64-v8a` z wyższym `versionCode`,
- audyt podpisu, braku `INTERNET` i dokładnego snapshotu w APK,
- ręczna aktualizacja `adb install -r` bez odinstalowania,
- potwierdzenie na ekranie nowej `releaseVersion` i checksumy snapshotu,
- raport automatyczny i manualny dla urządzenia.

## Out of scope

- benchmark 500 000 layoutów (`M3.5`),
- automatyczna instalacja z panelu,
- Google Play, publiczna dystrybucja i chmura,
- zmiana signing key albo `applicationId`,
- testy obrazu/OCR.

## Acceptance criteria

- [x] Każda kontrolowana awaria kończy job/release jako failed lub cancelled,
  nigdy `ready`.
- [x] Awaria przed końcowym checkpointem nie publikuje częściowego APK.
- [x] Utrata lease nie pozwala staremu workerowi oznaczyć release jako failed.
- [x] Retry zachowuje identyfikator joba i wznawia poprawny checkpoint bez
  duplikowania payoutów.
- [x] Uszkodzony istniejący snapshot lub APK jest odrzucany, nie nadpisywany.
- [x] Drugi release nie zmienia ścieżek, checksum ani bajtów pierwszego.
- [x] Pełny przebieg na PostgreSQL zapisuje dokładne źródła i oba artefakty.
- [x] Rzeczywisty APK przechodzi audyt offline i zawiera dokładny nowy snapshot.
- [x] `adb install -r` aktualizuje istniejący pakiet bez czyszczenia danych.
- [x] Po aktualizacji aplikacja pokazuje nową `releaseVersion`, waliduje
      checksumę snapshotu i uruchamia scenariusze na nowej bazie.
- [x] Pełna jakość i fizyczne testy PostgreSQL przechodzą.

## Assumptions

- Do fizycznego odbioru wersji `0.1` jest wymagany dokładnie jeden
  autoryzowany Pixel 10 Pro XL zgodnie z D-096.
- Kolejny kandydat ma wyższy `versionCode` od zainstalowanego `3` i ten sam
  prywatny signing key.
- Raport urządzenia zapisuje poprzednią oraz nową wersję pakietu, aby dowieść
  aktualizacji bez odinstalowania.
- Zaliczenie manualnego tekstu na ekranie wymaga obserwacji właściciela; agent
  nie zgaduje wyniku na podstawie samego procesu ADB.

## Expected files

- `services/worker/tests/test_release_workflow.py`
- test integracyjny release na fizycznym PostgreSQL
- skrypt przygotowania/odbioru wydania M3.4
- testy mobile aktywacji nowego snapshotu
- raport release i dokumentacja jakości
- `CURRENT_STATE.md`, plan M3 i dokumentacja testów

## Verification

```powershell
pytest services/worker/tests/test_release_workflow.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
pytest services/api/tests/integration -q
npm run quality
npm run android:verify:offline -- --ApkPath <candidate>
```

## Risks / open questions

- Pełny Gradle Release jest wolny i zależy od lokalnego toolchainu oraz
  ignorowanego signing key.
- Fizyczny etap wymaga urządzenia, trybu samolotowego i potwierdzenia tekstu
  diagnostycznego przez właściciela.

## Outcome

Automatyczna część została zaimplementowana: macierz awarii/retry, utrata lease,
anulowanie, niezmienność artefaktów oraz pełny przebieg dwóch wydań na
izolowanym PostgreSQL przechodzą. Generator rzeczywistego kandydata i rozszerzony
protokół aktualizacji urządzenia są gotowe.

Rzeczywisty workflow panel → PostgreSQL → snapshot → Gradle → audyt APK
zakończył się powodzeniem dla wydania `m3.4.3`. Job
`accaa679-0fdf-4456-b695-926b8db67883` ma status `completed`, etap
`apk_verified`, a release `afe2f1ba-fc72-4da2-ba6c-10dc880f6685` ma status
`ready`. APK ma `42 093 006` bajtów i SHA-256
`7a2e1dff24339380d601f19d7888c3dfb06d530e41e128eaeda6e3beca53e9f0`.
Zawiera dokładny snapshot SHA-256
`a22c7746b8367b433198e5ba87ffd539e4a2b991139f055c365cd7092dc2465a`,
wyłącznie ABI `arm64-v8a`, prywatny podpis i nie deklaruje `INTERNET`.
Kontrolowany endpoint pobrania zwraca HTTP 200 oraz
`application/vnd.android.package-archive`.

Usunięto trzy przyczyny awarii fizycznego builda:

- skrypt odnajduje Node również z lokalnego toolchainu/Codex, gdy `node.exe`
  nie znajduje się w wejściowym `PATH`,
- długie komendy Gradle odnawiają lease heartbeatem co 15 sekund,
- przywracanie bazowych assetów zapisuje bajty w miejscu i zachowuje Windows ACL;
  release build usuwa wyłącznie zweryfikowane, wygenerowane katalogi `.cxx`
  spod `node_modules`, aby nie dziedziczyć starej długiej ścieżki `.g`.

Korekta z 2026-07-31 usuwa również przyczyny sesyjne i nieograniczone
oczekiwanie:

- normalny Expo prebuild używa `--no-clean`, a pełne czyszczenie wymaga jawnego
  `-CleanNativeProject`,
- Gradle ma jeden worker, Kotlin działa `in-process`, CMake najwyżej dwa zadania,
  a plugin Expo odtwarza te ustawienia po wygenerowaniu katalogu `android`,
- prebuild i Gradle mają timeouty `5/30` minut kończące całe drzewo procesu,
- build wykonuje `:app:assembleRelease`, bez zbędnego składania AAR-ów bibliotek.

Test timeoutu usunął całe drzewo zimnego builda bez osieroconej Javy. Następnie
pełny build zakończył się w `18m56s`, a przyrostowy build nowym targetem w
`4m05s`. Oba wskazały APK `0.1.4 (5)` o SHA-256
`4fdec4407e54934024f84ea7a6f664cd2648359e8426a4914e185875931b5925`;
niezależny verifier potwierdził prywatny podpis, brak `INTERNET` i SQLite
`4365a33d066a354d212693cd9169dac102b7cb1c164df6693f655e8690e9224a`.

Test regresyjny potwierdza zachowanie tożsamości plików bazowych oraz heartbeat
podczas długiego subprocessu. Bazowy `m1-fixture.2` został po buildzie
przywrócony z pierwotnym SHA-256
`4365a33d066a354d212693cd9169dac102b7cb1c164df6693f655e8690e9224a`.

Raport `.tooling/device-acceptance/update-Pixel_10_Pro_XL.json` potwierdza
aktualizację in-place z `versionCode 4` do `5`, zachowanie `firstInstallTime`,
tryb samolotowy i oczekiwany snapshot `m1-fixture.2` o SHA-256
`4365a33d066a354d212693cd9169dac102b7cb1c164df6693f655e8690e9224a`.
Właściciel zaliczył na tej instalacji podpowiedź duplikatu, layout `#99`,
pełny Target i płynne przewijanie.

Utworzono `ai_docs/quality/m35-release-workflow-acceptance.json`, który wiąże
workflow panel → ready APK, niezmienność, rozmiary, audyt offline i aktualizację
Pixela. Ponowne testy zakończyły się wynikami `14 passed` dla macierzy release,
`1 passed` dla fizycznej integracji PostgreSQL oraz pozytywnym audytem APK
`0.1.4 (5)`. TASK-0039 i bramka G3.4 są ukończone.
