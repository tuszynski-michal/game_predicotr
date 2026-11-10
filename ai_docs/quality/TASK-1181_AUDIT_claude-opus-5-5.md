# Audyt TASK-1181 — Odczyt zadań jakości symboli w Jobs

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...a9af003222c0dcf052c96977bb0109396590902e oraz zmiany niezacommitowane, data 2026-11-10
Runda: 1
SHA pakietu: 7fe9fa0798b118c99893cc8d52d776a3974c20f7e9e1c72a3c55960039bae50e
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem, czy nowy model odczytu `SymbolReadabilityJobPayload` i gałąź w `_payload_from_domain` zgadzają się z rzeczywistym producentem w `storage/symbol_readability.py`. Sprawdziłem też pełność rozgałęzienia po wszystkich wartościach `JobType`, łańcuch backend → OpenAPI → wygenerowany klient → wrapper oraz nowe testy. Model odczytu jest ścisły i dokładnie odpowiada kontraktowi producenta. Nowa gałąź zamyka ostatni typ, który dotąd wpadał w awaryjną ścieżkę Androida. Ogólne `POST /jobs` się nie zmienia, a typy nie są pisane ręcznie. Ryzyka resztkowe są drobne: test Pythona nie sprawdza wprost liczników `succeeded/failed/review`, test SDK pokazuje tylko przekazywanie żądań i odpowiedzi, a dowód odczytu rzeczywistych danych leży w ignorowanym katalogu.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/tests/test_jobs_readability_response.py:33` — test ustawia `progress_current`, `progress_total` i `stage`, ale nie ustawia `success_count`, `failure_count` ani `review_count`. Asercje w liniach 65–67 sprawdzają tylko `current`, `total` i `stage`. Kryterium „liczniki nie znikają z Jobs” jest więc w Pythonie potwierdzone tylko częściowo. W praktyce mapowanie liczników jest wspólne dla wszystkich typów (`services/api/src/game_predictor_api/schemas/jobs.py:1209-1215`), więc ryzyko jest małe. Proponowana poprawka: ustawić w `replace(...)` niezerowe `success_count`, `failure_count` i `review_count` oraz dodać asercje `value["progress"]["succeeded"|"failed"|"review"]`.
- [P2-2] `packages/admin-api-client/test/jobs-readability-request.test.mjs:8` — fixture nie jest pełnym `JobResponse`: brakuje m.in. `workerVersion`, `attemptCount`, `createdAt` i `updatedAt`. Plik `.mjs` nie jest objęty sprawdzaniem typów. Test dowodzi więc tylko, że `listJobs` i `getJob` przekazują parametry i odpowiedź, a nie zgodności typu `SymbolReadabilityJobPayload` z unią `JobResponse.inputPayload`. Zgodność wynika z wygenerowanego `types.gen.ts`, który powstaje z OpenAPI. Proponuję akceptację ryzyka albo dodanie przypisania z `satisfies JobResponse` w pliku TS objętym typecheckiem.
- [P2-3] `ai_docs/quality/TASK-1181_VERIFICATION.md:50` — dowód odczytu 50 rzeczywistych jobów wskazuje na `artifacts/operator-readonly.json`, czyli na katalog ignorowany przez repozytorium. Po zamknięciu taska dowód nie zostanie w historii, zostaje tylko jego opis w dokumencie. Proponuję akceptację ryzyka: podsumowanie populacji i trybu READ ONLY jest zapisane w dokumencie, a dane operatora i tak nie powinny trafiać do repozytorium.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| prepare/fit/scan i AndroidBuild mają właściwe odpowiedzi; błąd historyczny i liczniki nie znikają; lista mieszana zwraca 200 | spełnione (statycznie, liczniki częściowo, zob. P2-1) | `services/api/src/game_predictor_api/schemas/jobs.py:664-668` i `:1545-1546`; producent `services/api/src/game_predictor_api/storage/symbol_readability.py:253-258` zapisuje dokładnie te cztery pola; każde `JobType` poza `ANDROID_BUILD` ma teraz własną gałąź (`schemas/jobs.py:1491-1583`, `domain/jobs.py:13-38`); test `services/api/tests/test_jobs_readability_response.py:13-75` (trzy akcje, status, błąd, Android w tej samej liście) |
| Wadliwe akcje, identyfikatory i pola pozostają odrzucane; API tworzenia bez zmian | spełnione | `ApiModel` ma `extra="forbid"` (`services/api/src/game_predictor_api/schemas/catalog.py:28-33`); `Literal[1]`, `Literal["symbol_readability"]`, `Literal["prepare","fit","scan"]` i `UUID` w `schemas/jobs.py:665-668`; testy `test_jobs_readability_response.py:78-100` (pięć wariantów) i `:103-121` (422, brak joba); `services/api/tests/test_jobs_api.py:1132-1140` sprawdza dokładnie pięć typów tworzenia; diff nie dotyka `JobCreateRequest` |
| Kontrakt klienta i request test zgodne; rzeczywisty odczyt bez zapisów | spełnione dla kontraktu; odczyt rzeczywisty niezweryfikowany | `packages/admin-api-client/openapi/openapi.json` (nowy schemat i wpis w unii), `src/generated/types.gen.ts` i `src/generated/index.ts`, eksport w `packages/admin-api-client/src/index.ts`; wrapper `src/index.ts:3239-3253` bez zmian; `test/jobs-readability-request.test.mjs:5-58`; odczyt READ ONLY tylko według deklaracji w `ai_docs/quality/TASK-1181_VERIFICATION.md:46-51` |
| Kontrole, audyt i zamknięcie rozliczone; wynik gotowy do decyzji o wdrożeniu | niezweryfikowane (w toku) | Wyniki testów, lint, mypy i build są deklaracjami wykonawcy (`TASK-1181_VERIFICATION.md:24-42`); ten audyt jest rundą 1; zamknięcie taska jeszcze nie nastąpiło (`ai_docs/tasks/1181-jobs-readability-response.md`, status `in_progress`) |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P2-1, P2-2, P2-3.

## Proponowane testy

- W `services/api/tests/test_jobs_readability_response.py` dopisać niezerowe `success_count`, `failure_count` i `review_count` oraz asercje pól `progress.succeeded`, `progress.failed` i `progress.review`. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_jobs_readability_response.py`.
- Opcjonalnie dodać kontrolę typu w pliku TS objętym `npm run typecheck --workspace @game-predictor/admin-api-client` (lub odpowiednim workspace). Literał readability przypisany do `JobResponse['inputPayload']` z `satisfies` potwierdzi zgodność wygenerowanej unii bez uruchamiania API.

## Zakres przeglądu i ograniczenia

Przeczytałem cały pakiet audytu (task, diff, nowe pliki) oraz potrzebny kod poza nim:
- `services/api/src/game_predictor_api/schemas/jobs.py`: `_payload_from_domain`, `JobResponse.from_domain`, `JobProgressResponse`;
- `services/api/src/game_predictor_api/domain/jobs.py` (enum `JobType`);
- miejsce, w którym producent zapisuje payload w `services/api/src/game_predictor_api/storage/symbol_readability.py`;
- konfigurację `ApiModel` w `schemas/catalog.py`;
- pomocnik `_client` i `MemoryJobRepository` w testach;
- wrapper `listJobs`/`getJob` w `packages/admin-api-client/src/index.ts`;
- etykiety i kontekst jobów w `apps/admin/src/features/jobs/job-state.ts`.

Etykieta `symbol_readability` już istnieje. `jobContextLabel` przy niepustym `gameId` nie zagląda do payloadu, a bez `mobileReleaseId` nie myli readability z budową Androida.

Nie uruchamiałem testów, lintera, mypy, generacji OpenAPI, buildów ani żadnych poleceń powłoki. Wszystkie wyniki PASS w Outcome i raporcie weryfikacji to deklaracje wykonawcy, których statycznie nie da się potwierdzić. Pełnej treści wygenerowanego `sdk.gen.ts` ani zgodności całego `openapi.json` z eksportem nie sprawdzałem. Odczytu rzeczywistej bazy w trybie READ ONLY i pliku `artifacts/operator-readonly.json` też nie weryfikowałem. Nie sprawdzałem plików TASK-1180 poza potwierdzeniem, że diff ich nie obejmuje.