# TASK-1253 — Własność modelu i utworzenie gry

## Status

`done`

## Goal

Zwykłe tworzenie gry V3 rezerwuje prywatny tryb nauki i wiąże grę z własną rodziną przy pierwszym dopuszczonym przypisaniu.

## Dependencies / entry conditions

Zadanie 1 zaakceptowanego planu. Wykonanie bez migracji bazy operatora, restartów usług i treningu.

## Recommended execution

`gpt-6.2-sol`, `high`. Zachowanie transakcji rezerwacji i historii wymaga sprawdzenia współbieżności oraz zgodności migracji. Kontrola integracyjna jest częścią zadania 3.

## Relevant docs

- [Plan](../delivery/PRIVATE_GAME_GRID_MODELS_PLAN_20261118.md#1-własność-modelu-i-utworzenie-gry)
- [Model danych](../architecture/DATA_MODEL.md#atomowa-rezerwacja-nowej-gry--task-1004)
- [Kontrakt istniejącego tworzenia i transferu](../architecture/API_CONTRACT.md#tworzenie-i-pierwszy-transfer-geometrii-v3--task-1004)
- [Wymagania modeli](../requirements/SUPERVISED_MODEL_IMPROVEMENT.md)

## Scope

- Addytywna migracja, własność rodziny, istniejąca rezerwacja i pierwszy transfer.
- Operatorowe włączenie istniejącej V3 przy aktualnej rewizji i przypisanej wersji, z trwałym potwierdzeniem.
- Ochrona przed wykorzystaniem prywatnych gier przez wspólne treningi, także przez starsze kohorty.

## Out of scope

Wykonanie opt-in Mumii A2 na bazie operatora, uczenie wersji prywatnej, UI zastosowania i pilot.

## Acceptance criteria

- [x] Dwie gry z jednej bazy mają dwie własne rodziny, bez kopii wspólnej wersji. Retry odtwarza rezerwację.
- [x] Bez dopuszczonej bazy rezerwacja zachowuje tryb prywatny. Pierwszy jawny transfer tworzy rodzinę i wiąże historię.
- [x] Stare zapisy zostają wspólne. Włączenie prywatności chroni CAS, aktywne operacje oraz tożsamość i historię bieżącej wersji.
- [x] Wspólny trening z grą prywatną jest blokowany przed pobraniem kohort i przy zapisie lub wznowieniu zadania. Ukończona historia pozostaje czytelna.

## Technical notes

Tryb prywatny zapisuje `games.grid_model_private`. Właściciel w `grid_model_families.owner_game_id` jest odrębny od przypisanej wersji. Kontrole używają istniejącej blokady rejestru 9910994. Przy braku jawnych parametrów forka kod rodziny wynika z UUID gry.

## Expected files

Istniejące `application/new_game_geometry.py`, `application/shared_grid_model_candidate.py`, `storage/grid_model_registry.py`, `storage/grid_model_registry_models.py`, `storage/models.py`. Nowe Alembic 0193 i polecenie operatora w `scripts/`. Testy rezerwacji, rejestru i migracji.

## Test cases

Rezerwacja, jawne i odłożone przypisanie, restart i retry, konflikt rewizji lub klucza, aktywna operacja innej gry z kohortą danej gry oraz blokady SQL i zachowanie historii.

## Outcome

Commit: v1.7.678 / `711d30137ca71781faa76c246a1bd03dfda3ee3c`.

### Changed

- Migracja 0193, prywatna rezerwacja V3, bootstrap i pierwszy transfer. Rodzina ma unikalny UUID właściciela, który chroni wersje także po fizycznym usunięciu gry.
- Polecenie operatora `enable_private_grid_model.py` sprawdza oczekiwaną rewizję, aktywność operacji w zakresie gry i bieżącą wersję. Przechowuje powtarzalny receipt `private_enable`.
- Kontrole nowych wspólnych treningów obejmują wszystkie piny gier i działają przy przygotowaniu, wstawieniu i wznowieniu zadania.

### Verification results

- Izolowany snapshot staged T1 i testowy PostgreSQL na porcie 55493. 54 testy PASS, w tym migracja, wspólny job innej gry, historia po zakończeniu, ochrona modelu po usunięciu gry testowej, HTTP tworzenia i transferu oraz testy rejestru.
- Starszy test rezerwacji TASK-1004 zatrzymał się na zastanej rozbieżności v19/v23. HEAD używa manifestu v23, a test porównuje v19. Nie zmieniano tej asercji.
- Wygenerowany kontrakt Admin API i klient sprawdzono poleceniem `check-generated-client.mjs`. Mapa kodu przeszła `generate_code_map.py --check`.
- Ruff dla zmienionych plików i mypy dla 8 modułów T1 PASS.

### Not completed

- Opt-in i migracja na bazie operatora, trening, publikacja, aktywacja i wdrożenie wymagają osobnych poleceń. Odbiór integracyjny i audyt należą do zadania 3.

### Documentation updates

- D-618, model danych, wymagania uczenia i kontrakt istniejących operacji V3.

### Recommended next task

- TASK-1254. Uczenie z przypisanej wersji danej gry i trwały pin rodziny docelowej.
