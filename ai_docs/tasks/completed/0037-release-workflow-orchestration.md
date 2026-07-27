---
title: Release workflow orchestration
status: done
last_updated: 2026-07-27
---

# TASK-0037 — Release workflow orchestration

## Status

`done`

## Goal

Połączyć niezmienny `mobile_release` z jednym trwałym workflow:
walidacja → brakujące payouty → snapshot → weryfikacja → Android build →
weryfikacja, kończąc statusem `ready` wyłącznie po pełnym sukcesie.

## Context

TASK-0036 dostarczył niezmienny wybór wersji gry i API release. Istnieją już
resumowalne payouty oraz deterministyczny, walidowany artefakt snapshotu, ale
brakuje atomowego uruchomienia, handlera nadrzędnego i publikacji APK.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- `POST /api/v1/admin/mobile-releases/{releaseId}/build`,
- atomowe utworzenie dokładnie jednego joba `android_build`, przypięcie go do
  draftu i przejście release do `building`,
- ponowna walidacja niezmiennego wyboru bezpośrednio przed startem,
- jeden resumowalny handler nadrzędny bez child-jobów,
- precompute wyłącznie brakujących payoutów z checkpointem per gra,
- publikacja i ponowna walidacja snapshotu,
- kontrolowany build Release APK bez dowolnej komendy od klienta,
- sprawdzenie, że APK zawiera dokładny snapshot i nie ma uprawnienia Internet,
- niezmienne ścieżki i SHA-256 snapshotu oraz APK,
- `ready` dopiero po zapisie obu zweryfikowanych artefaktów,
- `failed` po kontrolowanym błędzie lub anulowaniu; retry wznawia ten sam job,
- obsługa produkcyjnego manifestu snapshotu przez aplikację mobilną,
- OpenAPI, klient TypeScript oraz testy domeny, HTTP, restartu i PostgreSQL.

## Out of scope

- panel tworzenia i monitorowania release (`TASK-0038`),
- pełna macierz awarii i fizyczny test aktualizacji urządzenia (`TASK-0039`),
- benchmark 500 000 layoutów (`M3.5`),
- automatyczna instalacja APK,
- publiczna dystrybucja, chmura, Celery/Redis i dowolne komendy użytkownika.

## Acceptance criteria

- [x] Build draftu atomowo tworzy jeden job i ustawia `building`.
- [x] Drugi build tego samego release nie tworzy kolejnego joba.
- [x] Zmiana stanu wybranego źródła przed buildem blokuje start.
- [x] Workflow dopełnia brakujące payouty idempotentnymi upsertami i zachowuje
  ciągłość.
- [x] Retry wznawia payout albo używa ponownie w pełni zweryfikowanego artefaktu.
- [x] Snapshot jest zgodny z dokładnym zestawem release i zapisuje checksum.
- [x] Builder uruchamia wyłącznie przypięty proces Release dla arm64-v8a.
- [x] APK zawiera SQLite o checksumie release i przechodzi audyt offline.
- [x] Błąd lub anulowanie nie może ustawić `ready`.
- [x] `ready` ma kompletne, względne ścieżki i checksumy SQLite/APK.
- [x] Poprzednie artefakty nie są nadpisywane.
- [x] OpenAPI i klient TypeScript nie mają driftu.
- [x] Testy standardowe i fizyczny PostgreSQL przechodzą.

## Assumptions

- `android_build` jest nazwą typu nadrzędnego workflow, a nie tylko ostatniego
  procesu Gradle.
- Jeden lokalny worker wykonuje workflow sekwencyjnie; child-joby nie powstają.
- Checkpoint schema v1 przechowuje etap, ukończone gry i aktywny checkpoint
  payoutu, dzięki czemu retry dotyczy tego samego joba.
- `created_at` release jest stabilnym czasem wejściowym snapshotu.
- Android `versionCode` jest wyprowadzany deterministycznie z czasu utworzenia
  release; docelowa polityka dystrybucji pozostaje zakresem M8.
- Produkcyjny manifest schema v1 jest źródłem prawdy dla mobilnej walidacji;
  fixture M1 pozostaje wspierany przejściowo.

## Expected files

- domena, serwis i repozytorium `mobile_releases`
- schema/router Admin API i composition root
- `services/worker/src/game_predictor_worker/releases/`
- rejestracja handlera w worker CLI
- kontrolowany adapter/skrypt Android
- mobilna walidacja produkcyjnego manifestu
- testy API, handlera, artefaktów i PostgreSQL
- OpenAPI, klient TypeScript oraz dokumentacja

## Verification

```powershell
pytest services/api/tests/test_mobile_releases_domain.py -q
pytest services/api/tests/test_mobile_releases_api.py -q
pytest services/worker/tests/test_release_workflow.py -q
pytest services/api/tests/integration/test_mobile_release_repository.py -q
npm run quality
```

## Risks / open questions

- Pełny Gradle Release jest wolny i zależy od lokalnego toolchainu; testy
  standardowe używają kontrolowanego fake buildera, a rzeczywisty adapter jest
  statycznie i integracyjnie sprawdzany bez budowania APK przy każdym teście.
- Stała ścieżka assetu Metro wymaga kontrolowanej podmiany wejścia na czas
  builda i bezwarunkowego odtworzenia plików repozytorium.

## Outcome

- Endpoint `/mobile-releases/{id}/build` rewaliduje i blokuje źródła, atomowo
  tworzy jeden job `android_build`, przypina go do release i ustawia `building`.
- Worker wykonuje pełny workflow w jednym jobie. Checkpoint schema v1 zapisuje
  ukończone gry oraz aktywny checkpoint payoutu, a retry nie tworzy child-jobów.
- Produkcyjny publisher generuje i ponownie waliduje SQLite; release zapisuje
  względną ścieżkę oraz SHA-256. Kontrolowany adapter podmienia assety tylko na
  czas Release builda, zawsze je odtwarza, wymusza `arm64-v8a`, uruchamia audyt
  offline i publikuje content-addressed APK bez nadpisania historii.
- `ready` wymaga aktywnego, nieanulowanego joba, snapshotu i zweryfikowanego APK.
  Kontrolowany błąd lub anulowanie daje `failed`; częściowy APK nie trafia do
  rekordu release.
- Mobile obsługuje produkcyjny manifest M3 schema v1 oraz przejściowy fixture M1.
  OpenAPI, wygenerowany klient i publiczny wrapper zawierają operację build.
- Pełna bramka jakości przeszła: 219 standardowych testów Python, 64 mobile, 51
  panelu, 23 wspólnej domeny i 9 klienta API. Ponadto przeszło 7 fizycznych
  testów PostgreSQL. Rzeczywisty pełny Gradle/APK i aktualizacja urządzenia
  pozostają zgodnie z planem w TASK-0039.
