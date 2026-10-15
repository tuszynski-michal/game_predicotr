# Audyt TASK-0994 — Rejestr rodzin, wersji i przypisań

Werdykt: REVISE
Audytor: claude-fable-5-1, high
Wykonawca: gpt-6.1-sol, high
Zakres: b11cdb19d81711fa801157c8effb3fc78863e46c...c06b7432e76e6e3d24b1cd78757d9f900bc9cac7 oraz zmiany niezacommitowane (brak), data 2026-10-15
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano cały diff taska: migrację 0156 z zamrożonym JSON baz historycznych, warstwy domain/application/storage/schemas/api rejestru, manifest ownership v9, readiness, kontrakt OpenAPI z wygenerowanym klientem i wrapperem, przejściowy filtr UI oraz testy jednostkowe i izolowany test PostgreSQL. Logika rejestru jest spójna z notatkami technicznymi: immutable rodzina/wersja/receipt/zdarzenia pod advisory lock, fail-closed inspekcja artefaktów, jawny zakres gry, addytywny CHECK i wykluczenie kodu `7`, downgrade z odmową. Główne ryzyko to brak rejestracji nowych modeli ORM w `storage/models.py`: nowe tabele mają jawny schemat `public`, więc po załadowaniu w jednym procesie pytest (70 modułów testowych importuje `main`) istniejący test wyczerpujący klasyfikację tabel odrzuci klucze `public.grid_model_*`, co psuje bramkę `python:test`; wykonawca jawnie nie uruchomił pełnego zestawu.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/src/game_predictor_api/storage/grid_model_registry_models.py:23,34,51,61,75,93` oraz `services/api/src/game_predictor_api/storage/models.py:6970-6985` — sześć nowych mapowań ma jawny `{"schema": "public"}`, więc rejestrują się we wspólnym `Base.metadata` pod kluczami `public.grid_model_families`, `public.grid_model_versions`, `public.grid_model_registration_receipts`, `public.grid_model_version_events`, `public.game_grid_model_assignments`, `public.game_grid_model_assignment_events`. Nie dopisano ich do bloku rejestracji mapowań w `models.py` (wzorzec z TASK-0940 dla `management_models` i `grid_engine_acceptance_models`) ani nie zaktualizowano testu wyczerpującego `services/api/tests/test_game_data_v2_schema.py:29-42,57-67`, który nadal importuje manifest v8 i asertuje `set(Base.metadata.tables) <= known` oraz `VERSION == "game-data-v2-manifest-v8"`. Skutek: przy zbieraniu całego katalogu `services/api/tests` pytest importuje `main.py` (70 plików testowych) lub `test_grid_model_registry.py`, które przez `storage/grid_model_registry.py:24-31` ładują nowe mapowania; `known` zawiera tylko nieprefiksowane nazwy v8 i `public.management_*`, więc asercja w linii 60 odrzuca sześć nowych kluczy i bramka `npm run python:test`/`npm run quality` przestaje przechodzić. Dodatkowo nowe tabele są wyłączone z kontroli „każda tabela ORM jest sklasyfikowana”, a plik `models.py` był wymieniony w `Expected files` taska jako istniejący plik do zmiany. Proponowana poprawka: dopisać `grid_model_registry_models` do bloku rejestracji w `models.py`, przestawić `test_game_data_v2_schema.py` na manifest v9 (`VERSION == "game-data-v2-manifest-v9"`, `ADDED_CATALOG`/`ADDED_SHARED` w `known` z prefiksem `public.` albo ze zdjęciem prefiksu jak w `test_postgres_baseline.py:95-97`) i uruchomić pełny zestaw API w jednym procesie.

### P2

- [P2-1] `services/api/src/game_predictor_api/application/grid_model_registry.py:63,72-73,105,108` — każdy `GET /grid-model-versions` liczy SHA-256 wszystkich plików inference i training każdej wersji (dla dwóch baz historycznych ok. 270 MB), a `POST` wykonuje tę samą inspekcję dwukrotnie (przed zapisem i w `view`). Skutek: czas odpowiedzi rośnie liniowo z liczbą wersji i rozmiarem checkpointów, a odświeżanie UI będzie powtarzać pełne hashowanie. Propozycja: w `register` użyć wyniku pierwszej inspekcji zamiast ponownego `view`, a w odczycie listy rozważyć cache po (ścieżka, rozmiar, mtime) z pełnym SHA tylko przy zmianie; alternatywnie zaakceptować ryzyko z adnotacją w Outcome, bo zachowanie jest udokumentowane w `ai_docs/architecture/API_CONTRACT.md:29-30`.
- [P2-2] `services/api/tests/integration/test_postgres_baseline.py:95-97,152,187-192` — `EXPECTED_PUBLIC_TABLES` jest liczone w czasie importu modułu z `Base.metadata`, więc bez poprawki P1-1 wynik `_assert_head_schema` zależy od kolejności zbierania modułów (samodzielne uruchomienie pliku widzi w bazie sześć tabel nieznanych metadanym). Niezależnie od tego cykl downgrade do `0150_management_sessions` przechodzi teraz przez odmowę `0156` (`GRID_MODEL_REGISTRY_DOWNGRADE_REFUSED`), a komentarz „Everything above 0150 is reversible” jest nieaktualny; część tego problemu jest wcześniejsza (odmowa `0152_management_compact_panel`). Propozycja: po P1-1 zaktualizować test cyklu tak, by oczekiwał odmowy 0156 i sprawdzał head schema bez zależności od kolejności importu; wynik `npm run db:baseline:verify` odnotować w Outcome.
- [P2-3] `services/api/alembic/data/grid_model_baselines_v1.json:1-328` i `services/api/src/game_predictor_api/domain/grid_model_registry.py:226-293` — ta sama niezmienna tożsamość baz historycznych istnieje w dwóch źródłach (zamrożony JSON migracji i `historical_catalogue()` z kodu). Test PG porównuje tylko `versionId` (`services/api/tests/integration/test_grid_model_registry_postgres.py:241-244`); dryf pozostałych pól (etykieta, raporty, SHA) ujawniłby się dopiero jako `GRID_MODEL_VERSION_CONFLICT` przy rejestracji przez API albo niespójność `view`. Inspekcja ręczna nie wykazała różnic. Propozycja: test jednostkowy `json.loads(BASELINES_PATH) == list(historical_catalogue())` oraz asercja SHA listy z `0156_grid_model_registry.py:23-26`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Addytywny enum/CHECK dopuszcza `neural_grid_v3` i wszystkie stare wartości; istniejące gry nie są przepisywane | spełnione | `services/api/src/game_predictor_api/domain/catalog.py:45`; `services/api/alembic/versions/0156_grid_model_registry.py:49-57` (brak UPDATE `games`); `services/api/tests/integration/test_grid_model_registry_postgres.py:220-227,248-255`; `services/api/tests/test_grid_engine_profiles.py:326-331` |
| Migracja zachowuje modele obu gier, stara 777 nie otrzymuje neural assignment | spełnione (statycznie) | `0156_grid_model_registry.py:89-133` (`code <> '7'`); `test_grid_model_registry_postgres.py:142-153,233-244,284`; wynik PG4 PASS tylko z deklaracji wykonawcy |
| Brak artefaktu blokuje udostępnienie | spełnione | `services/api/src/game_predictor_api/storage/grid_model_registry.py:45-63,98-109`; `application/grid_model_registry.py:99-110`; `services/api/tests/test_grid_model_registry.py:199-206,316-321,333-350` |
| Powtórna rejestracja jest idempotentna | spełnione | `application/grid_model_registry.py:87-104`; `storage/grid_model_registry.py:119-122,203-224`; `test_grid_model_registry.py:172-196,214-232`; `test_grid_model_registry_postgres.py:290-339` |
| Gra nie odczytuje cudzych danych przez błędny zakres | spełnione | `storage/grid_model_registry.py:227-250`; `main.py:2282-2292` (plain Session bez routera, GET filtrowany po `game_id`); `test_grid_model_registry.py:252-256,294-302`; `test_grid_model_registry_postgres.py:281-287` |
| Wyniki kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | spełnione | `ai_docs/tasks/completed/0994-grid-model-registry.md:210-216`; `ai_docs/architecture/API_CONTRACT.md:9-31`; `ai_docs/architecture/DATA_MODEL.md:168-207`; `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md:316-327`; `ai_docs/guides/LOCAL_OPERATION_GUIDE.md:1674-1689`; niniejszy raport wymaga dopisania przez leada w Outcome i `CURRENT_STATE.md` |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy, runda 1.

Otwarte: P1-1, P2-1, P2-2, P2-3.

## Proponowane testy

- Pełny zestaw API w jednym procesie, który ujawnia P1-1: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_game_data_v2_schema.py services/api/tests/test_grid_model_registry.py` (oraz docelowo `npm run python:test`), po poprawce z rejestracją mapowań i manifestem v9.
- Test wyczerpujący klasyfikację nowych tabel: w `services/api/tests/test_game_data_v2_schema.py` asercja, że `ownership(name)` z manifestu v9 zwraca `shared` dla czterech tabel katalogu i `catalog` dla dwóch tabel przypisań, a klucze `public.*` z `Base.metadata` są objęte `known`.
- Test równości zamrożonego JSON i deskryptorów kodu (P2-3): `services/api/tests/test_grid_model_registry.py`, porównanie `json.loads(grid_model_baselines_v1.json) == list(historical_catalogue())` i SHA listy z migracji.
- Izolowany cykl migracji po poprawkach: `npm run db:baseline:verify` z oczekiwaną odmową `GRID_MODEL_REGISTRY_DOWNGRADE_REFUSED` w `test_postgres_baseline.py`.

## Zakres przeglądu i ograniczenia

Przeczytano w całości: brief, plik taska, fragment planu, migrację 0156 i JSON baz, `domain/grid_model_registry.py`, `application/grid_model_registry.py`, `storage/grid_model_registry.py`, `storage/grid_model_registry_models.py`, `storage/game_data_v2_manifest_v9.py`, `schemas/grid_model_registry.py`, `api/grid_model_registry.py`, diff `main.py`, `grid_engine_profiles.py`, `catalog.py`, readiness, zmiany admin/klienta/wrappera oraz oba nowe testy. Dla kontekstu przeczytano `grid_engine_model_store.py`, `database_roles.py`, `game_storage_routing.py`, `game_partition_lifecycle.py` (ścieżka DELETE gry), politykę legacy usuwania, migracje 0105/0140/0152/0155, `test_game_data_v2_schema.py`, `test_postgres_baseline.py` i skrypt `verify_postgres_baseline.ps1`. Diff `openapi.json`, `types.gen.ts` i `sdk.gen.ts` sprawdzono wyrywkowo (obecność trzech operacji i wartości `neural_grid_v3`), bez pełnej lektury. Nie uruchomiono żadnych testów, poleceń git ani obliczeń SHA (brak narzędzia powłoki w tej sesji); wyniki PG4, hash listy baz, `TASK-0994_PG_RECEIPT.json` i `TASK-0994_BASELINE_INTEGRITY.json` (pliki nieobecne w tym worktree) przyjęto wyłącznie z deklaracji wykonawcy. Nie weryfikowano plików commitu spoza pathspec briefu (`CURRENT_STATE.md`, notatki quality). Semantyka FastAPI 0.139 dla zależności z `yield` (commit po handlerze) jest spójna z pozostałymi zależnościami w `main.py` i nie była przedmiotem znaleziska.
