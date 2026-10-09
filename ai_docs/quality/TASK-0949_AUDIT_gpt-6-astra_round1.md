# Audyt TASK-0949 - Odrzucanie przyciętej planszy i slotu odroczonego w Reviewerze

Werdykt: REVISE
Audytor: gpt-6-astra, medium
Wykonawca: claude-sonnet-5-5, high
Zakres: HEAD...f8fa2ae0ba9ed57e0e8777f7c20c0a205de56040 oraz zmiany niezacommitowane, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono odrzucanie slotów i plansz, cofanie odrzucenia, integrację Reviewera oraz testy. Implementacja obejmuje wymagany pion API i UI, ale pozostawia odrzucone, wcześniej pocięte plansze w weryfikacji symboli. Brak trwałej identyfikacji operacji slotu pozwala ponowieniom zmieniać późniejszy stan i uniemożliwia bezpieczne odtworzenie wyniku po utracie odpowiedzi.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:2410` — Odrzucenie planszy zachowuje komórki i jedynie podbija rewizję katalogu. Komentarz zakłada wykluczenie przez projekcję wyszukiwarki, ale `_visible_cell_scope` (`:959`) czyta komórki bez powiązania z tą projekcją i bez filtra statusu pozycji. Wcześniej pocięta, odrzucona plansza nadal występuje w weryfikacji symboli. Test w `services/api/tests/integration/test_pending_slot_rejection_postgres.py:635` sprawdza zachowanie fizycznych wierszy, lecz nie sprawdza ich widoczności po odrzuceniu. Należy wykluczyć odrzucone pozycje ze wspólnego zakresu odczytów, liczników i operacji zbiorczych, zachowując historię decyzji.

- [P0-2] `services/api/src/game_predictor_api/storage/board_cell_geometry_pending_repository.py:387` — Idempotencja odrzucenia porównuje wyłącznie powód i opis; klucz służy tylko do blokady transakcyjnej. Inny klucz z identycznym powodem zwraca sukces zamiast wymaganego 409. Ponadto po cofnięciu odrzucenia opóźnione ponowienie pierwotnego żądania ponownie odrzuci slot, ponieważ nie zmieniono oczekiwanej rewizji. Należy trwale zapisywać klucz, tożsamość polecenia i wynik oraz odtwarzać wcześniejszy wynik bez ponownego wykonania mutacji.

- [P0-3] `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:243` — Ścieżka cofania slotu pomija `idempotency_key`, kasuje dane odrzucenia (`:294`) i zwraca niezapisany `revert_id` (`:311`). Po utracie odpowiedzi ponowienie zakończy się `GEOMETRY_REVERT_NOT_LATEST` zamiast odtworzeniem sukcesu. Jeśli slot zostanie ponownie odrzucony, stare żądanie cofnięcia może cofnąć nowe odrzucenie: identyfikator slotu i oba tokeny CAS pozostają takie same. Należy nadać odrzuceniom trwałą tożsamość lub rewizję oraz zapisywać historię i wynik cofnięcia związany z kluczem.

- [P0-4] `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:439` — `_slot` zwraca wpis także dla slotu, którego odrzucenie już cofnięto. Wtedy `rejected_at` jest `None`, a podgląd przekazuje tę wartość jako wymagane `created_at: datetime` do `GeometryCorrectionResponse` (`services/api/src/game_predictor_api/schemas/geometry_correction_reverts.py:35`). Otwarcie podglądu z nieaktualnej listy, np. po cofnięciu w drugiej karcie, kończy się błędem walidacji i HTTP 500. Należy zwrócić kontrolowaną odmowę albo zbudować podgląd z trwałego zdarzenia odrzucenia.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Odrzucony slot ma powód, znika z kolejki i liczników; zdjęcie pozostaje niekompletne, bez nowych komórek | spełnione | Implementacja i test PG: `services/api/tests/integration/test_pending_slot_rejection_postgres.py:232`; ocena statyczna |
| Odrzucona plansza poza weryfikacją symboli i wyszukiwarką; kanoniczny właściciel otrzymuje 409 | niespełnione | P0-1; odmowa kanonicznego właściciela jest zaimplementowana w `services/api/src/game_predictor_api/storage/image_review_repository.py:1177` |
| Cofnięcie przywraca `pending`; przejęcie przez zamiennik blokuje cofnięcie | niespełnione | Podstawowe ścieżki pokrywają testy w `services/api/tests/integration/test_pending_slot_rejection_postgres.py:344` i `:594`; bezpieczeństwo ponowień naruszają P0-3 i P0-4 |
| UI: wybór powodu, potwierdzenie, jedno żądanie, odświeżenie kolejki i listy | spełnione | `apps/reviewer/test-interactions/board-geometry-correction.test.mjs:738` i `:781`; ocena statyczna |
| Ten sam klucz odrzucenia odtwarza wynik; inny klucz daje 409 | niespełnione | P0-2; test w `services/api/tests/integration/test_pending_slot_rejection_postgres.py:275` sprawdza zmianę powodu zamiast wymaganego przypadku innego klucza z tym samym powodem |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P0-1, P0-2, P0-3, P0-4.

## Proponowane testy

Uzupełnić `services/api/tests/integration/test_pending_slot_rejection_postgres.py` o:

- Odrzucenie planszy z istniejącymi komórkami: brak jej komórek na liście, w licznikach i zakresie operacji zbiorczych; historia pozostaje.
- Odrzucenie innym kluczem przy identycznym powodzie: 409 bez zmiany danych.
- Odrzucenie, cofnięcie i opóźnione ponowienie pierwotnego odrzucenia: slot pozostaje `pending`.
- Cofnięcie z utraconą odpowiedzią i ponowienie w nowej sesji: ten sam zapisany wynik i `revert_id`.
- Ponowne odrzucenie slotu i wysłanie starego żądania cofnięcia: nowe odrzucenie pozostaje.
- HTTP `revert-preview` po cofnięciu odrzucenia w innej sesji: kontrolowana odpowiedź, bez 500.

Komenda po poprawkach, przy ustawionym środowisku PG opisanym w zadaniu:

`..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_pending_slot_rejection_postgres.py -q`

## Zakres przeglądu i ograniczenia

Przeczytano brief, zadanie, odpowiednie fragmenty planu i dokumentacji, implementację odrzucania i cofania, przepływ projekcji symboli oraz związane testy API i UI. Sprawdzono rzeczywisty HEAD i stan zmian niezacommitowanych. Wyniki testów z `Outcome` są deklaracjami wykonawcy; nie uruchamiano testów, usług, migracji ani przeglądarki. Przejęcie sekwencji przez nowy import w TASK-0950 pozostaje poza zakresem.