Raport audytu rundy 2 (tylko odczyt, bez uruchamiania testów):

```markdown
# Audyt TASK-1255 — Zastosowanie prywatnego modelu siatki gry

Werdykt: PASS
Audytor: Claude Opus 5.5, przegląd statyczny
Wykonawca: niepodany w pakiecie (gałąź codex/private-grid-models)
Zakres: main...6b4ab8c8 oraz zmiany niezacommitowane (delta naprawcza rundy 2), data 2026-11-18
Runda: 2
SHA pakietu: a6cfdff06cb652b7195faa8330388ba0d1c099b03da168dee3e45dd57ecde4fe
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem tylko poprawkę po rundzie 1 i jej testy regresyjne. Kod usuwa wszystkie trzy wcześniejsze znaleziska. Wspólne zastosowanie sprawdza teraz prywatność celów, gier treningowych i gier z ocenionych kohort. Sprawdzenie działa w podglądzie, przy starcie, wznowieniu i w każdym kroku `advance`. Sygnał wyzwalacza PostgreSQL `GRID_SHARED_PRIVATE_GAME` zamienia się w błąd domenowy z kodem 409 zamiast HTTP 500. Wyjątek przy cofnięciu obejmuje tylko poświadczone wpisy `bootstrap` i `private_enable`. Zostaje jedno nowe ryzyko P2: wyzwalacz bazy i blokada włączenia prywatności nie widzą gier występujących wyłącznie w kohortach.

## Znaleziska

### P0

Brak.

### P1

Brak nowych. Znalezisko P1-1 z rundy 1 jest zamknięte, dowód poniżej.

- [P1-1] zamknięte. Funkcja `services/api/src/game_predictor_api/application/grid_correction_apply.py:194-203` (`_require_shared_scope`) łączy cele, `pins.scope.trainingGameIds` i `pins.cohorts[*].gameId`. Flagi sprawdza jednym zapytaniem `shared_scope_has_private_game` (`services/api/src/game_predictor_api/storage/grid_model_registry.py:397-406`). Gdzie działa sprawdzenie:
  - podgląd: `grid_correction_apply.py:259-261`, a błąd trafia do `blockers` w `:325-326`;
  - start: przez `_preview` pod `repository.lock()`, `:459-469`;
  - wznowienie: `:551-553`;
  - `advance`: `:829`, `:847` i `:859`.

  Wszystkie te ścieżki biorą tę samą blokadę katalogu co `enable_private_model` (`services/api/src/game_predictor_api/application/new_game_geometry.py:275`), więc kontrola aplikacji jest serializowana z włączaniem prywatności. Ścieżka HTTP 500 jest zamknięta. `_map_shared_private_game` (`grid_correction_apply.py:61-72`) obejmuje start (`:442`), wznowienie (`:520`) i transakcje `advance` (`:826`, `:833`, `:844`, `:856`). Kontekst jest otwierany przed `Session`, więc łapie też błąd z flush i commit. `DBAPIError` z SQLSTATE `P0001` i komunikatem `GRID_SHARED_PRIVATE_GAME`, zgodnym z `services/api/alembic/versions/0193_private_game_grid_models.py:66`, zamienia się w `GridCohortError` 409. Worker przekłada ten błąd na `JobHandlerError` (`services/worker/src/game_predictor_worker/images/grid_correction_apply_handler.py:39-40`). Testy regresyjne:
  - `services/api/tests/test_grid_correction_apply.py:814-829` (parametryzacja target, training i cohort);
  - `services/api/tests/integration/test_grid_correction_apply_postgres.py:700-838` (podgląd, start, wznowienie i `advance`, a także wymuszony sygnał SQL przy wyłączonej kontroli aplikacji).

### P2

- [P2-1] zamknięte. W `services/api/src/game_predictor_api/application/grid_model_publication.py:367-378` wyjątek `inherited_base` wymaga teraz `previous_assignment(..., transfer_only=True)`. Implementacja w `services/api/src/game_predictor_api/storage/grid_model_registry.py:619-658` przyjmuje tylko wpisy `bootstrap` i `private_enable` z wcześniejszą rewizją. Pole `command_json` musi być kanoniczne, a jego hash zgodny. Receipt musi zgadzać się z poleceniem: `kind`, `gameId`, `versionId`, `commandSha256` i `evidenceSha256`. Dowód `transfer.sourceVersionId` musi wskazywać cel cofnięcia, a `descriptor_sha256(transfer)` musi równać się `evidence_sha256`. Zgadza się to z zapisem w `new_game_geometry.py:188-206` (bootstrap), `:313-332` (private_enable) i `grid_model_registry.py:665-675` (`apply_control`). Zwykły wpis `activate` przechodzi ocenę właściwą dla gry. Test: `services/api/tests/test_grid_model_publication_and_activation.py:352-401`.
- [P2-2] zamknięte. Sygnatury konkretnego adaptera `SqlAlchemyGridModelRegistryRepository` dokładnie odpowiadają Protocol:
  - `shared_scope_has_private_game(Sequence[UUID]) -> bool`: `grid_model_registry.py:397` wobec `grid_model_publication.py:30`;
  - `previous_assignment(..., *, transfer_only: bool = False) -> bool`: `grid_model_registry.py:619-621` wobec `grid_model_publication.py:34-36`.

  Inny produkcyjny implementator nie istnieje. Według wykonawcy ukierunkowany mypy objął rzeczywiste repozytorium SQLAlchemy. Nie uruchamiałem go, ale statyczna zgodność sygnatur jest potwierdzona.
- [P2-3] `services/api/alembic/versions/0193_private_game_grid_models.py:21-35` w powiązaniu z `services/api/src/game_predictor_api/application/grid_correction_apply.py:200`. Funkcja `grid_operation_game_ids` nie obejmuje `$.pins.cohorts[*].gameId`. Skutki są dwa:
  - wyzwalacz bazy chroni gry treningowe i dodatkowe cele, ale nie gry obecne wyłącznie w kohortach;
  - `active_grid_operation` (`grid_model_registry.py:413-432`) nie blokuje włączenia prywatności takiej gry, gdy wspólne zastosowanie jest aktywne. Następny krok `advance` odmówi wtedy z `GRID_APPLY_SHARED_PRIVATE_GAME`. Jeśli wcześniej zatwierdzono już `set_default`, zastosowanie zostanie częściowo wykonane bez możliwości wznowienia.

  Kontrola aplikacji pod wspólną blokadą zapobiega jednak publikacji i przełączeniu przypisań. Ryzyko ma znaczenie tylko wtedy, gdy kohorty oceny mogą wykraczać poza `trainingGameIds`. Propozycja: dodać ścieżkę `pins.cohorts[*].gameId` nową migracją albo jawnie zaakceptować ryzyko w dokumentacji taska.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Wspólne zastosowanie odmawia, gdy prywatna jest gra docelowa, treningowa lub z kohorty (podgląd, start, wznowienie, advance) | spełnione | `services/api/src/game_predictor_api/application/grid_correction_apply.py:194-203`, `:259-261`, `:442-469`, `:551-553`, `:829`, `:847`, `:859` |
| Odmowa z bazy po włączeniu prywatności daje 409 z kodem domenowym, nie 500 | spełnione statycznie | `services/api/src/game_predictor_api/application/grid_correction_apply.py:61-72`; `services/api/tests/integration/test_grid_correction_apply_postgres.py:823-829` |
| Brak publikacji i zmiany modelu domyślnego po odmowie | spełnione statycznie | `services/api/tests/integration/test_grid_correction_apply_postgres.py:830-835` |
| Wyjątek przy cofnięciu tylko dla poświadczonego bootstrap lub private_enable | spełnione | `services/api/src/game_predictor_api/storage/grid_model_registry.py:633-658`; `services/api/src/game_predictor_api/application/grid_model_publication.py:367-378` |
| Etykieta Admina dla nowego kodu | spełnione | `apps/admin/src/features/model-quality/grid-model-state.ts:166-167` |
| Zgodność typów konkretnych adapterów z Protocol | spełnione statycznie, mypy niezweryfikowany przez audytora | `services/api/src/game_predictor_api/storage/grid_model_registry.py:397`, `:619-621`; `services/api/src/game_predictor_api/application/grid_model_publication.py:30`, `:34-36` |

## Listy zamknięte i otwarte

Zamknięte: P1-1, P2-1, P2-2

Otwarte: P2-3.

## Proponowane testy

- W `services/api/tests/integration/test_grid_correction_apply_postgres.py` dodać wariant, w którym prywatna staje się gra obecna tylko w `pins.cohorts`, a nie w `trainingGameIds`. Należy sprawdzić odmowę `advance` i to, czy `enable_private_model` blokuje taką grę przy aktywnym zastosowaniu. Polecenie: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_correction_apply_postgres.py -k shared`.
- W `services/api/tests/test_grid_model_publication_and_activation.py` dodać przypadek wpisu `private_enable` z uszkodzonym `receipt_json` lub niezgodnym `transfer.sourceVersionId`. Oczekiwane: `transfer_only` zwraca `False`, a cofnięcie wymaga oceny gry.

## Zakres przeglądu i ograniczenia

Przeczytałem deltę naprawczą z pakietu i potrzebny kontekst:
- `services/api/src/game_predictor_api/application/grid_correction_apply.py`: podgląd, start, wznowienie i `advance`;
- `services/api/src/game_predictor_api/application/grid_model_publication.py:320-401`;
- `services/api/src/game_predictor_api/storage/grid_model_registry.py:380-740`;
- `services/api/src/game_predictor_api/application/new_game_geometry.py:150-364`;
- `services/api/src/game_predictor_api/domain/new_game_geometry.py:37-59`;
- migrację `services/api/alembic/versions/0193_private_game_grid_models.py`;
- router `services/api/src/game_predictor_api/api/grid_correction_apply.py`;
- handler workera `services/worker/src/game_predictor_worker/images/grid_correction_apply_handler.py`.

Nie uruchamiałem testów, mypy, lint ani PostgreSQL. Wyniki 71 i 8 testów, 69 interakcji Admina oraz scenariuszy na PostgreSQL 55493 opisuje wykonawca i nie zostały przeze mnie potwierdzone. Zgodność `error.orig.diag.message_primary` z psycopg 3 przyjąłem na podstawie kodu i opisanego testu integracyjnego. Nie przeglądałem ponownie szerokiego zakresu z rundy 1.
```