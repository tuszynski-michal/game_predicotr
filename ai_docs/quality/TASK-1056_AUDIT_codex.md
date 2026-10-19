# Audyt TASK-1056 — Publiczne trasy serii supergry udostępnionej wyszukiwarki

Werdykt: REVISE  
Audytor: codex, medium  
Wykonawca: claude-fable-5-1, high  
Zakres: HEAD...dc7d757fa4738dca2734063101f08676fadbdd6a oraz zmiany niezacommitowane, data 2026-10-19  
Runda: 1  

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przejrzano publiczne trasy serii, modele odpowiedzi, przekazanie zależności, OpenAPI i wygenerowany klient. Implementacja statycznie realizuje izolację gry z sesji, CAS, aktora audytu i ograniczenie danych publicznych. Brakuje jednak wymaganych testów żądań dla części kryteriów akceptacji.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/tests/test_board_search_share_public_api.py:824` — test czterech tras sprawdza wyłącznie `gameId`, a nie `game_id` i `rulesVersionId`; `services/api/tests/test_board_search_share_public_api.py:898` sprawdza wyłącznie Wild, bez symbolu uruchamiającego, zarchiwizowanego oraz gry typu `none`; `services/api/tests/test_board_search_share_public_api.py:928` nie weryfikuje aktora wpisu audytu. Są to jawnie wymagane przypadki taska. Dodać testy publicznych tras dla wszystkich wariantów i zachowanie bez zapisu po odmowie.

### P2

- [P2-1] `services/api/src/game_predictor_api/schemas/super_game_markers.py:53` — opis OpenAPI nadal twierdzi, że `seriesId` jest pomijane w online share, chociaż udostępniona wyszukiwarka zwraca je po tej zmianie. Poprawić opis na: zwracane przez Admin i share, pomijane tylko przez panel zarządzania.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Proxy, cookie, parametry gry i wersji | niezweryfikowane | Implementacja: `services/api/src/game_predictor_api/api/board_search_share_public.py:157`, `:748`; test nie obejmuje wszystkich parametrów. |
| Obca seria i gra `none`; CAS oraz walidacja symbolu | niezweryfikowane | Implementacja: `services/api/src/game_predictor_api/application/super_game_series.py:428`, `:476`; brakuje wymaganych testów publicznych. |
| Aktor sesji i audyt bez `definedBy` publicznie | spełnione | `services/api/src/game_predictor_api/api/board_search_share_public.py:709`, `services/api/src/game_predictor_api/storage/super_game_series_repository.py:428`, `services/api/src/game_predictor_api/schemas/board_search_shares.py:266`. |
| Brak identyfikatorów wewnętrznych | spełnione | `services/api/src/game_predictor_api/schemas/board_search_shares.py:283`, `services/api/tests/test_board_search_share_public_api.py:860`. |
| `seriesId` w share, brak w panelu zarządzania | spełnione | `services/api/src/game_predictor_api/schemas/board_search_shares.py:197`, `services/api/src/game_predictor_api/api/management_public_stakes.py:93`. |
| `superGameTriggerCount` w symbolach | spełnione | `services/api/src/game_predictor_api/api/board_search_share_public.py:314`, `services/api/src/game_predictor_api/schemas/board_search_shares.py:181`. |
| OpenAPI, klient i eksport typów | niezweryfikowane | Typy istnieją: `packages/admin-api-client/src/generated/types.gen.ts:2159`; nie uruchamiano wymaganych poleceń. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P1-1, P2-1.

## Proponowane testy

- Rozszerzyć `services/api/tests/test_board_search_share_public_api.py` o `game_id` i `rulesVersionId` dla każdej z czterech tras, symbol uruchamiający, zarchiwizowany, grę `none` i aktora wpisu audytu. Uruchomić: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_share_public_api.py services/api/tests/test_super_game_series_api.py -q`.

## Zakres przeglądu i ograniczenia

Przeczytano zmiany API, schematów, routera, integracji serwisu, testów i wygenerowanych typów klienta. Nie uruchamiano testów, generatora OpenAPI, lintów ani typechecków zgodnie z trybem wyłącznie do odczytu.