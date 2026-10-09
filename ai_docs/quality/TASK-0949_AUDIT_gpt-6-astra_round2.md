# Audyt TASK-0949 — Odrzucanie przyciętej planszy i slotu odroczonego w Reviewerze

Werdykt: REVISE
Audytor: gpt-6-astra, medium
Wykonawca: claude-sonnet-5-5, high
Zakres: HEAD...f8fa2ae0ba9ed57e0e8777f7c20c0a205de56040 oraz zmiany niezacommitowane, data 2026-10-09
Runda: 2

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Poprawki usuwają cztery problemy opisane w pierwszym raporcie: odrzucone plansze znikają z weryfikacji, operacje slotu mają trwałą tożsamość, a nieaktualny podgląd otrzymuje kontrolowaną odmowę. Pozostają dwa błędy dotyczące istniejących plansz: niepełna obsługa liczników przy ponownym rozstrzygnięciu oraz brak sprawdzania tożsamości polecenia podczas odtwarzania cofnięcia.

## Znaleziska

### P0

- **[P0-5] `services/api/src/game_predictor_api/storage/image_review_repository.py:1160` — Liczniki nie obsługują przejścia z `rejected` bezpośrednio do `accepted` lub `corrected`.** Istniejąca ścieżka rozstrzygnięcia nadal dopuszcza takie przejście. Odrzucenie odejmuje komórki od liczników, ale ich przywrócenie dodano wyłącznie w osobnej ścieżce cofnięcia odrzucenia. Zwykła synchronizacja traktuje komórki reaktywowanej pozycji jako wcześniej policzone (`services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:2538`). W rezultacie może zgłosić `SYMBOL_CELL_REVIEW_COUNT_PROJECTION_NEGATIVE` albo utrwalić liczniki niezgodne z listą. Należy uwzględnić poprzedni status także przy bezpośrednim ponownym rozstrzygnięciu i doliczyć przywracane komórki dokładnie raz.

- **[P0-6] `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:462` — Cofnięcie odrzucenia planszy odtwarza sukces dla innego polecenia.** Zapytanie `_REOPEN_REPLAY_SQL` wyszukuje zdarzenie według pozycji, klucza i akcji `reopened`, ale nie porównuje `command_sha256` ani `rejectionEventId`. Scenariusz: odrzucenie A, cofnięcie kluczem K, odrzucenie B, próba cofnięcia B kluczem K. API zwróci `created=false` i identyfikator cofnięcia A, przedstawiając wynik jako dotyczący B, mimo że plansza pozostanie odrzucona. Należy sprawdzać zgodność zapisanego polecenia z żądaniem i zwracać `409 GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT` przy ponownym użyciu klucza dla innego odrzucenia.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Odrzucony slot zachowuje powód, znika z kolejki i liczników; zdjęcie pozostaje niekompletne, bez nowych komórek | spełnione | Test PG: `services/api/tests/integration/test_pending_slot_rejection_postgres.py:234`; ocena statyczna |
| Odrzucona plansza znika z weryfikacji i wyszukiwarki; kanoniczny właściciel otrzymuje odmowę | spełnione | Test PG: `services/api/tests/integration/test_pending_slot_rejection_postgres.py:692`; regresja późniejszego rozstrzygnięcia opisana w P0-5 |
| Cofnięcie przywraca `pending`; zamiennik blokuje cofnięcie | niespełnione | Podstawowe scenariusze pokryte w `services/api/tests/integration/test_pending_slot_rejection_postgres.py:359` i `:692`; P0-6 pozwala zwrócić pozorny sukces |
| UI: wybór powodu, potwierdzenie, jedno żądanie, odświeżenie kolejki i listy | spełnione | `apps/reviewer/test-interactions/board-geometry-correction.test.mjs:738`, `:781`, `:816`; ocena statyczna |
| Idempotencja odrzucenia slotu i bezpieczne ponowienia po cofnięciu | spełnione | `services/api/tests/integration/test_pending_slot_rejection_postgres.py:278`, `:425`, `:470` |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1:** wspólny filtr wyklucza odrzucone pozycje; dodano aktualizację liczników i test listy — `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:196`, `:2191`; `services/api/tests/integration/test_pending_slot_rejection_postgres.py:692`.
- **P0-2:** odrzucenie slotu zapisuje klucz i sumę kontrolną polecenia — `services/api/src/game_predictor_api/storage/board_cell_geometry_pending_repository.py:335`.
- **P0-3:** cofnięcie slotu zapisuje trwałe zdarzenie powiązane z konkretnym odrzuceniem — `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:350`; testy ponowień i starego żądania w `services/api/tests/integration/test_pending_slot_rejection_postgres.py:425`.
- **P0-4:** wpis slotu korzysta z czasu trwałego zdarzenia; nieaktualny podgląd otrzymuje odmowę — `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:253`; test HTTP w `services/api/tests/integration/test_pending_slot_rejection_postgres.py:820`.

Otwarte: **P0-5, P0-6**.

## Proponowane testy

Uzupełnić `services/api/tests/integration/test_pending_slot_rejection_postgres.py` o:

- Odrzucenie planszy z komórkami, następnie bezpośrednie `accepted` i `corrected`: zapis powinien się udać, a liczniki odpowiadać liście oraz pełnej przebudowie.
- Odrzucenie A, cofnięcie kluczem K, odrzucenie B, cofnięcie B kluczem K: oczekiwany konflikt idempotencji i brak zmian.
- Ponowienie cofnięcia A kluczem K po odrzuceniu B: odtworzenie wcześniejszego wyniku bez cofania B.

Komenda przy środowisku PG opisanym w zadaniu:

`..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_pending_slot_rejection_postgres.py -q`

## Zakres przeglądu i ograniczenia

Przejrzano brief, poprzedni raport, odpowiednie fragmenty wymagań, decyzji i planu, implementację odrzucania i cofania, migrację oraz manifest, aktualizację widoczności i liczników, integrację Reviewera i powiązane testy. Potwierdzono HEAD i zakres zmian niezacommitowanych.

Nie uruchamiano testów, migracji, usług ani przeglądarki. Wyniki zapisane w `Outcome` pozostają deklaracjami wykonawcy. Przejmowanie sekwencji przez nowy import w TASK-0950 pozostaje poza zakresem.