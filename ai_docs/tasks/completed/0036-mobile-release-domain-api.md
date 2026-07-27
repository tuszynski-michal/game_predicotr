---
title: Mobile release domain and API
status: done
last_updated: 2026-07-27
---

# TASK-0036 — Mobile release domain and API

## Status

`done`

## Goal

Utworzyć trwały, wersjonowany rekord wydania Android wraz z dokładnym zestawem
gier i typowanym Admin API, który stanie się niezmiennym wejściem workflow
TASK-0037.

## Context

M3.3 dostarcza zweryfikowany produkcyjny snapshot, ale nie istnieje jeszcze
kanoniczny rekord wybierający wersję datasetu i reguł dla każdej gry. Payload
jobów `snapshot` i `android_build` wskazuje `mobileReleaseId`, dlatego wydanie
musi powstać przed podłączeniem handlerów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- migracja Alembic `0010_mobile_releases`,
- domena statusów i niezmiennego wyboru gier wydania,
- globalnie unikalna, bezpieczna wersja użytkowa wydania,
- zapis aktualnego `algorithm_version = payout-v2` oraz
  `snapshot_schema_version = 2` po stronie backendu,
- dokładnie jeden wybór dataset/rules dla każdej dołączonej gry,
- walidacja opublikowanych źródeł, właściciela gry, zgodnych wymiarów i dodatniej
  liczby layoutów,
- atomowe utworzenie rekordu rodzica i wszystkich wyborów,
- listowanie i pobranie szczegółów wydania przez Admin API,
- deterministyczna kolejność gier oraz wydań,
- OpenAPI i wygenerowany klient TypeScript,
- testy domeny, HTTP, migracji i fizycznego PostgreSQL.

## Out of scope

- endpoint `/build`, tworzenie joba i przejście do `building`,
- handler snapshotu albo Android build,
- zapis ścieżek i checksum artefaktów,
- zmiany statusu `building/ready/failed`,
- panel wydań oraz otwieranie katalogu,
- instalacja APK i aktywacja snapshotu na urządzeniu.

## Acceptance criteria

- [x] Migracja jest jedynym headem i ma poprawny upgrade/downgrade.
- [x] Wydanie zapisuje unikalną wersję, status `draft`, algorytm i schema.
- [x] Wydanie zawiera od 1 do 15 unikalnych gier.
- [x] Każdy wybór wskazuje dokładnie jedną opublikowaną wersję datasetu i reguł
  tej samej gry.
- [x] Niezgodne wymiary, staging/archived źródło, pusta lista albo duplikat gry
  są odrzucane stabilnym błędem.
- [x] Backend, a nie klient, ustala algorytm i schema snapshotu.
- [x] Utworzenie rodzica i wszystkich wyborów jest atomowe.
- [x] GET list/detail zwraca UUID i numery wersji, wymiary oraz `layoutCount`.
- [x] Lista gier jest uporządkowana po stabilnym kodzie, a lista wydań od
  najnowszego rekordu.
- [x] Ponowna wersja nie nadpisuje istniejącego wydania.
- [x] OpenAPI i klient TypeScript nie mają driftu.
- [x] Testy standardowe i fizyczny PostgreSQL przechodzą.

## Assumptions

- W TASK-0036 publiczny klient nie wybiera dowolnego algorytmu ani wersji schema;
  serwer zapisuje jedyny aktualnie obsługiwany zestaw `payout-v2` / `2`.
- Wersja jest bezpiecznym segmentem ścieżki zgodnym z produkcyjnym snapshotem:
  litery ASCII, cyfry, kropka, podkreślenie i łącznik, bez separatorów ścieżki.
- Draft po utworzeniu jest strukturalnie niezmienny. Korekta wyboru oznacza nowe
  wydanie z nową wersją.
- `buildJobId`, ścieżki, checksumy i czasy gotowości pozostają puste do TASK-0037.

## Expected files

- `services/api/alembic/versions/0010_mobile_releases.py`
- `services/api/src/game_predictor_api/domain/mobile_releases.py`
- `services/api/src/game_predictor_api/application/mobile_releases.py`
- `services/api/src/game_predictor_api/storage/mobile_release_repository.py`
- `services/api/src/game_predictor_api/api/mobile_releases.py`
- `services/api/src/game_predictor_api/schemas/mobile_releases.py`
- mapowania ORM, composition root, OpenAPI i klient TypeScript
- testy domeny/API/fizycznego PostgreSQL
- dokumentacja modelu, API, decyzji, testów i bieżącego stanu

## Verification

```powershell
pytest services/api/tests/test_mobile_releases_domain.py -q
pytest services/api/tests/test_mobile_releases_api.py -q
pytest services/api/tests/integration/test_mobile_release_repository.py -q
npm run quality
```

## Risks / open questions

- Brak pytania blokującego. Przejścia statusów i powiązanie z jednym build jobem
  należą do TASK-0037.

## Outcome

- Migracja `0010_mobile_releases` tworzy trwałe `mobile_releases` i
  `mobile_release_games`, enum lifecycle, constraints bezpiecznej wersji,
  kompletnych par path/checksum i nieujemnych źródeł oraz wszystkie FK.
- Domena i serwis wymagają 1–15 unikalnych aktywnych gier, opublikowanych
  dataset/rules tej samej gry, zgodnych wymiarów i dodatniej liczby layoutów.
  Backend zapisuje `payout-v2` i schema `2`, a wybory są kanonicznie sortowane.
- Repozytorium blokuje źródła i atomowo zapisuje rodzica z całym zestawem gier.
  Unikalna wersja oraz brak częściowego zapisu są chronione również przez
  fizyczny PostgreSQL.
- Admin API udostępnia typowane POST/list/detail, stabilne błędy oraz pełne
  identyfikatory i numery wersji. OpenAPI, wygenerowany klient i jego publiczny
  wrapper zostały zaktualizowane.
- Pełna bramka jakości przeszła: 212 standardowych testów Python, 63 mobile,
  51 panelu, 23 wspólnej domeny i 9 klienta API oraz 7 fizycznych testów
  PostgreSQL.
