# Audyt TASK-0970 - Odrzucanie przyciętej planszy i slotu odroczonego w Reviewerze

Werdykt: REVISE
Audytor: gpt-6-astra, medium
Wykonawca: claude-sonnet-5-5, high
Zakres: HEAD...f8fa2ae0ba9ed57e0e8777f7c20c0a205de56040 oraz zmiany niezacommitowane, data 2026-10-09
Runda: 3

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Poprawki zamykają P0-5 i P0-6: przywracają liczniki przy bezpośrednim rozstrzygnięciu odrzuconej planszy oraz rozróżniają kolejne odrzucenia tej samej pozycji. Pozostaje niepełna kontrola idempotencji między różnymi pozycjami i rodzajami operacji. Ten sam klucz może wykonać drugie cofnięcie albo spowodować nieobsłużony konflikt ograniczenia UNIQUE.

## Znaleziska

### P0

- **[P0-7] `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:175` — wyszukiwanie wykorzystanego klucza obejmuje tylko zdarzenia `reopened` jednej pozycji.** Po cofnięciu odrzucenia planszy A kluczem K można skutecznie cofnąć odrzucenie planszy B tym samym K. Zapytanie pomija zdarzenie A przez filtr `review_item_id`, a kontrola nadrzędna w `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:746` sprawdza wyłącznie tabelę audytu korekt geometrii. Narusza to kontrakt „ten sam klucz dla innej korekty powoduje konflikt” (`services/api/src/game_predictor_api/application/geometry_correction_reverts.py:312`). Dodatkowo cofnięcie z kluczem użytym do odrzucenia tej samej planszy pomija wcześniejsze zdarzenie przez filtr `action = 'reopened'`; zapis w `geometry_rejection_revert.py:518` narusza UNIQUE pozycji i klucza (`services/api/src/game_predictor_api/storage/models.py:2680`), zamiast zwrócić kontrolowane 409. Należy sprawdzać wykorzystanie klucza we wspólnym zakresie operacji cofania gry oraz wykrywać kolizje z innymi akcjami rozstrzygnięcia. Niezgodne polecenie powinno otrzymać `GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT` przed mutacją.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Odrzucony slot zachowuje powód, znika z kolejki i liczników; zdjęcie pozostaje niekompletne, bez nowych komórek | spełnione | `services/api/tests/integration/test_pending_slot_rejection_postgres.py:234` — ocena statyczna |
| Odrzucona plansza znika z weryfikacji i wyszukiwarki; kanoniczny właściciel otrzymuje odmowę | spełnione | `services/api/tests/integration/test_pending_slot_rejection_postgres.py:701` — ocena statyczna |
| Cofnięcie przywraca `pending`; przejęcie przez zamiennik blokuje cofnięcie | spełnione | `services/api/tests/integration/test_pending_slot_rejection_postgres.py:359`, `:768`, `:827` — podstawowe scenariusze |
| UI: wybór powodu, potwierdzenie, jedno żądanie, odświeżenie kolejki i listy | spełnione | `apps/reviewer/test-interactions/board-geometry-correction.test.mjs:738`, `:781`, `:816` |
| Idempotencja cofania: klucz przypisany do jednego polecenia | niespełnione | P0-7; testy obejmują kolejne odrzucenia jednej pozycji, pomijają kolizje między pozycjami i akcjami |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1:** odrzucone pozycje wyklucza wspólny filtr, a liczniki uwzględniają odrzucenie — `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:196`, `:2191`.
- **P0-2:** odrzucenie slotu zapisuje trwały klucz i sumę kontrolną polecenia — `services/api/src/game_predictor_api/storage/board_cell_geometry_pending_repository.py:361`, `:453`.
- **P0-3:** cofnięcie slotu zapisuje zdarzenie powiązane z konkretnym odrzuceniem — `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:306`, `:347`.
- **P0-4:** nieaktualne odrzucenie otrzymuje kontrolowaną odmowę podglądu — `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:244`.
- **P0-5:** wyjście ze statusu `rejected` przywraca liczniki przed synchronizacją — `services/api/src/game_predictor_api/storage/image_review_repository.py:1166`; regresja: `services/api/tests/integration/test_pending_slot_rejection_postgres.py:840`.
- **P0-6:** ponowienie klucza dla innego odrzucenia tej samej pozycji porównuje sumę kontrolną — `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:471`; regresja: `services/api/tests/integration/test_pending_slot_rejection_postgres.py:820`.

Otwarte: **P0-7**.

## Proponowane testy

Uzupełnić `services/api/tests/integration/test_pending_slot_rejection_postgres.py` o:

- Cofnięcie odrzucenia planszy A kluczem K, następnie próba cofnięcia planszy B kluczem K: 409, B pozostaje odrzucona.
- Ponowne użycie klucza między cofnięciem odrzucenia slotu, planszy i korekty geometrii: konflikt bez zmian danych.
- Cofnięcie odrzucenia planszy z kluczem jej odrzucenia: kontrolowane 409 przez HTTP, bez błędu 500.
- Ponowienie pierwotnego cofnięcia po odmowie: ten sam `revertId`, `created=false`.

Komenda w środowisku PG opisanym w zadaniu:

`..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_pending_slot_rejection_postgres.py -q`

## Zakres przeglądu i ograniczenia

Przejrzano brief, raport rundy 2, odpowiednie fragmenty planu, wymagań, decyzji i kontraktu, implementację odrzucania i cofania, zmiany migracji i modeli, widoczność komórek i liczniki, integrację Reviewera oraz powiązane testy.

Nie uruchamiano testów, migracji, usług ani przeglądarki. Wyniki w `Outcome` są deklaracjami wykonawcy; ocena kryteriów dotyczy kodu i istniejącego pokrycia testowego. TASK-0971 oraz wykonanie migracji na bazie operatora pozostają poza zakresem.