# Audyt TASK-0998 — Publikacja, aktywacja, domyślna wersja i rollback

Werdykt: REVISE
Audytor: claude-fable-5-1, medium
Wykonawca: gpt-6.1-sol, high
Zakres: acf9ce4079b3ed176b1d40babb77f4e5a3ac9988...acf9ce4079b3ed176b1d40babb77f4e5a3ac9988 oraz zmiany niezacommitowane, data 2026-10-15
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano pełny diff taska: migrację 0157 i frozen manifest v10, nowy serwis `GridModelPublicationService`, kontrakt odczytu dowodu oceny w `domain/grid_model_publication.py`, rozszerzenia repozytorium i modeli ORM, router, schematy, wygenerowany klient oraz testy jednostkowe i PostgreSQL. Mechanizm komend jest spójny z notatkami technicznymi: serializacja advisory lockiem 9910994, odczyt receipt przed CAS, atomowy zapis head/event/receipt, fail-closed dowód oceny bez writera HTTP, jawne historyczne dopuszczenie z realnym raportem i ograniczenia DB (unikalne rewizje, check constraints, triggery immutable). Nie znaleziono błędów P0. Jedyne P1 jest procesowe: task przyjmuje założenia zmieniające model domenowy i architekturę bez wpisu w `DECISION_LOG`. Główne ryzyko techniczne to nieobsłużone wyjątki typu `TypeError`/`ValueError` na ścieżce publikacji kandydata, które dają 500 zamiast stabilnego kodu 409.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `ai_docs/tasks/0998-grid-model-publication-and-activation.md:197` — task wprowadza nowy kontrakt architektoniczny (persisted evaluation read contract `grid-model-evaluation-read-v1`, pięć shared tabel kontrolnych, publikacja jako odrębny immutable wiersz, zasada „invalidation blokuje nowe komendy, ale nie zdejmuje assignment”) i zapisuje, że „Lead accepted the minimal read contract before implementation”. Decyzja nie ma wpisu w `ai_docs/process/decisions/DECISION_LOG_2026.md` (D-549 dotyczy wspólnej geometrii i default, D-548/D-551 pozostają proposed i nie opisują tego kontraktu). `AGENTS.md:235` wymaga wpisu w `DECISION_LOG.md`, gdy założenie zmienia model domenowy albo architekturę. Skutek: źródło prawdy wyższe od dokumentów architektury nie zna kontraktu, na którym mają polegać TASK-0997, TASK-1000 i TASK-1004. Poprawka: lead dodaje pełny wpis (np. D-553) z kontraktem oceny, semantyką currentness/invalidation, granicą „bez automatycznej deaktywacji” i wskazaniem właścicieli (TASK-0997 writer raportów, TASK-0995/0997 invalidations), plus wiersz w indeksie; alternatywnie udokumentowane rozszerzenie D-549.

### P2

- [P2-1] `services/api/src/game_predictor_api/application/grid_model_publication.py:3991` — `UUID(manifest["baseVersionId"])` wykonuje się przed kontrolą `cohortId`/dowodu; `validate_manifest` (`domain/grid_model_registry.py:200`) dopuszcza kandydata `not_evaluated` z `baseVersionId: None`, więc publish takiego kandydata z `evaluationId` kończy się `TypeError` i HTTP 500 zamiast 409 `GRID_MODEL_EVALUATION_REQUIRED`. Analogicznie `catalogue_model_version` w `_version` (`grid_model_publication.py:3968`) rzuca `ValueError`, nie `GridModelRegistryError`. Zachowanie pozostaje fail-closed (nic nie jest zapisane), ale kod błędu nie jest stabilny. Poprawka: sprawdzić `manifest["baseVersionId"] is None` i otoczyć `catalogue_model_version` mapowaniem na `GRID_MODEL_EVALUATION_REQUIRED`/`GRID_MODEL_CONTRACT_UNSUPPORTED`.
- [P2-2] `services/api/src/game_predictor_api/api/grid_model_registry.py:3041` i `:3055` — router woła bezpośrednio `service.repository.history(...)`, omijając warstwę application (`api/` → `application/` → `domain/` z `CLAUDE.md`). Poprawka: dodać `GridModelPublicationService.history(game_id)` i wywoływać ją z routera.
- [P2-3] `services/api/src/game_predictor_api/storage/grid_model_registry.py:3366` — receipt jest szukany tylko w ledgerze właściwym dla scope (globalny albo per gra), więc ten sam `idempotencyKey` użyty raz dla `publish`/`set_default`, a potem dla `activate` innej treści, nie daje `GRID_MODEL_IDEMPOTENCY_CONFLICT`, tylko drugi niezależny zapis. Zgodne z unikalnością DB, ale słabsze niż opis „zmieniona treść pod tym samym kluczem daje konflikt” w `API_CONTRACT.md:486`. Akceptacja ryzyka możliwa (UUID v4 po stronie klienta); alternatywnie sprawdzać oba ledgery przed CAS.
- [P2-4] `services/api/src/game_predictor_api/storage/grid_model_registry.py:3284` — `historical_evidence` czyta z dysku i hashuje raport (do 1 MB) przy każdym `view()` opublikowanej bazy historycznej, czyli przy każdym `GET grid-model-versions`, `GET assignment` i `GET default`; dodatkowo eligibility kandydatów robi osobne zapytania per wiersz (N+1). Funkcjonalnie poprawne, ale koszt rośnie liniowo z liczbą wersji i wywołań panelu TASK-1000. Poprawka: cache SHA raportu w procesie albo porównanie z `evidence_sha256` publikacji bez ponownego czytania pliku.
- [P2-5] `services/api/tests/test_grid_model_publication_and_activation.py:4989` — dowód „rozpoczęty job zachowuje wersję” to roundtrip payloadu `NeuralGridSnapshot` bez joba ani zmiany assignment; test PG (`test_grid_model_publication_postgres.py:4575`) sprawdza preflight po invalidation, nie po rollback. Kryterium jest pokryte pośrednio przez regresje TASK-1012 (`test_dynamic_grid_snapshots.py`, worker replay). Poprawka: dodać test, który po `activate` i `rollback` odczytuje snapshot zapisanego joba/propozycji i potwierdza niezmieniony pin.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Dwie konkurencyjne aktywacje nie nadpisują się | spełnione | `application/grid_model_publication.py:4104-4127` (lock, refreshed head, CAS), `storage/grid_model_registry.py:3275-3278` (`populate_existing`), `0157_grid_model_publication.py:3870-3875` (unikalne `(game_id, revision)`), test PG `test_grid_model_publication_postgres.py:4529-4555` (barrier, jeden zwycięzca, jeden `GRID_MODEL_REVISION_CONFLICT`); deklarowany wynik wykonawcy 2 PASS |
| Brak PASS blokuje nowego kandydata | spełnione | `domain/grid_model_publication.py:4189-4271` (fail-closed, tylko server producer/schema/policy, pełne per-game PASS), `schemas/grid_model_registry.py:3157-3161` (`extra="forbid"`, tylko `evaluationId`), testy `test_grid_model_publication_and_activation.py:4851-4897`, `:5067-5082`, `:5084-5107` (422 dla `passed`/`report`/`actor`, 409 bez raportu) |
| Rozpoczęty job zachowuje wersję | spełnione (pośrednio) | `storage/grid_model_registry.py:3392-3456` (`apply_control` dotyka tylko assignment/event/publication/default), test PG `:4557-4578` (preflight niezmieniony po invalidation), regresje TASK-1012 w Outcome (`test_dynamic_grid_snapshots.py`, worker replay); bezpośredni test po rollback brak, patrz P2-5 |
| Rollback nie zmienia wycinków | spełnione | `apply_control` nie dotyka tabel source/crop/canonical/sequence/symbol/job; test `test_grid_model_publication_and_activation.py:4953-4995` (bajty artefaktów identyczne, historia `rollback/activate/historical_assignment`), test PG `:4632-4649` |
| Wyniki kontroli, audytu i ograniczeń w Outcome; dokumentacja odpowiada zachowaniu | niezweryfikowane | Outcome wypełnione (`0998-...md:238-294`), `API_CONTRACT.md:461-515`, `DATA_MODEL.md:622-658`, `GAME_DATA_V2_OWNERSHIP.md:680-697`, `LOCAL_OPERATION_GUIDE.md:721-743` zgodne z kodem; checkbox pozostaje otwarty do czasu tego raportu i brakuje wpisu `DECISION_LOG` (P1-1); wyniki testów nie były odtwarzane przez audytora |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy, runda 1.

Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- Publish kandydata z `baseVersionId: None` i `evaluationId` zwraca 409 `GRID_MODEL_EVALUATION_REQUIRED`, nie 500; plik `services/api/tests/test_grid_model_publication_and_activation.py`, polecenie `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_model_publication_and_activation.py -k base_missing`.
- Po `activate` i `rollback` zapisany snapshot joba/propozycji (resolver TASK-1012 z zapisanym `engineSnapshot`) zwraca ten sam pin co przed komendą; ten sam plik, `-k job_pin_after_rollback`.
- Ten sam `idempotencyKey` użyty dla `set_default` i następnie `activate` innej treści: jawnie utrwalić oczekiwane zachowanie (konflikt albo akceptacja ryzyka) w teście i w `API_CONTRACT.md`.
- Rollback do wersji równej bieżącemu head (wcześniejszy event tej samej wersji istnieje) tworzy nową rewizję bez zmiany targetu; utrwalić, czy to pożądane, albo odrzucić kodem `GRID_MODEL_ROLLBACK_TARGET_INVALID`.

## Zakres przeglądu i ograniczenia

Przeczytano w całości brief `artifacts/audits/TASK-0998_BRIEF_claude.md` (task, plan, pełny diff śledzonych plików, nowe pliki: migracja 0157, `application/grid_model_publication.py`, `domain/grid_model_publication.py`, `game_data_v2_manifest_v10.py`, oba nowe testy) oraz dla weryfikacji fragmenty repozytorium: `alembic/versions/0156_grid_model_registry.py` (nazwy constraintów, triggery, unikalność `(game_id, idempotency_key)`), `storage/grid_model_registry.py` (lock, `version`, `assignment`), `domain/grid_model_registry.py` (`validate_manifest`), `domain/grid_model_snapshots.py` (`catalogue_model_version`, `uses_neural_grid`), `security/local_admin.py` (`ADMIN_ACTOR`), `main.py` (handler `GridModelRegistryError`), `AGENTS.md` (reguła DECISION_LOG), indeks D-548–D-552 i obecność `ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md`. Diff OpenAPI i wygenerowanego klienta (`openapi.json`, `sdk.gen.ts`, `types.gen.ts`) przejrzano tylko przez wrapper i test żądań; spójność opiera się na deklarowanym PASS `npm run openapi:check`. Nie uruchamiano testów, migracji, lintów ani poleceń git; wyniki weryfikacji wykonawcy (92 PASS + 1 celowany retry, 2 PASS PG, 116 PASS klienta) nie były odtwarzane. Nie oceniano rzeczywistej jakości modelu ani fixture'owych raportów PASS, zgodnie z granicą TASK-0997.
