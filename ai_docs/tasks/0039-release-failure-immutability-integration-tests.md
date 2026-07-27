---
title: Release failure and immutability integration tests
status: in_progress
last_updated: 2026-07-27
---

# TASK-0039 — Release failure and immutability integration tests

## Status

`in_progress`

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

- [ ] Każda kontrolowana awaria kończy job/release jako failed lub cancelled,
  nigdy `ready`.
- [ ] Awaria przed końcowym checkpointem nie publikuje częściowego APK.
- [ ] Utrata lease nie pozwala staremu workerowi oznaczyć release jako failed.
- [ ] Retry zachowuje identyfikator joba i wznawia poprawny checkpoint bez
  duplikowania payoutów.
- [ ] Uszkodzony istniejący snapshot lub APK jest odrzucany, nie nadpisywany.
- [ ] Drugi release nie zmienia ścieżek, checksum ani bajtów pierwszego.
- [ ] Pełny przebieg na PostgreSQL zapisuje dokładne źródła i oba artefakty.
- [ ] Rzeczywisty APK przechodzi audyt offline i zawiera dokładny nowy snapshot.
- [ ] `adb install -r` aktualizuje istniejący pakiet bez czyszczenia danych.
- [ ] Ekran po aktualizacji pokazuje nową `releaseVersion` oraz checksumę.
- [ ] Pełna jakość i fizyczne testy PostgreSQL przechodzą.

## Assumptions

- Do fizycznego odbioru będzie podłączony dokładnie jeden autoryzowany Pixel 10
  Pro XL albo Galaxy S21 Ultra; brak urządzenia nie blokuje automatycznej części.
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

Do uzupełnienia po implementacji i fizycznym odbiorze.
