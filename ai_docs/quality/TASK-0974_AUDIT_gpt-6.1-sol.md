# Audyt TASK-0974 — Import V3 dla profilu `grid_profile_777_v2`

Werdykt: REVISE
Audytor: gpt-6.1-sol, reasoning high
Wykonawca: claude-opus-5-5, reasoning high (według zadania)
Zakres: HEAD...cc1ef11a3475d37d6fb9a9799d7929c45bfa7b56 oraz zmiany niezacommitowane, data 2026-10-11
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zmiana wybiera model według profilu gry, rozszerza kontrakt snapshotu i pokazuje V3 dla profilu 777 v2. Zachowano historyczny identyfikator polityki oraz manifest modelu Mumii. Brakuje wymaganych testów przepływu odrzucającego snapshot innego profilu; nowy test sprawdza jedynie funkcję porównującą profile.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/tests/test_neural_page_geometry_api.py:703` — Test `test_frozen_neural_snapshot_is_reused_only_for_the_games_current_profile` wywołuje wyłącznie `_neural_profile_matches_game`. Nie sprawdza wymaganego pominięcia obcego kandydata podczas ponownego preflightu ani błędu `NEURAL_GRID_PREFLIGHT_INVALID` przy starcie importu. Usunięcie kontroli z miejsc wywołania w `application/jobs.py:2162` i `application/jobs.py:2222` pozostawiłoby ten test zielony. Dodać testy obu przepływów z poprawnym, ukończonym preflightem Mumii i bieżącym profilem gry 777 v2, zachowując zgodność pozostałych danych i checksum. Sprawdzić wybór snapshotu 777 przy ponownym preflighcie oraz odrzucenie startu bez utworzenia joba importu.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Preflight 777 v2 wybiera model 777, Mumie zachowują własny model | spełnione | `services/api/src/game_predictor_api/storage/grid_profile_snapshot_resolver.py:45`; `services/api/tests/test_grid_profile_snapshot_resolver.py:153` |
| Admin pokazuje V3 z etykietą 777 v2; gry bez profilu zachowują dotychczasowy wybór | spełnione | `apps/admin/src/features/imports/image-folder-import-panel.tsx:290`; `apps/admin/test-interactions/neural-import-readiness.test.mjs:409` |
| Obcy snapshot nie jest używany przy ponownym preflighcie ani starcie importu | spełnione w analizie statycznej; wymagane testy niespełnione | `services/api/src/game_predictor_api/application/jobs.py:2162` i `:2222`; P1-1 |
| Istniejące payloady Mumii i identyfikator polityki pozostają ważne | spełnione | `services/api/src/game_predictor_api/domain/neural_grid_proposal.py:38` i `:125`; `services/api/tests/test_neural_grid_proposal.py:174` |
| OpenAPI i klient zregenerowane; wymagane kontrole zielone | niezweryfikowane | Diff `packages/admin-api-client/openapi/openapi.json:20003` jest zgodny ze schematem; wyniki kontroli zadeklarowano w `ai_docs/tasks/completed/0974-neural-import-777-v2-profile.md:114`, bez uruchamiania podczas audytu |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P1-1.

## Proponowane testy

- W `services/api/tests/test_neural_page_geometry_api.py` dodać regresję ponownego preflightu: ukończony kandydat Mumii zostaje pominięty, a nowy job otrzymuje snapshot modelu 777 v2.
- W tym samym pliku dodać regresję startu importu: poprawny descriptor preflightu Mumii dla gry z bieżącym profilem 777 v2 powoduje `NEURAL_GRID_PREFLIGHT_INVALID`, bez zapisania importu.
- Po poprawce uruchomić w PowerShell, z właściwym `PYTHONPATH`: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_neural_page_geometry_api.py services/api/tests/test_grid_profile_snapshot_resolver.py services/api/tests/test_neural_grid_proposal.py -q`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, zmiany backendu, Admina, testów i kontraktu oraz powiązane fragmenty wymagań, architektury i decyzji D-521/D-544. Sprawdzono ścieżkę workera odczytującą model z zamrożonego snapshotu; wybór katalogu modelu korzysta z `snapshot.version`.

Nie uruchamiano testów, generatorów, usług ani importów. Deklarowane wyniki weryfikacji nie zostały niezależnie potwierdzone. Brak fragmentu planu w briefie uniemożliwia ocenę zgodności z osobnym zaakceptowanym planem. Nie oceniano jakości modelu na danych produkcyjnych ani wdrożenia.