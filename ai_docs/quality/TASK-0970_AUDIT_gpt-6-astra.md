# Audyt TASK-0970 - Odrzucanie przyciętej planszy i slotu odroczonego w Reviewerze

Werdykt: REVISE
Audytor: gpt-6-astra, medium
Wykonawca: claude-sonnet-5-5, high
Zakres: HEAD...f8fa2ae0ba9ed57e0e8777f7c20c0a205de56040 oraz zmiany niezacommitowane, data 2026-10-09
Runda: 4

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Poprawka zamyka P0-7: cofanie sprawdza wykorzystanie klucza w audycie korekt, zdarzeniach slotów i zdarzeniach rozstrzygnięcia pozycji. Nie znaleziono nowych błędów P0. Pozostaje brak wymaganego testu odrzucenia planszy `pending_partial`; obecne scenariusze używają plansz kompletnych.

## Znaleziska

### P0

Brak.

### P1

- **[P1-1] `services/api/tests/integration/test_pending_slot_rejection_postgres.py:656` — brak wymaganego scenariusza `pending_partial → rejected`.** Ten test sprawdza kompletną planszę na niekompletnym zdjęciu, a test rozpoczynający się w linii 701 również używa plansz kompletnych. Wspólny helper ustawia `completenessStatus = "complete"` w `services/api/tests/integration/test_image_geometry_completeness_gate.py:162`. Nie pokrywa to przypadku wymaganego w `ai_docs/tasks/0970-board-and-slot-rejection-in-reviewer.md:64`. Należy dodać test PG odrzucenia rzeczywistej planszy `pending_partial`, z istniejącymi komórkami, i potwierdzić status `rejected`, wykluczenie komórek z weryfikacji oraz zgodność liczników.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Odrzucony slot zachowuje powód, znika z kolejki i liczników; zdjęcie pozostaje niekompletne, bez nowych komórek | spełnione | `services/api/tests/integration/test_pending_slot_rejection_postgres.py:234` — ocena statyczna |
| Odrzucona plansza znika z weryfikacji i wyszukiwarki; kanoniczny właściciel otrzymuje odmowę | spełnione | `services/api/tests/integration/test_pending_slot_rejection_postgres.py:701` — ocena statyczna |
| Cofnięcie przywraca `pending`; zamiennik blokuje cofnięcie | spełnione | `services/api/tests/integration/test_pending_slot_rejection_postgres.py:359`, `:768`, `:827` |
| UI: wybór powodu, potwierdzenie, jedno żądanie, odświeżenie kolejki i listy | spełnione | `apps/reviewer/test-interactions/board-geometry-correction.test.mjs:738`, `:781`, `:816` |
| Idempotencja cofania między pozycjami i rodzajami operacji | spełnione | `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:743`; `services/api/tests/integration/test_pending_slot_rejection_postgres.py:874` |
| Wymagany test odrzucenia planszy `pending_partial` | niespełnione | P1-1 |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1:** wspólny filtr wyklucza odrzucone pozycje, a odrzucenie aktualizuje liczniki — `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:196`, `:2191`.
- **P0-2:** odrzucenie slotu zapisuje trwały klucz i sumę kontrolną polecenia — `services/api/src/game_predictor_api/storage/board_cell_geometry_pending_repository.py:361`, `:453`.
- **P0-3:** cofnięcie slotu zapisuje zdarzenie przypisane do konkretnego odrzucenia — `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:349`, `:392`.
- **P0-4:** podgląd nieaktualnego odrzucenia zwraca kontrolowaną odmowę — `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:283`.
- **P0-5:** bezpośrednie wyjście ze statusu `rejected` przywraca liczniki przed synchronizacją — `services/api/src/game_predictor_api/storage/image_review_repository.py:1166`.
- **P0-6:** ponowienie cofnięcia porównuje tożsamość konkretnego odrzucenia — `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:439`, `:502`.
- **P0-7:** kontrola klucza obejmuje wszystkie trzy magazyny, a niezgodne użycie kończy się konfliktem przed zapisem — `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:746`, `:760`; `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:355`, `:499`. Regresja: `services/api/tests/integration/test_pending_slot_rejection_postgres.py:874`.

Otwarte: **P1-1**.

## Proponowane testy

Dodać do `services/api/tests/integration/test_pending_slot_rejection_postgres.py` scenariusz planszy `pending_partial` dopuszczonej do materializacji wyjątkiem operatora. Po odrzuceniu sprawdzić `rejected`, brak komórek na liście weryfikacji, pomniejszone liczniki oraz zachowanie wierszy i historii decyzji.

Komenda w środowisku PG opisanym w zadaniu:

`..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_pending_slot_rejection_postgres.py -q`

## Zakres przeglądu i ograniczenia

Przejrzano brief, raport rundy 3, odpowiednie fragmenty planu, wymagań, decyzji i kontraktu API, implementację odrzucania i cofania, zmiany migracji i modeli, widoczność komórek, liczniki, integrację Reviewera oraz powiązane testy.

Nie uruchamiano testów, migracji, usług ani przeglądarki. Wyniki w `Outcome` pozostają deklaracjami wykonawcy; ocena kryteriów dotyczy kodu i pokrycia testowego. TASK-0971 oraz wykonanie migracji na bazie operatora pozostają poza zakresem.